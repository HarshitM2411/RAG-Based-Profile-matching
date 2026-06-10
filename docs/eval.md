# Evaluation Guide: Resume RAG System and Job Matching Engine


Reference: `architecture.md` (system design), `implementation_plan.md` (build plan), `edgecase.md` (edge cases)


This document defines how to measure whether the system is working correctly at each layer. It covers correctness checks, retrieval quality metrics, scoring validity, and the acceptance test suite.


---


## Evaluation Scope


This guide evaluates the exact design choices in `architecture.md` and `implementation_plan.md`:


- Pipeline A is validated through `build_vector_store()`, not by calling lower-level helpers as an alternative ingestion path.
- Pipeline B is validated through `match_jobs()` and `search_resumes()`, which must return candidate-level matches, not raw chunks.
- The final `match_score` is the Phase 8 candidate score (`0.50 / 0.30 / 0.20`), not the Phase 7 chunk-level hybrid score.
- Empty or invalid inputs should either return valid empty JSON where specified or fail with a clear, actionable message.


---


## 1. Evaluation Philosophy


The system has two distinct quality dimensions:


| Dimension | Question | Evaluated by |
|---|---|---|
| **Correctness** | Does the code run without crashing for all valid and edge-case inputs? | Unit and integration tests |
| **Relevance quality** | Does semantic search surface the right candidates for a given JD? | Retrieval metrics on labelled test cases |


Both dimensions must pass before the system is considered complete. A system that runs cleanly but returns the wrong candidates is not acceptable; equally, a system that sometimes crashes is not deployable even if the rankings look good.


---


## 2. Test Data Requirements


### 2.1 Minimum corpus for meaningful evaluation


| Asset | Minimum | Recommended |
|---|---|---|
| Sample resumes | 3 | 8-10 |
| Sample job descriptions | 1 | 3-4 |
| Resume formats covered | `.txt` | `.txt` + `.pdf` + `.docx` |
| Deliberately noisy / edge-case resumes | 0 | 2 (see §2.2) |


### 2.2 Recommended test resume personas


| Persona | Purpose |
|---|---|
| **Strong match** | Has all required skills, meets experience threshold, clear section headings. Should rank #1. |
| **Partial match** | Has 50% of required skills, 3 years vs. 5 required. Should rank in the middle. |
| **Weak match** | Completely different domain (e.g., pure finance resume for an ML JD). Should rank last. |
| **Skill-missing** | Has the right experience years but is missing the #1 required skill (e.g., no Python for a Python ML JD). Tests must-have filtering. |
| **No section headings** | Plain text resume with no `EXPERIENCE`, `SKILLS`, etc. Tests fallback chunking. |
| **Metadata extraction failure** | No parseable experience years, ambiguous name on first line. Tests graceful degradation. |
| **Duplicate filename** | Same filename as another persona but in a different sub-directory. Tests ID collision fix. |


### 2.2.1 Required fixture names


The code snippets below assume these files exist. If your local filenames differ, update the paths in the snippets before running them.


| Fixture | Suggested path |
|---|---|
| Strong match resume | `resumes/strong_match.txt` |
| Partial match resume | `resumes/partial_match.txt` |
| Weak match resume | `resumes/weak_match.txt` |
| Skill-missing resume | `resumes/skill_missing.txt` |
| No-heading resume | `resumes/no_headings.txt` |
| Empty file fixture | `resumes/empty_file.txt` |
| Canonical JD | `docs/jd_ml_engineer.txt` |


### 2.3 Sample job descriptions to prepare


| JD | Primary test purpose |
|---|---|
| `jd_ml_engineer.txt` — "Python ML engineer, 5+ years, SQL, AWS" | Primary correctness check; canonical scenario from `context.md` |
| `jd_frontend.txt` — "React developer, 2+ years, TypeScript" | Tests a domain shift from ML; ML resumes should score low |
| `jd_no_skills.txt` — "Experienced software developer needed" | Tests empty-skills fallback; no candidate should be excluded |
| `jd_unknown_skills.txt` — "Fortran/COBOL system programmer, 10+ years" | Tests unknown-skill fallback (EC-6.1); `required_skills` should be empty |
| `jd_must_have_rust.txt` — "Rust backend engineer, 10+ years" | Tests all-filtered-out edge case (EC-7.1) because `Rust` is in `KNOWN_SKILLS` |


