"""
graph/intent_router.py — Hybrid intent classifier.

Step 1: Rule-based check — obvious patterns, zero LLM, instant.
Step 2: LLM classification — Gemma fast model, ~50 tokens, for ambiguous messages.

Intent categories:
  casual         → greetings, thanks, acknowledgements
  conversational → follow-ups, clarifications, references to prior context
  personal_rag   → study queries that need document retrieval
  introspect     → self-reflection on learning activity
"""

from __future__ import annotations

import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from config import GEMMA_MODEL_FAST, GEMINI_API_KEY

# ── Rule-based patterns ────────────────────────────────────────────────────────

# Obvious casual — greetings and acknowledgements in EN / HI / KN
CASUAL_PATTERNS = [
    r"^(hi|hello|hey|hii+|helo)\b",
    r"^(thanks|thank you|thx|ty|thank)\b",
    r"^(ok|okay|alright|got it|sure|fine|good)\b",
    r"^(bye|goodbye|see you|cya)\b",
    r"^(haan|ha|theek hai|theek|shukriya|dhanyavaad|sari|naan|acha|accha)\b",
    r"^(👍|👋|🙏|😊|✅)$",
    r"^(yes|no|nope|yep|yup)\b",
]

# Obvious RAG triggers — study queries that clearly need retrieval
RAG_PATTERNS = [
    r"\b(explain|summarise|summarize|summary|quiz|test me|find|search)\b",
    r"\b(what is|what are|define|definition|describe|how does|how do)\b",
    r"\b(notes|lecture|chapter|topic|concept|formula|theorem|equation)\b",
    r"\b(samjhao|samjha|batao|dhundho|quiz do|notes dikhao)\b",   # Hindi
    r"\b(helri|summary maadi|quiz kodi|nodri|explain maadi)\b",    # Kannada
]

# Obvious introspect triggers
INTROSPECT_PATTERNS = [
    r"\b(what have i (studied|uploaded|learned|covered|read))\b",
    r"\b(my (progress|learning|study) (pattern|journey|history|summary))\b",
    r"\b(how (much|many) (have i|did i))\b",
    r"\b(what topics|which topics|topics covered)\b",
    r"\b(avalokana|introspect|reflect|meri progress|maine kya padha)\b",
]

VALID_INTENTS = {"casual", "conversational", "personal_rag", "introspect"}

_CLASSIFIER_SYSTEM = """You are an intent classifier for a student study assistant.
Classify the student's message into exactly ONE of these intents:

casual         — greeting, thanks, acknowledgement, filler (hi, ok, thanks, bye)
conversational — follow-up or clarification on something already discussed (explain that again, what did you mean, continue)
personal_rag   — a study question needing document retrieval (explain X, summarise chapter, find notes on Y, quiz me)
introspect     — self-reflection on learning activity (what have I studied, my progress, topics covered, learning journey)

Reply with ONLY the single intent word. No explanation. No punctuation."""


def _matches_any(text: str, patterns: list[str]) -> bool:
    text = text.strip().lower()
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _llm_classify(query: str, api_key: str) -> str:
    """
    Call Gemma fast model to classify intent.
    Returns one of: casual / conversational / personal_rag / introspect
    Falls back to 'personal_rag' if classification fails or returns unexpected value.
    """
    key = api_key.strip() if api_key.strip() else GEMINI_API_KEY
    try:
        llm = ChatGoogleGenerativeAI(
            model          = GEMMA_MODEL_FAST,
            google_api_key = key,
            temperature    = 0.0,
            max_tokens     = 10,    # we only need one word
        )
        response = llm.invoke([
            SystemMessage(content=_CLASSIFIER_SYSTEM),
            HumanMessage(content=f"Student message: {query}"),
        ])
        # Extract text content
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
        return intent if intent in VALID_INTENTS else "personal_rag"
    except Exception as e:
        print(f"[intent_router] LLM classification failed: {e} — defaulting to personal_rag")
        return "personal_rag"


def classify_intent(query: str, api_key: str = "") -> str:
    """
    Hybrid intent classifier.

    Step 1 — Rule-based: catches obvious patterns instantly.
    Step 2 — LLM: handles ambiguous messages.

    Args:
        query:   Student's message.
        api_key: User's Google AI Studio key (falls back to server key).

    Returns:
        One of: casual / conversational / personal_rag / introspect
    """
    # ── Step 1: Rule-based ────────────────────────────────────────────────────
    # Short messages (≤4 words) that match casual patterns → instant casual
    word_count = len(query.strip().split())
    if word_count <= 4 and _matches_any(query, CASUAL_PATTERNS):
        print(f"[intent_router] Rule → casual (short match): '{query}'")
        return "casual"

    if _matches_any(query, INTROSPECT_PATTERNS):
        print(f"[intent_router] Rule → introspect: '{query}'")
        return "introspect"

    if _matches_any(query, RAG_PATTERNS):
        print(f"[intent_router] Rule → personal_rag: '{query}'")
        return "personal_rag"

    # ── Step 2: LLM classification ────────────────────────────────────────────
    intent = _llm_classify(query, api_key)
    print(f"[intent_router] LLM → {intent}: '{query}'")
    return intent
