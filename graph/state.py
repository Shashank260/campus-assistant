"""
graph/state.py — LangGraph state definition for Campus Assistant.

GraphState flows through every node in the graph.
Each node reads what it needs and writes its outputs back to state.
"""

from __future__ import annotations
from typing import TypedDict


class GraphState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────────
    query:           str        # student's message
    user_id:         str        # determines which ChromaDB collection to query
    conversation_id: str        # SQLite thread ID
    api_key:         str        # user's Google AI Studio key
    fast_mode:       bool       # True → use GEMMA_MODEL_FAST

    # ── STM (loaded before graph runs) ────────────────────────────────────────
    stm_summary:     str        # summarised older messages ("" if not yet needed)
    recent_messages: list       # last N full message dicts

    # ── Routing ────────────────────────────────────────────────────────────────
    intent: str
    # casual        → hi/thanks/bye — system prompt + summary only
    # conversational→ follow-up/clarification — STM only, no RAG
    # personal_rag  → explain/quiz/find — full RAG flow
    # introspect    → what have I studied — learning coach flow

    # ── RAG (populated by personal_rag node) ──────────────────────────────────
    retrieved_chunks: list      # raw chunk dicts from retriever
    rag_context:      str       # formatted context string for LLM

    # ── Introspect data (populated by introspect node) ────────────────────────
    doc_titles:         list    # document titles from ChromaDB metadata
    conversation_stats: dict    # message counts, dates from SQLite

    # ── Output ─────────────────────────────────────────────────────────────────
    final_response: str         # LLM response text
    sources:        list        # source dicts for frontend citation display
