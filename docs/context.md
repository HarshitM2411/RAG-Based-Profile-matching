# Project Context: Resume RAG System and Job Matching Engine


## Purpose


This project builds a resume matching system using Retrieval-Augmented Generation (RAG) concepts. The system must ingest resumes, split them into meaningful chunks, create embeddings, store them in a vector database, and later retrieve and rank the best candidates for a given job description.


The assignment is divided into two equal parts:


| Part | File | Weight | Main Goal |
|---|---|---:|---|
| Part A | `resume_rag.py` | 50% | Build the resume ingestion, chunking, embedding, metadata extraction, and vector storage pipeline. |
| Part B | `job_matcher.py` | 50% | Build the job-description search, hybrid retrieval, scoring, filtering, and JSON output pipeline. |


## Learning Objectives From The Brief


The project should demonstrate that the implementation can:


- Chunk documents intelligently instead of splitting text randomly.
- Generate embeddings for resume chunks and job descriptions.
- Store and retrieve vectors from a vector database.
- Build a retrieval pipeline that returns useful candidate matches.
- Explain semantic search and combine it with keyword-based matching for critical skills.


## Recommended Technical Direction


For a local assignment, the simplest complete stack is:


| Concern | Recommended Choice | Reason |
|---|---|---|
| Vector database | ChromaDB | Easy local persistence and no cloud setup required. |
| Embeddings | HuggingFace `sentence-transformers/all-MiniLM-L6-v2` or OpenAI `text-embedding-3-small` | HuggingFace is free/local; OpenAI is stronger if API access is available. |
| PDF parsing | `pypdf` | Lightweight resume text extraction. |
| DOCX parsing | `python-docx` | Needed if resumes are Word documents. |
| Env management | `python-dotenv` | Keeps API keys/config out of code. |
| Validation | `pydantic` or dataclasses | Keeps output structure consistent. |


The embedding model must be shared by both files. If `resume_rag.py` embeds resumes with one model and `job_matcher.py` embeds job descriptions with another, similarity search will not work correctly.


## Suggested Project Structure


```text
airTribe RAG Project/
├── problemStatement.md
├── context.md
├── docs/
├── resumes/                     # Raw resume files: PDF, DOCX, TXT
├── vector_store/                # Persistent ChromaDB files
├── resume_rag.py                # Part A: ingestion and vector storage
├── job_matcher.py               # Part B: retrieval, ranking, scoring
├── requirements.txt             # Python dependencies
├── .env                         # Local secrets/config, not committed
└── README.md                    # Optional usage documentation
```


## Part A: `resume_rag.py`


### Responsibility


`resume_rag.py` owns the full resume ingestion pipeline:


1. Load resumes from the local file system.
2. Extract raw text from each resume.
3. Detect candidate-level metadata.
4. Split resumes into meaningful chunks while preserving sections.
5. Generate embeddings for each chunk.
6. Store chunks, embeddings, source paths, section labels, and metadata in a vector database.


### Expected Inputs


- A folder containing resumes, for example `resumes/`.
- Supported formats should include at least `.txt`; preferably also `.pdf` and `.docx`.
- Optional configuration values:
  - Embedding provider/model.
  - ChromaDB persistence directory.
  - Collection name.


### Expected Outputs


- A persistent vector database collection containing all resume chunks.
- Each vector record should include enough metadata for filtering, ranking, and explaining matches later.


### Milestone 1 File System Tools


The problem statement explicitly says: *"Load resumes using file system tools from Milestone 1"*.


Milestone 1 refers to a prior assignment that built basic file I/O utilities. If those utilities exist in the workspace, `resume_rag.py` should import and reuse them rather than duplicate the code.


Typical Milestone 1 file system functions that may be available:


```python
def list_files(directory: str, extensions: list[str]) -> list[str]:
    """Return all file paths in a directory matching the given extensions."""


def read_file(file_path: str) -> str:
    """Read and return the raw text content of a file."""
```


If Milestone 1 utilities are not present, implement equivalent functions directly inside `resume_rag.py` using `pathlib.Path` or `os.walk`. The expectation from the grader is that file loading is modular and not inline logic scattered across the script.


### Resume Loading Requirements


The loader should batch-load files from a resume directory.


Supported extraction behavior:


| File Type | Extraction Strategy |
|---|---|
| `.txt` | Read text directly. |
| `.pdf` | Use `pypdf.PdfReader` and concatenate page text. |
| `.docx` | Use `python-docx` and concatenate paragraph text. |


