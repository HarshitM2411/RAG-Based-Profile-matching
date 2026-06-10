import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db_utils import get_chroma_collection
from job_matcher import extract_job_requirements, match_jobs
from llm import normalize_experience_years
from resume_rag import build_vector_store, extract_metadata, list_files, load_resume_text

load_dotenv()

RESUME_DIR = Path(os.getenv("RESUME_DIR", "resumes"))
RESUME_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="TalentMatch RAG API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ParseJdRequest(BaseModel):
    job_description: str


class MatchRequest(BaseModel):
    job_description: str
    top_k: int = Field(default=10, ge=1)


def _vector_store_mtime() -> str | None:
    persist_dir = Path(os.getenv("CHROMA_PERSIST_DIR", "vector_store"))
    sqlite_path = persist_dir / "chroma.sqlite3"
    if not sqlite_path.exists():
        return None
    timestamp = datetime.fromtimestamp(sqlite_path.stat().st_mtime, tz=timezone.utc)
    return timestamp.isoformat()


def _dashboard_stats() -> dict:
    resume_files = list_files(str(RESUME_DIR), [".pdf", ".docx", ".txt"])
    chunk_count = 0
    indexed_resumes = 0
    vector_status = "not_built"

    try:
        collection = get_chroma_collection()
        chunk_count = collection.count()
        if chunk_count > 0:
            vector_status = "connected"
            results = collection.get(include=["metadatas"])
            resume_paths = {
                metadata.get("resume_path")
                for metadata in results.get("metadatas", [])
                if metadata and metadata.get("resume_path")
            }
            indexed_resumes = len(resume_paths)
    except Exception:
        vector_status = "error"

    return {
        "total_resumes": len(resume_files),
        "indexed_resumes": indexed_resumes,
        "total_chunks": chunk_count,
        "vector_store_status": vector_status,
        "last_ingestion": _vector_store_mtime(),
        "embedding_model": os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        "collection_name": os.getenv("CHROMA_COLLECTION_NAME", "resumes"),
        "llm_model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    }


def _resume_preview(file_path: str) -> dict:
    path = Path(file_path)
    raw_text = load_resume_text(file_path)
    if not raw_text.strip():
        return {
            "file_name": path.name,
            "file_path": str(path).replace("\\", "/"),
            "size_kb": round(path.stat().st_size / 1024, 1),
            "format": path.suffix.lstrip(".").upper(),
            "candidate_name": "Unknown",
            "skills": [],
            "experience_years": None,
            "education": "",
            "status": "failed",
        }

    metadata = extract_metadata(raw_text, file_path)
    skills = [
        skill.strip()
        for skill in str(metadata.get("skills", "")).split(",")
        if skill.strip()
    ]
    return {
        "file_name": path.name,
        "file_path": metadata.get("resume_path", str(path)).replace("\\", "/"),
        "size_kb": round(path.stat().st_size / 1024, 1),
        "format": path.suffix.lstrip(".").upper(),
        "candidate_name": metadata.get("candidate_name", "Unknown"),
        "skills": skills[:4],
        "experience_years": normalize_experience_years(
            int(metadata.get("experience_years", -1))
        ),
        "education": metadata.get("education", ""),
        "status": "pending",
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/dashboard")
def dashboard() -> dict:
    stats = _dashboard_stats()
    return {
        **stats,
        "recent_activity": [
            {
                "type": "ingestion",
                "label": f"{stats['indexed_resumes']} resumes indexed",
                "timestamp": stats["last_ingestion"],
            }
        ],
    }


@app.get("/api/resumes")
def get_resumes() -> dict:
    try:
        file_paths = list_files(str(RESUME_DIR), [".pdf", ".docx", ".txt"])
    except FileNotFoundError:
        return {"resumes": []}

    return {"resumes": [_resume_preview(file_path) for file_path in file_paths]}


@app.post("/api/resumes/upload")
async def upload_resumes(files: list[UploadFile] = File(...)) -> dict:
    saved: list[str] = []
    for upload in files:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in {".pdf", ".docx", ".txt"}:
            continue
        destination = RESUME_DIR / Path(upload.filename or "resume.txt").name
        with destination.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        saved.append(destination.name)
    return {"saved": saved, "count": len(saved)}


@app.post("/api/ingest")
def ingest() -> dict:
    try:
        build_vector_store(str(RESUME_DIR))
        stats = _dashboard_stats()
        return {
            "success": True,
            "message": (
                f"Ingestion complete — {stats['total_chunks']} chunks stored "
                f"across {stats['indexed_resumes']} resumes"
            ),
            "chunks_stored": stats["total_chunks"],
            "resumes_indexed": stats["indexed_resumes"],
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/parse-jd")
def parse_jd(request: ParseJdRequest) -> dict:
    requirements = extract_job_requirements(request.job_description)
    return {
        "required_skills": requirements["required_skills"],
        "min_experience_years": requirements["min_experience_years"],
        "jd_keywords_count": len(requirements["jd_keywords"]),
    }


@app.post("/api/match")
def match(request: MatchRequest) -> dict:
    if not request.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description is required.")

    try:
        return match_jobs(request.job_description, top_k=request.top_k)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
