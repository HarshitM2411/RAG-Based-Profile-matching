# Edge Cases: Resume RAG System and Job Matching Engine


Reference: `architecture.md` (system design), `implementation_plan.md` (build plan)


Each edge case is grouped by the pipeline stage it affects and the expected system behaviour.


---


## Review Notes


These cases intentionally follow the decisions already fixed in `architecture.md` and `implementation_plan.md`:


- `build_vector_store()` remains the only ingestion orchestrator.
- ChromaDB writes use `collection.upsert()` for idempotent re-runs.
- `KNOWN_SKILLS`, embedding configuration, and ChromaDB access are shared helpers, not duplicated between scripts.
- Candidate-level scoring happens only after chunk aggregation; chunk-level hybrid score is only an intermediate retrieval signal.
- Metadata-unavailable cases are degraded with uncertainty/neutral fallbacks, not automatically excluded.


---


## Legend


| Tag | Meaning |
|---|---|
| `P-A` | Pipeline A — Ingestion (`resume_rag.py`) |
| `P-B` | Pipeline B — Query (`job_matcher.py`) |
| `P-AB` | Affects both pipelines or their shared contract |
| **Expected:** | What a correct implementation must do |
| **Risk if missed:** | What breaks silently or loudly if the case is not handled |


---


## 1. File Loader Edge Cases (§3.2, Phase 1)


### EC-1.1 — Empty resume file
- **Input:** A `.pdf`, `.docx`, or `.txt` file that exists on disk but contains zero bytes or only whitespace.
- **Expected:** `load_resume_text()` returns `""`. `build_vector_store()` logs a warning and skips the file. No exception propagates.
- **Risk if missed:** `extract_metadata("")` and `chunk_resume("")` run on empty text, producing garbage metadata and zero chunks silently stored.


### EC-1.2 — Corrupted PDF
- **Input:** A `.pdf` file with a broken byte structure that `pypdf.PdfReader` cannot parse.
- **Expected:** The `pypdf` exception is caught inside `load_resume_text()`. A warning is logged with the file path. The function returns `""` and the pipeline moves to the next file.
- **Risk if missed:** One bad resume crashes the entire ingestion run, leaving the vector store partially populated.


### EC-1.3 — Password-protected PDF
- **Input:** A PDF that requires a password to read.
- **Expected:** `pypdf` raises `pypdf.errors.FileNotDecryptedError`. Treat the same as a corrupted file: log a warning mentioning the file requires a password, return `""`, skip.
- **Risk if missed:** Silent empty text extraction; the resume appears to succeed but stores no data.


### EC-1.4 — DOCX with images only, no paragraph text
- **Input:** A `.docx` where all content is in image objects, not paragraph elements.
- **Expected:** `python-docx` returns an empty paragraph list. `load_resume_text()` returns `""`. Warn and skip.
- **Risk if missed:** An empty string proceeds through metadata extraction and produces a `candidate_name = "Unknown"` record that wastes a ChromaDB entry.


### EC-1.5 — Non-UTF-8 encoded TXT file
- **Input:** A `.txt` file encoded in Latin-1 or Windows-1252.
- **Expected:** `open(file_path, encoding="utf-8")` may raise `UnicodeDecodeError`. At minimum, catch the exception, log a warning, return `""`, and let `build_vector_store()` skip the file. Optional hardening: retry with `encoding="latin-1"` or use `errors="replace"` before skipping.
- **Risk if missed:** A common Windows-produced resume file can crash the whole ingestion run.


### EC-1.6 — Resume directory does not exist
- **Input:** `--resume-dir` points to a path that does not exist.
- **Expected:** `list_files()` raises `FileNotFoundError` with a human-readable message. The CLI prints it and exits with a non-zero code. Does not silently return an empty list.
- **Risk if missed:** `build_vector_store()` exits cleanly with zero resumes processed; the user gets no error and queries return empty results.


### EC-1.7 — Resume directory exists but contains no supported files
- **Input:** Directory exists but contains only `.jpg` or `.xlsx` files.
- **Expected:** `list_files()` returns `[]`. `build_vector_store()` raises a `ValueError` with a clear message listing the supported extensions.
- **Risk if missed:** Same as EC-1.6 — silent empty store.


