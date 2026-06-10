import logging
import os
import time

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

logger = logging.getLogger(__name__)

MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_EMBED_MAX_RETRIES = 3
_EMBED_RETRY_BASE_SECS = 1  # exponential: 1s, 2s, 4s

_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Return a cached HuggingFace SentenceTransformer model."""
    global _model
    if _model is not None:
        return _model

    _model = SentenceTransformer(MODEL)
    return _model


def _encode_batch(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    """Encode a single batch, splitting in half on failure before giving up."""
    last_exc: Exception | None = None

    for attempt in range(_EMBED_MAX_RETRIES):
        try:
            vectors = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
            return vectors.tolist()
        except Exception as exc:
            last_exc = exc
            if len(texts) > 1:
                midpoint = len(texts) // 2
                logger.warning(
                    "Embedding batch of %d failed (%s); splitting into %d + %d",
                    len(texts),
                    exc,
                    midpoint,
                    len(texts) - midpoint,
                )
                left = _encode_batch(model, texts[:midpoint])
                right = _encode_batch(model, texts[midpoint:])
                return left + right

            if attempt < _EMBED_MAX_RETRIES - 1:
                wait = _EMBED_RETRY_BASE_SECS * (2 ** attempt)
                logger.warning(
                    "Embedding attempt %d/%d failed: %s — retrying in %ds",
                    attempt + 1,
                    _EMBED_MAX_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)

    raise RuntimeError(
        f"Embedding failed after {_EMBED_MAX_RETRIES} attempts: {last_exc}"
    ) from last_exc


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings with the configured HuggingFace model."""
    if not texts:
        return []

    model = get_embedding_model()
    return _encode_batch(model, texts)
