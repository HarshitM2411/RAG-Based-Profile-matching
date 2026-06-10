# Phase-Wise Implementation Plan: Resume RAG System


Reference documents: `context.md` (implementation spec), `architecture.md` (system design)


---


## Overview


| Phase | Name | File(s) Touched | Deliverable |
|---|---|---|---|
| 0 | Project Setup | `requirements.txt`, `.env`, `.gitignore`, folder structure | Runnable Python environment |
| 1 | File Loader | `resume_rag.py` | `list_files()`, `load_resume_text()` |
| 2 | Metadata Extractor | `resume_rag.py`, `skills_vocab.py` | `KNOWN_SKILLS`, `extract_metadata()` |
| 3 | Section-Aware Chunker | `resume_rag.py` | `chunk_resume()` |
| 4 | Shared Helpers | `skills_vocab.py`, `embedder.py`, `db_utils.py` | Shared `KNOWN_SKILLS`, embeddings, Chroma collection |
| 5 | Vector Store & Ingestion | `resume_rag.py`, `db_utils.py` | `build_vector_store()`, CLI |
| 6 | JD Parser | `job_matcher.py` | `extract_job_requirements()` |
| 7 | Hybrid Search & Filtering | `job_matcher.py` | Internal chunk retrieval with hybrid + must-have filter |
| 8 | Aggregation & Scoring | `job_matcher.py` | Public `search_resumes()`, `score_candidate()`, candidate aggregator |
| 9 | JSON Output & CLI | `job_matcher.py` | `match_jobs()`, CLI, required JSON schema |
| 10 | Validation & Acceptance | — | End-to-end test against acceptance criteria |


### AI Provider Stack


| Role | Provider | Configuration |
|---|---|---|
| **Embeddings** | HuggingFace | `EMBEDDING_MODEL` — any `sentence-transformers` model (default: `sentence-transformers/all-MiniLM-L6-v2`); runs locally, no API key required |
| **LLM** | Groq | `GROQ_API_KEY` + `GROQ_MODEL` — match reasoning in Phase 8 |


Both pipelines share the same HuggingFace embedding model. Groq is used only for generative reasoning text at query time.


---


## Phase 0 — Project Setup


**Goal:** Get the environment running before writing any domain logic.


### Steps


1. Create the project folder structure:
   ```
   airTribe RAG Project/
   ├── resumes/          # drop 3-5 sample resumes here
   ├── vector_store/     # ChromaDB will create this; create the empty dir now
   ├── docs/             # place sample JD files here
   ├── resume_rag.py     # empty file
   ├── job_matcher.py    # empty file
   ├── skills_vocab.py   # shared KNOWN_SKILLS vocabulary
   ├── embedder.py       # shared HuggingFace embedding functions
   ├── llm.py            # shared Groq LLM client for reasoning
   ├── db_utils.py       # shared ChromaDB collection helper
   ├── requirements.txt
   ├── .env
   └── .gitignore
   ```


2. Write `requirements.txt`:
   ```text
   pypdf>=3.0.0
   python-docx>=1.1.0
   sentence-transformers>=2.7.0
   groq>=0.9.0
   chromadb>=0.5.0
   python-dotenv>=1.0.0
   pydantic>=2.0.0
   ```


3. Create `.env`:
   ```
   EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
   GROQ_API_KEY=gsk_...
   GROQ_MODEL=llama-3.3-70b-versatile
   CHROMA_PERSIST_DIR=vector_store
   CHROMA_COLLECTION_NAME=resumes
   ```
   `EMBEDDING_MODEL` can be any HuggingFace model compatible with `sentence-transformers` (e.g. `sentence-transformers/all-MiniLM-L6-v2`, `sentence-transformers/all-mpnet-base-v2`).


4. Run `pip install -r requirements.txt` and verify no import errors.


5. Add sample resumes (at least 3-5 `.txt`, `.pdf`, or `.docx` files) in `resumes/`.


6. Add `.gitignore` entries for local generated/runtime files:
   ```text
   .env
   vector_store/
   __pycache__/
   *.pyc
   ```


