"""
stm_manager.py — Short Term Memory manager.

Strategy (from spec):
- Keep last 6 full messages as a sliding window.
- When count exceeds 6: summarise the older messages via Gemma 4,
  persist summary to SQLite, then keep summary + last 3 full messages.
- Every LLM call receives:
    system_prompt + stm_summary + last_3_messages + retrieved_chunks + query
- Target total context per call: under 3000 tokens (~12000 chars).

The STMContext dataclass is what main.py passes into the chat prompt.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from config import (
    GEMINI_API_KEY,
    GEMMA_MODEL_FAST,      # use fast model for summarisation — saves quota
    STM_FULL_WINDOW,
    STM_RECENT_WINDOW,
)
from memory.sqlite_client import (
    get_messages,
    count_messages,
    update_stm_summary,
    get_conversation,
)


@dataclass
class STMContext:
    """
    Everything the LLM needs from memory for one chat turn.
    main.py unpacks this into the prompt.
    """
    summary:       str         # summarised older messages ("" if not yet needed)
    recent:        list[dict]  # last N full messages [{"role": ..., "content": ...}]
    total_messages: int        # total message count in this thread


_SUMMARISE_PROMPT = """You are summarising a student's study conversation to compress memory.
Write a concise factual summary (max 150 words) of what was discussed.
Focus on: topics studied, questions asked, key answers given, any documents referenced.
Do not add commentary. Just the summary."""

# TODO: accept api_key param after MongoDB integration
def _get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=GEMMA_MODEL_FAST,
        google_api_key=GEMINI_API_KEY,
        temperature=0.0,    # summaries should be deterministic
        max_tokens=300,
    )


def _messages_to_text(messages: list[dict]) -> str:
    """Convert message dicts to a readable transcript for summarisation."""
    lines = []
    for m in messages:
        role = "Student" if m["role"] == "user" else "Assistant"
        lines.append(f"{role}: {m['content']}")
    return "\n\n".join(lines)


def _summarise_messages(messages: list[dict]) -> str:
    """
    Call Gemma 4 (fast variant) to summarise a list of messages.
    Returns the summary string.
    Falls back to a plain concatenation if the LLM call fails —
    better to have noisy context than crash the chat.
    """
    transcript = _messages_to_text(messages)
    try:
        llm      = _get_llm()
        response = llm.invoke([
            SystemMessage(content=_SUMMARISE_PROMPT),
            HumanMessage(content=f"Conversation to summarise:\n\n{transcript}"),
        ])
        content = response.content
        if isinstance(content, list):
            content = "".join(
                b.get("text", "") if isinstance(b, dict) else getattr(b, "text", "")
                for b in content
                if (isinstance(b, dict) and b.get("type") == "text")
                or (hasattr(b, "type") and getattr(b, "type") == "text")
            )
        elif isinstance(content, dict):
            content = content.get("text", "")
        return content.strip()
    except Exception as e:
        print(f"[stm] Summarisation failed (using fallback): {e}")
        # Fallback: truncate transcript to first 500 chars
        return f"[Summary unavailable — prior context]: {transcript[:500]}"


def load_stm_context(conversation_id: str) -> STMContext:
    """
    Load STM context for a conversation.

    Logic:
    - Fetch total message count.
    - If count > STM_FULL_WINDOW (6): summarisation mode.
        - Return existing summary from SQLite + last STM_RECENT_WINDOW (3) messages.
    - Else: full window mode.
        - Return empty summary + all messages so far.

    NOTE: Summarisation is triggered by save_and_update_stm() AFTER saving
    the new messages, not here. This function only reads.
    """
    conv  = get_conversation(conversation_id)
    total = count_messages(conversation_id)

    if conv is None:
        return STMContext(summary="", recent=[], total_messages=0)

    existing_summary = conv.get("stm_summary", "")

    if total > STM_FULL_WINDOW:
        # Summarisation has (or should have) already happened.
        # Return persisted summary + last STM_RECENT_WINDOW messages.
        recent = get_messages(conversation_id, limit=STM_RECENT_WINDOW)
        return STMContext(
            summary        = existing_summary,
            recent         = recent,
            total_messages = total,
        )
    else:
        # Still within the full window — return everything.
        recent = get_messages(conversation_id)
        return STMContext(
            summary        = "",
            recent         = recent,
            total_messages = total,
        )


def save_and_update_stm(
    conversation_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    """
    Called AFTER a successful LLM response.
    1. Saves both the user and assistant messages to SQLite.
    2. Checks if total count now exceeds STM_FULL_WINDOW.
    3. If yes: summarises the older messages and persists the summary.

    This is synchronous — called via asyncio.to_thread() in main.py.
    """
    from memory.sqlite_client import save_message, count_messages, touch_conversation, _make_title

    # Check if this is the very first message in the conversation thread
    is_first_message = (count_messages(conversation_id) == 0)

    save_message(conversation_id, "user",      user_message)
    save_message(conversation_id, "assistant", assistant_message)

    # Automatically set conversation title from the first message
    if is_first_message:
        new_title = _make_title(user_message)
        touch_conversation(conversation_id, title=new_title)

    total = count_messages(conversation_id)

    if total > STM_FULL_WINDOW:
        # Get all messages older than the recent window
        all_messages    = get_messages(conversation_id)
        older_messages  = all_messages[:-STM_RECENT_WINDOW]

        if older_messages:
            print(f"[stm] Summarising {len(older_messages)} older messages for {conversation_id}")
            summary = _summarise_messages(older_messages)
            update_stm_summary(conversation_id, summary)


def build_prompt_messages(
    stm: STMContext,
    system_prompt: str,
    rag_context: str,
    user_query: str,
) -> list:
    """
    Assemble the full message list for the LLM call.

    Order:
    1. System prompt
    2. STM summary (if exists) — injected as a system-level memory note
    3. Recent messages (last N turns) — gives the model conversation continuity
    4. Current user message with RAG context

    This keeps total context predictable and under STM_MAX_TOKENS.
    """
    
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

    messages = [SystemMessage(content=system_prompt)]

    # Inject summary as a memory note so the model knows prior context
    if stm.summary:
        messages.append(SystemMessage(
            content=f"[Memory from earlier in this conversation]\n{stm.summary}"
        ))

    # Replay recent messages so the model has conversational continuity
    for msg in stm.recent:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    # Current turn: RAG context + user query
    messages.append(HumanMessage(content=(
        f"Context from student's uploaded documents:\n\n{rag_context}"
        f"\n\nStudent question: {user_query}"
    )))

    return messages
