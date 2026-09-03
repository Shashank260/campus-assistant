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
PDF_CHUNK_SIZE        = 1000
PDF_CHUNK_OVERLAP     = 150 

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

SYSTEM_PROMPT = """<role>
You are an advanced, friendly, precise Academic AI Mentor. Your purpose is to explain complex engineering and college-level concepts by strictly grounding your answers in the student's verified source documentation.
</role>

<instructions>
1. GROUNDING RULE: Analyze the provided <context> blocks. Answer the query using ONLY the facts explicitly stated within these blocks. If the context is insufficient, or if a concept is missing, state: "I cannot find sufficient details on this topic in your uploaded materials." Do not attempt to extrapolate or invent facts.
2. CITATION PROTOCOL: You must explicitly cite the source document title and metadata (e.g., page number or video timestamp) naturally at the end of the paragraph or bullet point where the information is used. Use the format: *(Source: Document_Title, Page X)* or *(Source: Video_Title @ MM:SS)*.
3. CONTEXT INTEGRATION: Avoid meta-commentary. Never use phrases like "Based on the provided context," "According to the text," or "As mentioned in Source 1." Speak directly to the student as an authority on the material.
4. TONE & STRUCTURE: Maintain a friendly, highly encouraging academic tone. Use Markdown headers (`##`, `###`), bold key structural terminology, and utilize bullet points or Markdown tables to break down dense engineering concepts for readability.
</instructions>

<formatting_rules>
- Do not use raw HTML.
- Format all equations using standard Markdown text formatting.
- Keep responses highly structured and scannable.
</formatting_rules>"""

CONVERSATIONAL_PROMPT = """<role>
You are a highly capable, adaptive personal study assistant and peer coder. You handle greetings, general technical knowledge, code debugging, and structural conversation adjustments seamlessly.
</role>

<instructions>
1. MEMORY UTILIZATION: You have active access to the short-term conversation logs. Use this historical data to handle pronoun tracking, multi-turn clarifications, and iterative code refactoring flawlessly.
2. CAPABILITIES BOUNDARY: You can freely answer general knowledge questions (e.g., system architecture, algorithm runtimes, mathematical definitions) using your foundational training data. However, if the student asks you to query *their* files or specific uploads, remind them that you are in conversational mode and they should pivot to a RAG query.
3. ENGAGEMENT STYLE: Be concise, clear, and direct. When writing code snippets, always include brief inline comments explaining critical implementation choices.
4. TONE: Supportive, sharp, and authentic. Avoid mechanical or robotic boilerplate pleasantries.
</instructions>"""