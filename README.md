# TalentMatch RAG

Semantic resume matching engine for enterprise talent acquisition. Upload resumes, build a vector store, and match candidates against job descriptions using RAG (Retrieval-Augmented Generation) with hybrid skill filtering and AI-generated reasoning.

## Features

- **Resume ingestion** — Upload PDF, DOCX, and TXT files; extract metadata, chunk by section, and index into ChromaDB
- **Job matching** — Parse job descriptions, run semantic search, apply hybrid filters, and rank candidates by match score
- **AI reasoning** — Groq LLM generates per-candidate explanations for why they fit the role
- **Web dashboard** — React UI with dashboard stats, ingestion pipeline, job matching, and ranked results

## Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python, FastAPI, Uvicorn |
| **RAG** | ChromaDB, sentence-transformers (local embeddings) |
| **LLM** | Groq API (match reasoning) |
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS 4 |

## Prerequisites

- Python 3.10+
- Node.js 18+
- A [Groq API key](https://console.groq.com/) (for match reasoning)

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/HarshitM2411/RAG-Based-Profile-matching.git
cd RAG-Based-Profile-matching

pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
CHROMA_PERSIST_DIR=vector_store
CHROMA_COLLECTION_NAME=resumes
RESUME_DIR=resumes
```

Embeddings run locally via HuggingFace — no API key needed for indexing.

### 3. Start the backend

```bash
uvicorn api:app --reload --host 127.0.0.1 --port 8080
```

### 4. Start the frontend

In a second terminal:

```bash
cd frontend
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The Vite dev server proxies `/api` requests to the backend on port 8080.

## Usage Workflow

1. **Dashboard** — View system stats (resume count, chunk count, vector store status)
2. **Resume Ingestion** — Upload resumes, then click **Build / Update Vector Store**
3. **Job Matching** — Paste a job description and click **Find Top Matches**
4. **Match Results** — Review ranked candidates with skills, excerpts, and AI reasoning

A sample job description is available at `docs/sample_jd.txt`.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/dashboard` | System stats and recent activity |
| `GET` | `/api/resumes` | List uploaded resumes with metadata |
| `POST` | `/api/resumes/upload` | Upload resume files |
| `POST` | `/api/ingest` | Build or update the vector store |
| `POST` | `/api/parse-jd` | Extract skills and requirements from a JD |
| `POST` | `/api/match` | Run job matching and return ranked results |

## CLI (optional)

The core pipelines can also be run from the command line:

```bash
# Build the vector store from resumes/
python resume_rag.py

# Match a job description file
python job_matcher.py --jd docs/sample_jd.txt --top-k 10

# Run validation tests
python validate.py

# Run retrieval accuracy + latency benchmarks
python eval_harness.py
```

## Evaluation Notebook

Deliverable: experimentation, retrieval accuracy, and latency analysis.

```bash
# Install notebook dependencies (one-time)
pip install jupyter ipykernel pandas matplotlib

# Or install everything from requirements.txt
pip install -r requirements.txt

# Build vector store first if not already done
python resume_rag.py --resume-dir resumes

# Option A — Jupyter in browser
jupyter notebook notebooks/rag_evaluation.ipynb

# Option B — Open notebooks/rag_evaluation.ipynb in Cursor/VS Code
# Select the Python kernel for the project and run all cells
```

| Asset | Purpose |
|---|---|
| `notebooks/rag_evaluation.ipynb` | Interactive experiments, charts, and analysis |
| `eval_harness.py` | Reusable metrics module (Precision@K, Recall@K, MRR, latency) |
| `data/eval_labels.json` | Manually labelled ground truth per job description |
| `docs/eval.md` | Full evaluation methodology |

## Project Structure

```
├── api.py                 # FastAPI server
├── resume_rag.py          # Ingestion pipeline (chunk, embed, store)
├── job_matcher.py         # Query pipeline (search, filter, score)
├── embedder.py            # Shared embedding model
├── db_utils.py            # ChromaDB client
├── llm.py                 # Groq LLM integration
├── skills_vocab.py        # Known skills vocabulary
├── validate.py            # Acceptance tests
├── eval_harness.py        # Retrieval accuracy & latency benchmarks
├── notebooks/             # Jupyter evaluation notebook
├── data/eval_labels.json  # Labelled evaluation ground truth
├── resumes/               # Uploaded resume files
├── vector_store/          # ChromaDB persistence (gitignored)
├── docs/                  # Architecture, implementation, sample JD
├── frontend/              # React web application
│   └── src/
│       ├── pages/         # Dashboard, Ingestion, Matching, Results
│       └── components/    # Sidebar, TopBar, MatchScoreRing
└── frontend-designs/      # UI design references
```

## Scoring

Candidates are ranked using a hybrid score:

| Component | Weight |
|---|---|
| Semantic similarity | 50% |
| Skill overlap | 30% |
| Experience fit | 20% |

Groq generates a natural-language `reasoning` field for each top match.

## Documentation

- [System Architecture](docs/architecture.md) — pipelines, component map, data flow
- [Implementation Plan](docs/implementation.md) — phase-wise build guide

## License

This project was built as part of the AirTribe RAG assignment.