### ✅ Completion Check
- `python -c "import chromadb, sentence_transformers, groq, pypdf, docx, dotenv"` exits with no errors.
- `.env` file exists and is listed in `.gitignore`.
- `skills_vocab.py`, `embedder.py`, `llm.py`, and `db_utils.py` exist as shared helper modules.


---


## Phase 1 — File Loader


**File:** `resume_rag.py`  
**Goal:** Build the file discovery and text extraction layer. This corresponds to §3.2 of `architecture.md`.


### Steps


1. At the top of `resume_rag.py`, import `pathlib`, `pypdf`, `docx`, and `load_dotenv`.


2. Implement `list_files(directory, extensions)`:
   - Use `pathlib.Path(directory).rglob("*")` to walk the tree.
   - Filter by extension (case-insensitive).
   - Return a list of absolute path strings.
   - If the directory does not exist, raise a `FileNotFoundError` with a helpful message.


3. Implement `load_resume_text(file_path)`:
   - `.txt` → `open(file_path, encoding="utf-8").read()`
   - `.pdf` → `pypdf.PdfReader`, concatenate `page.extract_text()` for all pages
   - `.docx` → `python-docx Document`, concatenate `para.text` for all paragraphs
   - Unsupported extension → log a warning, return `""`
   - Corrupt/empty file → catch exception, log warning, return `""`


4. **Milestone 1 check:** If Milestone 1 utilities exist elsewhere in the workspace, import and call them instead of re-implementing. Wrap them so the function signatures match what Phase 5 expects.


5. Keep file discovery separate from text extraction. The File Loader returns paths; `build_vector_store()` is the orchestrator that calls `load_resume_text()`, metadata extraction, chunking, embedding, and ChromaDB upsert.


### Data Contract Out
```python
list_files(directory: str, extensions: list[str]) -> list[str]  # file paths only
load_resume_text(file_path: str) -> str   # "" on failure
```


### ✅ Completion Check
```python
paths = list_files("resumes", [".pdf", ".docx", ".txt"])
assert len(paths) >= 3
text = load_resume_text(paths[0])
assert len(text) > 50
```


---


## Phase 2 — Metadata Extractor


**File:** `resume_rag.py`  
**Goal:** Extract candidate-level metadata from raw resume text. Corresponds to §3.4 of `architecture.md`.


### Steps


1. Define `KNOWN_SKILLS` in `skills_vocab.py` and import it into `resume_rag.py` and `job_matcher.py`. Do not keep separate copies.
   ```python
   KNOWN_SKILLS = [
       "Python", "SQL", "Java", "JavaScript", "TypeScript", "C++", "Go", "Rust",
       "Machine Learning", "Deep Learning", "NLP", "Computer Vision",
       "AWS", "Azure", "GCP", "Docker", "Kubernetes",
       "TensorFlow", "PyTorch", "scikit-learn", "pandas", "NumPy",
       "FastAPI", "Flask", "Django", "React", "Node.js",
       "PostgreSQL", "MongoDB", "Redis", "Elasticsearch",
       "Git", "Linux", "Spark", "Kafka", "Airflow",
   ]
   ```


2. Define `SECTION_PATTERNS` near the metadata/chunking helpers, or place it in a shared `text_patterns.py` module if both metadata extraction and chunking use it. Metadata extraction needs these patterns before Phase 3 because skills and education extraction depend on locating sections.


3. Implement name extraction:
   - Strip the first non-empty line of the resume text.
   - If the line looks like a name (2-4 words, no digits), use it.
   - Fallback: derive from filename stem (e.g. `john_doe.pdf` → `"John Doe"`).


4. Implement skills extraction:
   - Locate the skills section using the regex from §3.3 (`SECTION_PATTERNS["skills"]`).
   - If no skills section is detected, scan the full resume text as a fallback.
   - Find case-insensitive matches against `KNOWN_SKILLS`, preserving canonical casing from `skills_vocab.py`.
   - Match multi-word skills such as `Machine Learning` with word-boundary regex, not naive token splitting.
   - Return as a **comma-separated string** `"Python,SQL,AWS"` (ChromaDB metadata cannot store lists).


5. Implement experience years extraction:
   - Try regex patterns: `(\d+)\+?\s+years?`, `(\d+)\s+yrs?`.
   - Optionally map common word numbers such as `one`, `two`, `three`, `five`, `ten` to integers.
   - If nothing found, scan for date ranges (e.g. `2018-2023`, `2018 to present`) and infer years conservatively.
   - Default to `0` if no evidence found.