### EC-1.8 — Duplicate filenames in different sub-directories
- **Input:** `resumes/2024/john_doe.pdf` and `resumes/2023/john_doe.pdf` are both discovered.
- **Expected:** Both are processed. Because chunk IDs use `hashlib.md5(resume_path.encode())[:8]`, the full path (not just the stem) is hashed, so IDs remain distinct.
- **Risk if missed:** Stem-only IDs (`john_doe_experience_2` for both files) collide. `upsert()` silently overwrites one candidate's chunks with another's.


---


## 2. Metadata Extractor Edge Cases (§3.4, Phase 2)


### EC-2.1 — Resume begins with a phone number or address, not a name
- **Input:** First non-empty line is `+91-9876543210` or `123 Main Street, Bangalore`.
- **Expected:** The name extraction heuristic (2-4 words, no digits) rejects this line. Fallback derives the name from the filename stem (e.g. `john_doe.pdf` → `"John Doe"`).
- **Risk if missed:** `candidate_name` is set to a phone number or address, producing unusable output and incorrect grouping.


### EC-2.2 — No skills section in the resume
- **Input:** Resume contains no heading matching `SECTION_PATTERNS["skills"]`.
- **Expected:** Skills extractor falls back to scanning the full resume text for `KNOWN_SKILLS` matches. Returns a comma-separated string of found skills, or `""` if none found.
- **Risk if missed:** `skills` is always `""` for resumes that use informal layouts; skill matching and filtering fail for all such candidates.


### EC-2.3 — Skills expressed as synonyms not in KNOWN_SKILLS
- **Input:** Resume says "deep neural networks" but `KNOWN_SKILLS` only contains `"Deep Learning"`.
- **Expected:** No match is found. `skills` field will not include this technology. Semantic search may still surface the candidate via embedding similarity.
- **Risk if missed:** No specific code failure, but scores and reasoning will understate skill match for candidates with non-standard vocabulary. This is a known limitation; reasoning should not claim a skill is absent without qualification.


### EC-2.4 — Experience stated only in months
- **Input:** "18 months of experience in Python".
- **Expected:** The years regex does not match. Date-range inference is attempted. If that also fails, `experience_years = 0`. If the regex is extended to handle months, the value should be converted: 18 months → 1 year.
- **Risk if missed:** A 1.5-year candidate is treated as having zero experience and may fail a `min_experience_years = 1` filter.


### EC-2.5 — Multiple experience claims with different numbers
- **Input:** "5 years of Python, 2 years of Kubernetes, 10+ years total experience".
- **Expected:** Take the maximum value found (10) as `experience_years`, or document a consistent rule (e.g., always take the value nearest "total" or the maximum). The rule must be consistent.
- **Risk if missed:** Taking the minimum (2) causes a senior candidate to fail experience filters.


### EC-2.6 — Education section missing entirely
- **Input:** Resume has no heading matching `SECTION_PATTERNS["education"]`.
- **Expected:** `education` field is set to `""`. No exception raised. Reasoning may note "education data unavailable".
- **Risk if missed:** `None` instead of `""` breaks ChromaDB metadata storage (non-scalar value).


### EC-2.7 — `resume_path` is an OS-absolute path
- **Input:** `load_resume_text("/Users/alice/Desktop/john_doe.pdf")` is called with an absolute path.
- **Expected:** `extract_metadata()` and all downstream components store the path consistently. Prefer normalizing to a workspace-relative path before metadata extraction (for example, `resumes/john_doe.pdf`) and hash that same normalized path for `chunk_id`. If the implementation stores absolute paths, it must do so consistently across ingestion, chunk IDs, aggregation, and JSON output.
- **Risk if missed:** JSON output contains machine-specific absolute paths that break on any other machine, and grouping by `resume_path` fails if paths are mixed.


### EC-2.8 — Skill names are substrings of unrelated words
- **Input:** Resume text says `JavaScript` and `PostgreSQL`; `KNOWN_SKILLS` also contains `Java` and `SQL`.
- **Expected:** Multi-word and single-word skills are matched using case-insensitive word-boundary or token-aware regex. `Java` should not be extracted from `JavaScript`, and `SQL` should not be extracted from `PostgreSQL` unless the standalone skill is also present.
- **Risk if missed:** Metadata overstates skills. A candidate may pass must-have filtering for `Java` or `SQL` even though the resume only contains a different technology.


