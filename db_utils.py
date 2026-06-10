import os

import chromadb
from dotenv import load_dotenv

load_dotenv()


def get_chroma_collection():
    """Return the configured persistent ChromaDB collection."""
    client = chromadb.PersistentClient(path=os.getenv("CHROMA_PERSIST_DIR", "vector_store"))
    return client.get_or_create_collection(
        name=os.getenv("CHROMA_COLLECTION_NAME", "resumes"),
        metadata={"hnsw:space": "cosine"},
    )
