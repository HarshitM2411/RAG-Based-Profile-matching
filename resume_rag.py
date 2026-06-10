import hashlib
import logging
import os
import re
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

import pypdf
from docx import Document
from dotenv import load_dotenv

from db_utils import get_chroma_collection
from embedder import embed_texts
from skills_vocab import KNOWN_SKILLS

load_dotenv()

logger = logging.getLogger(__name__)

SECTION_PATTERNS = {
    "summary": r"(summary|objective|profile|about\s*me|professional\s*summary|career\s*objective|overview)",
    "skills": r"(skills|technical\s*skills|technologies|competencies|core\s*competencies|key\s*skills|expertise|tech\s*stack)",
    "experience": r"(experience|work\s*experience|employment|work\s*history|professional\s*experience|career\s*history|positions?\s*held)",
    "education": r"(education|academic|qualifications|degrees?|educational\s*background|academic\s*background)",
    "projects": r"(projects?|personal\s*projects?|key\s*projects?|notable\s*projects?|open.?source)",
    "certifications": r"(certifications?|certificates?|licenses?|credentials?|accreditations?)",
    "achievements": r"(achievements?|accomplishments?|awards?|honors?|recognition|highlights?)",
}

# Maximum chars a line can have to still be treated as a section heading
_HEADING_MAX_CHARS = 60

MAX_CHUNK_CHARS = 900
CHUNK_OVERLAP = 100
MIN_CHUNK_CHARS = 80

WORD_NUMBER_MAP = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
}


def list_files(directory: str, extensions: list[str]) -> list[str]:
    """Discover files under directory matching the given extensions."""
    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(
            f"Resume directory not found: {directory}. "
            "Create the directory or pass a valid --resume-dir path."
        )

    normalized_extensions = {
        ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        for ext in extensions
    }

    paths = [
        str(file_path.resolve())
        for file_path in root.rglob("*")
        if file_path.is_file() and file_path.suffix.lower() in normalized_extensions
    ]
    return sorted(paths)


def load_resume_text(file_path: str) -> str:
    """Extract raw text from a TXT, PDF, or DOCX resume file."""
    path = Path(file_path)
    extension = path.suffix.lower()

    try:
        if extension == ".txt":
            try:
                return path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return path.read_text(encoding="latin-1")

        if extension == ".pdf":
            reader = pypdf.PdfReader(str(path))
            if reader.is_encrypted:
                logger.warning("Password-protected PDF %s; cannot extract text.", file_path)
                return ""
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages)

        if extension == ".docx":
            document = Document(str(path))
            paragraphs = [paragraph.text for paragraph in document.paragraphs]
            return "\n".join(paragraphs)

        logger.warning("Unsupported file extension for %s; skipping.", file_path)
        return ""
    except Exception as exc:
        logger.warning("Failed to load resume %s: %s", file_path, exc)
        return ""


def _normalize_resume_path(resume_path: str) -> str:
    path = Path(resume_path)
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _looks_like_name(line: str) -> bool:
    words = line.split()
    if not 2 <= len(words) <= 4:
        return False
    return all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", word) for word in words)


def _extract_candidate_name(text: str, resume_path: str) -> str:
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if _looks_like_name(candidate):
            return candidate
        break

    stem = Path(resume_path).stem.replace("_", " ").replace("-", " ")
    if stem:
        return stem.title()
    return "Unknown"


def _match_section_heading(line: str) -> str | None:
    cleaned = line.strip().rstrip(":").strip()
    # Headings are short; long lines are body text, not headings
    if not cleaned or len(cleaned) > _HEADING_MAX_CHARS:
        return None

    for label, pattern in SECTION_PATTERNS.items():
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            return label
    return None


def _extract_section_text(text: str, section_label: str) -> str:
    lines = text.splitlines()
    section_lines: list[str] = []
    in_section = False

    for line in lines:
        heading = _match_section_heading(line)
        if heading == section_label:
            in_section = True
            continue
        if in_section and heading is not None:
            break
        if in_section:
            section_lines.append(line)

    return "\n".join(section_lines).strip()


def _find_skills_in_text(text: str) -> list[str]:
    matched: list[str] = []
    for skill in sorted(KNOWN_SKILLS, key=len, reverse=True):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(skill)}(?![A-Za-z0-9])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            matched.append(skill)
    return matched


def _extract_skills(text: str) -> str:
    """Collect skills from the dedicated section and the full resume text."""
    section_text = _extract_section_text(text, "skills")
    section_skills = _find_skills_in_text(section_text) if section_text else []
    full_text_skills = _find_skills_in_text(text)
    merged_skills = list(dict.fromkeys(section_skills + full_text_skills))
    return ",".join(merged_skills)


