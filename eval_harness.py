"""
Evaluation harness for retrieval accuracy and latency benchmarks.

Used by notebooks/rag_evaluation.ipynb and runnable standalone:
    python eval_harness.py
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

from db_utils import get_chroma_collection
from embedder import embed_texts
from job_matcher import (
    _search_n_results,
    _search_resume_chunks,
    _semantic_search,
    extract_job_requirements,
    search_resumes,
)
from resume_rag import build_vector_store, list_files

PROJECT_ROOT = Path(__file__).resolve().parent
LABELS_PATH = PROJECT_ROOT / "data" / "eval_labels.json"
RESUME_DIR = PROJECT_ROOT / "resumes"

POSITIVE_LABELS = {"relevant", "partial"}


def load_labels(path: Path | str = LABELS_PATH) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_job_description(jd_path: str | Path) -> str:
    path = PROJECT_ROOT / jd_path if not Path(jd_path).is_absolute() else Path(jd_path)
    return path.read_text(encoding="utf-8").strip()


def precision_at_k(
    retrieved_paths: list[str],
    labels: dict[str, str],
    k: int,
    positive_labels: set[str] = POSITIVE_LABELS,
) -> float:
    top_k = retrieved_paths[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for path in top_k if labels.get(path) in positive_labels)
    return hits / k


def recall_at_k(
    retrieved_paths: list[str],
    labels: dict[str, str],
    k: int,
    positive_labels: set[str] = POSITIVE_LABELS,
) -> float:
    known_positive = {path for path, label in labels.items() if label in positive_labels}
    if not known_positive:
        return 0.0
    top_k = set(retrieved_paths[:k])
    found = known_positive.intersection(top_k)
    return len(found) / len(known_positive)


def mean_reciprocal_rank(
    retrieved_paths: list[str],
    labels: dict[str, str],
    positive_labels: set[str] = POSITIVE_LABELS,
) -> float:
    for rank, path in enumerate(retrieved_paths, start=1):
        if labels.get(path) in positive_labels:
            return 1.0 / rank
    return 0.0


def run_retrieval_for_jd(
    job_description: str,
    top_k: int = 10,
    *,
    include_reasoning: bool = False,
) -> list[dict]:
    if include_reasoning:
        return search_resumes(job_description, top_k=top_k)

    with patch("job_matcher._generate_reasoning", return_value="(skipped for benchmark)"):
        return search_resumes(job_description, top_k=top_k)


def evaluate_jd_case(
    jd_key: str,
    jd_config: dict,
    top_k: int = 10,
) -> dict[str, Any]:
    job_description = load_job_description(jd_config["path"])
    results = run_retrieval_for_jd(job_description, top_k=top_k)
    retrieved_paths = [candidate["resume_path"] for candidate in results]
    labels = jd_config["labels"]

    return {
        "jd_key": jd_key,
        "title": jd_config.get("title", jd_key),
        "jd_path": jd_config["path"],
        "precision_at_3": precision_at_k(retrieved_paths, labels, 3),
        "precision_at_5": precision_at_k(retrieved_paths, labels, 5),
        "recall_at_5": recall_at_k(retrieved_paths, labels, 5),
        "recall_at_10": recall_at_k(retrieved_paths, labels, 10),
        "mrr": mean_reciprocal_rank(retrieved_paths, labels),
        "retrieved_paths": retrieved_paths,
        "top_matches": [
            {
                "candidate_name": candidate["candidate_name"],
                "resume_path": candidate["resume_path"],
                "match_score": candidate["match_score"],
                "matched_skills": candidate.get("matched_skills", []),
                "expected_label": labels.get(candidate["resume_path"], "unlabeled"),
            }
            for candidate in results
        ],
    }


def evaluate_all_cases(top_k: int = 10) -> list[dict[str, Any]]:
    labels_data = load_labels()
    return [
        evaluate_jd_case(jd_key, jd_config, top_k=top_k)
        for jd_key, jd_config in labels_data["job_descriptions"].items()
    ]


def corpus_stats() -> dict[str, Any]:
    resume_files = list_files(str(RESUME_DIR), [".pdf", ".docx", ".txt"])
    collection = get_chroma_collection()
    chunk_count = collection.count()

    results = collection.get(include=["metadatas"])
    indexed_paths = {
        metadata.get("resume_path")
        for metadata in results.get("metadatas", [])
        if metadata and metadata.get("resume_path")
    }

    format_counts: dict[str, int] = {}
    for file_path in resume_files:
        suffix = Path(file_path).suffix.lower()
        format_counts[suffix] = format_counts.get(suffix, 0) + 1

    return {
        "total_resumes": len(resume_files),
        "indexed_resumes": len(indexed_paths),
        "total_chunks": chunk_count,
        "format_counts": format_counts,
    }


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[index]


def _time_call(func, *args, **kwargs) -> tuple[float, Any]:
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return elapsed_ms, result


def benchmark_latency(
    job_description: str,
    runs: int = 5,
) -> dict[str, Any]:
    requirements = extract_job_requirements(job_description)
    n_results = _search_n_results(10)

    embed_samples: list[float] = []
    semantic_samples: list[float] = []
    hybrid_samples: list[float] = []
    retrieval_samples: list[float] = []

    for _ in range(runs):
        elapsed, _ = _time_call(embed_texts, [job_description])
        embed_samples.append(elapsed)

        elapsed, _ = _time_call(_semantic_search, job_description, n_results)
        semantic_samples.append(elapsed)

        elapsed, _ = _time_call(_search_resume_chunks, job_description, requirements, n_results)
        hybrid_samples.append(elapsed)

        elapsed, _ = _time_call(run_retrieval_for_jd, job_description, 10)
        retrieval_samples.append(elapsed)

    def summarize(samples: list[float]) -> dict[str, float]:
        return {
            "mean_ms": round(statistics.mean(samples), 2),
            "median_ms": round(statistics.median(samples), 2),
            "p95_ms": round(_percentile(samples, 95), 2),
        }

    return {
        "runs": runs,
        "jd_embedding": summarize(embed_samples),
        "semantic_search": summarize(semantic_samples),
        "hybrid_filter_and_score": summarize(hybrid_samples),
        "full_retrieval_no_llm": summarize(retrieval_samples),
    }


def benchmark_ingestion() -> dict[str, Any]:
    elapsed, _ = _time_call(build_vector_store, str(RESUME_DIR))
    stats = corpus_stats()
    return {
        "total_ingestion_ms": round(elapsed, 2),
        "per_resume_ms": round(elapsed / max(stats["total_resumes"], 1), 2),
        **stats,
    }


def results_to_dataframe_rows(eval_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in eval_results:
        rows.append(
            {
                "jd": case["title"],
                "precision@3": case["precision_at_3"],
                "precision@5": case["precision_at_5"],
                "recall@5": case["recall_at_5"],
                "recall@10": case["recall_at_10"],
                "mrr": case["mrr"],
            }
        )
    return rows


def print_summary(eval_results: list[dict[str, Any]], latency: dict[str, Any]) -> None:
    print("=== Retrieval Accuracy ===")
    for case in eval_results:
        print(
            f"{case['title']}: "
            f"P@3={case['precision_at_3']:.2f}, "
            f"R@5={case['recall_at_5']:.2f}, "
            f"MRR={case['mrr']:.2f}"
        )

    print("\n=== Latency (ms, retrieval without LLM) ===")
    for stage, stats in latency.items():
        if stage == "runs":
            continue
        print(
            f"{stage}: mean={stats['mean_ms']}ms, "
            f"median={stats['median_ms']}ms, p95={stats['p95_ms']}ms"
        )


if __name__ == "__main__":
    stats = corpus_stats()
    if stats["total_chunks"] == 0:
        print("Vector store empty — running ingestion first...")
        build_vector_store(str(RESUME_DIR))

    eval_results = evaluate_all_cases()
    canonical_jd = load_job_description("docs/sample_jd.txt")
    latency = benchmark_latency(canonical_jd, runs=3)
    print_summary(eval_results, latency)
