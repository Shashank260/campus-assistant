"""
sqlite_client.py — Conversation thread storage using SQLite.

Stores:
- Conversation threads (id, user_id, title, created_at, last_active)
- Messages per thread (role, content, timestamp)
- STM summary per thread (updated after every summarisation)

Schema is created automatically on first import.
All functions are synchronous — FastAPI endpoints call them in a threadpool
via asyncio.to_thread() to avoid blocking the event loop.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from config import SQLITE_DB_PATH


# ── Connection helper ──────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    """
    Return a SQLite connection with row_factory set so rows behave like dicts.
    Each call returns a new connection — SQLite connections are not thread-safe
    and FastAPI runs handlers in threads, so we don't share a single connection.
    """
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # better concurrent read performance
    return conn


# ── Schema init ───────────────────────────────────────────────────────────────

def init_db() -> None:
    """
    Create tables if they don't exist.
    Called once at app startup from main.py lifespan.
    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS.
    """
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL,
                title           TEXT NOT NULL DEFAULT 'New conversation',
                created_at      TEXT NOT NULL,
                last_active     TEXT NOT NULL,
                stm_summary     TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS messages (
                message_id      TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role            TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content         TEXT NOT NULL,
                timestamp       TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                user_id         TEXT PRIMARY KEY,
                notion_key      TEXT NOT NULL DEFAULT '',
                notion_page_id  TEXT NOT NULL DEFAULT '',
                updated_at      TEXT NOT NULL
            );           

            CREATE INDEX IF NOT EXISTS idx_conversations_user
                ON conversations(user_id, last_active DESC);

            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id, timestamp ASC);
        """)
        conn.commit()
        print("[sqlite] Database initialised.")
    finally:
        conn.close()


# ── Conversation CRUD ─────────────────────────────────────────────────────────

def create_conversation(user_id: str, first_message: str = "") -> dict:
    """
    Create a new conversation thread.
    Title is auto-generated from the first message (first 60 chars).
    Returns the full conversation dict.
    """
    conversation_id = str(uuid.uuid4())
    now             = _now()
    title           = _make_title(first_message)

    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO conversations
               (conversation_id, user_id, title, created_at, last_active, stm_summary)
               VALUES (?, ?, ?, ?, ?, '')""",
            (conversation_id, user_id, title, now, now)
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "conversation_id": conversation_id,
        "user_id":         user_id,
        "title":           title,
        "created_at":      now,
        "last_active":     now,
        "stm_summary":     "",
    }


def get_conversation(conversation_id: str) -> dict | None:
    """Return a conversation by ID, or None if not found."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (conversation_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_conversations(user_id: str) -> list[dict]:
    """
    Return all conversations for a user, newest first.
    Does not include messages — just metadata for the thread list UI.
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT conversation_id, title, created_at, last_active
               FROM conversations
               WHERE user_id = ?
               ORDER BY last_active DESC""",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def touch_conversation(conversation_id: str, title: str | None = None) -> None:
    """Update last_active timestamp. Optionally update title."""
    now  = _now()
    conn = _get_conn()
    try:
        if title:
            conn.execute(
                "UPDATE conversations SET last_active = ?, title = ? WHERE conversation_id = ?",
                (now, title, conversation_id)
            )
        else:
            conn.execute(
                "UPDATE conversations SET last_active = ? WHERE conversation_id = ?",
                (now, conversation_id)
            )
        conn.commit()
    finally:
        conn.close()


def update_stm_summary(conversation_id: str, summary: str) -> None:
    """Persist the STM summary for a conversation after summarisation."""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE conversations SET stm_summary = ? WHERE conversation_id = ?",
            (summary, conversation_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_conversation(conversation_id: str) -> None:
    """Delete a conversation and all its messages."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM messages    WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
        conn.commit()
    finally:
        conn.close()


# ── Message CRUD ──────────────────────────────────────────────────────────────

def save_message(conversation_id: str, role: str, content: str) -> dict:
    """
    Append a message to a conversation.
    Also updates last_active on the parent conversation.
    """
    message_id = str(uuid.uuid4())
    now        = _now()

    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO messages (message_id, conversation_id, role, content, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (message_id, conversation_id, role, content, now)
        )
        conn.execute(
            "UPDATE conversations SET last_active = ? WHERE conversation_id = ?",
            (now, conversation_id)
        )
        conn.commit()
    finally:
        conn.close()

    return {"message_id": message_id, "role": role, "content": content, "timestamp": now}


def get_messages(conversation_id: str, limit: int | None = None) -> list[dict]:
    """
    Return messages for a conversation in chronological order.
    If limit is set, returns the last N messages only.
    """
    conn = _get_conn()
    try:
        if limit:
            rows = conn.execute(
                """SELECT role, content, timestamp FROM (
                       SELECT role, content, timestamp
                       FROM messages
                       WHERE conversation_id = ?
                       ORDER BY timestamp DESC
                       LIMIT ?
                   ) ORDER BY timestamp ASC""",
                (conversation_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT role, content, timestamp FROM messages
                   WHERE conversation_id = ?
                   ORDER BY timestamp ASC""",
                (conversation_id,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_messages(conversation_id: str) -> int:
    """Return total message count for a conversation."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = ?",
            (conversation_id,)
        ).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()

# ── User settings CRUD ────────────────────────────────────────────────────────

def save_user_settings(user_id: str, notion_key: str, notion_page_id: str) -> None:
    """Save or update Notion credentials for a user."""
    now  = _now()
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO user_settings (user_id, notion_key, notion_page_id, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   notion_key     = excluded.notion_key,
                   notion_page_id = excluded.notion_page_id,
                   updated_at     = excluded.updated_at""",
            (user_id, notion_key, notion_page_id, now)
        )
        conn.commit()
    finally:
        conn.close()


def get_user_settings(user_id: str) -> dict | None:
    """Return user settings or None if not configured."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().isoformat()


def _make_title(text: str, max_len: int = 60) -> str:
    """Generate a conversation title from the first message."""
    if not text.strip():
        return "New conversation"
    text = text.strip().replace("\n", " ")
    return text[:max_len] + ("..." if len(text) > max_len else "")
