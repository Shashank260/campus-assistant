"""
youtube_ingest.py — Fetch a YouTube transcript and index it into personal_{user_id}.

This is the PERMANENT path — student explicitly saves a video to their RAG.
For ephemeral YouTube chat (drop URL in conversation), see context/youtube_context.py.

Chunking strategy: 120-second windows (not token-based).
Rationale: transcript chunks tied to timestamps are more useful for citation
("this was explained around 14:30") than arbitrary token splits.
"""
import hashlib
from urllib.parse import urlparse, parse_qs

from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from langchain_core.documents import Document

from config import YOUTUBE_CHUNK_SIZE, YOUTUBE_CHUNK_OVERLAP
from retrieval.chroma_client import get_personal_collection, personal_collection_stats

WINDOW_SECONDS = 120   # chunk transcripts into 2-minute windows


def _extract_video_id(url: str) -> str:
    """
    Extract YouTube video ID from any standard URL format.
    Handles: youtu.be/ID, youtube.com/watch?v=ID, youtube.com/shorts/ID
    """
    parsed = urlparse(url)

    if parsed.hostname in ("youtu.be",):
        return parsed.path.lstrip("/")

    if parsed.hostname in ("www.youtube.com", "youtube.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            if "v" in qs:
                return qs["v"][0]
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/shorts/")[1].split("/")[0]

    raise ValueError(f"Could not extract video ID from URL: {url}")


def _chunk_id(user_id: str, video_id: str, window_index: int) -> str:
    raw = f"{user_id}::{video_id}::w{window_index}"
    return hashlib.md5(raw.encode()).hexdigest()


def _seconds_to_timestamp(seconds: float) -> str:
    """Convert float seconds to MM:SS string for readable citations."""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def ingest_youtube(
    url: str,
    user_id: str,
    language_code: str,
    doc_title: str = "",
) -> dict:
    """
    Fetch a YouTube transcript and index it into the student's personal collection.

    Args:
        url:           Full YouTube URL.
        user_id:       Student ID.
        language_code: Transcript language code (e.g. "en", "hi"). Required.
                       Get available codes from GET /tools/youtube/languages first.
        doc_title:     Optional title override. Defaults to "YouTube: {video_id}".

    Returns:
        { "status": "ok", "chunks_added": N, "video_id": str, "title": str }

    Raises:
        ValueError: Bad URL, language unavailable, or transcript fetch failed.
    """
    video_id = _extract_video_id(url)
    title = doc_title or f"YouTube: {video_id}"

    print(f"[youtube_ingest] Fetching transcript for: {video_id}")

    # ── Fetch transcript ──────────────────────────────────────────────────────
    try:
        yt_api = YouTubeTranscriptApi()
        transcript_raw = yt_api.fetch(video_id, languages=[language_code])
    except NoTranscriptFound:
        raise ValueError(
            f"No transcript in '{language_code}' for video: {video_id}. "
            f"Check available languages via GET /tools/youtube/languages."
        )
    except TranscriptsDisabled:
        raise ValueError(f"Transcripts are disabled for video: {video_id}")
    except Exception as e:
        raise ValueError(f"Transcript fetch failed: {e}")

    print(f"[youtube_ingest]   Transcript segments: {len(transcript_raw)}")

    # ── Window chunking by time ───────────────────────────────────────────────
    # Group transcript segments into WINDOW_SECONDS buckets.
    windows: list[dict] = []
    current_window: list[dict] = []
    window_start = 0.0

    for segment in transcript_raw:
        if current_window and (segment.start - window_start) >= WINDOW_SECONDS:
            windows.append({
                "text":  " ".join(s.text for s in current_window),
                "start": window_start,
                "end":   current_window[-1].start + getattr(current_window[-1], "duration", 0),
            })
            current_window = []
            window_start = segment.start
        current_window.append(segment)

# flush last window
    if current_window:
        windows.append({
            "text":  " ".join(s.text for s in current_window),
            "start": window_start,
            "end":   current_window[-1].start + getattr(current_window[-1], "duration", 0),
        })

    print(f"[youtube_ingest]   Windows (2-min): {len(windows)}")

    # ── Build Documents ───────────────────────────────────────────────────────
    ids: list[str] = []
    chunks: list[Document] = []

    for i, window in enumerate(windows):
        start_ts = _seconds_to_timestamp(window["start"])
        end_ts   = _seconds_to_timestamp(window["end"])
        url_with_ts = f"https://youtu.be/{video_id}?t={int(window['start'])}"

        ids.append(_chunk_id(user_id, video_id, i))
        chunks.append(Document(
            page_content=window["text"],
            metadata={
                "source_type": "youtube",
                "doc_title": title,
                "video_id": video_id,
                "video_url": url,
                "start_time": start_ts,
                "end_time": end_ts,
                "timestamp_url": url_with_ts,
                "user_id": user_id,
            },
        ))

    # ── Upsert ────────────────────────────────────────────────────────────────
    collection = get_personal_collection(user_id)
    collection.add_documents(documents=chunks, ids=ids)

    stats = personal_collection_stats(user_id)
    print(f"[youtube_ingest]   Done. Total docs in personal_{user_id}: {stats['count']}")

    return {
        "status": "ok",
        "chunks_added": len(chunks),
        "video_id": video_id,
        "title": title,
        "total_in_collection": stats["count"],
    }
