import re

from pydantic import BaseModel

from db_utils import get_chroma_collection
from embedder import embed_texts
from llm import generate_reasoning, normalize_experience_years
from skills_vocab import KNOWN_SKILLS


class MatchEntry(BaseModel):
    candidate_name: str
    resume_path: str
    match_score: float
    matched_skills: list[str]
    experience_years: int | None = None  # None means experience data was unavailable
    relevant_excerpts: list[str]
    reasoning: str
    matched_sections: list[str] = []


class MatchOutput(BaseModel):
    job_description: str
    top_matches: list[MatchEntry]

STOPWORDS = {
    "and",
    "or",
    "the",
    "with",
    "for",
    "a",
    "an",
    "in",
    "of",
    "to",
    "is",
    "are",
    "be",
    "that",
    "at",
    "on",
}


def _find_required_skills(job_description: str) -> list[str]:
    matched: list[str] = []
    for skill in sorted(KNOWN_SKILLS, key=len, reverse=True):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(skill)}(?![A-Za-z0-9])"
        if re.search(pattern, job_description, flags=re.IGNORECASE):
            matched.append(skill)
    return matched


def _extract_min_experience_years(job_description: str) -> int | None:
    patterns = [
        r"(\d+)\+?\s*years?",
        r"at least (\d+)\s*years?",
        r"minimum (\d+)\s*years?",
    ]

    values: list[int] = []
    for pattern in patterns:
        for match in re.finditer(pattern, job_description, flags=re.IGNORECASE):
            values.append(int(match.group(1)))

    return max(values) if values else None