Invalid, empty, corrupted, or unsupported files should not crash the full ingestion run. They should be skipped with a clear warning.


### Intelligent Chunking Requirements


The assignment explicitly asks to preserve resume sections such as Education and Experience. Chunking should therefore be section-aware.


Recommended section labels:


- `summary`
- `skills`
- `experience`
- `education`
- `projects`
- `certifications`
- `achievements`
- `other`


Recommended approach:


1. Normalize text spacing and line breaks.
2. Detect section headings using case-insensitive regex.
3. Split the document at detected headings.
4. Keep each section label attached to the text extracted from that section.
5. If a section is too long, split it into overlapping subchunks.


Suggested chunk settings:


| Setting | Suggested Value |
|---|---:|
| Target chunk size | 500-900 characters or 150-300 words |
| Chunk overlap | 50-150 characters or 25-50 words |
| Minimum useful chunk size | 80-100 characters |


Every chunk should preserve this information:


```json
{
  "chunk_id": "unique-id",
  "resume_path": "resumes/john_doe.pdf",
  "candidate_name": "John Doe",
  "section_label": "experience",
  "chunk_text": "Built ML pipelines using Python and AWS...",
  "chunk_index": 3
}
```


### Metadata Extraction Requirements


The brief requires extraction of:


- Name
- Skills
- Experience years
- Education


Recommended metadata schema:


```json
{
  "candidate_name": "John Doe",
  "skills": ["Python", "Machine Learning", "SQL"],
  "experience_years": 5,
  "education": "B.Tech Computer Science",
  "resume_path": "resumes/john_doe.pdf"
}
```


Practical extraction rules:


| Field | Suggested Extraction Method |
|---|---|
| `candidate_name` | First non-empty line, filename fallback, or simple name regex. |
| `skills` | Parse `Skills` section and match against a known skill vocabulary. |
| `experience_years` | Regex patterns like `5 years`, `5+ years`, `five years`, or infer from date ranges if needed. |
| `education` | Extract text from the Education section. |
| `resume_path` | Store the relative or absolute path consistently. |


Important ChromaDB note: Chroma metadata values must generally be simple scalar types. If storing a list such as `skills`, store it as a comma-separated string like `Python,SQL` or as a JSON string, then parse it back in `job_matcher.py`.


### Embedding Requirements


The implementation can use OpenAI, Cohere, or HuggingFace. It should expose the selected provider clearly so both ingestion and search use the same embedding function.


Recommended helper functions/classes:


```python
def get_embedding_model():
    """Return the configured embedding model used by ingestion and search."""



def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of text chunks."""
```


### Vector Database Requirements


For ChromaDB, each stored document should include:


- `ids`: unique chunk IDs.
- `documents`: chunk text.
- `embeddings`: vector embeddings if using manual embedding.
- `metadatas`: candidate and chunk metadata.


Recommended metadata keys:


```json
{
  "candidate_name": "John Doe",
  "resume_path": "resumes/john_doe.pdf",
  "section_label": "experience",
  "chunk_index": 3,
  "skills": "Python,Machine Learning,SQL",
  "experience_years": 5,
  "education": "B.Tech Computer Science"
}
```


### Suggested `resume_rag.py` Interface


The file should be usable both as a module and from the command line.


Suggested module-level functions:


```python
def load_resume_text(file_path: str) -> str:
    pass



def extract_metadata(text: str, resume_path: str) -> dict:
    pass



def chunk_resume(text: str, metadata: dict) -> list[dict]:
    pass



def build_vector_store(resume_dir: str) -> None:
    pass
```


Suggested CLI usage:


```bash
python resume_rag.py --resume-dir resumes --persist-dir vector_store
```


## Part B: `job_matcher.py`


### Responsibility


`job_matcher.py` owns the job matching pipeline:


1. Accept a job description as input.
2. Extract must-have requirements and skills from the job description.
3. Convert the job description into an embedding using the same model as ingestion.
4. Query the vector store for top-K similar resume chunks. Default K must be 10.
5. Combine semantic results with keyword/skill matching.
6. Apply hard filters such as required skills or minimum experience.
7. Aggregate chunk-level results to candidate-level results.
8. Score candidates on a 0-100 scale.
9. Return the required JSON output.


### Expected Inputs


- Raw job description text.
- Optional `top_k`, defaulting to `10`.
- Optional must-have requirements, either user-provided or extracted from the JD.