---


## 3. Section-Aware Chunker Edge Cases (§3.3, Phase 3)


### EC-3.1 — Resume with no section headings at all
- **Input:** A plain paragraph resume with no `EDUCATION`, `EXPERIENCE`, or `SKILLS` headings.
- **Expected:** `_detect_sections()` returns an empty boundary list. The entire text is assigned to section `"other"`. It is then subchunked normally.
- **Risk if missed:** `chunk_resume()` returns an empty list; no chunks are stored for this candidate.


### EC-3.2 — Very short resume (< 80 characters of text)
- **Input:** A one-line placeholder resume or a stub.
- **Expected:** All subchunks produced fall below `MIN_CHUNK_CHARS` (80 chars) and are discarded. `chunk_resume()` returns `[]`. `build_vector_store()` logs a warning and skips.
- **Risk if missed:** No warning is issued; the resume appears processed but stores nothing.


### EC-3.2b — Resume text is mostly section headings
- **Input:** A resume has headings such as `SKILLS`, `EXPERIENCE`, and `EDUCATION`, but each section contains only a few words.
- **Expected:** Headings alone should not become stored chunks. After subchunk filtering, `chunk_resume()` may return `[]`, and `build_vector_store()` should warn and skip.
- **Risk if missed:** Header-only chunks are embedded and retrieved, creating noisy matches with no useful excerpts.


### EC-3.3 — Single section with extremely long text (> 5000 chars)
- **Input:** A single "Experience" section listing 15 jobs without sub-headings, totalling 6000 characters.
- **Expected:** `_subchunk()` splits it into overlapping windows of ≤900 chars with 100-char overlap. Each window becomes a separate chunk with the same `section_label = "experience"` and an incrementing `chunk_index`.
- **Risk if missed:** One massive chunk is embedded as a single vector; embeddings average over too much text, producing a diluted similarity score.


### EC-3.4 — Section heading detected inside body text (false positive)
- **Input:** Body text says "I have strong experience in EDUCATION technology tools."
- **Expected:** The heading regex should be anchored to match lines that look like standalone headings, not inline mentions. Use `re.match` on stripped lines, or require the heading to be on its own line.
- **Risk if missed:** The resume is incorrectly split mid-sentence; chunk context is broken, embedding quality degrades.


### EC-3.5 — Same section heading repeated twice
- **Input:** Two `EXPERIENCE` headings in one resume (e.g., a two-page PDF with repeated section headers at the top of page 2).
- **Expected:** Both boundaries are detected. The second occurrence extends or appends to the first `experience` block, or creates a second group named `experience_2`. Either behavior is acceptable as long as no content is lost and chunk IDs remain unique.
- **Risk if missed:** The second occurrence overwrites the first block; job history is partially lost.


### EC-3.6 — Chunk ID collision across two resumes processed in the same run
- **Input:** `resumes/alice.pdf` and `resumes/bob.pdf` each have an `experience` section, each producing 3 chunks.
- **Expected:** Because the ID includes `hashlib.md5(resume_path)[:8]`, the hashes for different paths will differ. IDs are `{hash_alice}_experience_0` and `{hash_bob}_experience_0`, which are distinct.
- **Risk if missed:** If IDs are generated from stem-only names and both files happen to share a stem (`cv.pdf`), `upsert()` silently overwrites chunks, losing one candidate.


---


## 4. Embedding Edge Cases (§3.5, Phase 4)


### EC-4.1 — API key missing for OpenAI or Cohere provider
- **Input:** `.env` sets `EMBEDDING_PROVIDER=openai` but `OPENAI_API_KEY` is absent or empty.
- **Expected:** `get_embedding_model()` raises a `ValueError` with a message naming the missing variable. The process exits immediately rather than failing mid-ingestion after processing some files.
- **Risk if missed:** Ingestion starts, processes 10 resumes, then crashes on the embedding call; partial data in ChromaDB, inconsistent state.


