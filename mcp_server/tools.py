"""
MCP tool implementations for the Learning Path Generator.

Tools call external APIs (YouTube Data API, Wikipedia REST API) and always return
structured JSON dicts so LangGraph / Gemini agents can parse results reliably.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Final
from urllib.parse import quote

import httpx
from fastmcp import FastMCP
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tool_limits import enforce_tool_limit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read from environment at import/runtime)
# ---------------------------------------------------------------------------

# YouTube Data API key — create at https://console.cloud.google.com/
YOUTUBE_API_KEY_ENV: Final[str] = "YOUTUBE_API_KEY"

# Default number of videos returned per YouTube search.list call (max 50 per API)
DEFAULT_MAX_RESULTS: Final[int] = 10
YOUTUBE_MAX_RESULTS_ENV: Final[str] = "YOUTUBE_MAX_RESULTS"

# Reject overly long queries to avoid abuse and API errors
MAX_QUERY_LENGTH: Final[int] = 200

# YouTube category ID 27 = Education (used to bias toward instructional content)
YOUTUBE_EDUCATION_CATEGORY_ID: Final[str] = "27"

# Wikipedia REST summary endpoint (no API key required)
WIKIPEDIA_SUMMARY_URL: Final[str] = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

# Search angles used by find_learning_resources (each triggers one YouTube search)
LEARNING_RESOURCE_SEARCH_ANGLES: Final[list[tuple[str, str]]] = [
    ("getting_started", "{topic} beginner tutorial"),
    ("tutorials", "{topic} full course tutorial"),
    ("deep_dives", "{topic} advanced explained"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format for response metadata."""
    return datetime.now(timezone.utc).isoformat()


def _sanitize_query(text: str, *, field_name: str = "query") -> str:
    """
    Normalize and validate user-provided search text.

    - Strips leading/trailing whitespace
    - Collapses internal runs of whitespace
    - Enforces a maximum length
    """
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    if len(cleaned) > MAX_QUERY_LENGTH:
        raise ValueError(
            f"{field_name} must be at most {MAX_QUERY_LENGTH} characters "
            f"(got {len(cleaned)})."
        )
    return cleaned


def _get_youtube_api_key() -> str:
    """Load the YouTube API key from the environment or raise a clear error."""
    api_key = os.getenv(YOUTUBE_API_KEY_ENV, "").strip()
    if not api_key:
        raise ValueError(
            f"Missing {YOUTUBE_API_KEY_ENV}. "
            "Set it in your environment or .env file before starting the MCP server."
        )
    return api_key


def _get_max_results() -> int:
    """Resolve max YouTube results per search from env with a safe default."""
    raw = os.getenv(YOUTUBE_MAX_RESULTS_ENV, str(DEFAULT_MAX_RESULTS))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{YOUTUBE_MAX_RESULTS_ENV} must be an integer (got {raw!r})."
        ) from exc
    if value < 1 or value > 50:
        raise ValueError(
            f"{YOUTUBE_MAX_RESULTS_ENV} must be between 1 and 50 (got {value})."
        )
    return value


def _build_youtube_client():
    """
    Create a YouTube Data API v3 client.

    Uses google-api-python-client's discovery builder; credentials are API-key only
    (no OAuth) which is appropriate for public search operations.
    """
    return build(
        "youtube",
        "v3",
        developerKey=_get_youtube_api_key(),
        cache_discovery=False,
    )


def _format_video_item(item: dict[str, Any]) -> dict[str, Any]:
    """
    Map a YouTube search.list item into a stable JSON shape for agents.

    We only request the 'snippet' part to minimize quota usage (100 units/search).
    """
    snippet = item.get("snippet") or {}
    video_id = (item.get("id") or {}).get("videoId")
    thumbnails = snippet.get("thumbnails") or {}
    thumbnail_url = (
        (thumbnails.get("high") or {}).get("url")
        or (thumbnails.get("medium") or {}).get("url")
        or (thumbnails.get("default") or {}).get("url")
    )

    return {
        "video_id": video_id,
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "channel_title": snippet.get("channelTitle"),
        "channel_id": snippet.get("channelId"),
        "published_at": snippet.get("publishedAt"),
        "thumbnail_url": thumbnail_url,
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
    }


