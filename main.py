"""
main.py — Campus Assistant FastAPI backend, Phase 3.

What's new in Phase 2:
  - SQLite conversation threads (create, list, delete)
  - STM (Short Term Memory) — sliding window + summarisation
  - /chat now loads thread context, injects memory, saves messages
  - GET  /conversations/{user_id}    → list all threads
  - POST /conversations/new          → create new thread
  - DELETE /conversations/{id}       → delete thread

Everything from Phase 1 is unchanged.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
from config import (
    GEMINI_API_KEY,
    GEMMA_MODEL,
    GEMMA_MODEL_FAST,
    SYSTEM_PROMPT,
    IMAGE_MAX_SIZE_MB,
    PDF_MAX_SIZE_MB,
    SUPPORTED_IMAGE_EXTENSIONS,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from retrieval.retriever import retrieve, format_context
from graph import run_graph
from retrieval.chroma_client import personal_collection_stats, list_user_collections
from ingestion.pdf_ingest import ingest_pdf
from ingestion.image_ingest import ingest_image
from context.image_context import process_image_for_context, format_image_context_for_llm
from memory.sqlite_client import (
    init_db,
    create_conversation,
    get_conversation,
    list_conversations,
    delete_conversation,
    save_message,
    get_user_settings,      # ← add
    save_user_settings, 
)
from memory.stm_manager import load_stm_context, save_and_update_stm, build_prompt_messages
from notion.notion_push import push_to_notion, verify_notion_connection

# ── Lifespan — runs once on startup ───────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise SQLite schema on startup. Nothing to clean up on shutdown."""
    await asyncio.to_thread(init_db)
    yield


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Campus Assistant API",
    description="Personal AI study assistant — Phase 2",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    user_id:         str  = Field(..., description="Student identifier")
    message:         str  = Field(..., min_length=1)
    conversation_id: str  = Field(..., description="Thread ID from POST /conversations/new")
    fast_mode:       bool = Field(default=False, description="Use faster MoE model")
    api_key:         str  = Field(default="") 


class SourceInfo(BaseModel):
    model_config    = {"protected_namespaces": ()}
    doc_title:   str
    source_type: str
    page:        str | int = ""
    score:       float


class ChatResponse(BaseModel):
    model_config    = {"protected_namespaces": ()}
    response:        str
    sources:         list[SourceInfo]
    conversation_id: str
    model_used:      str


class NewConversationRequest(BaseModel):
    user_id: str

class NotionSetupRequest(BaseModel):
    user_id:        str
    notion_key:     str
    notion_page_id: str


class NotionPushRequest(BaseModel):
    user_id:    str
    content:    str = Field(..., min_length=1)
    page_title: str = ""

# ── LLM ───────────────────────────────────────────────────────────────────────

def get_llm(fast: bool = False) -> ChatGoogleGenerativeAI:
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured.")
    return ChatGoogleGenerativeAI(
        model       = GEMMA_MODEL_FAST if fast else GEMMA_MODEL,
        google_api_key = GEMINI_API_KEY,
        temperature = 0.1,
        max_tokens  = 1024,
    )

def extract_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
            block.get("text", "") if isinstance(block, dict)
            else getattr(block, "text", "")
            for block in content
            if (isinstance(block, dict) and block.get("type") == "text")
            or (hasattr(block, "type") and getattr(block, "type") == "text")
            )
        return str(content)

