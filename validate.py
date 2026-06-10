"""
Phase 10 — Validation and Acceptance

Runs the acceptance checklist from docs/implementation.md against the
Resume RAG system. Use --run-ingestion to build the vector store first.

Usage:
    python validate.py
    python validate.py --run-ingestion
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from dataclasses import dataclass, field
from typing import Callable
from unittest.mock import MagicMock, patch

from db_utils import get_chroma_collection
from embedder import embed_texts, get_embedding_model  # get_embedding_model used in type checks
from job_matcher import (
    _hybrid_score,
    _search_resume_chunks,
    _semantic_search,
    extract_job_requirements,
    match_jobs,
    score_candidate,
    search_resumes,
)
from resume_rag import (
    build_vector_store,
    chunk_resume,
    extract_metadata,
    list_files,
    load_resume_text,
)
from skills_vocab import KNOWN_SKILLS as VOCAB_SKILLS

RESUME_DIR = "resumes"
VECTOR_DIR = "vector_store"
SAMPLE_JD = (
    "Looking for a Python Machine Learning Engineer with 5+ years of "
    "experience, SQL, and AWS."
)
CANONICAL_JD_PATH = "docs/sample_jd.txt"
REQUIRED_MATCH_FIELDS = {
    "candidate_name",
    "resume_path",
    "match_score",
    "matched_skills",
    "experience_years",
    "relevant_excerpts",
    "reasoning",
    "matched_sections",
}
KNOWN_SECTIONS = {
    "summary",
    "skills",
    "experience",
    "education",
    "projects",
    "certifications",
    "achievements",
    "other",
}
METADATA_KEYS = {
    "candidate_name",
    "skills",
    "experience_years",
    "education",
    "resume_path",
}


@dataclass
class CheckResult:
    criterion: str
    passed: bool
    detail: str
    skipped: bool = False


@dataclass
class ValidationReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, criterion: str, passed: bool, detail: str, skipped: bool = False) -> None:
        self.results.append(CheckResult(criterion, passed, detail, skipped))

    def print_summary(self) -> None:
        print("\n" + "=" * 72)
        print("PHASE 10 — ACCEPTANCE VALIDATION REPORT")
        print("=" * 72)
        for result in self.results:
            if result.skipped:
                status = "SKIP"
            else:
                status = "PASS" if result.passed else "FAIL"
            print(f"[{status}] {result.criterion}")
            print(f"       {result.detail}")
        passed = sum(1 for result in self.results if result.passed and not result.skipped)
        skipped = sum(1 for result in self.results if result.skipped)
        failed = sum(1 for result in self.results if not result.passed and not result.skipped)
        total = len(self.results)
        print("-" * 72)
        print(f"Result: {passed} passed, {failed} failed, {skipped} skipped (of {total})")
        print("=" * 72)


def _safe_run(
    report: ValidationReport,
    criterion: str,
    fn: Callable[[], None],
) -> None:
    try:
        fn()
        report.add(criterion, True, "OK")
    except AssertionError as error:
        report.add(criterion, False, str(error) or "Assertion failed")
    except Exception as error:
        report.add(criterion, False, f"{type(error).__name__}: {error}")


def check_resume_files_loaded(report: ValidationReport) -> None:
    def _check() -> None:
        paths = list_files(RESUME_DIR, [".pdf", ".docx", ".txt"])
        assert len(paths) >= 3, f"Expected >= 3 resume files, found {len(paths)}"

    _safe_run(report, "1. Resumes loaded from file system", _check)


def check_section_aware_chunking(report: ValidationReport) -> None:
    def _check() -> None:
        paths = list_files(RESUME_DIR, [".txt"])
        assert paths, "No .txt resumes available for chunking check"
        text = load_resume_text(paths[0])
        metadata = extract_metadata(text, paths[0])
        chunks = chunk_resume(text, metadata)
        assert chunks, "Chunker returned no chunks"
        labels = {chunk["section_label"] for chunk in chunks}
        assert labels.issubset(KNOWN_SECTIONS), f"Unknown section labels: {labels - KNOWN_SECTIONS}"
        assert labels - {"other"}, "All chunks fell into section_label='other'"

    _safe_run(report, "2. Section-aware chunking", _check)


def check_embeddings_in_store(report: ValidationReport) -> None:
    def _check() -> None:
        collection = get_chroma_collection()
        assert collection.count() > 0, "Vector store is empty — run with --run-ingestion"
        sample = collection.get(limit=5, include=["embeddings"])
        raw_embeddings = sample.get("embeddings")
        assert raw_embeddings is not None and len(raw_embeddings) > 0, (
            "No embeddings returned from collection"
        )
        embeddings = list(raw_embeddings)
        assert all(embedding is not None for embedding in embeddings), "Found None embeddings"
        assert all(len(embedding) > 0 for embedding in embeddings), "Found empty embeddings"

    _safe_run(report, "3. Each chunk has an embedding", _check)


def check_chromadb_storage(report: ValidationReport) -> None:
    def _check() -> None:
        collection = get_chroma_collection()
        count = collection.count()
        assert count > 0, "Vector store is empty"
        sample = collection.get(limit=1, include=["metadatas", "documents"])
        assert sample["metadatas"], "No metadata stored"
        assert sample["documents"], "No documents stored"
        meta = sample["metadatas"][0]
        for key in ("candidate_name", "resume_path", "section_label", "skills"):
            assert key in meta, f"Missing metadata key: {key}"

    _safe_run(report, "4. Chunks and metadata in ChromaDB", _check)


def check_metadata_fields(report: ValidationReport) -> None:
    def _check() -> None:
        collection = get_chroma_collection()
        if collection.count() == 0:
            paths = list_files(RESUME_DIR, [".txt"])
            text = load_resume_text(paths[0])
            meta = extract_metadata(text, paths[0])
            assert METADATA_KEYS.issubset(meta.keys())
            assert meta["candidate_name"]
            assert meta["skills"]
            assert meta["resume_path"]
            return

        results = collection.get(include=["metadatas"])
        found_complete = False
        for meta in results["metadatas"]:
            if not meta:
                continue
            if METADATA_KEYS.issubset(meta.keys()) and meta.get("candidate_name"):
                exp = int(meta.get("experience_years", -1))
                if meta.get("skills") or meta.get("education") or exp >= 0:
                    found_complete = True
                    break
        assert found_complete, "No record with complete metadata found"

    _safe_run(report, "5. Metadata includes name, skills, experience, education, path", _check)


def check_shared_embedding_model(report: ValidationReport) -> None:
    def _check() -> None:
        import embedder
        import job_matcher
        import resume_rag

        assert resume_rag.embed_texts is embed_texts, "resume_rag must use shared embed_texts"
        assert job_matcher.embed_texts is embed_texts, "job_matcher must use shared embed_texts"
        assert embedder.MODEL, "EMBEDDING_MODEL not configured"

    _safe_run(report, "6. JD embedded with same HuggingFace model", _check)


def check_top_k_default_and_reasoning(report: ValidationReport) -> None:
    def _check() -> None:
        collection = get_chroma_collection()
        assert collection.count() > 0, "Vector store is empty — run with --run-ingestion"

        with open(CANONICAL_JD_PATH, encoding="utf-8") as handle:
            jd_text = handle.read()

        result = match_jobs(jd_text)
        assert len(result["top_matches"]) <= 10, "Default top_k should cap at 10"
        schema_keys = {"job_description", "top_matches"}
        assert schema_keys.issubset(result.keys())
        if result["top_matches"]:
            for match in result["top_matches"]:
                assert match["reasoning"].strip(), "Reasoning must be non-empty"

    _safe_run(report, "7. Top-K defaults to 10; reasoning is non-empty", _check)


def check_hybrid_search_active(report: ValidationReport) -> None:
    def _check() -> None:
        source = inspect.getsource(_search_resume_chunks)
        assert "_semantic_search" in source
        assert "_hybrid_score" in source
        assert "_must_have_filter" in source

        chunk = {
            "distance": 0.2,
            "document": "Built Python ML pipelines with SQL and AWS.",
        }
        score = _hybrid_score(chunk, ["python", "ml"], ["Python", "SQL"])
        assert 0 <= score <= 1

    _safe_run(report, "8. Hybrid search (semantic + keyword) active", _check)


def check_scores_in_range(report: ValidationReport) -> None:
    def _check() -> None:
        collection = get_chroma_collection()
        assert collection.count() > 0, "Vector store is empty — run with --run-ingestion"
        result = match_jobs(SAMPLE_JD, top_k=10)
        for match in result["top_matches"]:
            assert 0 <= match["match_score"] <= 100, f"Score out of range: {match['match_score']}"

        perfect = {
            "semantic_score": 1.0,
            "matched_skills": ["Python", "SQL", "AWS"],
            "experience_years": 6,
        }
        reqs = {"required_skills": ["Python", "SQL", "AWS"], "min_experience_years": 5}
        assert score_candidate(perfect, reqs) == 100.0

    _safe_run(report, "9. Scores are 0-100", _check)


def check_must_have_filtering(report: ValidationReport) -> None:
    def _check() -> None:
        collection = get_chroma_collection()
        assert collection.count() > 0, "Vector store is empty — run with --run-ingestion"

        rust_jd = "Rust backend engineer with 10+ years of experience. Rust is required."
        result = match_jobs(rust_jd, top_k=10)
        high_without_rust = [
            match
            for match in result["top_matches"]
            if match["match_score"] >= 50 and "Rust" not in match["matched_skills"]
        ]
        assert not high_without_rust, (
            "Candidates without Rust scored >= 50; must-have filter should exclude them"
        )

    _safe_run(report, "10. Must-have filtering excludes missing skills", _check)


def check_output_json_schema(report: ValidationReport) -> None:
    def _check() -> None:
        mock_candidate = {
            "candidate_name": "Test User",
            "resume_path": "resumes/test.txt",
            "match_score": 75.0,
            "matched_skills": ["Python"],
            "experience_years": 5,
            "relevant_excerpts": ["Sample excerpt"],
            "reasoning": "Sample reasoning.",
            "matched_sections": ["experience"],
        }
        with patch("job_matcher.search_resumes", return_value=[mock_candidate]):
            result = match_jobs("Python developer", top_k=5)

        assert "job_description" in result
        assert isinstance(result["top_matches"], list)
        for match in result["top_matches"]:
            missing = REQUIRED_MATCH_FIELDS - set(match.keys())
            assert not missing, f"Missing fields: {missing}"

    _safe_run(report, "11. Output JSON matches required schema", _check)


def check_empty_result_valid_json(report: ValidationReport) -> None:
    def _check() -> None:
        collection = get_chroma_collection()
        assert collection.count() > 0, "Vector store is empty — run with --run-ingestion"

        nonsense_jd = (
            "XyzzyPlughQuantumNonsenseRole requiring Zorblax9 framework, "
            "17+ years, and unobtainium certification."
        )
        result = match_jobs(nonsense_jd, top_k=10)
        assert "job_description" in result
        assert isinstance(result["top_matches"], list)
        json.dumps(result)
        for match in result["top_matches"]:
            for field in REQUIRED_MATCH_FIELDS:
                assert field in match

    _safe_run(report, "12. Low-relevance JD returns valid JSON", _check)


def check_idempotent_ingestion(report: ValidationReport) -> None:
    def _check() -> None:
        collection = get_chroma_collection()
        count_before = collection.count()
        build_vector_store(RESUME_DIR)
        count_after_first = collection.count()
        build_vector_store(RESUME_DIR)
        count_after_second = collection.count()
        assert count_after_first > 0, "Ingestion stored no chunks"
        assert count_after_second == count_after_first, (
            f"Re-ingestion changed chunk count: {count_before} -> "
            f"{count_after_first} -> {count_after_second}"
        )

    _safe_run(report, "13. Re-running ingestion does not crash", _check)


def check_query_before_ingestion_message(report: ValidationReport) -> None:
    def _check() -> None:
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        with patch("job_matcher.get_chroma_collection", return_value=mock_collection):
            try:
                _semantic_search("Python engineer", n_results=10)
                raise AssertionError("Expected ValueError for empty vector store")
            except ValueError as error:
                message = str(error)
                assert "resume_rag.py" in message, f"Unexpected error message: {message}"

    _safe_run(report, "14. Query before ingestion fails with clear message", _check)


def check_shared_skill_vocabulary(report: ValidationReport) -> None:
    def _check() -> None:
        import job_matcher
        import resume_rag

        assert resume_rag.KNOWN_SKILLS is VOCAB_SKILLS
        assert job_matcher.KNOWN_SKILLS is VOCAB_SKILLS
        assert len(VOCAB_SKILLS) >= 10

    _safe_run(report, "15. Shared KNOWN_SKILLS from skills_vocab.py", _check)


def check_sample_validation_scenario(report: ValidationReport) -> None:
    def _check() -> None:
        collection = get_chroma_collection()
        assert collection.count() > 0, "Vector store is empty — run with --run-ingestion"

        result = match_jobs(SAMPLE_JD, top_k=10)
        assert result["top_matches"], "Expected at least one match for canonical JD"

        top_three = result["top_matches"][:3]
        top_name = top_three[0]["candidate_name"]
        top_reasoning = top_three[0]["reasoning"].lower()
        top_skills = {skill.lower() for skill in top_three[0]["matched_skills"]}

        assert "python" in top_skills or "python" in top_reasoning, (
            "Top match should reference Python"
        )

        for match in top_three:
            matched = {skill.lower() for skill in match["matched_skills"]}
            if "python" in matched:
                continue
            assert match["match_score"] < top_three[0]["match_score"], (
                f"Candidate without Python ({match['candidate_name']}) should not outrank "
                f"Python matches in top 3"
            )

        experience_terms = ("experience", "year", "5", "senior")
        assert any(term in top_reasoning for term in experience_terms), (
            f"Top reasoning should mention experience fit: {top_reasoning[:120]}"
        )

        print(f"       Top match: {top_name} ({top_three[0]['match_score']})")

    _safe_run(report, "16. Sample validation scenario (context.md)", _check)


def run_validation(run_ingestion: bool) -> ValidationReport:
    report = ValidationReport()

    if run_ingestion:
        print("Running ingestion: python resume_rag.py --resume-dir resumes")
        try:
            build_vector_store(RESUME_DIR)
            print("Ingestion complete.\n")
        except Exception as error:
            print(f"Ingestion failed: {error}")
            print("Continuing with checks that do not require a populated vector store.\n")

    check_resume_files_loaded(report)
    check_section_aware_chunking(report)
    check_metadata_fields(report)
    check_shared_embedding_model(report)
    check_hybrid_search_active(report)
    check_output_json_schema(report)
    check_shared_skill_vocabulary(report)
    check_query_before_ingestion_message(report)

    collection = get_chroma_collection()
    has_store = collection.count() > 0

    if has_store:
        check_embeddings_in_store(report)
        check_chromadb_storage(report)
        check_top_k_default_and_reasoning(report)
        check_scores_in_range(report)
        check_must_have_filtering(report)
        check_empty_result_valid_json(report)
        check_sample_validation_scenario(report)
        if run_ingestion:
            check_idempotent_ingestion(report)
        else:
            report.add(
                "13. Re-running ingestion does not crash",
                True,
                "Skipped — pass --run-ingestion to test idempotent re-ingestion",
                skipped=True,
            )
    else:
        skipped = [
            "3. Each chunk has an embedding",
            "4. Chunks and metadata in ChromaDB",
            "7. Top-K defaults to 10; reasoning is non-empty",
            "9. Scores are 0-100",
            "10. Must-have filtering excludes missing skills",
            "12. Low-relevance JD returns valid JSON",
            "13. Re-running ingestion does not crash",
            "16. Sample validation scenario (context.md)",
        ]
        for criterion in skipped:
            report.add(
                criterion,
                True,
                "Vector store empty — run: python validate.py --run-ingestion",
                skipped=True,
            )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 10 acceptance validation")
    parser.add_argument(
        "--run-ingestion",
        action="store_true",
        help="Build/update vector store before running integration checks",
    )
    args = parser.parse_args()

    report = run_validation(run_ingestion=args.run_ingestion)
    report.print_summary()

    failed = [result for result in report.results if not result.passed and not result.skipped]
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