6. Implement education extraction:
   - Locate the education section using `SECTION_PATTERNS["education"]`.
   - Return the first non-empty paragraph of that section as a string.
   - Default to `""` if section not found.


7. Store `resume_path` consistently. Prefer a workspace-relative path such as `resumes/john_doe.pdf`, because it is stable across machines and works well in JSON output.


8. Assemble `extract_metadata(text, resume_path) -> dict`:
   ```python
   {
       "candidate_name"  : str,
       "skills"          : str,   # comma-separated
       "experience_years": int,
       "education"       : str,
       "resume_path"     : str,
   }
   ```


### ✅ Completion Check
```python
meta = extract_metadata(text, "resumes/sample.pdf")
assert "candidate_name" in meta
assert isinstance(meta["skills"], str)         # not a list
assert isinstance(meta["experience_years"], int)
assert isinstance(meta["resume_path"], str)
```


---


## Phase 3 — Section-Aware Chunker


**File:** `resume_rag.py`  
**Goal:** Split resume text into section-labelled chunks with overlap. Corresponds to §3.3 of `architecture.md`.


### Steps


1. Define `SECTION_PATTERNS` dictionary (use the regex map from §3.3 of architecture.md).


2. Write a `_detect_sections(text)` helper:
   - Scan each line for a match against any `SECTION_PATTERNS` entry (case-insensitive).
   - Return a list of `(line_number, section_label)` boundary tuples.
   - If no headings are detected, treat the entire resume as one `"other"` section.


3. Write `_split_into_sections(text)`:
   - Use the boundary list to slice `text` into `{section_label: section_text}` blocks.
   - Lines before the first detected heading go into `"other"`.


4. Write `_subchunk(section_text, section_label, metadata, start_index)`:
   - For `experience`, split on blank-line job blocks first so each role becomes its own chunk when possible.
   - If a unit is still `> MAX_CHUNK_CHARS` (900), split using a sliding window with `CHUNK_OVERLAP` (100 chars) overlap.
   - Skip short pre-heading contact blocks in structured resumes; keep full-text `"other"` chunks when no headings exist.
   - Pad short but meaningful sections such as `education` so they still meet `MIN_CHUNK_CHARS` (80).
   - Discard sliding-window fragments shorter than `MIN_CHUNK_CHARS` (80 chars).


5. Implement `chunk_resume(text, metadata) -> list[dict]`:
   - Call `_split_into_sections(text)` to get labelled blocks.
   - For each section, call `_subchunk(...)`.
   - Assign each chunk a unique `chunk_id`:
     ```python
     import hashlib
       path_hash = hashlib.md5(metadata["resume_path"].encode("utf-8")).hexdigest()[:8]
     chunk_id = f"{path_hash}_{section_label}_{chunk_index}"
     ```
    - Hash the same normalized path stored in metadata so IDs stay stable across re-runs.
   - Attach all metadata fields to each chunk dict.
   - Return the flat list of all chunk dicts.


6. Each chunk dict must contain:
   ```python
   {
       "chunk_id"        : str,
       "resume_path"     : str,
       "candidate_name"  : str,
       "section_label"   : str,
       "chunk_text"      : str,
       "chunk_index"     : int,
       "skills"          : str,
       "experience_years": int,
       "education"       : str,
   }
   ```


### ✅ Completion Check
```python
chunks = chunk_resume(text, meta)
assert all("section_label" in c for c in chunks)
assert all(len(c["chunk_text"]) >= 80 for c in chunks)
assert len({c["chunk_id"] for c in chunks}) == len(chunks)  # no ID collisions
```


---


## Phase 4 — Shared Helpers


**Files:** `skills_vocab.py`, `embedder.py`, `llm.py`, `db_utils.py`  
**Goal:** Provide shared vocabulary, HuggingFace embeddings, Groq LLM access, and ChromaDB access without making `resume_rag.py` and `job_matcher.py` import each other. Corresponds to §3.5, §3.5.1, §3.7, and §6 of `architecture.md`.


### Steps