---


## 3. Pipeline A — Ingestion Evaluation


Run this after every change to `resume_rag.py`, `embedder.py`, or `db_utils.py`.


### 3.1 File Loader checks


```python
from resume_rag import list_files, load_resume_text


# Must discover all supported formats
paths = list_files("resumes", [".pdf", ".docx", ".txt"])
assert len(paths) >= 3, "Expected at least 3 resume files"


# Must return non-empty text for a valid resume
text = load_resume_text(paths[0])
assert isinstance(text, str)
assert len(text.strip()) > 50, "Expected at least 50 chars of text"


# Must return "" for a corrupted/empty file without raising
text_bad = load_resume_text("resumes/empty_file.txt")   # fixture from §2.2.1
assert text_bad == "", f"Expected '' but got: {repr(text_bad)}"
```


**Pass criteria:** All assertions pass; no exception is raised for the corrupted file.


### 3.2 Metadata extraction checks


```python
from resume_rag import load_resume_text, extract_metadata


text = load_resume_text("resumes/strong_match.txt")
meta = extract_metadata(text, "resumes/strong_match.txt")


# Schema compliance
required_keys = {"candidate_name", "skills", "experience_years", "education", "resume_path"}
assert required_keys == set(meta.keys()), f"Missing keys: {required_keys - set(meta.keys())}"


# Type compliance (ChromaDB scalar constraint)
assert isinstance(meta["candidate_name"], str)
assert isinstance(meta["skills"], str)           # must be comma-separated string, not list
assert isinstance(meta["experience_years"], int)
assert isinstance(meta["education"], str)
assert isinstance(meta["resume_path"], str)


# Value checks for known resume
assert meta["candidate_name"] != ""              # fallback to filename if needed
assert "Python" in meta["skills"]                # strong_match resume must have Python
assert meta["experience_years"] >= 1             # strong_match has >1 year
assert meta["resume_path"] == "resumes/strong_match.txt"
```


**Pass criteria:** All assertions pass for the strong-match resume. For edge-case resumes, `candidate_name` may be `"Unknown"` and `experience_years` may be `0`, but no `None` values appear.


### 3.3 Chunker checks


```python
from resume_rag import load_resume_text, extract_metadata, chunk_resume


text = load_resume_text("resumes/strong_match.txt")
meta = extract_metadata(text, "resumes/strong_match.txt")
chunks = chunk_resume(text, meta)


# Must produce at least one chunk
assert len(chunks) > 0, "Chunker produced zero chunks for a valid resume"


# Each chunk must have required fields
required = {"chunk_id", "resume_path", "candidate_name", "section_label",
            "chunk_text", "chunk_index", "skills", "experience_years", "education"}
for c in chunks:
    assert required.issubset(c.keys()), f"Chunk missing keys: {required - c.keys()}"


# Minimum content size
assert all(len(c["chunk_text"]) >= 80 for c in chunks), "Chunk below minimum size"


# No ID collisions within the same resume
ids = [c["chunk_id"] for c in chunks]
assert len(ids) == len(set(ids)), "Duplicate chunk IDs detected"


# Section labels must be known values
known_sections = {"summary","skills","experience","education",
                  "projects","certifications","achievements","other"}
for c in chunks:
    assert c["section_label"] in known_sections, f"Unknown section: {c['section_label']}"
```


**Pass criteria:** All assertions pass. For a resume with clear section headings, at least one chunk with `section_label != "other"` should exist.


### 3.4 Full ingestion run check


```python
from db_utils import get_chroma_collection


# Run ingestion first:
# python resume_rag.py --resume-dir resumes


col = get_chroma_collection()


# Collection must be populated
assert col.count() > 0, "Vector store is empty after ingestion"


# Sample one record and verify metadata schema
result = col.get(limit=1, include=["metadatas", "documents", "embeddings"])
meta = result["metadatas"][0]
doc  = result["documents"][0]
emb  = result["embeddings"][0]


assert isinstance(doc, str) and len(doc) >= 80
assert emb is not None and len(emb) in (384, 768, 1024, 1536)
assert meta.get("candidate_name") is not None
assert meta.get("skills") is not None


# Re-run the exact same command manually; it must be idempotent (no duplicate-ID error)
count_before = col.count()
# python resume_rag.py --resume-dir resumes   (run again)
count_after = col.count()
assert count_after == count_before, "Re-ingestion changed the chunk count unexpectedly"
```