Examples of requirements to extract:


- Required skills: `Python`, `Machine Learning`, `SQL`, `AWS`.
- Minimum experience: `5+ years`, `at least 3 years`, `minimum 2 years`.
- Education/certification keywords where applicable.


### Semantic Search Flow


1. Load the same vector database collection built by `resume_rag.py`.
2. Embed the job description.
3. Query the vector store for at least top 10 relevant chunks.
4. Request documents, distances/scores, and metadata from the vector DB.
5. Group chunks by candidate identity or resume path.


Top-K in the assignment refers to `K=10`. A strong implementation can retrieve more than 10 chunks internally and then return the top 10 candidates after aggregation.


### Hybrid Search Requirements


The brief explicitly requires hybrid search: semantic + keyword for critical skills.


Recommended strategy:


- Use semantic search to find conceptually similar resume chunks.
- Use keyword matching to identify exact skill overlap.
- Use metadata filters or post-filtering for must-have requirements.
- Penalize or exclude candidates missing critical skills.


Suggested skill extraction:


```python
KNOWN_SKILLS = {
    "python", "java", "sql", "machine learning", "deep learning",
    "nlp", "aws", "azure", "gcp", "docker", "kubernetes",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch"
}
```


### Must-Have Filtering


Must-have requirements are hard constraints and should be handled before final ranking.


Example:


If the JD says `5+ years Python`, a candidate should be excluded or heavily penalized when:


- `experience_years < 5`
- `Python` is not present in extracted resume skills


Recommended behavior:


| Requirement Type | Behavior |
|---|---|
| Required skill missing | Exclude candidate or apply a major penalty. |
| Minimum experience missing | Exclude candidate if clearly below threshold. |
| Metadata unavailable | Do not automatically exclude; mark uncertainty in reasoning or apply partial penalty. |


### Candidate Aggregation


Vector DB results are chunk-level, but the output must be candidate-level.


When multiple chunks from the same resume match:


- Combine their semantic scores.
- Keep the best 2-3 excerpts for `relevant_excerpts`.
- Merge section labels to explain which parts matched.
- Use the candidate-level metadata from the matched chunks.


Candidate grouping key should preferably be `resume_path`. Candidate name alone may not be unique.


### Scoring Requirements


The assignment requires scores from 0 to 100.


Suggested scoring formula:


```text
final_score = (
    semantic_score * 0.50 +
    skill_overlap_score * 0.30 +
    experience_score * 0.20
) * 100
```


Where:


| Signal | Meaning | Example Normalization |
|---|---|---|
| `semantic_score` | Similarity between JD and matched chunks | Convert cosine similarity/distance to 0-1. |
| `skill_overlap_score` | Ratio of required JD skills found in candidate skills | matched_required_skills / total_required_skills. |
| `experience_score` | Candidate years compared to required years | min(candidate_years / required_years, 1.0). |


If no required skills are extracted from the JD, `skill_overlap_score` can be based on all overlapping known skills or default to a neutral value.


### Match Reasoning Requirements


The output must explain why each candidate matched.


Good reasoning should mention:


- Matched skills.
- Relevant sections such as `experience`, `skills`, or `projects`.
- Whether experience requirements were satisfied.
- Why the candidate ranked highly or why the score is limited.


Example:


```text
Strong match because the candidate's experience and skills sections mention Python, ML pipelines, and AWS. The candidate meets the 5-year experience requirement.
```


### Required Output Format


The final output must be a JSON object matching the problem statement:


```json
{
  "job_description": "...",
  "top_matches": [
    {
      "candidate_name": "John Doe",
      "resume_path": "resumes/john_doe.pdf",
      "match_score": 92,
      "matched_skills": ["Python", "Machine Learning"],
      "relevant_excerpts": ["Built machine learning pipelines using Python..."],
      "reasoning": "Strong match for ML experience with direct skill overlap and sufficient seniority."
    }
  ]
}
```


Field requirements:


| Field | Required | Description |
|---|---:|---|
| `job_description` | Yes | Original JD text passed to the matcher. |
| `top_matches` | Yes | List of best candidates sorted by descending match score. |
| `candidate_name` | Yes | Extracted candidate name, with fallback if unknown. |
| `resume_path` | Yes | Path to the resume source file. |
| `match_score` | Yes | Integer or float from 0 to 100. |
| `matched_skills` | Yes | Skills found in both JD and resume. |
| `relevant_excerpts` | Yes | Most relevant retrieved resume chunks. |
| `reasoning` | Yes | Human-readable explanation of the match. |