def _youtube_search(
    query: str,
    *,
    max_results: int | None = None,
    prefer_education: bool = True,
) -> list[dict[str, Any]]:
    """
    Execute YouTube Data API search.list and return normalized video records.

    Parameters bias results toward educational content:
    - type=video (exclude channels/playlists)
    - order=relevance
    - safeSearch=strict
    - optional videoCategoryId=27 (Education)
    """
    max_results = max_results or _get_max_results()
    youtube = _build_youtube_client()

    # Base request parameters shared across searches
    request_kwargs: dict[str, Any] = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "order": "relevance",
        "safeSearch": "strict",
        "relevanceLanguage": "en",
    }

    # Prefer the Education category when enabled; fall back if the API rejects it
    if prefer_education:
        request_kwargs["videoCategoryId"] = YOUTUBE_EDUCATION_CATEGORY_ID

    try:
        response = youtube.search().list(**request_kwargs).execute()
    except HttpError as err:
        # Some queries + category filters return 400; retry without category filter
        if prefer_education and err.resp is not None and err.resp.status == 400:
            logger.warning(
                "YouTube search with education category failed; retrying without category filter."
            )
            request_kwargs.pop("videoCategoryId", None)
            response = youtube.search().list(**request_kwargs).execute()
        else:
            raise

    items = response.get("items") or []
    return [_format_video_item(item) for item in items if item.get("id", {}).get("videoId")]


def _dedupe_videos_by_id(videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate videos (same video_id) while preserving first-seen order."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for video in videos:
        video_id = video.get("video_id")
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        unique.append(video)
    return unique


def _fetch_wikipedia_summary(topic: str) -> dict[str, Any] | None:
    """
    Fetch a short Wikipedia summary for the topic (free REST API, no key).

    Returns None if no page is found or the request fails non-critically.
    """
    # Wikipedia titles use underscores in URLs; spaces are also accepted
    title_for_url = quote(topic.replace(" ", "_"), safe="")
    url = WIKIPEDIA_SUMMARY_URL.format(title=title_for_url)

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                url,
                headers={"User-Agent": "LearningPathGenerator-MCP/1.0"},
            )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as err:
        logger.warning("Wikipedia summary fetch failed for %r: %s", topic, err)
        return None

    return {
        "title": data.get("title"),
        "summary": data.get("extract"),
        "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
        "type": "wikipedia",
    }