**Pass criteria:** Collection is populated; re-run does not change the count and raises no exception.


---


## 4. Pipeline B — Query Evaluation


Run this after every change to `job_matcher.py`.


### 4.1 JD parser checks


```python
from job_matcher import extract_job_requirements


jd = "Looking for a Python Machine Learning engineer with 5+ years of experience, SQL and AWS."
reqs = extract_job_requirements(jd)


assert "Python" in reqs["required_skills"], "Python not extracted from JD"
assert "SQL" in reqs["required_skills"], "SQL not extracted from JD"
assert reqs["min_experience_years"] == 5, f"Expected 5, got {reqs['min_experience_years']}"
assert isinstance(reqs["jd_keywords"], list) and len(reqs["jd_keywords"]) > 0


# Edge: no skills, no experience
jd_empty = "We need a good developer."
reqs_empty = extract_job_requirements(jd_empty)
assert reqs_empty["required_skills"] == []
assert reqs_empty["min_experience_years"] is None
```


**Pass criteria:** Both test cases pass. The parser does not crash on a sparse JD.


### 4.2 End-to-end output schema check


```python
from job_matcher import match_jobs
import json


jd = "Python Machine Learning engineer, 5+ years, SQL, AWS."
result = match_jobs(jd, top_k=10)


# Top-level schema
assert "job_description" in result
assert "top_matches" in result
assert result["job_description"] == jd
assert isinstance(result["top_matches"], list)
assert len(result["top_matches"]) <= 10


# Per-match schema
required_fields = {"candidate_name", "resume_path", "match_score",
                   "matched_skills", "relevant_excerpts", "reasoning"}
for m in result["top_matches"]:
    assert required_fields.issubset(m.keys()), f"Missing fields: {required_fields - m.keys()}"
    assert isinstance(m["match_score"], (int, float))
    assert 0 <= m["match_score"] <= 100, f"Score out of range: {m['match_score']}"
    assert isinstance(m["matched_skills"], list)
    assert isinstance(m["relevant_excerpts"], list)
    assert isinstance(m["reasoning"], str) and len(m["reasoning"]) > 0


# Must be strict JSON-serializable. allow_nan=False catches NaN/Infinity.
json.dumps(result, allow_nan=False)
```


**Pass criteria:** All assertions pass; `json.dumps()` succeeds.


### 4.3 Score ordering check


```python
scores = [m["match_score"] for m in result["top_matches"]]
assert scores == sorted(scores, reverse=True), "Results are not sorted by descending score"
```


**Pass criteria:** Scores are in non-increasing order.


---


## 5. Retrieval Quality Metrics


These metrics require a manually labelled relevance judgement set. Prepare a small set using the test personas from §2.2.


### 5.1 Relevance judgement format


Create a small table like the following for each JD:


| JD | Candidate (resume file) | Expected relevance |
|---|---|---|
| `jd_ml_engineer.txt` | `strong_match.txt` | `relevant` |
| `jd_ml_engineer.txt` | `partial_match.txt` | `partial` |
| `jd_ml_engineer.txt` | `weak_match.txt` | `not_relevant` |
| `jd_ml_engineer.txt` | `skill_missing.txt` | `not_relevant` (missing Python) |
| `jd_ml_engineer.txt` | `no_headings.txt` | `partial` |


For binary retrieval metrics, treat both `relevant` and `partial` as positive labels. Keep `not_relevant` as the negative label. This matches the assignment expectation that strong and partial matches should still appear near the top, while clearly missing must-have requirements should not.


### 5.2 Precision@K


$$
\text{Precision@K} = \frac{\text{number of relevant candidates in top-K results}}{K}
$$


**Target:** Lenient Precision@3 ≥ 0.67 (at least 2 of the top 3 results are `relevant` or `partial`) for the canonical ML engineer JD.


