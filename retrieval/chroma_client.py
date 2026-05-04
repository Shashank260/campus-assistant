"""
chroma_client.py — ChromaDB initialisation and collection management.

Revised architecture: personal_{user_id} collections only.
No central/shared knowledge base — every student's data is isolated.

Singletons:
- One PersistentClient shared across the app lifetime.
- One HuggingFaceEmbeddings instance (loads ~120 MB BGE model once, then cached).
"""
from __future__ import annotations
import chromadb
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

from config import (
    CHROMA_PERSIST_DIR,
    PERSONAL_COLLECTION_PREFIX,
    EMBEDDING_MODEL,
    EMBEDDING_CACHE_DIR,
)

# ── Singletons ─────────────────────────────────────────────────────────────────

from typing import Optional
_chroma_client: Optional[chromadb.PersistentClient] = None
_embeddings: Optional[HuggingFaceEmbeddings] = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Return (or lazily create) the shared ChromaDB persistent client."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _chroma_client


def get_embeddings() -> HuggingFaceEmbeddings:
    """
    Return (or lazily load) the BGE embedding model.
    First call downloads ~120 MB to EMBEDDING_CACHE_DIR.
    All subsequent calls reuse the loaded model — no re-download, no re-load.
    """
    global _embeddings
    if _embeddings is None:
        print(f"[chroma] Loading embedding model '{EMBEDDING_MODEL}'...")
        _embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            cache_folder=EMBEDDING_CACHE_DIR,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},  # required for BGE cosine similarity
        )
        print("[chroma] Embedding model ready.")
    return _embeddings


# ── Collection access ──────────────────────────────────────────────────────────

def get_personal_collection(user_id: str) -> Chroma:
    """
    Return the LangChain Chroma wrapper for a student's personal collection.
    Collection is created automatically on first use if it doesn't exist.
    """
    return Chroma(
        client=get_chroma_client(),
        collection_name=f"{PERSONAL_COLLECTION_PREFIX}{user_id}",
        embedding_function=get_embeddings(),
    )


def personal_collection_stats(user_id: str) -> dict:
    """
    Return doc count for a student's collection.
    Returns count=0 if the collection doesn't exist yet (student hasn't uploaded anything).
    """
    collection_name = f"{PERSONAL_COLLECTION_PREFIX}{user_id}"
    client = get_chroma_client()
    try:
        col = client.get_collection(collection_name)
        return {"collection": collection_name, "count": col.count()}
    except Exception:
        return {"collection": collection_name, "count": 0}


def list_user_collections() -> list[str]:
    """
    List all personal collection names currently in ChromaDB.
    Useful for admin/debug — returns e.g. ['personal_alice', 'personal_bob'].
    """
    client = get_chroma_client()
    return [c.name for c in client.list_collections()
            if c.name.startswith(PERSONAL_COLLECTION_PREFIX)]
