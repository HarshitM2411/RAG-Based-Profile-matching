import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_client: Groq | None = None


def get_groq_client() -> Groq:
    """Return a cached Groq client for chat completions."""
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is required for LLM reasoning.")

    _client = Groq(api_key=api_key)
    return _client


def normalize_experience_years(years: int | None) -> int | None:
    """Map internal sentinel (-1) to None for prompts and JSON consumers."""
    if years is None or years < 0:
        return None
    return years


def _experience_label(years: int | None) -> str:
    normalized = normalize_experience_years(years)
    if normalized is None:
        return "unavailable"
    return f"{normalized} years"


def _build_reasoning_prompt(prompt_context: dict) -> str:
    matched_skills = prompt_context.get("matched_skills", [])
    matched_sections = prompt_context.get("matched_sections", [])
    experience_years = prompt_context.get("experience_years")
    min_experience_years = prompt_context.get("min_experience_years")
    match_score = prompt_context.get("match_score", 0)
    relevant_excerpts = prompt_context.get("relevant_excerpts", [])
    filter_reasons = prompt_context.get("filter_reasons", [])
    candidate_name = prompt_context.get("candidate_name", "Candidate")

    skills_text = ", ".join(matched_skills) if matched_skills else "none"
    sections_text = ", ".join(matched_sections) if matched_sections else "none"
    requirement_text = (
        f"{min_experience_years}+ years"
        if min_experience_years
        else "not specified"
    )
    excerpts_text = "\n".join(f"- {excerpt}" for excerpt in relevant_excerpts[:3])
    constraints_text = "; ".join(filter_reasons) if filter_reasons else "none"

    return (
        f"Candidate: {candidate_name}\n"
        f"Match score: {match_score}\n"
        f"Matched skills: {skills_text}\n"
        f"Relevant sections: {sections_text}\n"
        f"Candidate experience: {_experience_label(experience_years)}\n"
        f"Required experience: {requirement_text}\n"
        f"Filter notes: {constraints_text}\n"
        f"Relevant excerpts:\n{excerpts_text or '- none'}\n\n"
        "Write 2-3 concise sentences explaining why this candidate matches or partially matches the job. "
        "Mention matched skills, experience fit, and the strongest resume evidence."
    )


def _template_reasoning(prompt_context: dict) -> str:
    matched_skills = prompt_context.get("matched_skills", [])
    matched_sections = prompt_context.get("matched_sections", [])
    experience_years = normalize_experience_years(prompt_context.get("experience_years"))
    min_experience_years = prompt_context.get("min_experience_years")
    match_score = prompt_context.get("match_score", 0)
    filter_reasons = prompt_context.get("filter_reasons", [])

    if matched_skills:
        skill_line = f"Matched skills: {', '.join(matched_skills)}."
    else:
        skill_line = "No required skills matched."

    if matched_sections:
        section_line = f"Relevant content found in: {', '.join(matched_sections)}."
    else:
        section_line = "Limited section coverage found."

    if experience_years is None:
        experience_line = "Experience data unavailable."
    elif min_experience_years:
        experience_line = (
            f"Candidate has {experience_years} years "
            f"(requirement: {min_experience_years}+)."
        )
    else:
        experience_line = f"Candidate has {experience_years} years of experience."

    if match_score >= 75:
        judgment = "Strong match."
    elif match_score >= 50:
        judgment = "Partial match."
    else:
        judgment = "Weak match."

    parts = [skill_line, section_line, experience_line, judgment]
    if filter_reasons:
        parts.insert(3, " ".join(filter_reasons))
    return " ".join(parts)


def generate_reasoning(prompt_context: dict) -> str:
    """Generate match reasoning text via the Groq LLM."""
    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You explain resume-to-job matches clearly and honestly. "
                        "Use only the provided context."
                    ),
                },
                {
                    "role": "user",
                    "content": _build_reasoning_prompt(prompt_context),
                },
            ],
            temperature=0.2,
            max_tokens=180,
        )
        content = response.choices[0].message.content
        if content and content.strip():
            return content.strip()
    except Exception:
        pass

    return _template_reasoning(prompt_context)