```python
# Manual check after running match_jobs on jd_ml_engineer.txt
top3 = [m["resume_path"] for m in result["top_matches"][:3]]
relevant_in_top3 = sum(1 for p in top3 if p in {"resumes/strong_match.txt", "resumes/partial_match.txt"})
precision_at_3 = relevant_in_top3 / 3
print(f"Lenient Precision@3: {precision_at_3:.2f}")
assert precision_at_3 >= 0.67
```


### 5.3 Recall@K (for a corpus of known relevant candidates)


$$
\text{Recall@K} = \frac{\text{number of relevant candidates in top-K results}}{\text{total relevant candidates in corpus}}
$$


**Target:** Lenient Recall@5 = 1.0 — both the strong-match and partial-match candidates must appear in the top 5.


```python
top5_paths = [m["resume_path"] for m in result["top_matches"][:5]]
known_relevant = {"resumes/strong_match.txt", "resumes/partial_match.txt"}
found = known_relevant.intersection(top5_paths)
recall_at_5 = len(found) / len(known_relevant)
print(f"Lenient Recall@5: {recall_at_5:.2f}")
assert recall_at_5 == 1.0
```


### 5.4 Must-have filter effectiveness


**Target:** Any candidate marked `not_relevant` due to a missing hard-required skill should NOT appear in the top-3 results for a JD that lists that skill.


```python
# skill_missing.txt has experience but no Python
# For jd_ml_engineer.txt (requires Python), it must not be in top 3
top3_paths = [m["resume_path"] for m in result["top_matches"][:3]]
assert "resumes/skill_missing.txt" not in top3_paths, \
    "Skill-missing candidate incorrectly ranked in top 3"
```


### 5.5 Score distribution sanity check


For the canonical ML JD, the expected score bands are:


```
strong_match > partial_match > weak_match
skill_missing should not appear in top 3 if missing a hard required skill
no_headings may rank as partial if semantic content and metadata are still recoverable
```


```python
# Build a lookup: resume_path -> match_score
score_map = {m["resume_path"]: m["match_score"] for m in result["top_matches"]}


strong  = score_map.get("resumes/strong_match.txt", 0)
partial = score_map.get("resumes/partial_match.txt", 0)
weak    = score_map.get("resumes/weak_match.txt", 0)


assert strong > partial, f"Strong ({strong}) should outscore partial ({partial})"
assert partial > weak,   f"Partial ({partial}) should outscore weak ({weak})"
assert strong >= 65,     "Strong match should score at least 65/100"
assert weak <= 50,       "Weak match should score at most 50/100"
```


---


## 6. Scoring Component Validation


### 6.1 Formula unit tests


```python
from job_matcher import score_candidate


# Perfect candidate: all signals at 1.0
perfect = {
    "semantic_score"  : 1.0,
    "matched_skills"  : ["Python", "SQL", "AWS"],
    "experience_years": 6,
}
reqs_full = {"required_skills": ["Python", "SQL", "AWS"], "min_experience_years": 5}
score = score_candidate(perfect, reqs_full)
assert score == 100.0, f"Perfect candidate should score 100, got {score}"


# No skill overlap
no_skills = {
    "semantic_score"  : 0.8,
    "matched_skills"  : [],
    "experience_years": 6,
}
score_ns = score_candidate(no_skills, reqs_full)
# = (0.8*0.50 + 0.0*0.30 + 1.0*0.20) * 100 = (0.40 + 0.00 + 0.20) * 100 = 60.0
assert abs(score_ns - 60.0) < 0.1, f"Expected ~60.0, got {score_ns}"


# Experience below requirement, experience_years=0 (metadata unavailable) → neutral 0.5
metadata_failure = {
    "semantic_score"  : 0.9,
    "matched_skills"  : ["Python"],
    "experience_years": 0,
}
score_mf = score_candidate(metadata_failure, reqs_full)
# skill_overlap = 1/3 = 0.333
# experience = 0.5 (neutral fallback for cand_years=0)
# = (0.9*0.50 + 0.333*0.30 + 0.5*0.20) * 100 ≈ (0.45 + 0.10 + 0.10) * 100 = 65.0
assert 60 <= score_mf <= 70, f"Expected ~65.0, got {score_mf}"


# Empty required_skills → neutral skill score (0.5)
no_reqs = {"required_skills": [], "min_experience_years": None}
candidate = {"semantic_score": 0.7, "matched_skills": [], "experience_years": 4}
score_nr = score_candidate(candidate, no_reqs)
# = (0.7*0.50 + 0.5*0.30 + 0.5*0.20) * 100 = (0.35 + 0.15 + 0.10) * 100 = 60.0
assert abs(score_nr - 60.0) < 0.1, f"Expected ~60.0, got {score_nr}"


# Score is always in [0, 100]
assert 0 <= score <= 100
assert 0 <= score_ns <= 100
assert 0 <= score_mf <= 100
assert 0 <= score_nr <= 100
```