### EC-4.1b — Unsupported embedding provider configured
- **Input:** `.env` sets `EMBEDDING_PROVIDER=foo`.
- **Expected:** `get_embedding_model()` or `embed_texts()` raises a clear `ValueError` listing valid providers: `huggingface`, `openai`, `cohere`.
- **Risk if missed:** The code falls through to an undefined branch, producing a confusing `UnboundLocalError` or returning no vectors.


### EC-4.2 — Empty text batch passed to embed_texts
- **Input:** `embed_texts([])` is called (e.g., a resume produces zero valid chunks).
- **Expected:** Returns `[]` immediately without calling the provider API. No API error.
- **Risk if missed:** OpenAI and Cohere raise errors for empty input lists; HuggingFace returns an empty array silently but some versions raise `ValueError`.


### EC-4.3 — Single very long chunk text exceeding model token limit
- **Input:** A subchunk of 900 characters that maps to ~250 tokens — within typical limits, but a user who sets `MAX_CHUNK_CHARS = 5000` would exceed the 512-token limit of `all-MiniLM-L6-v2`.
- **Expected:** HuggingFace `SentenceTransformer` silently truncates at the model's max token length. The embedding is valid but represents only the first portion of the text. Consider logging a warning if a chunk exceeds ~400 tokens.
- **Risk if missed:** Silent truncation means the tail of the chunk is never represented in the embedding; experience descriptions that appear late in a long section are invisible to semantic search.


### EC-4.4 — Cohere `input_type` mismatch between pipelines
- **Input:** `resume_rag.py` calls `embed_texts(chunks)` (defaults to `"search_document"`). `job_matcher.py` accidentally calls `embed_texts([jd_text])` without passing `input_type="search_query"`.
- **Expected:** Both calls use the correct `input_type`. The shared `embed_texts()` function accepts `input_type` as a parameter; callers in `job_matcher.py` must explicitly pass `"search_query"`.
- **Risk if missed:** Cohere embeds query and documents with the same mode; similarity scores degrade significantly for Cohere provider while working correctly for HuggingFace and OpenAI (which ignore the parameter).


### EC-4.5 — Embedding model changed between ingestion runs
- **Input:** First run uses `all-MiniLM-L6-v2` (384 dims). `.env` is changed to `all-mpnet-base-v2` (768 dims). Second run adds new resumes.
- **Expected:** ChromaDB will reject vectors of dimension 768 if the collection was created with dimension 384. The second run should fail loudly, not silently store incompatible vectors.
- **Risk if missed:** ChromaDB raises a dimension mismatch error at `upsert()`. But if the collection is deleted and recreated, old resumes are lost. Document this: changing the model requires a full re-ingestion.


---


## 5. ChromaDB / Vector Store Edge Cases (§3.6, Phase 5)


### EC-5.1 — Query before any ingestion has run
- **Input:** `vector_store/` directory is absent or the ChromaDB collection is empty; user runs `job_matcher.py`.
- **Expected:** `_semantic_search()` checks `collection.count() == 0` (or catches `chromadb.errors.InvalidCollectionException`) and raises a clear error: "Vector store is empty. Run `python resume_rag.py --resume-dir resumes` first."
- **Risk if missed:** An empty result set propagates silently; `match_jobs()` returns `{"job_description": ..., "top_matches": []}` without any indication that something is wrong.


### EC-5.2 — Metadata value is a Python `None`
- **Input:** `extract_metadata()` returns `{"education": None, ...}` because the section was not found.
- **Expected:** ChromaDB metadata values must be `str`, `int`, `float`, or `bool`. `None` causes a ChromaDB `ValueError` at `upsert()`. Normalize all `None` values to their default empty strings or `0` before calling `upsert()`.
- **Risk if missed:** Ingestion crashes on any resume with an absent education section.


### EC-5.3 — ChromaDB persistence directory lacks write permissions
- **Input:** `vector_store/` exists but the running user has read-only access.
- **Expected:** ChromaDB raises an `OSError` or `PermissionError`. The application should catch this and print a human-readable message: "Cannot write to vector_store/. Check directory permissions."
- **Risk if missed:** Cryptic ChromaDB internal error message; difficult to debug.