1. Create `skills_vocab.py` with the canonical `KNOWN_SKILLS` list from Phase 2. Both pipelines import this same list.


2. Create `embedder.py` with:
   ```python
   import os
   from dotenv import load_dotenv
   load_dotenv()


   MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
   ```


3. Implement `get_embedding_model()`:
   - Instantiate `sentence_transformers.SentenceTransformer(MODEL)`.
   - Cache the model in a module-level variable so it is loaded once per process.
   - On first run, the model weights are downloaded from the HuggingFace Hub (one-time, requires internet).


4. Implement `embed_texts(texts) -> list[list[float]]`:
   - Call `model.encode(texts, convert_to_numpy=True)`.
   - Return `vectors.tolist()`.
   - `MODEL` can be any sentence-transformers model from the HuggingFace Hub.


5. Create `llm.py` with:
   ```python
   import os
   from dotenv import load_dotenv
   load_dotenv()


   GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
   ```


6. Implement `get_groq_client()`:
   - Instantiate `groq.Groq(api_key=os.getenv("GROQ_API_KEY"))`.
   - Raise `ValueError` if `GROQ_API_KEY` is missing.
   - Cache the client in a module-level variable.


7. Implement `generate_reasoning(prompt_context: dict) -> str`:
   - Build a concise prompt from `prompt_context` (matched skills, score, experience, excerpts).
   - Call Groq chat completions with `GROQ_MODEL`.
   - Return the generated reasoning string.
   - Used by `job_matcher.py` in Phase 8; ingestion does not call this.


8. Create `db_utils.py` with `get_chroma_collection()`:
   ```python
   import os
   import chromadb
   from dotenv import load_dotenv


   load_dotenv()


   def get_chroma_collection():
       client = chromadb.PersistentClient(path=os.getenv("CHROMA_PERSIST_DIR", "vector_store"))
       return client.get_or_create_collection(
           name=os.getenv("CHROMA_COLLECTION_NAME", "resumes"),
           metadata={"hnsw:space": "cosine"},
       )
   ```


9. Both `resume_rag.py` and `job_matcher.py` import from the shared helpers:
   ```python
   from embedder import embed_texts, get_embedding_model
   from db_utils import get_chroma_collection
   from skills_vocab import KNOWN_SKILLS
   ```
   `job_matcher.py` also imports `generate_reasoning` from `llm.py` in Phase 8.


### ✅ Completion Check
```python
from embedder import embed_texts
from db_utils import get_chroma_collection
vecs = embed_texts(["Hello world", "Python developer"])
assert len(vecs) == 2
assert len(vecs[0]) > 0  # dimension depends on EMBEDDING_MODEL (e.g. 384 for all-MiniLM-L6-v2)
assert get_chroma_collection().name == "resumes"
```


---


## Phase 5 — Vector Store & Ingestion Orchestrator


**Files:** `resume_rag.py`, `db_utils.py`  
**Goal:** Persist all chunks with embeddings to ChromaDB and expose a CLI entry point. Corresponds to §3.1 and §3.6 of `architecture.md`.


### Steps


1. Import the shared helpers:
   ```python
   from embedder import embed_texts
   from db_utils import get_chroma_collection
   ```


2. Implement `build_vector_store(resume_dir)`:
   ```python
   def build_vector_store(resume_dir: str) -> None:
       collection = get_chroma_collection()
       file_paths = list_files(resume_dir, [".pdf", ".docx", ".txt"])
       if not file_paths:
           raise ValueError("No supported resume files found. Add PDF, DOCX, or TXT files to the resume directory.")


       for file_path in file_paths:
           raw_text = load_resume_text(file_path)
           if not raw_text.strip():
               print(f"Warning: skipping empty or unreadable resume: {file_path}")
               continue


           metadata = extract_metadata(raw_text, file_path)
           chunks = chunk_resume(raw_text, metadata)
           if not chunks:
               print(f"Warning: no useful chunks produced for: {file_path}")
               continue


           vectors = embed_texts([c["chunk_text"] for c in chunks])
           collection.upsert(
               ids=[c["chunk_id"] for c in chunks],
               embeddings=vectors,
               documents=[c["chunk_text"] for c in chunks],
               metadatas=[
                   {k: v for k, v in c.items() if k not in {"chunk_text", "embedding"}}
                   for c in chunks
               ],
           )
   ```
   Use `upsert()` — never `add()` — so the command is safe to re-run. Make sure every metadata value is a ChromaDB scalar (`str`, `int`, `float`, or `bool`). Keep `skills` as a comma-separated string.


