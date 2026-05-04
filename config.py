"""
config.py — Central configuration for Campus Assistant backend.
Load once, import everywhere. No magic strings scattered in code.

Phase 1 complete. Single LLM provider: Google AI Studio (Gemma 4).
Gemma 4 handles both text (RAG/chat) and vision (image context).
"""

from __future__ import annotations

import os
import langchain
from pathlib import Path
from dotenv import load_dotenv
from langchain_community.cache import SQLiteCache

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR            = Path(__file__).resolve().parent
DB_DIR              = BASE_DIR / "db"
EMBEDDINGS_CACHE    = BASE_DIR / ".embeddings_cache"

for d in [DB_DIR, EMBEDDINGS_CACHE]:
    d.mkdir(parents=True, exist_ok=True)

# ── ChromaDB ───────────────────────────────────────────────────────────────────
CHROMA_PERSIST_DIR         = str(DB_DIR / "chroma")
PERSONAL_COLLECTION_PREFIX = "personal_"    # e.g. personal_student42

# ── Embeddings ─────────────────────────────────────────────────────────────────
EMBEDDING_MODEL     = "BAAI/bge-small-en"   # 33M params, CPU-only, no API cost
EMBEDDING_CACHE_DIR = str(EMBEDDINGS_CACHE)

# ── LLMs — single provider: Google AI Studio (free tier) ──────────────────────
# Gemma 4 handles everything: chat, RAG responses, AND vision.
# No Groq needed anymore.
# Get your free key at: aistudio.google.com
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")
GEMMA_MODEL      = "gemma-4-31b-it"
GEMMA_MODEL_FAST = "gemma-4-26b-a4b-it"   # MoE — faster for simple queries

# ── Chunking ───────────────────────────────────────────────────────────────────
PDF_CHUNK_SIZE        = 400
PDF_CHUNK_OVERLAP     = 50

YOUTUBE_CHUNK_SIZE    = 400
YOUTUBE_CHUNK_OVERLAP = 50

# ── Retrieval ──────────────────────────────────────────────────────────────────
TOP_K           = 5      # chunks returned per query
SCORE_THRESHOLD = 0.3    # discard below this cosine similarity (0–1)

# ── STM (Phase 2) ──────────────────────────────────────────────────────────────
STM_FULL_WINDOW   = 6     # keep last N full messages before summarising
STM_RECENT_WINDOW = 3     # after summarisation, keep last N full messages
STM_MAX_TOKENS    = 3000  # target total tokens per LLM call

# ── SQLite ─────────────────────────────────────────────────────────────────────
SQLITE_DB_PATH    = str(DB_DIR / "campus_assistant.db")
SQLITE_CACHE_PATH = str(DB_DIR / "llm_cache.db")

# ── LLM cache — activated on import ───────────────────────────────────────────
langchain.llm_cache = SQLiteCache(database_path=SQLITE_CACHE_PATH)

# ── File upload limits ─────────────────────────────────────────────────────────
IMAGE_MAX_SIZE_MB = 10
PDF_MAX_SIZE_MB   = 50

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
SUPPORTED_PDF_EXTENSIONS   = {".pdf"}

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a helpful personal study assistant for college students.
Answer questions based only on the provided context retrieved from the student's own uploaded documents.
If the context doesn't contain enough information to answer, say so clearly — do not guess or hallucinate.
Always mention which document your answer comes from when possible.
When asked to make flashcards, format them as numbered Q&A pairs: Q: ... A: ...
When asked to draw diagrams, use clean ASCII art.
Be concise, accurate, and friendly."""