### EC-5.4 — Re-ingestion after modifying a resume file
- **Input:** `resumes/john_doe.pdf` is updated with new content. `build_vector_store()` is run again.
- **Expected:** Because IDs are deterministic (`hash(resume_path)[:8]_section_index`), `upsert()` updates chunks whose IDs still exist and adds new chunks. If the resume now produces fewer chunks than before, stale higher-index chunks can remain unless the implementation deletes existing rows for that `resume_path` before re-upserting.
- **Risk if missed:** A shortened resume may still retrieve content from its old version. For the assignment's idempotency requirement, same-file re-runs must not crash; for true refresh correctness, delete old chunks for the same `resume_path` before upserting the new chunk set.


### EC-5.5 — `n_results` requested from ChromaDB exceeds collection size
- **Input:** Collection has 8 chunks total but `collection.query(n_results=50)` is called.
- **Expected:** ChromaDB returns all 8 available chunks without error. The calling code handles a result set smaller than the requested `n_results`.
- **Risk if missed:** Some ChromaDB versions raise an error if `n_results > collection.count()`. Guard with `n_results = min(n_results, collection.count())`.


---


## 6. JD Parser Edge Cases (§4.2, Phase 6)


### EC-6.1 — Job description contains no skills from KNOWN_SKILLS
- **Input:** JD is for a niche role (`"Seeking an expert Fortran developer with COBOL experience"`).
- **Expected:** `required_skills` is `[]` because Fortran and COBOL are not in the default vocabulary. `skill_overlap_score` falls back to `0.5` (neutral). All candidates are compared using semantic similarity and experience only; no candidate is excluded by a skill that the parser did not extract.
- **Risk if missed:** `skill_overlap_score = 0 / max(0, 1) = 0` unfairly penalizes every candidate.


### EC-6.2 — JD contains no experience requirement
- **Input:** JD says "Looking for a talented Python developer" with no years mentioned.
- **Expected:** `min_experience_years` is `None`. `experience_score` defaults to `0.5` for all candidates. No candidate is excluded on experience grounds.
- **Risk if missed:** Division by zero in `min(cand_years / req_years, 1.0)` if `req_years` defaults to `0` instead of being guarded.


### EC-6.3 — JD experience requirement stated in ambiguous phrasing
- **Input:** "The ideal candidate will have worked for several years in ML."
- **Expected:** The years regex does not match "several". `min_experience_years = None`. No hard filter applied.
- **Risk if missed:** If a naive integer scan extracts any nearby number, a false `min_experience_years` is set and candidates are incorrectly filtered.


### EC-6.4 — JD is a single sentence with no structure
- **Input:** `"Python dev needed."` (4 words).
- **Expected:** `required_skills = ["Python"]` (if "Python" matches). `min_experience_years = None`. `jd_keywords = ["python", "dev", "needed"]`. System proceeds with reduced precision.
- **Risk if missed:** `jd_keywords` after stopword removal may be empty; the keyword fallback in `_hybrid_score()` divides by `max(0, 1) = 1`, returning a score of 0 for all chunks. Semantic search still works correctly.


### EC-6.5 — JD is empty or whitespace only
- **Input:** `match_jobs("")` or `match_jobs("   ")`.
- **Expected:** `match_jobs()` should validate `job_description.strip()` before embedding. For an empty JD, return valid JSON with `top_matches: []` or raise a clear `ValueError` at the CLI boundary. Do not send an empty string to the embedding provider.
- **Risk if missed:** Provider-specific exception (`openai` raises for empty input; `sentence-transformers` may return a degenerate vector), or arbitrary low-quality matches for a query with no signal.


---


## 7. Hybrid Search and Filtering Edge Cases (§4.3–4.4, Phase 7)


### EC-7.1 — All candidates filtered out by must-have constraints
- **Input:** JD requires `"Rust"` with 10+ years. No resume in the corpus mentions Rust.
- **Expected:** `_search_resume_chunks()` returns `[]`. `_aggregate_by_candidate()` returns `[]`. `search_resumes()` returns `[]`. `match_jobs()` returns `{"job_description": ..., "top_matches": []}`. No exception.
- **Risk if missed:** The scoring or output phase receives an empty list and crashes on index access or sorting.


