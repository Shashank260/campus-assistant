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


def _parse_table(lines: list[str], start_idx: int) -> tuple[dict, int] | None:
    if start_idx + 1 >= len(lines):
        return None
    first_line = lines[start_idx].strip()
    sep_line = lines[start_idx + 1].strip()
    if not (first_line.startswith('|') and first_line.endswith('|')):
        return None
    if not (sep_line.startswith('|') and sep_line.endswith('|')):
        return None
    cleaned_sep = sep_line.replace(':', '').replace('-', '').replace('|', '').replace(' ', '')
    if cleaned_sep != "":
        return None
    headers = [c.strip() for c in first_line.split('|')[1:-1]]
    table_width = len(headers)
    if table_width == 0:
        return None
    children = []
    header_cells = []
    for h in headers:
        clean_h = h.replace("**", "").replace("*", "").replace("`", "")
        header_cells.append([{"type": "text", "text": {"content": clean_h}}])
    children.append({
        "object": "block",
        "type": "table_row",
        "table_row": {"cells": header_cells}
    })
    idx = start_idx + 2
    while idx < len(lines):
        row_line = lines[idx].strip()
        if not (row_line.startswith('|') and row_line.endswith('|')):
            break
        cells = [c.strip() for c in row_line.split('|')[1:-1]]
        if len(cells) < table_width:
            cells += [""] * (table_width - len(cells))
        elif len(cells) > table_width:
            cells = cells[:table_width]
        row_cells = []
        for cell in cells:
            clean_cell = cell.replace("**", "").replace("*", "").replace("`", "")
            row_cells.append([{"type": "text", "text": {"content": clean_cell}}])
        children.append({
            "object": "block",
            "type": "table_row",
            "table_row": {"cells": row_cells}
        })
        idx += 1
    table_block = {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": table_width,
            "has_column_header": True,
            "has_row_header": False,
            "children": children
        }
    }
    return table_block, idx


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

        # ── Table block ───────────────────────────────────────────────────────
        table_res = _parse_table(lines, i)
        if table_res:
            table_block, next_idx = table_res
            blocks.append(table_block)
            i = next_idx
            continue

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


def clean_notion_page_id(input_str: str) -> str:
    """
    Extracts the clean 32-character Notion page ID from a URL or raw ID string.
    Works for:
      - 3560a86a8fd780e2beb0fed83b879b55
      - 3560a86a-8fd7-80e2-beb0-fed83b879b55
      - 3560a86a8fd780e2beb0fed83b879b55?pvs=4
      - https://www.notion.so/My-Page-3560a86a8fd780e2beb0fed83b879b55?pvs=4
      - https://www.notion.so/3560a86a8fd780e2beb0fed83b879b55
    """
    # 1. Strip whitespace
    s = input_str.strip()
    
    # 2. Remove query parameters if any (e.g. ?pvs=4 or ?source=...)
    s = s.split("?")[0]
    
    # 3. If it's a URL, extract the last path segment
    if "/" in s:
        s = s.split("/")[-1]
    
    # 4. If it ends with a 32-char hex string separated by a dash (e.g. My-Page-3560a86a8fd780e2beb0fed83b879b55)
    if "-" in s:
        parts = s.split("-")
        last_part = parts[-1]
        if len(last_part) == 32 and all(c in "0123456789abcdefABCDEF" for c in last_part):
            return last_part
            
    # Remove dashes to check length if it's a raw UUID with dashes
    no_dashes = s.replace("-", "")
    if len(no_dashes) == 32 and all(c in "0123456789abcdefABCDEF" for c in no_dashes):
        return s
    
    return s


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
    cleaned_page_id = clean_notion_page_id(master_page_id)
    title  = page_title.strip() if page_title.strip() else _make_default_title(content)
    blocks = _text_to_notion_blocks(content)

    # Notion API limits 100 blocks per request — truncate if needed
    if len(blocks) > 100:
        blocks = blocks[:100]

    payload = {
        "parent": {"page_id": cleaned_page_id},
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
    cleaned_page_id = clean_notion_page_id(master_page_id)
    response = requests.get(
        f"{NOTION_API_BASE}/pages/{cleaned_page_id}",
        headers=_headers(notion_key),
        timeout=10,
    )
    return response.status_code == 200


def append_to_notion_page(
    notion_key: str,
    page_id:    str,
    content:    str,
) -> dict:
    """
    Append content blocks to an existing Notion page.
    Used for subsequent pushes from the same conversation.

    Adds a divider before the new content to visually separate each push.

    Args:
        notion_key: Notion integration token.
        page_id:    ID of the existing Notion sub-page.
        content:    Text content to append.

    Returns:
        { "status": "ok", "page_url": str, "page_id": str, "appended": True }

    Raises:
        ValueError: Notion API error.
    """
    blocks = _text_to_notion_blocks(content)

    # Add a divider before new content to separate pushes visually
    divider = {"object": "block", "type": "divider", "divider": {}}
    blocks = [divider] + blocks

    # Notion API limits 100 blocks per request
    if len(blocks) > 100:
        blocks = blocks[:100]

    response = requests.patch(
        f"{NOTION_API_BASE}/blocks/{page_id}/children",
        headers=_headers(notion_key),
        json={"children": blocks},
        timeout=10,
    )

    if response.status_code != 200:
        raise ValueError(
            f"Notion API error {response.status_code}: "
            f"{response.json().get('message', 'Unknown error')}"
        )

    page_url = f"https://notion.so/{page_id.replace('-', '')}"

    return {
        "status":   "ok",
        "page_url": page_url,
        "page_id":  page_id,
        "appended": True,
    }