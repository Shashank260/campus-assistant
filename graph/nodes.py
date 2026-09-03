"""
graph/nodes.py — All LangGraph node functions for Campus Assistant.

Each function takes GraphState, does one job, returns updated state fields.

Nodes:
  route_intent          → classifies query, sets state["intent"]
  handle_conversational → greetings, general knowledge, follow-ups — no RAG
  handle_personal_rag   → full RAG flow
  handle_introspect     → learning coach flow
"""

from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from config import (
    GEMINI_API_KEY,
    GEMMA_MODEL,
    GEMMA_MODEL_FAST,
    SYSTEM_PROMPT,
    CONVERSATIONAL_PROMPT,    
)
from graph.intent_router import classify_intent
from graph.state import GraphState
from retrieval.retriever import retrieve, format_context
from retrieval.chroma_client import get_personal_collection


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _get_llm(state: GraphState) -> ChatGoogleGenerativeAI:
    key = state["api_key"].strip() if state.get("api_key", "").strip() else GEMINI_API_KEY
    return ChatGoogleGenerativeAI(
        model          = GEMMA_MODEL_FAST if state.get("fast_mode") else GEMMA_MODEL,
        google_api_key = key,
        temperature    = 0.1,
        max_tokens     = 1024,
    )


def _extract_text(content) -> str:
    """Extract plain text from LLM response — handles thinking block models."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else getattr(b, "text", "")
            for b in content
            if (isinstance(b, dict) and b.get("type") == "text")
            or (hasattr(b, "type") and getattr(b, "type") == "text")
        )
    return str(content)


def _build_stm_messages(state: GraphState) -> list:
    """Build message history from STM for LLM context."""
    messages = []
    if state.get("stm_summary"):
        messages.append(SystemMessage(
            content=f"[Memory from earlier in this conversation]\n{state['stm_summary']}"
        ))
    for msg in state.get("recent_messages", []):
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    return messages


# ── Node 1: Route intent ───────────────────────────────────────────────────────

def route_intent(state: GraphState) -> GraphState:
    """
    Classify the student's query and set state["intent"].
    Uses hybrid rule-based + LLM classifier with doc titles injected.
    """
    intent = classify_intent(
        query   = state["query"],
        api_key = state.get("api_key", ""),
        user_id = state.get("user_id", ""),
    )
    return {**state, "intent": intent}

# ── Node 3: Handle conversational ─────────────────────────────────────────────

def handle_conversational(state: GraphState) -> GraphState:
    """
    Reply to greetings, general knowledge questions, follow-ups and clarifications.
    Casual messages (hi, thanks, ok) are also handled here — no separate casual node.
    Uses full STM context (summary + recent messages).
    No RAG retrieval.
    """
    messages = [SystemMessage(content=CONVERSATIONAL_PROMPT)]
    messages += _build_stm_messages(state)
    messages.append(HumanMessage(content=state["query"]))

    try:
        llm      = _get_llm(state)
        response = llm.invoke(messages)
        answer   = _extract_text(response.content)
    except Exception as e:
        answer = "I'm having trouble recalling that — could you rephrase?"
        print(f"[nodes] conversational LLM failed: {e}")

    return {**state, "final_response": answer, "sources": []}


# ── Node 4: Handle personal RAG ───────────────────────────────────────────────

def handle_personal_rag(state: GraphState) -> GraphState:
    """
    Full RAG flow — retrieve chunks + LLM response.
    Uses system prompt + STM + RAG context + query.
    """
    # ── Retrieve ──────────────────────────────────────────────────────────────
    chunks      = retrieve(query=state["query"], user_id=state["user_id"])
    rag_context = format_context(chunks)

    # ── Build prompt ──────────────────────────────────────────────────────────
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    messages += _build_stm_messages(state)
    messages.append(HumanMessage(content=(
        f"Context from student's uploaded documents:\n\n{rag_context}"
        f"\n\nStudent question: {state['query']}"
    )))

    try:
        llm      = _get_llm(state)
        response = llm.invoke(messages)
        answer   = _extract_text(response.content)
    except Exception as e:
        answer = "I had trouble processing that. Please try again."
        print(f"[nodes] personal_rag LLM failed: {e}")

    sources = [
        {
            "doc_title":   c["metadata"].get("doc_title", c["metadata"].get("filename", "Unknown")),
            "source_type": c["metadata"].get("source_type", "unknown"),
            "page":        c["metadata"].get("page", ""),
            "score":       c["score"],
        }
        for c in chunks
    ]

    return {
        **state,
        "retrieved_chunks": chunks,
        "rag_context":      rag_context,
        "final_response":   answer,
        "sources":          sources,
    }


# ── Node 5: Handle introspect ─────────────────────────────────────────────────

INTROSPECT_SYSTEM = """<role>
You are an empathetic, metrics-driven Academic Performance Coach. Your task is to analyze a student's system telemetry data (uploaded assets, chronological chat topic strings, and message volumes) to build a clear, actionable dashboard review of their learning patterns.
</role>

