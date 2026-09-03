"""
context/image_context.py — Process an image dropped in chat (ephemeral).

Uses Gemma 4 vision directly — no EasyOCR needed.
Gemma 4 is fully multimodal and handles OCR, diagrams, equations, and slides natively.
NOT stored in ChromaDB — for permanent indexing use ingestion/image_ingest.py.
"""

from __future__ import annotations

import tempfile
import os
from pathlib import Path

import google.generativeai as genai
from PIL import Image

from config import GEMINI_API_KEY, GEMMA_MODEL, SUPPORTED_IMAGE_EXTENSIONS


def process_image_for_context(
    image_bytes: bytes,
    filename: str,
    question: str = "",
    api_key: str = "",
) -> dict:
    """
    Process an image dropped in chat using Gemma 4 vision.
    Returns dict for STM injection and immediate LLM response.

    Returns:
        { visual_description, filename }
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image type: {suffix}")

    key = api_key.strip() if api_key.strip() else GEMINI_API_KEY
    if not key:
        raise ValueError("No API key available. Add your Gemini key in Settings.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    visual_description = ""
    image              = None

    try:
        genai.configure(api_key=key)
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
        if image is not None:
            image.close()
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return {
        "visual_description": visual_description,
        "filename":           filename,
    }


def format_image_context_for_llm(image_result: dict) -> str:
    """Format image result as context string for the LLM prompt."""
    return (
        f"[Image uploaded: {image_result['filename']}]\n\n"
        f"Visual analysis:\n{image_result['visual_description']}"
    )