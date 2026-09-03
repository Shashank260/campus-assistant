"""
context/youtube_context.py — Fetch a YouTube transcript for ephemeral conversation context.

EPHEMERAL path — transcript injected into conversation context only, not stored in ChromaDB.
If the student wants to save it permanently, they call POST /ingest/youtube.

The transcript is truncated to fit within STM token budget if it's very long.
"""

from urllib.parse import urlparse, parse_qs

from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

# Rough character limit for injecting into context — keeps total prompt under budget.
# ~6000 chars ≈ ~1500 tokens, leaves room for system prompt + messages + query.
CONTEXT_CHAR_LIMIT = 6000


def _extract_video_id(url: str) -> str:
    """Extract video ID from any standard YouTube URL format."""
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


def fetch_transcript_for_context(url: str) -> dict:
    """
    Fetch a YouTube transcript to inject into conversation context.

    Args:
        url: YouTube video URL.

    Returns:
        {
            "video_id": str,
            "transcript_text": str,   # full or truncated transcript
            "truncated": bool,        # True if transcript was cut for length
            "char_count": int,
        }

    Raises:
        ValueError: Bad URL, no transcript, or transcripts disabled.
    """
    video_id = _extract_video_id(url)

    try:
        yt_api = YouTubeTranscriptApi()
        segments = yt_api.fetch(video_id)
    except NoTranscriptFound:
        raise ValueError(f"No transcript available for: {video_id}")
    except TranscriptsDisabled:
        raise ValueError(f"Transcripts disabled for: {video_id}")
    except Exception as e:
        raise ValueError(f"Could not fetch transcript: {e}")

    full_text = " ".join(s.text for s in segments).strip()
    
    truncated = False
    if len(full_text) > CONTEXT_CHAR_LIMIT:
        full_text = full_text[:CONTEXT_CHAR_LIMIT]
        truncated = True

    return {
        "video_id": video_id,
        "url": url,
        "transcript_text": full_text,
        "truncated": truncated,
        "char_count": len(full_text),
    }


def format_youtube_context_for_llm(result: dict) -> str:
    """
    Format transcript result for injection into LLM prompt context.
    Phase 2 STM manager calls this when a YouTube URL is dropped in chat.
    """
    note = " (truncated to fit context window)" if result["truncated"] else ""
    return (
        f"[YouTube transcript: {result['url']}{note}]\n\n"
        f"{result['transcript_text']}"
    )