# ── /chat — Phase 2 ───────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    RAG chat with LangGraph intent routing + STM memory.

    Flow:
    1. Validate conversation ownership
    2. Load STM context from SQLite
    3. Run LangGraph — routes to correct handler based on intent
       casual        → direct reply, no RAG
       conversational→ STM-only reply
       personal_rag  → full RAG flow
       introspect    → learning coach reflection
    4. Save messages to SQLite + trigger STM summarisation
    5. Return response + sources
    """
    # ── Validate thread ───────────────────────────────────────────────────────
    conv = await asyncio.to_thread(get_conversation, req.conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation '{req.conversation_id}' not found. "
                   f"Create one first with POST /conversations/new."
        )
    if conv["user_id"] != req.user_id:
        raise HTTPException(
            status_code=403,
            detail="This conversation does not belong to the provided user_id."
        )

    # ── Load STM ──────────────────────────────────────────────────────────────
    stm = await asyncio.to_thread(load_stm_context, req.conversation_id)

    # ── Run graph ─────────────────────────────────────────────────────────────
    try:
        result = await asyncio.to_thread(
            run_graph,
            req.message,
            req.user_id,
            req.conversation_id,
            req.api_key,
            req.fast_mode,
            stm,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Graph error: {e}")

    answer = result["final_response"]
    chunks = result.get("sources", [])

    # ── Save messages + update STM (background) ────────────────────────────────
    asyncio.create_task(asyncio.to_thread(
        save_and_update_stm,
        req.conversation_id,
        req.message,
        answer,
    ))

    # ── Format sources ────────────────────────────────────────────────────────
    sources = [
        SourceInfo(
            doc_title   = c.get("doc_title", "Unknown"),
            source_type = c.get("source_type", "unknown"),
            page        = c.get("page", ""),
            score       = c.get("score", 0.0),
        )
        for c in chunks
    ]

    return ChatResponse(
        response        = answer,
        sources         = sources,
        conversation_id = req.conversation_id,
        model_used      = GEMMA_MODEL_FAST if req.fast_mode else GEMMA_MODEL,
    )

# ── Conversation thread endpoints ──────────────────────────────────────────────

@app.post("/conversations/new")
async def new_conversation(req: NewConversationRequest):
    """
    Create a new conversation thread for a student.
    Always call this before /chat — conversation_id is required.

    Returns: { conversation_id, user_id, title, created_at, last_active }
    """
    conv = await asyncio.to_thread(create_conversation, req.user_id)
    return conv


@app.get("/conversations/{user_id}")
async def get_conversations(user_id: str):
    """
    List all conversation threads for a student, newest first.
    Returns: [ { conversation_id, title, created_at, last_active }, ... ]
    """
    convs = await asyncio.to_thread(list_conversations, user_id)
    return {"user_id": user_id, "conversations": convs}


@app.delete("/conversations/{conversation_id}")
async def remove_conversation(conversation_id: str):
    """
    Delete a conversation thread and all its messages.
    """
    conv = await asyncio.to_thread(get_conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    await asyncio.to_thread(delete_conversation, conversation_id)
    return {"status": "deleted", "conversation_id": conversation_id}


@app.get("/conversations/{conversation_id}/history")
async def conversation_history(conversation_id: str):
    """
    Return full message history for a conversation thread.
    Useful for the frontend to restore a previous chat.
    """
    from memory.sqlite_client import get_messages, count_messages
    conv = await asyncio.to_thread(get_conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    messages = await asyncio.to_thread(get_messages, conversation_id)
    count    = await asyncio.to_thread(count_messages, conversation_id)

    return {
        "conversation_id": conversation_id,
        "title":           conv["title"],
        "stm_summary":     conv["stm_summary"],
        "message_count":   count,
        "messages":        messages,
    }


# ── Permanent ingestion (unchanged from Phase 1) ───────────────────────────────

@app.post("/ingest/pdf")
async def ingest_pdf_endpoint(
    user_id:   str        = Form(...),
    doc_title: str        = Form(default=""),
    doc_type:  str        = Form(default="pdf"),
    file:      UploadFile = File(...),
):
    if Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files accepted.")
    contents = await file.read()
    if len(contents) / (1024 * 1024) > PDF_MAX_SIZE_MB:
        raise HTTPException(status_code=413, detail=f"PDF too large. Max {PDF_MAX_SIZE_MB} MB.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(contents)
        tmp_path = tmp.name
    try:
        result = ingest_pdf(
            file_path = tmp_path,
            user_id   = user_id,
            doc_type  = doc_type,
            doc_title = doc_title or Path(file.filename).stem,
        )
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        os.unlink(tmp_path)
    return result


@app.post("/ingest/image")
async def ingest_image_endpoint(
    user_id:   str        = Form(...),
    doc_title: str        = Form(default=""),
    file:      UploadFile = File(...),
):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {suffix}")
    contents = await file.read()
    if len(contents) / (1024 * 1024) > IMAGE_MAX_SIZE_MB:
        raise HTTPException(status_code=413, detail=f"Image too large. Max {IMAGE_MAX_SIZE_MB} MB.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name
    try:
        result = ingest_image(
            file_path = tmp_path,
            user_id   = user_id,
            doc_title = doc_title or Path(file.filename).stem,
        )
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        os.unlink(tmp_path)
    return result


# ── Ephemeral context (unchanged from Phase 1) ────────────────────────────────

@app.post("/context/image")
async def context_image_endpoint(
    user_id:         str        = Form(...),
    question:        str        = Form(default=""),
    conversation_id: str        = Form(default=""),
    file:            UploadFile = File(...),
):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {suffix}")
    contents = await file.read()
    if len(contents) / (1024 * 1024) > IMAGE_MAX_SIZE_MB:
        raise HTTPException(status_code=413, detail=f"Image too large. Max {IMAGE_MAX_SIZE_MB} MB.")
    try:
        image_result = process_image_for_context(
            image_bytes = contents,
            filename    = file.filename,
            question    = question,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    context_str  = format_image_context_for_llm(image_result)
    user_content = context_str
    if question:
        user_content += f"\n\nStudent's question: {question}"

    try:
        llm      = get_llm()
        response = llm.invoke([
            SystemMessage(content="You are a helpful study assistant. Use the OCR text and visual analysis to answer clearly."),
            HumanMessage(content=user_content),
        ])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    answer = extract_text(response.content)

    if conversation_id:
        conv = await asyncio.to_thread(get_conversation, conversation_id)
        if conv and conv["user_id"] == user_id:
            user_turn = f"[Image: {file.filename}]"
            if question:
                user_turn += f"\nQuestion: {question}"
            user_turn += f"\n\n{context_str}"
            asyncio.create_task(asyncio.to_thread(
                save_and_update_stm, conversation_id, user_turn, answer,
            ))

    return {
        "response":   answer,
        "ocr_text":   image_result["ocr_text"],
        "has_text":   image_result["has_text"],
        "filename":   image_result["filename"],
        "model_used": GEMMA_MODEL,
    }


# ── YouTube Transcript Tool ───────────────────────────────────────────────────

PROMPT_STYLES = {
    "bullet_summary": "Summarise this transcript as concise bullet points covering all key ideas.",
    "detailed":       "Write a detailed summary in clear paragraphs covering everything discussed.",
    "eli5":           "Explain this transcript simply, as if to a 12-year-old student.",
    "raw":            None,
}


def _extract_video_id(url: str) -> str:
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    if parsed.hostname in ("youtu.be",):
        return parsed.path.lstrip("/")
    if parsed.hostname in ("www.youtube.com", "youtube.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            if "v" in qs:
                return qs["v"][0]
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/shorts/")[1].split("/")[0]
    raise ValueError(f"Could not extract video ID from URL: {url}")


@app.get("/tools/youtube/languages")
async def youtube_languages(url: str):
    """
    Step 1 — fetch available transcript languages for a video.
    Tries common languages and reports which ones are available.
    """
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

    try:
        video_id = _extract_video_id(url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # New API — try fetching with no language preference to discover what's available
    yt_api   = YouTubeTranscriptApi()
    COMMON = ["en", "hi", "kn", "ta", "te", "bn", "ml", "mr", "gu", "pa", "ur", "es", "fr", "de", "zh", "ar", "pt", "ru", "ja", "ko"]
    available = []

    for lang in COMMON:
        try:
            fetched = yt_api.fetch(video_id, languages=[lang])
            available.append({
                "code":          lang,
                "name":          fetched.language,
                "auto_generated": fetched.is_generated,
            })
        except Exception:
            continue

    if not available:
        raise HTTPException(
            status_code=422,
            detail="No captions available for this video, or the video is restricted."
        )

    return {"video_id": video_id, "languages": available}


class YouTubeToolRequest(BaseModel):
    url:             str
    language_code:   str
    prompt_style:    str = "bullet_summary"
    custom_prompt:   str = ""
    output_language: str = "English"
    conversation_id: str = ""
    user_id:         str = ""


@app.post("/tools/youtube")
async def youtube_tool(req: YouTubeToolRequest):
    """
    Step 2 — fetch transcript in selected language, process with LLM.
    """
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

    try:
        video_id = _extract_video_id(req.url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # ── Fetch transcript ──────────────────────────────────────────────────────
    try:
        yt_api     = YouTubeTranscriptApi()
        fetched    = yt_api.fetch(video_id, languages=[req.language_code])
        raw_transcript  = " ".join(chunk.text for chunk in fetched).strip()
        auto_generated  = fetched.is_generated
        detected_lang   = fetched.language
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Could not fetch transcript in '{req.language_code}'. "
                   f"Try checking available languages first via GET /tools/youtube/languages. Error: {e}"
        )

    # ── Raw mode — skip LLM ───────────────────────────────────────────────────
    # Replace the raw mode return block:
    if req.prompt_style == "raw":
        if req.conversation_id and req.user_id:
            conv = await asyncio.to_thread(get_conversation, req.conversation_id)
            if conv and conv["user_id"] == req.user_id:
                user_turn = f"[YouTube: {req.url}]\nStyle: raw"
                asyncio.create_task(asyncio.to_thread(
                    save_and_update_stm,
                    req.conversation_id,
                    user_turn,
                    raw_transcript,
                ))
        return {
            "video_id":          video_id,
            "processed_text":    raw_transcript,
            "raw_transcript":    raw_transcript,
            "auto_generated":    auto_generated,
            "detected_language": detected_lang,
            "output_language":   req.output_language,
            "prompt_style":      "raw",
        }

    # ── Build prompt ──────────────────────────────────────────────────────────
    if req.prompt_style == "custom" and req.custom_prompt.strip():
        base_prompt = req.custom_prompt.strip()
    else:
        base_prompt = PROMPT_STYLES.get(req.prompt_style, PROMPT_STYLES["bullet_summary"])

    if req.output_language.lower() != "english":
        base_prompt += f" Respond in {req.output_language}."

    # ── Call LLM ─────────────────────────────────────────────────────────────
    try:
        llm      = get_llm()
        response = llm.invoke([
            SystemMessage(content="You are a helpful study assistant that processes video transcripts for students."),
            HumanMessage(content=f"{base_prompt}\n\nTranscript:\n{raw_transcript[:6000]}"),
        ])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    if req.conversation_id and req.user_id:
        conv = await asyncio.to_thread(get_conversation, req.conversation_id)
        if conv and conv["user_id"] == req.user_id:
            user_turn = f"[YouTube: {req.url}]\nStyle: {req.prompt_style}"
            asyncio.create_task(asyncio.to_thread(
                save_and_update_stm,
                req.conversation_id,
                user_turn,
                extract_text(response.content),
            ))

    return {
        "video_id":          video_id,
        "processed_text":    extract_text(response.content),
        "raw_transcript":    raw_transcript,
        "auto_generated":    auto_generated,
        "detected_language": detected_lang,
        "output_language":   req.output_language,
        "prompt_style":      req.prompt_style,
    }
    
    
# ── Notion endpoints ──────────────────────────────────────────────────────────

@app.post("/notion/setup")
async def notion_setup(req: NotionSetupRequest):
    """
    Save Notion credentials for a user.
    Validates the key + page ID against Notion API before saving.
    Student needs to:
      1. Create a Notion integration at notion.so/my-integrations
      2. Share their master page with the integration
      3. Paste the integration token + page ID here
    """
    try:
        valid = await asyncio.to_thread(
            verify_notion_connection,
            req.notion_key,
            req.notion_page_id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Notion API: {e}")

    if not valid:
        raise HTTPException(
            status_code=422,
            detail="Invalid Notion key or page ID. "
                   "Make sure you shared the page with your integration."
        )

    await asyncio.to_thread(
        save_user_settings,
        req.user_id,
        req.notion_key,
        req.notion_page_id,
    )

    return {"status": "ok", "message": "Notion connected successfully."}


@app.get("/notion/status/{user_id}")
async def notion_status(user_id: str):
    """Check if Notion is connected for a user."""
    settings = await asyncio.to_thread(get_user_settings, user_id)
    if not settings or not settings.get("notion_key"):
        return {"connected": False}
    return {
        "connected":      True,
        "notion_page_id": settings["notion_page_id"],
        "updated_at":     settings["updated_at"],
    }


@app.post("/notion/push")
async def notion_push(req: NotionPushRequest):
    """
    Push a single assistant response to Notion as a dated subpage.
    Student selects any response in chat and clicks Push to Notion.
    No LLM involved — content pushed as-is.
    """
    settings = await asyncio.to_thread(get_user_settings, req.user_id)
    if not settings or not settings.get("notion_key"):
        raise HTTPException(
            status_code=422,
            detail="Notion not connected. Set up via POST /notion/setup first."
        )

    try:
        result = await asyncio.to_thread(
            push_to_notion,
            settings["notion_key"],
            settings["notion_page_id"],
            req.content,
            req.page_title,
        )
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return result
# ── Utility ───────────────────────────────────────────────────────────────────

@app.get("/my/docs/{user_id}")
async def my_docs(user_id: str):
    stats = personal_collection_stats(user_id)
    return {
        "user_id":    user_id,
        "collection": stats["collection"],
        "doc_count":  stats["count"],
    }


@app.get("/health")
async def health():
    collections = list_user_collections()
    return {
        "status":          "ok",
        "phase":           "2",
        "active_students": len(collections),
        "collections":     collections,
    }


@app.get("/")
async def root():
    return {
        "message": "Campus Assistant API — Phase 3",
        "docs":    "/docs",
        "health":  "/health",
    }