### 6.2 Score bounds check across all candidates


```python
from job_matcher import match_jobs


result = match_jobs("Python ML engineer, 5+ years, SQL, AWS.")
for m in result["top_matches"]:
    assert 0 <= m["match_score"] <= 100, f"Out-of-range score: {m['match_score']}"
```


---


## 7. Reasoning Quality Check


Reasoning is qualitative but should satisfy these structural checks:


```python
from job_matcher import match_jobs


result = match_jobs("Python Machine Learning engineer, 5+ years, SQL, AWS.")
assert result["top_matches"], "Expected at least one match for the canonical JD"
top = result["top_matches"][0]


r = top["reasoning"]


# Must be non-empty
assert len(r.strip()) > 20, "Reasoning too short"


# Must mention at least one matched skill if skills were matched
if top["matched_skills"]:
    assert any(s.lower() in r.lower() for s in top["matched_skills"]), \
        "Reasoning does not mention any matched skill"


# Must contain a judgment word
judgment_words = {"strong", "partial", "weak"}
assert any(w in r.lower() for w in judgment_words), \
    f"Reasoning lacks a judgment word ({judgment_words}): {r}"
```


**Pass criteria:** All three checks pass for the top-ranked candidate in the canonical ML JD test.


---


## 8. Edge Case Test Suite


Run these after all standard tests pass. Each maps to an entry in `edgecase.md`.


| Edge case ref | Test description | Pass condition |
|---|---|---|
| EC-1.1 | Run `load_resume_text` on a zero-byte file | Returns `""` without raising |
| EC-1.2 | Run ingestion with a corrupted PDF in `resumes/` | Only corrupted file is skipped; other resumes ingest normally |
| EC-1.6 | Run `list_files("nonexistent_dir", ...)` | Raises `FileNotFoundError` with a message |
| EC-1.7 | Run `build_vector_store` on a dir with only `.jpg` files | Raises `ValueError` with a useful message |
| EC-2.1 | Run `extract_metadata` on a resume starting with a phone number | `candidate_name` is derived from filename, not the phone number |
| EC-2.2 | Run `extract_metadata` on a resume with no skills section | `skills` is a string (may be `""` or partial); no exception |
| EC-3.1 | Run `chunk_resume` on a resume with no section headings | Returns at least one chunk with `section_label = "other"` |
| EC-3.2 | Run `chunk_resume` on a 50-char stub resume | Returns `[]` without raising |
| EC-3.2b | Run `chunk_resume` on heading-only section text | Returns `[]` or only chunks with useful content, not heading-only chunks |
| EC-4.1 | Set `EMBEDDING_PROVIDER=openai` with no API key | Raises `ValueError` mentioning `OPENAI_API_KEY` |
| EC-4.1b | Set `EMBEDDING_PROVIDER=foo` | Raises `ValueError` listing valid providers |
| EC-4.2 | Call `embed_texts([])` | Returns `[]` without API call |
| EC-5.1 | Delete `vector_store/` and run `job_matcher.py` | Raises/prints clear error: "Run resume_rag.py first" |
| EC-5.2 | Store `{"education": None}` as metadata | Raises before `upsert()` or normalizes to `""` |
| EC-5.5 | Set `n_results=500` on a 10-chunk collection | Returns ≤10 results; no exception |
| EC-6.1 | Run `match_jobs` with a Fortran/COBOL JD | No skill-based exclusion occurs because `required_skills == []`; output remains valid JSON |
| EC-6.5 | Run `match_jobs("")` | Returns empty valid JSON or raises a clear `ValueError`; no provider exception |
| EC-7.1 | Run a JD requiring known skill `Rust` when no candidate has Rust | `match_jobs()` returns `{"top_matches": []}` without raising |
| EC-7.1b | Candidate has empty `skills` metadata but relevant chunk text | Chunk is retained with metadata-unavailable penalty/reason |
| EC-9.1 | Score candidate with `required_skills = []` | `match_score` is not zero solely due to skill score; `≥ 35` expected |
| EC-9.4 | Score with `min_experience_years = 0` | No `ZeroDivisionError` |
| EC-10.4 | `top_k=10` with only 3 resumes | `len(top_matches) == 3`, no index error |
| EC-10.5 | Inject `distance = float('inf')` into a chunk | Final score clamped to `[0, 100]`; no `NaN` in JSON |
| EC-10.6 | Run CLI with `--top-k 0` or negative value | Rejects invalid value or normalizes to default; no negative slicing |
| EC-11.2 | Query with a different `CHROMA_COLLECTION_NAME` than ingestion used | Clear empty-collection/config error, not a silent empty result |
| EC-12.4 | Rename one metadata key in a fake chunk | Aggregation/scoring test fails loudly or reports missing key |


