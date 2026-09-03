"""
graph/graph.py — LangGraph graph definition for Campus Assistant.

Wires all nodes together and exposes run_graph() for main.py to call.

Graph structure:
 #   START → route_intent → [conversational | personal_rag | introspect] → END
 
Each intent routes to its own handler node.
No shared synthesis node needed — each handler produces its own final_response.
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from graph.state import GraphState
from graph.nodes import (
    route_intent,
    handle_conversational,
    handle_personal_rag,
    handle_introspect,
)
from memory.stm_manager import STMContext


def _route_condition(state: GraphState) -> str:
    """Conditional edge — reads intent from state, returns node name."""
    return state.get("intent", "personal_rag")


def build_graph() -> StateGraph:
    """
    Build and compile the LangGraph state graph.
    Called once at startup — compiled graph is reused for every request.

    Graph structure:
      START → route_intent → [conversational | personal_rag | introspect] → END
    """
    graph = StateGraph(GraphState)

    # ── Add nodes ─────────────────────────────────────────────────────────────
    graph.add_node("route_intent",   route_intent)
    graph.add_node("conversational", handle_conversational)
    graph.add_node("personal_rag",   handle_personal_rag)
    graph.add_node("introspect",     handle_introspect)

    # ── Entry point ───────────────────────────────────────────────────────────
    graph.set_entry_point("route_intent")

    # ── Conditional routing after intent classification ────────────────────────
    graph.add_conditional_edges(
        "route_intent",
        _route_condition,
        {
            "conversational": "conversational",
            "personal_rag":   "personal_rag",
            "introspect":     "introspect",
        }
    )

    # ── All handlers go to END ────────────────────────────────────────────────
    graph.add_edge("conversational", END)
    graph.add_edge("personal_rag",   END)
    graph.add_edge("introspect",     END)

    return graph.compile()

# ── Module-level compiled graph — built once on import ────────────────────────
_graph = build_graph()


def run_graph(
    query:           str,
    user_id:         str,
    conversation_id: str,
    api_key:         str,
    fast_mode:       bool,
    stm:             STMContext,
) -> dict:
    """
    Run the intent graph for one chat turn.

    Args:
        query:           Student's message.
        user_id:         For ChromaDB collection scoping.
        conversation_id: For SQLite history lookup (introspect).
        api_key:         User's Google AI Studio key.
        fast_mode:       Use faster model variant.
        stm:             Loaded STM context (summary + recent messages).

    Returns:
        { "final_response": str, "sources": list }
    """
    initial_state: GraphState = {
        # Input
        "query":           query,
        "user_id":         user_id,
        "conversation_id": conversation_id,
        "api_key":         api_key,
        "fast_mode":       fast_mode,

        # STM — pre-loaded before graph runs
        "stm_summary":     stm.summary,
        "recent_messages": stm.recent,

        # Routing — set by route_intent node
        "intent": "",

        # RAG — set by handle_personal_rag node
        "retrieved_chunks": [],
        "rag_context":      "",

        # Introspect — set by handle_introspect node
        "doc_titles":         [],
        "conversation_stats": {},

        # Output — set by whichever handler runs
        "final_response": "",
        "sources":        [],
    }

    result = _graph.invoke(initial_state)

    return {
        "final_response": result.get("final_response", ""),
        "sources":        result.get("sources", []),
        "intent":         result.get("intent", ""),
    }
