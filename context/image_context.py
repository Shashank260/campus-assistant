"""
context/image_context.py — Process an image dropped in chat (ephemeral).

Uses Gemma 4 vision for both OCR understanding and visual analysis.
Result is returned to main.py and injected into conversation context.
NOT stored in ChromaDB — for permanent indexing use ingestion/image_ingest.py.
"""

from __future__ import annotations

import tempfile
import os
from pathlib import Path

import easyocr
import google.generativeai as genai
from PIL import Image

from config import GEMINI_API_KEY, GEMMA_MODEL, SUPPORTED_IMAGE_EXTENSIONS

_reader: easyocr.Reader | None = None


def get_reader() -> easyocr.Reader:
    global _reader
    if _reader is None:
        print("[image_context] Loading EasyOCR model...")
        _reader = easyocr.Reader(["en"], gpu=False)
        print("[image_context] EasyOCR ready.")
    return _reader


def process_image_for_context(
    image_bytes: bytes,
    filename: str,
    question: str = "",
) -> dict:
    """
    Process an image dropped in chat.
    Returns dict for STM injection and immediate LLM response.

    Returns:
        { ocr_text, visual_description, filename, has_text }
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image type: {suffix}")

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set. Get a free key at aistudio.google.com")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    ocr_text           = ""
    has_text           = False
    visual_description = ""
    image              = None

    try:
        # ── OCR ───────────────────────────────────────────────────────────────
        try:
            reader   = get_reader()
            raw      = reader.readtext(tmp_path, detail=0, paragraph=True)
            ocr_text = "\n\n".join(raw).strip()
            has_text = len(ocr_text) > 30
        except Exception as e:
            print(f"[image_context] OCR warning (non-fatal): {e}")

        # ── Gemma 4 vision ────────────────────────────────────────────────────
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMMA_MODEL)
        image = Image.open(tmp_path)

        prompt = (
            f"A student uploaded an image and asked: '{question}'\n\n"
            f"Analyse the image carefully and answer the question. "
            f"If it contains text, equations, or diagrams, reference them directly."
        ) if question else (
            "Describe this image for a student's study context. "
            "If it contains text, equations, diagrams, or slides, explain the key content clearly."
        )

        try:
            response           = model.generate_content([prompt, image])
            visual_description = response.text
        except Exception as e:
            raise RuntimeError(f"Gemma vision error: {e}")

    finally:
        # Close PIL handle before deleting — required on Windows
        if image is not None:
            image.close()
        try:
            os.unlink(tmp_path)
        except Exception:
            pass  # Windows temp folder will clean it up

    return {
        "ocr_text":           ocr_text,
        "visual_description": visual_description,
        "filename":           filename,
        "has_text":           has_text,
    }


def format_image_context_for_llm(image_result: dict) -> str:
    """Format image result as context string for the LLM prompt."""
    parts = [f"[Image uploaded: {image_result['filename']}]"]
    if image_result["has_text"] and image_result["ocr_text"]:
        parts.append(f"Text extracted from image:\n{image_result['ocr_text']}")
    parts.append(f"Visual analysis:\n{image_result['visual_description']}")
    return "\n\n".join(parts)