### EC-7.1b — Required skill absent from metadata but present in chunk text
- **Input:** Resume metadata `skills` is empty because the skills section was not parsed, but an experience chunk says `Built production Python services`.
- **Expected:** The must-have filter follows the implementation contract and reads candidate skills from metadata. If `skills == ""`, treat skill metadata as unavailable and keep the chunk with `filter_penalty = 0.5` and `filter_reason = "metadata unavailable"`. Do not infer hard constraints from chunk text in this filter unless the architecture is updated.
- **Risk if missed:** The filter becomes inconsistent with candidate-level metadata and may include/exclude different chunks from the same resume differently.


### EC-7.2 — Candidate passes must-have but has `experience_years = 0` (metadata extraction failure)
- **Input:** A strong candidate whose experience years could not be parsed. `experience_years = 0` in metadata.
- **Expected:** The must-have filter does not hard-exclude (`experience_years == 0` is treated as unavailable, not as "zero years"). `filter_reason` is set to `"metadata unavailable"`. `experience_score = 0.5` (neutral fallback). Reasoning mentions "experience data unavailable".
- **Risk if missed:** A senior candidate with an unusual date format is permanently excluded from all matches.


### EC-7.3 — Chunk distance from ChromaDB is exactly 0 (perfect match)
- **Input:** The exact JD text was stored as a resume chunk (a contrived test).
- **Expected:** `semantic_sim = 1 - 0 = 1.0`. Hybrid score calculation proceeds normally. No division by zero.
- **Risk if missed:** No issue mathematically, but this edge validates the distance-to-similarity formula.


### EC-7.4 — Chunk distance exceeds 1.0 (numerical noise)
- **Input:** Due to floating-point imprecision, a returned cosine distance is `1.0000001`.
- **Expected:** `semantic_sim = max(0.0, 1 - distance)` is clamped to `0.0` rather than going slightly negative.
- **Risk if missed:** A negative `semantic_sim` feeds into the hybrid score and the final score, producing scores below zero or below the expected range.


### EC-7.5 — `required_skills` list contains duplicates
- **Input:** JD parser extracts `["Python", "python", "Python"]` due to case-insensitive matching returning multiple hits.
- **Expected:** Deduplicate `required_skills` (case-insensitive) before using it in scoring. `keyword_hit_ratio` divides by a correct unique count, not an inflated one.
- **Risk if missed:** The denominator `len(required_skills) = 3` instead of `1`, causing `keyword_hit_ratio = 0.33` even when Python is present.


---


## 8. Candidate Aggregation Edge Cases (§4.5, Phase 8)


### EC-8.1 — Single candidate produces only one matching chunk
- **Input:** A resume with a very small skills section that matches; all other chunks are filtered.
- **Expected:** `_aggregate_by_candidate()` produces a candidate dict with `semantic_score` from that single chunk, `relevant_excerpts` with that single text, and `matched_sections` with that section label.
- **Risk if missed:** Mean or max across a single-item list works correctly in Python; no specific handling needed, but verify the aggregation function does not assume `len(chunks) > 1`.


### EC-8.2 — Two candidates with identical names but different resume paths
- **Input:** Two files named `alice_smith_cv.pdf` (different directories) produce `candidate_name = "Alice Smith"` for both.
- **Expected:** Grouping is done by `resume_path`, not `candidate_name`. Both candidates appear in the results independently.
- **Risk if missed:** Grouping by name merges two different candidates into one, mixing their scores and excerpts.


### EC-8.3 — A resume's chunks span wildly different distances (0.1 and 0.9)
- **Input:** The skills chunk is very relevant (distance 0.1) but the education chunk is not (distance 0.9). Both pass the must-have filter.
- **Expected:** `semantic_score = mean([0.9, 0.1]) = 0.5`, matching Phase 8 of `implementation_plan.md`. `relevant_excerpts` still picks the top 2-3 chunks by best individual similarity, so the skills chunk appears first.
- **Risk if missed:** Using `max` instead of the planned mean over-rewards one highly relevant chunk and can hide that the rest of the resume is weakly related.


---


## 9. Scoring Edge Cases (§4.6, Phase 8)


### EC-9.1 — `required_skills` is empty (JD had no parseable skills)
- **Input:** `requirements["required_skills"] = []`.
- **Expected:** `skill_overlap_score = 0.5` (neutral fallback), not `0 / max(0, 1) = 0`.
- **Risk if missed:** All candidates receive `skill_overlap_score = 0`, pulling every final score down to ≤75 even for perfect semantic matches.


