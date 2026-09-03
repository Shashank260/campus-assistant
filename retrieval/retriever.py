"""
retriever.py — Retrieve relevant chunks from a student's personal ChromaDB collection.

All retrieval is scoped to personal_{user_id}. No shared/central collection.

ChromaDB similarity_search_with_score returns cosine distance (lower = more similar).
We convert to similarity score (higher = better) for consistent threshold logic.
"""
from __future__ import annotations
from langchain_core.documents import Document
from retrieval.chroma_client import get_personal_collection
from config import TOP_K, SCORE_THRESHOLD
from typing import Optional


def retrieve(
    query: str,
    user_id: str,
    top_k: int = TOP_K,
    score_threshold: float = SCORE_THRESHOLD,
    filter_metadata: Optional[dict] = None
) -> list[dict]:
    """
    Retrieve top_k relevant chunks from the student's personal collection.

    Args:
        query:           The student's question or search string.
        user_id:         Determines which personal_{user_id} collection to query.
        top_k:           Max number of chunks to return.
        score_threshold: Drop chunks with similarity below this (0–1 scale).
        filter_metadata: Optional ChromaDB where-filter.
                         e.g. {"source_type": "pdf"} or {"doc_title": "OS Notes"}

    Returns:
        List of dicts sorted by score descending:
        [{ "content": str, "metadata": dict, "score": float }, ...]
        Empty list if collection doesn't exist or no matches above threshold.
    """
    try:
        collection = get_personal_collection(user_id)
    except Exception as e:
        print(f"[retriever] Could not load collection for user '{user_id}': {e}")
        return []

    kwargs: dict = {"k": top_k}
    if filter_metadata:
        kwargs["filter"] = filter_metadata

    try:
        results: list[tuple[Document, float]] = collection.similarity_search_with_score(
            query, **kwargs
        )
    except Exception as e:
        print(f"[retriever] Search failed for user '{user_id}': {e}")
        return []

    chunks = []
    for doc, distance in results:
        # Clamp distance safely between 0.0 and 2.0 to handle wrapper scaling variations
        clamped_dist = max(0.0, min(float(distance), 2.0))
        similarity = round(1.0 - (clamped_dist / 2.0), 4)
        
        # DEBUG LOG: Check your terminal when a query runs to see actual matching metrics
        print(f"[DEBUG RAG] Doc: {doc.metadata.get('doc_title', 'Unknown')} | Distance: {distance:.4f} | Similarity: {similarity:.4f}")

        if similarity < score_threshold:
            continue
        chunks.append({
            "content": doc.page_content,
            "metadata": doc.metadata,
            "score": similarity,
        })

    chunks.sort(key=lambda x: x["score"], reverse=True)
    return chunks


def format_context(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into a context string for the LLM.
    Includes source label and score so the model can ground its citations.
    Returns a clear "nothing found" message when chunks is empty so the LLM
    knows not to fabricate an answer.
    """
    if not chunks:
        return (
            "No relevant content found in the student's uploaded documents. "
            "Ask the student to upload relevant material first."
        )

    parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk["metadata"]
        title = meta.get("doc_title", meta.get("filename", "Unknown document"))
        source_type = meta.get("source_type", "")
        page = meta.get("page", "")

        label_parts = [f"Source {i}: {title}"]
        if source_type:
            label_parts.append(source_type)
        if page != "":
            label_parts.append(f"page {page}")
        label_parts.append(f"score {chunk['score']}")

        parts.append(f"[{' | '.join(label_parts)}]\n{chunk['content']}")

    return "\n\n---\n\n".join(parts)