3. Add CLI entry point at the bottom of `resume_rag.py`:
   ```python
   if __name__ == "__main__":
       import argparse
       parser = argparse.ArgumentParser()
       parser.add_argument("--resume-dir",  default="resumes")
       parser.add_argument("--persist-dir", default=None)
       args = parser.parse_args()
       if args.persist_dir:
           os.environ["CHROMA_PERSIST_DIR"] = args.persist_dir
       build_vector_store(args.resume_dir)
   ```


### ✅ Completion Check
```bash
python resume_rag.py --resume-dir resumes
```
Then verify in Python:
```python
col = get_chroma_collection()
assert col.count() > 0
result = col.get(limit=1, include=["metadatas", "documents", "embeddings"])
assert result["metadatas"][0]["candidate_name"] != ""
assert len(result["ids"]) == 1
```


---


## Phase 6 — JD Parser


**File:** `job_matcher.py`  
**Goal:** Extract structured requirements from a raw job description. Corresponds to §4.2 of `architecture.md`.


### Steps


1. Import `KNOWN_SKILLS` from `skills_vocab.py` — **same list used in Phase 2**. Do not redeclare it.


2. Implement `extract_job_requirements(job_description) -> dict`:
   - `required_skills`: tokenise the JD and find case-insensitive matches against `KNOWN_SKILLS`. Return as a list.
   - `min_experience_years`: apply regex patterns such as `(\d+)\+?\s*years?`, `at least (\d+) years`, and `minimum (\d+) years`. Return the highest integer found, or `None`.
   - `jd_keywords`: lowercase the JD, remove stopwords (`{"and", "or", "the", "with", "for", "a", "an", "in", "of", "to", "is", "are", "be", "that", "at", "on"}`), return the remaining tokens.


3. Output shape:
   ```python
   {
       "required_skills"     : ["Python", "SQL", "AWS"],
       "min_experience_years": 5,
       "jd_keywords"         : ["machine", "learning", "pipeline", ...]
   }
   ```


### ✅ Completion Check
```python
sample_jd = "Looking for a Python ML engineer with 5+ years, SQL, and AWS experience."
reqs = extract_job_requirements(sample_jd)
assert "Python" in reqs["required_skills"]
assert reqs["min_experience_years"] == 5
```


---


## Phase 7 — Hybrid Search and Filtering


**File:** `job_matcher.py`  
**Goal:** Query ChromaDB, apply chunk-level hybrid scoring, and apply must-have filtering. Corresponds to §4.1, §4.3, §4.4 of `architecture.md`.


### Steps


1. Implement `_semantic_search(jd_text, n_results=50) -> list[dict]`:
   - Embed the JD using `embed_texts([jd_text])`.
   - Query ChromaDB: `collection.query(query_embeddings=[jd_vec], n_results=n_results, include=["documents", "distances", "metadatas"])`.
   - ChromaDB returns nested lists (`results["ids"][0]`, `results["documents"][0]`, etc.). Flatten those into a list of chunk dicts, each enriched with `id`, `distance`, `document`, and `metadata`.
   - If the collection does not exist or `count() == 0`, raise a clear error telling the user to run `resume_rag.py` first.


2. Implement `_hybrid_score(chunk, jd_keywords, required_skills) -> float`:
   ```python
   # cosine distance -> similarity
   semantic_sim = 1 - chunk["distance"]


   # keyword hit ratio: prefer required skill hits, fall back to JD keyword hits
   chunk_text_lower = chunk["document"].lower()
   if required_skills:
       hits = sum(1 for s in required_skills if s.lower() in chunk_text_lower)
       keyword_hit_ratio = hits / len(required_skills)
   else:
       hits = sum(1 for kw in jd_keywords if kw.lower() in chunk_text_lower)
       keyword_hit_ratio = hits / max(len(jd_keywords), 1)


   return 0.7 * semantic_sim + 0.3 * keyword_hit_ratio
   ```
   > This is the **chunk-level** intermediate score. It is used for pre-filtering only — not the final 0-100 candidate score.