### EC-9.2 — Candidate `experience_years` is `0` and `min_experience_years` is `5`
- **Input:** Metadata extraction failed; `experience_years = 0`.
- **Expected:** `experience_score = 0.5` (neutral, not zero). This is different from a candidate who genuinely has zero years, which is a known limitation.
- **Risk if missed:** `experience_score = 0 / 5 = 0.0`, pulling the final score down for a candidate whose experience simply could not be parsed.


### EC-9.3 — `match_score` exceeds 100 due to floating-point arithmetic
- **Input:** `semantic_score = 1.0`, `skill_overlap_score = 1.0`, `experience_score = 1.0`. Formula gives `(0.5 + 0.3 + 0.2) * 100 = 100.0`.
- **Expected:** Score is exactly `100.0`. Clamp each component into `[0, 1]` before applying weights, then clamp the final rounded score into `[0, 100]`.
- **Risk if missed:** A score of `100.1` is invalid per the schema (`0-100` range).


### EC-9.4 — Division by zero in experience score
- **Input:** `min_experience_years = 0` (extracted from a JD like "0+ years").
- **Expected:** Guard: `if req_years > 0: experience_score = ...` else `experience_score = 0.5`. With `req_years = 0`, the neutral fallback applies.
- **Risk if missed:** `ZeroDivisionError` crashes the scoring function.


---


## 10. JSON Output Edge Cases (§4.7 / §5.4, Phase 9)


### EC-10.1 — `matched_skills` is an empty list
- **Input:** A candidate passes must-have filtering on experience alone, but no required skill from the JD appears in their metadata.
- **Expected:** `matched_skills = []`. The JSON field is present and is an empty array, not `null` or missing.
- **Risk if missed:** A consumer expecting an array receives `null` and crashes.


### EC-10.2 — `relevant_excerpts` contains fewer than 2 items
- **Input:** A candidate matched only one chunk.
- **Expected:** `relevant_excerpts = ["...one excerpt..."]`. The field is a one-element array. The JSON schema requires an array; it does not require exactly 2-3 elements.
- **Risk if missed:** Code that assumes `excerpts[1]` exists to build reasoning throws an `IndexError`.


### EC-10.3 — `reasoning` string contains special characters or newlines
- **Input:** Candidate name is `"O'Brien, Pat"` or their resume text contains quotes and backslashes.
- **Expected:** Build `reasoning` as a normal Python string and serialize the final dict with `json.dumps(result, indent=2)`. Let the JSON encoder escape quotes, newlines, and backslashes.
- **Risk if missed:** Manually concatenating JSON text can produce malformed output when reasoning contains quotes, newlines, or backslashes.


### EC-10.4 — `top_k` is set larger than the number of candidates in the corpus
- **Input:** `match_jobs(jd, top_k=10)` but only 3 resumes were ingested, producing 3 candidates.
- **Expected:** `top_matches` contains 3 entries, not 10. The list is shorter than `top_k`; no padding or error.
- **Risk if missed:** Code that iterates `for i in range(top_k)` crashes on index 3.


### EC-10.5 — `match_score` is `NaN` or `Inf`
- **Input:** A degenerate embedding returns `distance = Inf` from ChromaDB (a hardware or numerical error).
- **Expected:** `semantic_sim = 1 - Inf = -Inf`. Guard with `semantic_sim = max(0.0, min(1.0, 1 - distance))`. Final score clamped to `[0, 100]`.
- **Risk if missed:** `NaN` or `Infinity` propagates through the formula. Strict JSON serialization with `json.dumps(result, allow_nan=False)` raises `ValueError: Out of range float values are not JSON compliant`.


### EC-10.6 — `top_k` is zero or negative
- **Input:** User runs `python job_matcher.py --job-description-file docs/sample_jd.txt --top-k 0` or `--top-k -5`.
- **Expected:** CLI validation rejects non-positive `top_k` with a clear error, or `search_resumes()` normalizes it to the default `10`. Silent negative slicing should not be allowed.
- **Risk if missed:** Python slicing with a negative `top_k` returns all but the last N results, which is surprising and violates the Top-K contract.


