"""
graph/intent_router.py — Hybrid intent classifier.

Step 1: Rule-based check — obvious patterns, zero LLM, instant.
Step 2: LLM classification — Gemma fast model, with user's doc titles injected.

Intent categories:
  conversational → greetings, thanks, follow-ups, general knowledge, clarifications
  personal_rag   → study queries that match the student's uploaded documents
  introspect     → self-reflection on learning activity
"""

from __future__ import annotations

import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from config import GEMMA_MODEL_FAST, GEMINI_API_KEY

# ── Rule-based patterns ────────────────────────────────────────────────────────

# Obvious RAG triggers — only very specific study actions, not generic what/how
RAG_PATTERNS = [
    r"\b(explain|summarise|summarize|summary|quiz|test me)\b",
    r"\b(notes|lecture|chapter|topic|concept|formula|theorem|equation)\b",
    r"\b(find in my|search my|from my notes|in my documents|from my docs)\b",
    r"\b(samjhao|samjha|batao|dhundho|quiz do|notes dikhao)\b",   # Hindi
    r"\b(helri|summary maadi|quiz kodi|nodri|explain maadi)\b",    # Kannada
    r"\b(what is|how does|why is|explain the difference|define|derive)\b"
]

# Obvious introspect triggers
INTROSPECT_PATTERNS = [
    r"\b(what have i (studied|uploaded|learned|covered|read))\b",
    r"\b(my (progress|learning|study) (pattern|journey|history|summary))\b",
    r"\b(how (much|many) (have i|did i))\b",
    r"\b(what topics|which topics|topics covered)\b",
    r"\b(avalokana|introspect|reflect|meri progress|maine kya padha)\b",
]

VALID_INTENTS = {"conversational", "personal_rag", "introspect"}

_CLASSIFIER_SYSTEM = """<role>
You are a deterministic, high-speed intent classification node in a student graph architecture. Your sole job is to evaluate a raw incoming student string and output exactly one token representing the intent category.
</role>

<knowledge_base_state>
The student has currently uploaded these files to their personal database directory:
{doc_titles}
</knowledge_base_state>

<intent_categories>
- conversational: Default fallback status. Greetings ("hi", "hello"), parting acknowledgments ("thanks", "bye"), casual validation loops ("ok", "makes sense"), generic programming questions, or broad general knowledge prompts (e.g., "explain how linear regression optimization works from scratch") that do NOT refer to any items listed in the <knowledge_base_state>.
- personal_rag: High-priority data path. Triggered ONLY if the query specifically references a document title listed above, or demands structural lookup from their materials (e.g., "explain chapter 3 from my notes", "quiz me on the OS syllabus", "what does the uploaded guide say about virtual memory?").
- introspect: Metacognitive data path. Triggered when the student wants an evaluation of their own usage habits, covered topics, upload counts, or progress history (e.g., "what have I studied today?", "give me my progress summary", "summarize the current chat so far").
</intent_categories>

<strict_rules>
1. CRITICAL: If a question is general knowledge and does not directly reference or heavily imply an uploaded document title listed in <knowledge_base_state>, you MUST classify it as "conversational". Do not force a RAG lookup if they do not have relevant files.
2. OUTPUT CONSTRAINT: Output exactly ONE of these exact lowercase text strings: "conversational", "personal_rag", or "introspect".
3. ZERO TOLERANCE: Do not include punctuation, markdown backticks, whitespaces, trailing periods, or introductory commentary. The response must be a single, raw string token.
</strict_rules>"""


def _matches_any(text: str, patterns: list[str]) -> bool:
    text = text.strip().lower()
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _fetch_doc_titles(user_id: str) -> str:
    """
    Fetch user's uploaded document titles from ChromaDB.
    Returns formatted string for LLM prompt injection.
    Falls back to empty string if fetch fails.
    """
    try:
        from retrieval.chroma_client import get_personal_collection
        collection = get_personal_collection(user_id)
        result     = collection._collection.get(include=["metadatas"])
        seen       = set()
        titles     = []
        for meta in result.get("metadatas", []):
            title = meta.get("doc_title", "")
            if title and title not in seen:
                seen.add(title)
                source = meta.get("source_type", "unknown")
                titles.append(f"  - {title} ({source})")
        if not titles:
            return "  No documents uploaded yet."
        return "\n".join(titles)
    except Exception as e:
        print(f"[intent_router] doc title fetch failed: {e}")
        return "  Could not fetch documents."


def _llm_classify(query: str, api_key: str, doc_titles: str) -> str:
    """
    Call Gemma fast model to classify intent.
    Injects user's doc titles so model can make context-aware decision.
    Falls back to 'conversational' if classification fails.
    """
    key = api_key.strip() if api_key.strip() else GEMINI_API_KEY
    try:
        llm = ChatGoogleGenerativeAI(
            model          = GEMMA_MODEL_FAST,
            google_api_key = key,
            temperature    = 0.0,
            max_tokens     = 10,
        )
        system_prompt = _CLASSIFIER_SYSTEM.format(doc_titles=doc_titles)
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Student message: {query}"),
        ])
        content = response.content
        if isinstance(content, list):
            content = "".join(
                b.get("text", "") if isinstance(b, dict) else getattr(b, "text", "")
                for b in content if (
                    isinstance(b, dict) and b.get("type") == "text"
                ) or (
                    hasattr(b, "type") and getattr(b, "type") == "text"
                )
            )
        intent = content.strip().lower().rstrip(".")
        return intent if intent in VALID_INTENTS else "conversational"
    except Exception as e:
        print(f"[intent_router] LLM classification failed: {e} — defaulting to conversational")
        return "conversational"


def classify_intent(query: str, api_key: str = "", user_id: str = "") -> str:
    """
    Hybrid intent classifier.

    Step 1 — Rule-based: catches obvious patterns instantly.
    Step 2 — LLM: handles ambiguous messages with doc titles injected.

    Args:
        query:   Student's message.
        api_key: User's Google AI Studio key (falls back to server key).
        user_id: Used to fetch doc titles for context-aware LLM classification.

    Returns:
        One of: conversational / personal_rag / introspect
    """
    # ── Step 1: Rule-based ────────────────────────────────────────────────────
    if _matches_any(query, INTROSPECT_PATTERNS):
        print(f"[intent_router] Rule -> introspect: '{query}'")
        return "introspect"

    if _matches_any(query, RAG_PATTERNS):
        print(f"[intent_router] Rule -> personal_rag: '{query}'")
        return "personal_rag"

    # ── Step 2: LLM classification with doc titles ────────────────────────────
    doc_titles = _fetch_doc_titles(user_id) if user_id else "  No documents available."
    intent     = _llm_classify(query, api_key, doc_titles)
    print(f"[intent_router] LLM -> {intent}: '{query}'")
    return intent