def _extract_jd_keywords(job_description: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9+.#-]*", job_description.lower())
    return [token for token in tokens if token not in STOPWORDS]


def extract_job_requirements(job_description: str) -> dict:
    """Extract required skills, minimum experience, and useful keywords from a JD."""
    normalized_jd = job_description.strip()

    return {
        "required_skills": _find_required_skills(normalized_jd),
        "min_experience_years": _extract_min_experience_years(normalized_jd),
        "jd_keywords": _extract_jd_keywords(normalized_jd),
    }


def _semantic_search(jd_text: str, n_results: int = 50) -> list[dict]:
    """Query ChromaDB for resume chunks semantically similar to the job description."""
    collection = get_chroma_collection()
    if collection.count() == 0:
        raise ValueError(
            "Vector store is empty. Run `python resume_rag.py --resume-dir resumes` first."
        )

    total_chunks = collection.count()
    effective_n = min(n_results, total_chunks)

    jd_vector = embed_texts([jd_text])[0]
    results = collection.query(
        query_embeddings=[jd_vector],
        n_results=effective_n,
        include=["documents", "distances", "metadatas"],
    )

    chunks: list[dict] = []
    result_ids = results.get("ids", [[]])[0]
    result_documents = results.get("documents", [[]])[0]
    result_distances = results.get("distances", [[]])[0]
    result_metadatas = results.get("metadatas", [[]])[0]

    for index in range(len(result_ids)):
        chunks.append(
            {
                "id": result_ids[index],
                "distance": result_distances[index],
                "document": result_documents[index],
                "metadata": result_metadatas[index],
            }
        )

    return chunks


def _term_in_text(term: str, text: str) -> bool:
    """Return True if term appears in text as a whole token (word-boundary safe)."""
    pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _hybrid_score(chunk: dict, jd_keywords: list[str], required_skills: list[str]) -> float:
    """Compute chunk-level semantic + keyword hybrid score."""
    semantic_sim = max(0.0, 1 - chunk["distance"])
    chunk_text = chunk["document"]

    if required_skills:
        hits = sum(1 for skill in required_skills if _term_in_text(skill, chunk_text))
        keyword_hit_ratio = hits / len(required_skills)
    else:
        hits = sum(1 for keyword in jd_keywords if _term_in_text(keyword, chunk_text))
        keyword_hit_ratio = hits / max(len(jd_keywords), 1)

    return 0.7 * semantic_sim + 0.3 * keyword_hit_ratio


def _parse_candidate_skills(metadata: dict) -> list[str]:
    skills_value = metadata.get("skills", "")
    if not skills_value:
        return []
    return [skill.strip() for skill in str(skills_value).split(",") if skill.strip()]


def _must_have_filter(chunk: dict, requirements: dict) -> tuple[bool, float, str]:
    """Apply hard constraints using candidate metadata attached to the chunk."""
    metadata = chunk["metadata"]
    candidate_skills = _parse_candidate_skills(metadata)
    required_skills = requirements.get("required_skills", [])
    min_experience_years = requirements.get("min_experience_years")
    experience_years = int(metadata.get("experience_years", -1))
    # -1 means the extractor found no parseable date/year — treat as truly unavailable
    skills_unavailable = not metadata.get("skills")
    experience_unavailable = experience_years < 0

    if skills_unavailable or experience_unavailable:
        unavailable_reasons = []
        if skills_unavailable:
            unavailable_reasons.append("skills data unavailable")
        if experience_unavailable:
            unavailable_reasons.append("experience data unavailable")
        return True, 0.5, "metadata unavailable: " + ", ".join(unavailable_reasons)

    normalized_candidate_skills = {skill.lower() for skill in candidate_skills}
    chunk_text = chunk.get("document", "")
    for required_skill in required_skills:
        if required_skill.lower() in normalized_candidate_skills:
            continue
        if _term_in_text(required_skill, chunk_text):
            continue
        return False, 0.3, f"missing required skill: {required_skill}"

    if min_experience_years and experience_years < min_experience_years:
        return False, 0.5, "below required experience"

    return True, 1.0, "passed"


def _search_resume_chunks(
    job_description: str,
    requirements: dict,
    n_results: int = 50,
) -> list[dict]:
    """Run semantic search, hybrid scoring, and must-have filtering at chunk level."""
    chunks = _semantic_search(job_description, n_results=n_results)
    required_skills = requirements.get("required_skills", [])
    jd_keywords = requirements.get("jd_keywords", [])

    filtered_chunks: list[dict] = []
    for chunk in chunks:
        passed_filter, filter_penalty, filter_reason = _must_have_filter(chunk, requirements)
        if not passed_filter:
            continue

        hybrid_score = _hybrid_score(chunk, jd_keywords, required_skills) * filter_penalty
        enriched_chunk = {
            **chunk,
            "hybrid_score": hybrid_score,
            "passed_filter": passed_filter,
            "filter_penalty": filter_penalty,
            "filter_reason": filter_reason,
        }
        filtered_chunks.append(enriched_chunk)

    return sorted(filtered_chunks, key=lambda item: item["hybrid_score"], reverse=True)


def _match_skills(candidate_skills: list[str], required_skills: list[str]) -> list[str]:
    """Return required skills present in the candidate skill list."""
    normalized_candidate_skills = {skill.lower() for skill in candidate_skills}
    return [
        skill
        for skill in required_skills
        if skill.lower() in normalized_candidate_skills
    ]


def _aggregate_by_candidate(chunks: list[dict], requirements: dict) -> list[dict]:
    """Collapse chunk-level search results into one dict per candidate."""
    grouped_chunks: dict[str, list[dict]] = {}
    for chunk in chunks:
        resume_path = chunk["metadata"]["resume_path"]
        grouped_chunks.setdefault(resume_path, []).append(chunk)

    candidates: list[dict] = []
    required_skills = requirements.get("required_skills", [])

    for resume_path, candidate_chunks in grouped_chunks.items():
        metadata = candidate_chunks[0]["metadata"]
        candidate_skills = _parse_candidate_skills(metadata)
        semantic_scores = [max(0.0, 1 - chunk["distance"]) for chunk in candidate_chunks]

        ranked_chunks = sorted(
            candidate_chunks,
            key=lambda chunk: max(0.0, 1 - chunk["distance"]),
            reverse=True,
        )
        relevant_excerpts = [chunk["document"] for chunk in ranked_chunks[:3]]
        matched_sections = sorted(
            {
                chunk["metadata"]["section_label"]
                for chunk in candidate_chunks
                if chunk["metadata"].get("section_label")
            }
        )
        filter_reasons = sorted(
            {
                chunk["filter_reason"]
                for chunk in candidate_chunks
                if chunk.get("filter_reason") and chunk["filter_reason"] != "passed"
            }
        )

        candidates.append(
            {
                "candidate_name": metadata.get("candidate_name", "Unknown"),
                "resume_path": resume_path,
                "experience_years": int(metadata.get("experience_years", -1)),
                "education": metadata.get("education", ""),
                "semantic_score": sum(semantic_scores) / len(semantic_scores),
                "candidate_skills": candidate_skills,
                "matched_skills": _match_skills(candidate_skills, required_skills),
                "relevant_excerpts": relevant_excerpts,
                "matched_sections": matched_sections,
                "filter_reasons": filter_reasons,
            }
        )

    return candidates


def score_candidate(candidate: dict, requirements: dict) -> float:
    """Combine semantic, skill, and experience signals into a 0-100 score."""
    semantic_score = candidate["semantic_score"]

    required = requirements["required_skills"]
    matched = candidate["matched_skills"]
    if required:
        skill_overlap_score = len(matched) / len(required)
    else:
        # No required skills in JD: score by breadth — how many KNOWN_SKILLS
        # the candidate has, normalised so ~¼ of the vocab = full score.
        candidate_skills = candidate.get("candidate_skills", [])
        breadth_target = max(len(KNOWN_SKILLS) // 4, 1)
        skill_overlap_score = min(len(candidate_skills) / breadth_target, 1.0)

    req_years = requirements.get("min_experience_years") or 0
    cand_years = candidate.get("experience_years", -1)
    if req_years > 0:
        # cand_years < 0 → unavailable → neutral 0.5; otherwise proportional
        experience_score = 0.5 if cand_years < 0 else min(cand_years / req_years, 1.0)
    else:
        experience_score = 0.5

    final_score = (
        semantic_score * 0.50
        + skill_overlap_score * 0.30
        + experience_score * 0.20
    ) * 100

    return round(final_score, 1)


def _generate_reasoning(candidate: dict, requirements: dict, score: float) -> str:
    """Generate human-readable match reasoning via Groq with template fallback."""
    prompt_context = {
        "candidate_name": candidate.get("candidate_name", "Candidate"),
        "matched_skills": candidate.get("matched_skills", []),
        "matched_sections": candidate.get("matched_sections", []),
        "experience_years": normalize_experience_years(candidate.get("experience_years")),
        "min_experience_years": requirements.get("min_experience_years"),
        "match_score": score,
        "relevant_excerpts": candidate.get("relevant_excerpts", []),
        "filter_reasons": candidate.get("filter_reasons", []),
    }
    return generate_reasoning(prompt_context)


def _validate_top_k(top_k: int) -> int:
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    return top_k


def _search_n_results(top_k: int) -> int:
    """Scale semantic search breadth with corpus size so all resumes can surface."""
    collection = get_chroma_collection()
    total_chunks = collection.count()
    if total_chunks == 0:
        return max(top_k * 5, 50)
    return min(total_chunks, max(top_k * 10, 100))


def search_resumes(job_description: str, top_k: int = 10) -> list[dict]:
    """Run hybrid search and return ranked candidate-level matches."""
    top_k = _validate_top_k(top_k)
    requirements = extract_job_requirements(job_description)
    chunks = _search_resume_chunks(
        job_description,
        requirements,
        n_results=_search_n_results(top_k),
    )
    candidates = _aggregate_by_candidate(chunks, requirements)

    for candidate in candidates:
        candidate["match_score"] = score_candidate(candidate, requirements)
        candidate["reasoning"] = _generate_reasoning(
            candidate,
            requirements,
            candidate["match_score"],
        )

    return sorted(candidates, key=lambda item: item["match_score"], reverse=True)[:top_k]


def match_jobs(job_description: str, top_k: int = 10) -> dict:
    """Return the final JSON-compatible match output, validated via MatchOutput."""
    if not job_description.strip():
        raise ValueError("Job description is required.")

    top_k = _validate_top_k(top_k)
    top = search_resumes(job_description, top_k=top_k)

    entries = [
        MatchEntry(
            candidate_name=candidate["candidate_name"],
            resume_path=candidate["resume_path"],
            match_score=candidate["match_score"],
            matched_skills=candidate["matched_skills"],
            experience_years=normalize_experience_years(candidate.get("experience_years")),
            relevant_excerpts=candidate["relevant_excerpts"],
            reasoning=candidate["reasoning"],
            matched_sections=candidate.get("matched_sections", []),
        )
        for candidate in top
    ]

    output = MatchOutput(job_description=job_description, top_matches=entries)
    return output.model_dump()


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Match resumes against a job description.")
    parser.add_argument("--job-description-file", required=True)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    with open(args.job_description_file, encoding="utf-8") as handle:
        jd_text = handle.read()

    try:
        result = match_jobs(jd_text, top_k=args.top_k)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    print(json.dumps(result, indent=2))