---


## 9. Acceptance Criteria Summary


The following table maps the graded acceptance criteria from `context.md` and `architecture.md` §11 to the evaluation checks above.


| # | Requirement | Covered by |
|---|---|---|
| 1 | Resumes loaded from the file system | §3.1 File Loader checks |
| 2 | Section-aware chunking | §3.3 Chunker checks — `section_label` field |
| 3 | Embeddings generated per chunk | §3.4 Full ingestion run check — `embeddings` field |
| 4 | Chunks and metadata stored in ChromaDB | §3.4 Full ingestion run check — `col.count() > 0` |
| 5 | Metadata includes name, skills, experience, education, path | §3.2 Metadata extraction checks |
| 6 | JD embedded with the same model | §4.1 / §4.2 Query checks and shared `embed_texts()` path |
| 7 | Top-K defaults to 10 | §4.2 Schema check — `len(top_matches) <= 10` |
| 8 | Hybrid search combines semantic + keyword | §5.4 Must-have filter effectiveness and code inspection of `_hybrid_score()` |
| 9 | Scores are 0-100 | §6.2 Score bounds check |
| 10 | Must-have filtering works | §5.4 + EC-7.1 |
| 11 | Output JSON matches required schema | §4.2 End-to-end output schema check |
| 12 | Empty result is valid JSON | EC-7.1 and EC-6.5 |
| 13 | Re-running ingestion does not crash | §3.4 idempotency check |
| 14 | Query before ingestion fails clearly | EC-5.1 |
| 15 | Shared skill vocabulary is single-source | Code inspection: both scripts import `KNOWN_SKILLS` from `skills_vocab.py` |


---


## 10. Running the Full Evaluation


```bash
# 1. Ingest sample resumes
python resume_rag.py --resume-dir resumes --persist-dir vector_store


# 2. Run all standard evaluations after adapting the snippets above into tests
# Optional, only if you create a tests/ directory:
python -m pytest tests/ -v


# 3. Run the canonical end-to-end scenario
python job_matcher.py --job-description-file docs/jd_ml_engineer.txt --top-k 10 | python -m json.tool


# 4. Manually verify the score bands:
#    strong_match ranks above partial_match, weak_match stays low,
#    and skill_missing does not appear in the top 3 for the canonical JD.


# 5. Run edge case suite after wrapping EC-* checks into a local script:
# python eval_edge_cases.py
```


### Interpreting results


| Outcome | Meaning |
|---|---|
| All schema assertions pass | Implementation is structurally correct |
| Lenient Precision@3 ≥ 0.67 | Semantic search is surfacing useful candidates |
| Strong > Partial > Weak score ordering | Scoring weights and aggregation are calibrated correctly |
| Skill-missing candidate absent from top 3 | Must-have filtering is working |
| All edge case checks pass | Error handling is robust |
| JSON serialization succeeds for all outputs | Output is integration-ready |