---


## 11. Shared Contract Edge Cases (§6, Phase 4)


### EC-11.1 — `KNOWN_SKILLS` list is modified in one script only
- **Input:** A developer adds `"LangChain"` to `KNOWN_SKILLS` in `resume_rag.py` but forgets to update `skills_vocab.py`.
- **Expected:** Since both scripts import from `skills_vocab.py`, this scenario cannot occur if the shared import is enforced. The risk is only present if a developer redeclares `KNOWN_SKILLS` locally.
- **Risk if missed:** Resumes ingested after the change have `"LangChain"` in their `skills` metadata, but `extract_job_requirements()` never matches it from the JD because the JD parser's vocabulary does not include it.


### EC-11.2 — `CHROMA_COLLECTION_NAME` differs between ingestion and query
- **Input:** `resume_rag.py` was run with `CHROMA_COLLECTION_NAME=resumes_v2` but `job_matcher.py` reads `CHROMA_COLLECTION_NAME=resumes`.
- **Expected:** `get_chroma_collection()` in `job_matcher.py` opens or creates a different collection (`resumes`) that contains zero chunks. `_semantic_search()` must detect `count() == 0` and raise the same clear "run ingestion first / check collection name" error used in EC-5.1.
- **Risk if missed:** The user sees empty results with no explanation; very difficult to diagnose without inspecting `.env`.


### EC-11.3 — Embedding model changed between ingestion and query
- **Input:** Ingestion used `all-MiniLM-L6-v2` (384 dims). `.env` is changed before query to `all-mpnet-base-v2` (768 dims).
- **Expected:** ChromaDB raises a dimension mismatch error when the 768-dim JD vector is queried against a 384-dim collection. The error message should be surfaced clearly.
- **Risk if missed:** The user receives an opaque vector-dimension error and may try to debug the scoring logic instead of rebuilding the vector store with a single embedding model.


---


## 12. Cross-Cutting Edge Cases


### EC-12.1 — `chunk_id` string contains characters invalid for ChromaDB IDs
- **Input:** `resume_path = "resumes/José García.pdf"`. The MD5 hash is computed before any non-ASCII chars reach the ID, so the hash is always alphanumeric. The section label and index are also ASCII. No issue.
- **Expected:** IDs of the form `{8 hex chars}_{section_label}_{integer}` are always ASCII-safe.
- **Risk if missed:** If path stem is used instead of hash, non-ASCII filenames produce IDs that ChromaDB rejects or URL-encodes unexpectedly.


### EC-12.2 — Concurrent ingestion of two resume directories
- **Input:** Two processes both run `python resume_rag.py --resume-dir resumes_batch_1` and `--resume-dir resumes_batch_2` simultaneously.
- **Expected:** The assignment implementation should treat ingestion as a single-process operation. If concurrent ingestion is needed later, serialize writes with a lock or move ingestion to an async/job-queue design as described in `architecture.md` §13.
- **Risk if missed:** Concurrent writes can fail with locking errors or leave partially ingested batches, depending on the local ChromaDB/SQLite state.


### EC-12.3 — `chunk_text` field is accidentally included in ChromaDB metadata
- **Input:** The `metadatas` list is built without excluding `chunk_text` (the document is stored separately in `documents`).
- **Expected:** `{k: v for k, v in c.items() if k not in {"chunk_text", "embedding"}}` filters out these non-scalar fields.
- **Risk if missed:** A multi-hundred-character string in `metadatas` is not inherently invalid in ChromaDB, but it doubles storage and is retrieved as a metadata string rather than via `include=["documents"]`, causing confusion.


### EC-12.4 — Metadata key contract drifts between writer and reader
- **Input:** `resume_rag.py` stores `experience`, but `job_matcher.py` reads `experience_years`; or ingestion stores `section`, but aggregation reads `section_label`.
- **Expected:** Metadata keys must match the schema in `architecture.md` §3.6 and the Phase 3 chunk dict: `candidate_name`, `resume_path`, `section_label`, `chunk_index`, `skills`, `experience_years`, and `education`.
- **Risk if missed:** ChromaDB still returns chunks, but filters, aggregation, scoring, and reasoning silently use empty/default values.