<instructions>
1. ANALYSIS STRATEGY: 
   - Cross-reference the user's active discussion history against their uploaded knowledge base files.
   - Actively identify structural blind spots. For instance, if they uploaded "Computer_Networks_Syllabus.pdf" but their last 10 chat entries are exclusively about "Operating Systems", point out that they have not initiated lookups on their networking materials yet.
2. ENGAGEMENT MODEL: Do not answer direct subject-matter questions. If they ask you how an algorithm works inside this node, re-route them by saying: "Let's track that subject directly in the chat panel! From a coaching perspective, that aligns perfectly with your notes on..."
3. PRESENTATION STRUCTURE: 
   - Format your review using a clean, scannable dashboard layout.
   - Use a clear Markdown table to map out **Covered Concepts** vs. **Neglected Core Materials**.
   - Conclude with a punchy, 2-bullet-point action plan for their next study session.
4. PERSONALITY: Inspiring, data-oriented, and highly encouraging. Speak directly to their growth metrics.
</instructions>"""


def _get_doc_titles(user_id: str) -> list[dict]:
    """
    Fetch unique document titles from the student's ChromaDB collection.
    Returns list of { doc_title, source_type } dicts.
    """
    try:
        collection = get_personal_collection(user_id)
        # Get all items — we only need metadata
        result = collection._collection.get(include=["metadatas"])
        seen   = set()
        titles = []
        for meta in result.get("metadatas", []):
            key = (meta.get("doc_title", ""), meta.get("source_type", ""))
            if key not in seen and key[0]:
                seen.add(key)
                titles.append({
                    "doc_title":   meta.get("doc_title", "Unknown"),
                    "source_type": meta.get("source_type", "unknown"),
                })
        return titles
    except Exception as e:
        print(f"[nodes] doc title fetch failed: {e}")
        return []


def _get_conversation_stats(conversation_id: str) -> dict:
    """
    Fetch conversation statistics from SQLite.
    Returns message count, date range, and sample topics.
    """
    from memory.sqlite_client import get_messages, count_messages, get_conversation
    try:
        count    = count_messages(conversation_id)
        messages = get_messages(conversation_id)
        conv     = get_conversation(conversation_id)

        # Extract user messages only for topic analysis
        user_msgs = [m["content"] for m in messages if m["role"] == "user"]

        return {
            "total_messages": count,
            "created_at":     conv.get("created_at", "") if conv else "",
            "last_active":    conv.get("last_active", "") if conv else "",
            "user_messages":  user_msgs[-10:],   # last 10 for topic analysis
            "stm_summary":    conv.get("stm_summary", "") if conv else "",
        }
    except Exception as e:
        print(f"[nodes] conversation stats failed: {e}")
        return {}


def handle_introspect(state: GraphState) -> GraphState:
    """
    Learning coach reflection on the student's study activity.
    Combines ChromaDB doc titles + SQLite conversation history.
    Uses a different system prompt — mentor/coach tone.
    """
    # ── Gather data ───────────────────────────────────────────────────────────
    doc_titles = _get_doc_titles(state["user_id"])
    conv_stats = _get_conversation_stats(state["conversation_id"])

    # ── Format context for LLM ────────────────────────────────────────────────
    docs_text = "\n".join(
        f"  - {d['doc_title']} ({d['source_type']})" for d in doc_titles
    ) or "  No documents uploaded yet."

    msgs_text = "\n".join(
        f"  - {m[:120]}" for m in conv_stats.get("user_messages", [])
    ) or "  No conversation history yet."

    summary_text = conv_stats.get("stm_summary", "") or "No summary available yet."

    introspect_context = f"""Student's knowledge base:
{docs_text}

Recent questions asked by student:
{msgs_text}

Conversation summary so far:
{summary_text}

Total messages in this conversation: {conv_stats.get('total_messages', 0)}
Conversation started: {conv_stats.get('created_at', 'Unknown')}
Last active: {conv_stats.get('last_active', 'Unknown')}"""

    messages = [
        SystemMessage(content=INTROSPECT_SYSTEM),
        HumanMessage(content=(
            f"Student's learning data:\n\n{introspect_context}"
            f"\n\nStudent's question: {state['query']}"
        )),
    ]

    try:
        llm      = _get_llm(state)
        response = llm.invoke(messages)
        answer   = _extract_text(response.content)
    except Exception as e:
        answer = "I'm having trouble analysing your learning journey right now. Please try again."
        print(f"[nodes] introspect LLM failed: {e}")

    return {
        **state,
        "doc_titles":         doc_titles,
        "conversation_stats": conv_stats,
        "final_response":     answer,
        "sources":            [],
    }
