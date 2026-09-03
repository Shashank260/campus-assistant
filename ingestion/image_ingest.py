"""
image_ingest.py — OCR an image and index extracted text into personal_{user_id}.

This is the PERMANENT path — student explicitly uploads an image to their RAG.
For ephemeral image chat (drop in conversation), see context/image_context.py.

OCR engine: EasyOCR
- No system binary required (unlike pytesseract which needs tesseract on PATH)
- Downloads ~100 MB model on first use, cached at ~/.EasyOCR
- Handles printed text, lecture slides, mixed fonts reasonably well
- gpu=False — runs on CPU as per project constraints
"""

import hashlib
from pathlib import Path

import easyocr
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import PDF_CHUNK_SIZE, PDF_CHUNK_OVERLAP, SUPPORTED_IMAGE_EXTENSIONS
from retrieval.chroma_client import get_personal_collection, personal_collection_stats

# ── EasyOCR singleton ──────────────────────────────────────────────────────────
_reader: easyocr.Reader | None = None


def get_reader() -> easyocr.Reader:
    global _reader
    if _reader is None:
        print("[image_ingest] Loading EasyOCR model (first run ~100 MB download)...")
        _reader = easyocr.Reader(["en"], gpu=False)
        print("[image_ingest] EasyOCR ready.")
    return _reader


def _chunk_id(user_id: str, filename: str, chunk_index: int) -> str:
    raw = f"{user_id}::{filename}::c{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()


def ingest_image(
    file_path: str,
    user_id: str,
    doc_title: str = "",
) -> dict:
    """
    OCR an image and index the extracted text into the student's personal collection.

    Args:
        file_path:  Path to the image file.
        user_id:    Student ID.
        doc_title:  Optional title. Defaults to filename stem.

    Returns:
        { "status": "ok", "chunks_added": N, "extracted_chars": N, "file": filename }

    Raises:
        FileNotFoundError: Image path doesn't exist.
        ValueError: Unsupported extension or OCR yields no text.
    """
    path = Path(file_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(
            f"Unsupported image type '{path.suffix}'. "
            f"Accepted: {', '.join(SUPPORTED_IMAGE_EXTENSIONS)}"
        )

    title = doc_title or path.stem
    print(f"[image_ingest] Running OCR on: {path.name} -> personal_{user_id}")

    # ── OCR ───────────────────────────────────────────────────────────────────
    reader = get_reader()
    # detail=0 → plain strings (not bounding boxes)
    # paragraph=True → merges nearby text blocks into readable paragraphs
    raw_results = reader.readtext(str(path), detail=0, paragraph=True)
    extracted_text = "\n\n".join(raw_results).strip()

    if not extracted_text:
        raise ValueError(
            f"No text extracted from '{path.name}'. "
            "Image may be blank, too low-resolution, or contain only graphics."
        )

    print(f"[image_ingest]   Extracted {len(extracted_text)} characters.")

    # ── Chunk ─────────────────────────────────────────────────────────────────
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=PDF_CHUNK_SIZE,
        chunk_overlap=PDF_CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    raw_chunks = splitter.split_text(extracted_text)

    ids: list[str] = []
    chunks: list[Document] = []

    for i, text in enumerate(raw_chunks):
        ids.append(_chunk_id(user_id, path.name, i))
        chunks.append(Document(
            page_content=text,
            metadata={
                "source_type": "image",
                "doc_title": title,
                "filename": path.name,
                "user_id": user_id,
                "source": str(path),
            },
        ))

    # ── Upsert ────────────────────────────────────────────────────────────────
    collection = get_personal_collection(user_id)
    collection.add_documents(documents=chunks, ids=ids)

    stats = personal_collection_stats(user_id)
    print(f"[image_ingest]   Done. Total docs in personal_{user_id}: {stats['count']}")

    return {
        "status": "ok",
        "chunks_added": len(chunks),
        "extracted_chars": len(extracted_text),
        "file": path.name,
        "total_in_collection": stats["count"],
    }