3. Implement `_must_have_filter(chunk, requirements) -> tuple[bool, float, str]`:
   - Parse candidate skills from `chunk["metadata"]["skills"]` (split by comma).
   - If a required skill is clearly missing, return `(False, 0.3, "missing required skill: X")` or keep the chunk with a heavy penalty if you choose a penalty-based mode.
   - If `experience_years` is clearly below `min_experience_years`, return `(False, 0.5, "below required experience")`.
   - If metadata is unavailable (`skills == ""` or `experience_years == 0`), do not automatically exclude. Return `(True, 0.5, "metadata unavailable")` so reasoning can mention uncertainty.
   - Return `(True, 1.0, "passed")` when no hard constraint fails.


4. Implement `_search_resume_chunks(job_description, requirements, n_results=50) -> list[dict]`:
   - Use the already-extracted `requirements` passed into this helper.
   - Call `_semantic_search(job_description, n_results=50)`.
   - For each chunk, compute `_hybrid_score(...)` and check `_must_have_filter(...)`.
   - Drop chunks that fail hard constraints, or multiply the hybrid score by the returned penalty if using penalty mode.
   - Store `hybrid_score`, `passed_filter`, `filter_penalty`, and `filter_reason` on each returned chunk.
   - Sort remaining chunks by hybrid score descending.
   - Return the sorted list (still chunk-level at this point — aggregation is Phase 8).


5. Keep this function internal. The public `search_resumes(job_description, top_k=10)` from the architecture should return candidate-level matches after aggregation/scoring, so it is completed in Phase 8.


### ✅ Completion Check
```python
reqs = extract_job_requirements("Python ML engineer with 5+ years, SQL, AWS")
chunks = _search_resume_chunks("Python ML engineer with 5+ years, SQL, AWS", reqs)
assert all("hybrid_score" in c for c in chunks)
assert all("filter_reason" in c for c in chunks)
```


---


## Phase 8 — Candidate Aggregation and Scoring


**File:** `job_matcher.py`  
**Goal:** Collapse chunk-level results to candidate-level results, then score each candidate 0-100. Corresponds to §4.5 and §4.6 of `architecture.md`.


### Steps


1. Implement `_aggregate_by_candidate(chunks, requirements) -> list[dict]`.


   Group chunks by `chunk["metadata"]["resume_path"]`. For each candidate group, produce one candidate dict with these fields:


   | Field | Source / Calculation |
   |---|---|
   | `semantic_score` | Mean of `(1 - chunk["distance"])` across matched chunks, assuming cosine distance. |
   | `matched_skills` | Intersection of candidate skills from metadata with `requirements["required_skills"]`. |
   | `relevant_excerpts` | Text of the top 2-3 chunks, sorted by `1 - distance` descending. |
   | `matched_sections` | Sorted unique `section_label` values across matched chunks. |
   | `candidate_name`, `resume_path`, `experience_years`, `education` | Candidate metadata copied from any chunk in the group. |
   | `filter_reasons` | Unique non-`"passed"` reasons from the candidate's matched chunks. |


2. Implement `score_candidate(candidate, requirements) -> float`:
   ```python
   def score_candidate(candidate: dict, requirements: dict) -> float:
       semantic_score = candidate["semantic_score"]  # already [0, 1]


       required = requirements["required_skills"]
       matched = candidate["matched_skills"]
       skill_overlap_score = len(matched) / max(len(required), 1)
       if not required:
           skill_overlap_score = 0.5  # neutral when no required skills were extracted


       req_years = requirements.get("min_experience_years") or 0
       cand_years = candidate.get("experience_years", 0)
       if req_years > 0:
           experience_score = 0.5 if cand_years == 0 else min(cand_years / req_years, 1.0)
       else:
           experience_score = 0.5  # neutral when no requirement is stated


       final_score = (
           semantic_score * 0.50 +
           skill_overlap_score * 0.30 +
           experience_score * 0.20
       ) * 100


       return round(final_score, 1)
   ```


