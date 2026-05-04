"""
notion/notion_push.py — Push a single assistant response to Notion as a subpage.

Design:
- One master page per student (set up via POST /notion/setup)
- Each push creates a dated subpage under the master page
- No LLM involved — content is pushed as-is
- Notion key stored in SQLite user_settings
"""

from __future__ import annotations

import re
import requests
from datetime import datetime


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION  = "2022-06-28"


def _headers(notion_key: str) -> dict:
    return {
        "Authorization":  f"Bearer {notion_key}",
        "Content-Type":   "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def _make_default_title(content: str) -> str:
    """Generate title from date + first 6 words of content."""
    date  = datetime.utcnow().strftime("%Y-%m-%d")
    words = content.strip().split()[:6]
    snippet = " ".join(words)
    if len(content.split()) > 6:
        snippet += "..."
    return f"{date} — {snippet}"


def _text_to_notion_blocks(content: str) -> list[dict]:
    """
    Convert plain text to Notion block objects.
    - Lines starting with # → heading_2
    - Lines starting with - or * → bulleted_list_item
    - Code blocks (``` ```) → code block
    - Everything else → paragraph
    """
    blocks  = []
    lines   = content.split("\n")
    i       = 0

    while i < len(lines):
        line = lines[i]

        # ── Code block ────────────────────────────────────────────────────────
        if line.strip().startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append({
                "object": "block",
                "type":   "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}],
                    "language":  "plain text",
                }
            })

        # ── Heading ───────────────────────────────────────────────────────────
        elif line.startswith("# "):
            blocks.append({
                "object": "block",
                "type":   "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]
                }
            })

        elif line.startswith("## ") or line.startswith("### "):
            text = re.sub(r"^#{2,3} ", "", line).strip()
            blocks.append({
                "object": "block",
                "type":   "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": text}}]
                }
            })

        # ── Bullet ────────────────────────────────────────────────────────────
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append({
                "object": "block",
                "type":   "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]
                }
            })

        # ── Empty line → skip ─────────────────────────────────────────────────
        elif line.strip() == "":
            pass

        # ── Paragraph ─────────────────────────────────────────────────────────
        else:
            blocks.append({
                "object": "block",
                "type":   "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": line.strip()}}]
                }
            })

        i += 1

    return blocks


def push_to_notion(
    notion_key:     str,
    master_page_id: str,
    content:        str,
    page_title:     str = "",
) -> dict:
    """
    Create a subpage under master_page_id with the given content.

    Args:
        notion_key:     Notion integration token.
        master_page_id: ID of the student's master Notion page.
        content:        Text content to push (assistant response).
        page_title:     Optional custom title. Auto-generated if empty.

    Returns:
        { "status": "ok", "page_url": str, "page_id": str }

    Raises:
        ValueError: Notion API error or bad credentials.
    """
    title  = page_title.strip() if page_title.strip() else _make_default_title(content)
    blocks = _text_to_notion_blocks(content)

    # Notion API limits 100 blocks per request — truncate if needed
    if len(blocks) > 100:
        blocks = blocks[:100]

    payload = {
        "parent": {"page_id": master_page_id},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
        "children": blocks,
    }

    response = requests.post(
        f"{NOTION_API_BASE}/pages",
        headers=_headers(notion_key),
        json=payload,
        timeout=10,
    )

    if response.status_code != 200:
        raise ValueError(
            f"Notion API error {response.status_code}: {response.json().get('message', 'Unknown error')}"
        )

    data     = response.json()
    page_id  = data["id"]
    page_url = data.get("url", f"https://notion.so/{page_id.replace('-', '')}")

    return {
        "status":   "ok",
        "page_url": page_url,
        "page_id":  page_id,
        "title":    title,
    }


def verify_notion_connection(notion_key: str, master_page_id: str) -> bool:
    """
    Check if the Notion key and page ID are valid.
    Used by POST /notion/setup to validate before saving.
    """
    response = requests.get(
        f"{NOTION_API_BASE}/pages/{master_page_id}",
        headers=_headers(notion_key),
        timeout=10,
    )
    return response.status_code == 200