def _extract_experience_years(text: str) -> int:
    values: list[int] = []

    for match in re.finditer(r"(\d+)\+?\s*(?:years?|yrs?)\b", text, flags=re.IGNORECASE):
        values.append(int(match.group(1)))

    word_pattern = r"\b(" + "|".join(WORD_NUMBER_MAP) + r")\+?\s*(?:years?|yrs?)\b"
    for match in re.finditer(word_pattern, text, flags=re.IGNORECASE):
        values.append(WORD_NUMBER_MAP[match.group(1).lower()])

    for match in re.finditer(r"(\d+)\s*months?\b", text, flags=re.IGNORECASE):
        values.append(max(int(match.group(1)) // 12, 1))

    current_year = datetime.now().year
    for match in re.finditer(
        r"(?P<start>\d{4})\s*(?:-|–|to)\s*(?P<end>\d{4}|present|current)",
        text,
        flags=re.IGNORECASE,
    ):
        start_year = int(match.group("start"))
        end_token = match.group("end")
        end_year = current_year if end_token.lower() in {"present", "current"} else int(end_token)
        if end_year >= start_year:
            values.append(end_year - start_year)

    # -1 means "could not parse" — distinct from a genuine 0-year candidate
    return max(values) if values else -1


def _extract_education(text: str) -> str:
    section_text = _extract_section_text(text, "education")
    if not section_text:
        return ""

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", section_text) if part.strip()]
    if paragraphs:
        return paragraphs[0]

    for line in section_text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""


def extract_metadata(text: str, resume_path: str) -> dict:
    """Extract candidate-level metadata from raw resume text."""
    normalized_path = _normalize_resume_path(resume_path)

    return {
        "candidate_name": _extract_candidate_name(text, normalized_path),
        "skills": _extract_skills(text),
        "experience_years": _extract_experience_years(text),
        "education": _extract_education(text),
        "resume_path": normalized_path,
    }


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _detect_sections(text: str) -> list[tuple[int, str]]:
    """Return (line_number, section_label) boundaries for detected headings."""
    boundaries: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines()):
        heading = _match_section_heading(line)
        if heading:
            boundaries.append((line_number, heading))
    return boundaries


def _split_into_sections(text: str) -> dict[str, str]:
    """Slice resume text into labelled section blocks."""
    section_list = _split_into_section_list(text)
    sections: dict[str, str] = {}
    for label, content in section_list:
        if label in sections:
            sections[label] = f"{sections[label]}\n\n{content}"
        else:
            sections[label] = content
    return sections


def _split_into_section_list(text: str) -> list[tuple[str, str]]:
    """Return ordered section blocks, merging repeated headings."""
    normalized = _normalize_text(text)
    if not normalized:
        return []

    lines = normalized.splitlines()
    boundaries = _detect_sections(normalized)
    if not boundaries:
        return [("other", normalized)]

    sections: list[tuple[str, str]] = []
    first_line_idx = boundaries[0][0]
    pre_heading = "\n".join(lines[:first_line_idx]).strip()
    if pre_heading and len(pre_heading) >= MIN_CHUNK_CHARS:
        sections.append(("other", pre_heading))

    for idx, (line_number, label) in enumerate(boundaries):
        start = line_number + 1
        end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(lines)
        content = "\n".join(lines[start:end]).strip()
        if content:
            sections.append((label, content))

    merged: list[tuple[str, str]] = []
    for label, content in sections:
        if merged and merged[-1][0] == label:
            previous_label, previous_content = merged[-1]
            merged[-1] = (previous_label, f"{previous_content}\n\n{content}")
        else:
            merged.append((label, content))
    return merged


def _split_section_units(section_text: str, section_label: str) -> list[str]:
    """Split a section into retrieval-friendly units before character windows."""
    if section_label == "experience":
        job_blocks = [block.strip() for block in re.split(r"\n\s*\n", section_text) if block.strip()]
        if len(job_blocks) > 1:
            return job_blocks

    return [section_text]


def _pad_short_section(section_label: str, text: str) -> str:
    """Keep short but meaningful sections above the minimum chunk size."""
    if len(text) >= MIN_CHUNK_CHARS:
        return text

    heading = section_label.replace("_", " ").upper()
    padded = f"{heading}\n{text.strip()}"
    if len(padded) < MIN_CHUNK_CHARS:
        padded = f"{padded}\nRelevant {heading.lower()} information for resume retrieval."
    return padded


def _sliding_window_chunks(text: str) -> list[str]:
    """Split long text into overlapping character windows."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    windows: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + MAX_CHUNK_CHARS, len(text))
        windows.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return windows


def _build_chunk_dict(
    section_label: str,
    chunk_text: str,
    chunk_index: int,
    metadata: dict,
    path_hash: str,
) -> dict:
    return {
        "chunk_id": f"{path_hash}_{section_label}_{chunk_index}",
        "resume_path": metadata["resume_path"],
        "candidate_name": metadata["candidate_name"],
        "section_label": section_label,
        "chunk_text": chunk_text,
        "chunk_index": chunk_index,
        "skills": metadata["skills"],
        "experience_years": metadata["experience_years"],
        "education": metadata["education"],
    }


def _subchunk(
    section_text: str,
    section_label: str,
    metadata: dict,
    path_hash: str,
    start_index: int,
) -> tuple[list[dict], int]:
    chunks: list[dict] = []
    chunk_index = start_index

    for unit in _split_section_units(section_text, section_label):
        prepared_unit = _pad_short_section(section_label, unit)
        for window in _sliding_window_chunks(prepared_unit):
            if len(window) < MIN_CHUNK_CHARS:
                continue
            chunks.append(
                _build_chunk_dict(section_label, window, chunk_index, metadata, path_hash)
            )
            chunk_index += 1

    return chunks, chunk_index


def chunk_resume(text: str, metadata: dict) -> list[dict]:
    """Split resume text into section-labelled chunks with overlap."""
    normalized = _normalize_text(text)
    if not normalized:
        return []

    path_hash = hashlib.md5(metadata["resume_path"].encode("utf-8")).hexdigest()[:8]
    sections = _split_into_section_list(normalized)

    all_chunks: list[dict] = []
    chunk_index = 0
    for section_label, section_text in sections:
        section_chunks, chunk_index = _subchunk(
            section_text,
            section_label,
            metadata,
            path_hash,
            chunk_index,
        )
        all_chunks.extend(section_chunks)

    return all_chunks


def _delete_stale_chunks(collection, resume_path: str, current_ids: set[str]) -> None:
    """Remove chunk IDs for a resume that are no longer produced after re-ingestion."""
    existing = collection.get(where={"resume_path": resume_path}, include=[])
    stale_ids = [chunk_id for chunk_id in existing.get("ids", []) if chunk_id not in current_ids]
    if stale_ids:
        collection.delete(ids=stale_ids)
        logger.info("Deleted %d stale chunks for %s", len(stale_ids), resume_path)


def _delete_orphaned_resume_chunks(collection, active_resume_paths: set[str]) -> None:
    """Remove chunks whose resume files are no longer on disk."""
    if collection.count() == 0:
        return

    existing = collection.get(include=["metadatas"])
    orphan_ids: list[str] = []
    for chunk_id, metadata in zip(existing.get("ids", []), existing.get("metadatas", [])):
        if not metadata:
            continue
        resume_path = metadata.get("resume_path")
        if resume_path and resume_path not in active_resume_paths:
            orphan_ids.append(chunk_id)

    if orphan_ids:
        collection.delete(ids=orphan_ids)
        logger.info("Deleted %d orphaned chunks for removed resumes", len(orphan_ids))


def build_vector_store(resume_dir: str) -> None:
    """Load resumes, chunk them, embed them, and persist them to ChromaDB."""
    persist_dir = os.getenv("CHROMA_PERSIST_DIR", "vector_store")
    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    collection = get_chroma_collection()
    file_paths = list_files(resume_dir, [".pdf", ".docx", ".txt"])
    if not file_paths:
        raise ValueError(
            "No supported resume files found. Add PDF, DOCX, or TXT files to the resume directory."
        )

    stored_chunks = 0
    ingested_paths: set[str] = set()
    for file_path in file_paths:
        raw_text = load_resume_text(file_path)
        if not raw_text.strip():
            logger.warning("Skipping empty or unreadable resume: %s", file_path)
            continue

        metadata = extract_metadata(raw_text, file_path)
        resume_path = metadata["resume_path"]
        ingested_paths.add(resume_path)
        chunks = chunk_resume(raw_text, metadata)
        if not chunks:
            logger.warning("No useful chunks produced for: %s", file_path)
            continue

        current_ids = {chunk["chunk_id"] for chunk in chunks}
        _delete_stale_chunks(collection, resume_path, current_ids)

        vectors = embed_texts([chunk["chunk_text"] for chunk in chunks])
        collection.upsert(
            ids=[chunk["chunk_id"] for chunk in chunks],
            embeddings=vectors,
            documents=[chunk["chunk_text"] for chunk in chunks],
            metadatas=[
                {key: value for key, value in chunk.items() if key not in {"chunk_text", "embedding"}}
                for chunk in chunks
            ],
        )
        stored_chunks += len(chunks)
        logger.info("Stored %d chunks for %s", len(chunks), resume_path)

    _delete_orphaned_resume_chunks(collection, ingested_paths)

    if stored_chunks == 0:
        raise ValueError("No resume chunks were stored. Check resume files and parsing output.")

    logger.info("Ingestion complete. Stored %d chunks in collection '%s'.", stored_chunks, collection.name)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build or update the resume vector store.")
    parser.add_argument("--resume-dir", default="resumes")
    parser.add_argument("--persist-dir", default=None)
    args = parser.parse_args()

    if args.persist_dir:
        os.environ["CHROMA_PERSIST_DIR"] = args.persist_dir

    build_vector_store(args.resume_dir)