3. Implement `_generate_reasoning(candidate, requirements, score) -> str`:
   - Primary path: call `generate_reasoning()` from `llm.py` with a `prompt_context` dict containing `matched_skills`, `matched_sections`, `experience_years`, `min_experience_years`, `match_score`, `relevant_excerpts`, and `filter_reasons`.
   - Groq generates a concise human-readable explanation from that context.
   - Fallback (if Groq fails): template-based reasoning with skill, section, experience, constraint, and score-band lines (`"Strong"` ≥ 75, `"Partial"` ≥ 50, `"Weak"` < 50).


4. Implement public `search_resumes(job_description, top_k=10) -> list[dict]`:
   ```python
   def search_resumes(job_description: str, top_k: int = 10) -> list[dict]:
       requirements = extract_job_requirements(job_description)
       chunks = _search_resume_chunks(job_description, requirements, n_results=max(top_k * 5, 50))
       candidates = _aggregate_by_candidate(chunks, requirements)


       for candidate in candidates:
           candidate["match_score"] = score_candidate(candidate, requirements)
           candidate["reasoning"] = _generate_reasoning(candidate, requirements, candidate["match_score"])


       return sorted(candidates, key=lambda c: c["match_score"], reverse=True)[:top_k]
   ```
   This satisfies the architecture contract that `search_resumes()` returns candidate-level matches, not raw chunks.


### ✅ Completion Check
```python
reqs = extract_job_requirements("Python ML engineer, 5+ years, SQL, AWS")
# assume chunks from previous phase
candidates = _aggregate_by_candidate(chunks, reqs)
for c in candidates:
    c["match_score"] = score_candidate(c, reqs)
assert all(0 <= c["match_score"] <= 100 for c in candidates)
matches = search_resumes("Python ML engineer, 5+ years, SQL, AWS")
assert len(matches) <= 10
assert all("resume_path" in m and "match_score" in m for m in matches)
```


---


## Phase 9 — JSON Output and CLI


**File:** `job_matcher.py`  
**Goal:** Assemble the final required JSON structure and expose a CLI. Corresponds to §4.7, §5.4, and §6.2 of `architecture.md`.


### Steps


1. Implement `match_jobs(job_description, top_k=10) -> dict`:
   ```python
   def match_jobs(job_description: str, top_k: int = 10) -> dict:
       top = search_resumes(job_description, top_k=top_k)


       return {
           "job_description": job_description,
           "top_matches": [
               {
                   "candidate_name"  : c["candidate_name"],
                   "resume_path"     : c["resume_path"],
                   "match_score"     : c["match_score"],
                   "matched_skills"  : c["matched_skills"],
                   "relevant_excerpts": c["relevant_excerpts"],
                   "reasoning"       : c["reasoning"],
               }
               for c in top
           ]
       }
   ```


2. Add CLI entry point at the bottom of `job_matcher.py`:
   ```python
   if __name__ == "__main__":
       import argparse, json
       parser = argparse.ArgumentParser()
       parser.add_argument("--job-description-file", required=True)
       parser.add_argument("--top-k", type=int, default=10)
       args = parser.parse_args()
       with open(args.job_description_file, encoding="utf-8") as f:
           jd_text = f.read()
       result = match_jobs(jd_text, top_k=args.top_k)
       print(json.dumps(result, indent=2))
   ```


3. Verify the output JSON has all required fields:


   | Field | Required | Type |
   |---|---|---|
   | `job_description` | Yes | string |
   | `top_matches` | Yes | array |
   | `top_matches[].candidate_name` | Yes | string |
   | `top_matches[].resume_path` | Yes | string |
   | `top_matches[].match_score` | Yes | float 0-100 |
   | `top_matches[].matched_skills` | Yes | array of strings |
   | `top_matches[].experience_years` | Yes | integer or `null` when unavailable |
   | `top_matches[].relevant_excerpts` | Yes | array of strings |
   | `top_matches[].reasoning` | Yes | string |
   | `top_matches[].matched_sections` | Yes | array of strings (UI enrichment) |


### ✅ Completion Check
```bash
python job_matcher.py --job-description-file docs/sample_jd.txt --top-k 10
```
Output should be valid JSON matching the schema above. Validate:
```python
import json
from job_matcher import match_jobs
with open("docs/sample_jd.txt", encoding="utf-8") as f:
   result = match_jobs(f.read(), top_k=10)
assert "job_description" in result
assert len(result["top_matches"]) <= 10
assert all("reasoning" in m for m in result["top_matches"])
```