def _format_youtube_http_error(err: HttpError) -> str:
    """Extract a concise, agent-friendly message from a YouTube HttpError."""
    try:
        payload = json.loads(err.content.decode("utf-8"))
        api_message = (payload.get("error") or {}).get("message")
        if api_message:
            return api_message
    except (AttributeError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return str(err)


def _error_payload(tool: str, message: str, **extra: Any) -> dict[str, Any]:
    """Consistent error envelope so agents can branch on success=false."""
    return {
        "success": False,
        "tool": tool,
        "error": message,
        "generated_at": _utc_now_iso(),
        **extra,
    }


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_tools(mcp: FastMCP) -> None:
    """
    Attach MCP tools to the FastMCP server instance.

    Called from server.py after the FastMCP object is created.
    """

    @mcp.tool
    def search_youtube(query: str) -> dict[str, Any]:
        """
        Search YouTube for top educational videos matching the query.

        Uses the YouTube Data API v3. Returns structured JSON with video metadata
        (title, channel, URL, thumbnail, description snippet).

        Args:
            query: Natural-language search phrase (e.g. "python basics for beginners").

        Returns:
            JSON object with success flag, query echo, and a list of video records.
        """
        tool_name = "search_youtube"
        try:
            # Step 0: Enforce per-run server-side call limit (max 3)
            allowed, limit_error = enforce_tool_limit(tool_name)
            if not allowed:
                return _error_payload(tool_name, limit_error, query=query)

            # Step 1: Validate and normalize the query string
            safe_query = _sanitize_query(query, field_name="query")

            # Step 2: Call YouTube search with educational bias
            videos = _youtube_search(safe_query, prefer_education=True)

            # Step 3: Return structured JSON for the agent
            return {
                "success": True,
                "tool": tool_name,
                "query": safe_query,
                "result_count": len(videos),
                "videos": videos,
                "generated_at": _utc_now_iso(),
            }
        except ValueError as err:
            return _error_payload(tool_name, str(err), query=query)
        except HttpError as err:
            logger.exception("YouTube API error in search_youtube")
            return _error_payload(
                tool_name,
                f"YouTube API error: {_format_youtube_http_error(err)}",
                query=query,
            )
        except Exception as err:
            logger.exception("Unexpected error in search_youtube")
            return _error_payload(tool_name, f"Unexpected error: {err}", query=query)

    @mcp.tool
    def find_learning_resources(topic: str) -> dict[str, Any]:
        """
        Discover curated learning resources for a topic.

        Combines multiple targeted YouTube searches (beginner, tutorial, advanced)
        with an optional Wikipedia reference summary. Returns structured JSON grouped
        by resource category for learning-path planning.

        Args:
            topic: Subject to learn (e.g. "machine learning", "react hooks").

        Returns:
            JSON object with categorized video resources, reference links, and focus areas.
        """
        tool_name = "find_learning_resources"
        try:
            # Step 0: Enforce per-run server-side call limit (max 1)
            allowed, limit_error = enforce_tool_limit(tool_name)
            if not allowed:
                return _error_payload(tool_name, limit_error, topic=topic)

            # Step 1: Validate the topic
            safe_topic = _sanitize_query(topic, field_name="topic")
            max_per_search = min(_get_max_results(), 8)

            # Step 2: Run multiple YouTube searches from different learning angles
            categorized_videos: dict[str, list[dict[str, Any]]] = {}
            all_videos: list[dict[str, Any]] = []

            for category_key, template in LEARNING_RESOURCE_SEARCH_ANGLES:
                search_query = template.format(topic=safe_topic)
                videos = _youtube_search(
                    search_query,
                    max_results=max_per_search,
                    prefer_education=True,
                )
                categorized_videos[category_key] = videos
                all_videos.extend(videos)

            # Step 3: Deduplicate across categories for a flat "featured" list
            featured_videos = _dedupe_videos_by_id(all_videos)[: max_per_search * 2]

            # Step 4: Add a free textual reference from Wikipedia when available
            reference_links: list[dict[str, Any]] = []
            wiki = _fetch_wikipedia_summary(safe_topic)
            if wiki:
                reference_links.append(wiki)

            # Step 5: Derive simple focus areas from categories that returned results
            suggested_focus_areas = [
                key.replace("_", " ").title()
                for key, videos in categorized_videos.items()
                if videos
            ]

            return {
                "success": True,
                "tool": tool_name,
                "topic": safe_topic,
                "summary": (
                    f"Found {len(featured_videos)} unique video(s) across "
                    f"{len(suggested_focus_areas)} learning angle(s) for {safe_topic!r}."
                ),
                "video_resources": categorized_videos,
                "featured_videos": featured_videos,
                "reference_links": reference_links,
                "suggested_focus_areas": suggested_focus_areas,
                "generated_at": _utc_now_iso(),
            }
        except ValueError as err:
            return _error_payload(tool_name, str(err), topic=topic)
        except HttpError as err:
            logger.exception("YouTube API error in find_learning_resources")
            return _error_payload(
                tool_name,
                f"YouTube API error: {_format_youtube_http_error(err)}",
                topic=topic,
            )
        except Exception as err:
            logger.exception("Unexpected error in find_learning_resources")
            return _error_payload(tool_name, f"Unexpected error: {err}", topic=topic)
