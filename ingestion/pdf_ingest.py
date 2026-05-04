"""
pdf_ingest.py — Load a PDF, chunk it, embed it, store in personal_{user_id}.

Each student's PDFs go into their own isolated ChromaDB collection.
Re-ingesting the same file is safe — chunk IDs are deterministic (MD5 of path+page+index),
so ChromaDB upserts are no-ops for existing chunks.

CLI usage:
    cd backend
    python ingestion/pdf_ingest.py --file /path/to/notes.pdf --user_id student42
    python ingestion/pdf_ingest.py --file /path/to/notes.pdf --user_id student42 --doc_type syllabus
"""

import hashlib
import argparse
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from config import PDF_CHUNK_SIZE, PDF_CHUNK_OVERLAP
from retrieval.chroma_client import get_personal_collection, personal_collection_stats


def _chunk_id(user_id: str, file_path: str, page: int, chunk_index: int) -> str:
    """
    Deterministic chunk ID scoped to user.
    Same user + same file + same position = same ID = safe upsert.
    """
    raw = f"{user_id}::{file_path}::p{page}::c{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()


def ingest_pdf(
    file_path: str,
    user_id: str,
    doc_type: str = "pdf",
    doc_title: str = "",
) -> dict:
    """
    Ingest a PDF into the student's personal ChromaDB collection.

    Args:
        file_path:  Path to the PDF file.
        user_id:    Student ID — determines which collection to write to.
        doc_type:   Label for this document e.g. 'syllabus', 'notes', 'pdf'.
        doc_title:  Human-readable title. Defaults to filename stem.

    Returns:
        { "status": "ok", "chunks_added": N, "pages": N, "file": filename }
    """
    path = Path(file_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {path.suffix}")

    title = doc_title or path.stem
    print(f"[pdf_ingest] Loading: {path.name} → personal_{user_id}")

    # ── Load pages ────────────────────────────────────────────────────────────
    loader = PyPDFLoader(str(path))
    pages = loader.load()   # one Document per page, metadata has 'page' key
    print(f"[pdf_ingest]   Pages: {len(pages)}")

    # ── Chunk ─────────────────────────────────────────────────────────────────
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=PDF_CHUNK_SIZE,
        chunk_overlap=PDF_CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    raw_chunks = splitter.split_documents(pages)
    print(f"[pdf_ingest]   Chunks: {len(raw_chunks)}")

    # ── Assign IDs + enrich metadata ──────────────────────────────────────────
    ids: list[str] = []
    chunks: list[Document] = []

    for i, chunk in enumerate(raw_chunks):
        page_num = chunk.metadata.get("page", 0)
        ids.append(_chunk_id(user_id, str(path), page_num, i))

        chunk.metadata.update({
            "source_type": "pdf",
            "doc_type": doc_type,
            "doc_title": title,
            "filename": path.name,
            "user_id": user_id,
            "source": str(path),
        })
        chunks.append(chunk)

    # ── Upsert ────────────────────────────────────────────────────────────────
    collection = get_personal_collection(user_id)
    collection.add_documents(documents=chunks, ids=ids)

    stats = personal_collection_stats(user_id)
    print(f"[pdf_ingest]   Done. Total docs in personal_{user_id}: {stats['count']}")

    return {
        "status": "ok",
        "chunks_added": len(chunks),
        "pages": len(pages),
        "file": path.name,
        "total_in_collection": stats["count"],
    }


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    parser = argparse.ArgumentParser(description="Ingest a PDF into a student's personal collection")
    parser.add_argument("--file",      required=True,          help="Path to PDF")
    parser.add_argument("--user_id",   required=True,          help="Student user ID")
    parser.add_argument("--doc_type",  default="pdf",          help="Document type label")
    parser.add_argument("--doc_title", default="",             help="Human-readable title (optional)")
    args = parser.parse_args()

    result = ingest_pdf(
        file_path=args.file,
        user_id=args.user_id,
        doc_type=args.doc_type,
        doc_title=args.doc_title,
    )
    print(result)