---


## Phase 10 — Validation and Acceptance


**Goal:** Run the end-to-end flow against the acceptance criteria from `context.md` and `architecture.md` §11.


### End-to-End Test Script (manual)


```bash
# Step 1: Build the vector store
python resume_rag.py --resume-dir resumes --persist-dir vector_store


# Step 2: Run a job match
python job_matcher.py --job-description-file docs/sample_jd.txt --top-k 10
```


### Acceptance Checklist


| # | Criterion | How to Verify |
|---|---|---|
| 1 | Resumes are loaded from the file system | `list_files("resumes", [".pdf",".docx",".txt"])` returns ≥ 3 paths |
| 2 | Resumes are chunked section-by-section | Chunks have `section_label` in `{"experience","skills","education","projects",...}` |
| 3 | Each chunk has an embedding | `collection.get(include=["embeddings"])["embeddings"]` — no `None` values |
| 4 | Chunks and metadata are in ChromaDB | `col.count() > 0`; inspect metadata keys |
| 5 | Metadata includes name, skills, experience, education, path | Verify all 5 keys are present and non-empty in at least one record |
| 6 | JD is embedded with the same HuggingFace model | Confirmed by single `get_embedding_model()` / `embed_texts()` call path |
| 7 | Match reasoning uses Groq LLM | `reasoning` field is non-empty and generated via `generate_reasoning()` |
| 7 | Top-K defaults to 10 | `match_jobs(jd)` returns `len(top_matches) <= 10` with no `--top-k` flag |
| 8 | Hybrid search is active | Code calls both semantic query and keyword hit count |
| 9 | Scores are 0-100 | All `match_score` values in `[0, 100]` |
| 10 | Must-have filtering works | Inject a JD requiring `"Fortran"` — no resume should rank highly |
| 11 | Output JSON matches required schema | All required fields present in every `top_matches` entry (incl. `experience_years`, `matched_sections`) |
| 12 | Empty result is valid JSON | Pass a nonsense JD → `{"job_description": ..., "top_matches": []}` |
| 13 | Re-running ingestion does not crash | Run `resume_rag.py` twice → no duplicate-ID error |
| 14 | Query before ingestion fails clearly | Delete/rename `vector_store/`, run matcher, verify message says to run `resume_rag.py` first |
| 15 | Shared skill vocabulary is single-source | `resume_rag.py` and `job_matcher.py` both import `KNOWN_SKILLS` from `skills_vocab.py` |


### Sample Validation Scenario (from `context.md`)


```
JD: "Looking for a Python Machine Learning Engineer with 5+ years of experience, SQL, and AWS."


Expected:
- Candidates with Python, ML, SQL, AWS, and 5+ years rank in the top 3.
- Candidates without Python should not appear in top 3 even if semantically similar.
- Reasoning for #1 should mention Python, ML, and the experience fit.
```


---


## Dependency Map Between Phases


```
Phase 0 (setup)
    └── Phase 1 (file loader)
            └── Phase 2 (metadata extractor)
            │       └── Phase 5 (vector store) ←──────────────────┐
            └── Phase 3 (chunker)              ←─────────────────┐ │
                                                                  │ │
Phase 4 (embedder) ─────────────────────────────────────────────>┘ │
                    └──────────────────────────────────────────────>┘
                                                                     │
Phase 5 (ingestion complete) ────────────────────────────────────────┘
    └── Phase 6 (JD parser)
            └── Phase 7 (hybrid search + filter)
                    └── Phase 8 (aggregation + scoring)
                            └── Phase 9 (JSON output + CLI)
                                    └── Phase 10 (validation)
```


Phases 1-3 can be developed in parallel after Phase 0, but Phase 2 and Phase 3 should share the same section-pattern constants. Phase 4 should be completed before Phase 5 and Phase 6, because both pipelines depend on shared embeddings, Chroma access, and `KNOWN_SKILLS`. Phase 5 must complete before Phases 7-9 can be tested end to end, because the vector store must contain resume chunks before queries run.