### Suggested `job_matcher.py` Interface


Suggested module-level functions:


```python
def extract_job_requirements(job_description: str) -> dict:
    pass



def search_resumes(job_description: str, top_k: int = 10) -> list[dict]:
    pass



def score_candidate(candidate: dict, requirements: dict) -> float:
    pass



def match_jobs(job_description: str, top_k: int = 10) -> dict:
    pass
```


Suggested CLI usage:


```bash
python job_matcher.py --job-description-file docs/sample_jd.txt --top-k 10
```


## Required `requirements.txt` Contents


The project depends on the following packages. Pin major versions to avoid breaking changes:


```text
# Resume file parsing
pypdf>=3.0.0
python-docx>=1.1.0


# Embeddings — choose one provider block
# HuggingFace (local, free)
sentence-transformers>=2.7.0
torch>=2.0.0


# OpenAI (cloud, best quality)
# openai>=1.30.0


# Cohere (cloud, good balance)
# cohere>=5.0.0


# Vector database — ChromaDB recommended
chromadb>=0.5.0


# If using Pinecone instead
# pinecone-client>=3.0.0


# If using Weaviate instead
# weaviate-client>=4.0.0


# Utilities
python-dotenv>=1.0.0
pydantic>=2.0.0


# Optional: LangChain or LlamaIndex for orchestration
# langchain>=0.2.0
# llama-index>=0.10.0
```


Install with:


```bash
pip install -r requirements.txt
```


## Configuration Guidelines


Use environment variables for provider-specific configuration:


```text
EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
CHROMA_PERSIST_DIR=vector_store
CHROMA_COLLECTION_NAME=resumes
OPENAI_API_KEY=...
COHERE_API_KEY=...
```


Only one embedding provider is required for the assignment, but the selected provider should be easy to identify and reuse.


## Error Handling Expectations


The implementation should handle common failure cases gracefully:


| Failure Case | Expected Handling |
|---|---|
| Resume directory missing | Show a clear error message. |
| No supported resume files found | Stop with a useful message. |
| Empty extracted text | Skip file and warn. |
| Vector store missing during search | Tell user to run `resume_rag.py` first. |
| API key missing | Explain which key/config is missing. |
| No matching resumes | Return valid JSON with an empty `top_matches` list. |


## Testing And Validation Ideas


At minimum, test with 3-5 sample resumes and 1-2 job descriptions.


Useful checks:


- Resume chunks preserve section labels like `education` and `experience`.
- Metadata extraction returns name, skills, experience years, education, and path.
- Vector database contains one record per chunk.
- Job matching returns at most 10 top matches by default.
- Candidates missing must-have skills are filtered or penalized.
- Output is valid JSON and follows the required schema.


Suggested sample validation scenario:


```text
JD: Looking for a Python Machine Learning Engineer with 5+ years of experience, SQL, and AWS.


Expected behavior:
- Candidates with Python, ML, SQL, AWS, and 5+ years rank highest.
- Candidates without Python should not rank highly even if semantically similar.
- Reasoning should mention matched skills and experience fit.
```


## Acceptance Criteria


The assignment can be considered complete when:


- `resume_rag.py` loads resumes from the file system.
- Resumes are chunked in a section-aware way.
- Embeddings are generated for chunks.
- Chunks and metadata are stored in a vector database.
- Metadata includes name, skills, experience years, education, and resume path.
- `job_matcher.py` accepts a job description.
- The JD is embedded using the same model as the resumes.
- Top-K retrieval uses `K=10` by default.
- Hybrid search combines semantic similarity with keyword/skill matching.
- Ranking returns match scores from 0 to 100.
- Must-have requirements such as `5+ years Python` are filtered or penalized correctly.
- Output JSON matches the required format exactly.


## Implementation Notes And Shortcomings Filled


The original brief was concise and left several details open. This context fills those gaps by specifying:


- Concrete responsibilities for `resume_rag.py` and `job_matcher.py`.
- Recommended local stack choices for embeddings and vector storage.
- Section-aware chunking behavior and metadata shape.
- Candidate aggregation from chunk-level retrieval.
- Hybrid search implementation guidance.
- A practical scoring formula with suggested weights.
- CLI expectations for both scripts.
- Error handling expectations.
- Testing ideas and acceptance criteria.