"""
Unit tests for mcp_server/tools.py — 16 tests, zero real API calls.

Run:
    source mcp_server/.venv/bin/activate
    pytest mcp_server/tests/test_tools.py -v
"""

import json
import pytest
from unittest.mock import MagicMock, patch

# Patch the fastmcp.server.dependencies import BEFORE tools.py is imported,
# because tool_limits.py (imported by tools.py) calls get_http_headers at
# module level on first enforce_tool_limit() call.
import sys
from unittest.mock import MagicMock as _MagicMock

# Stub out fastmcp.server.dependencies so tool_limits imports cleanly
_dep_module = _MagicMock()
_dep_module.get_http_headers = _MagicMock(return_value={"x-agent-run-id": "test-run"})
sys.modules.setdefault("fastmcp.server.dependencies", _dep_module)

from tools import (
    _sanitize_query,
    _dedupe_videos_by_id,
    _error_payload,
    _fetch_wikipedia_summary,
    _format_youtube_http_error,
    _format_video_item,
    _get_max_results,
    _http_client,   # the module-level httpx singleton
)


# ===========================================================================
# _sanitize_query
# ===========================================================================

class TestSanitizeQuery:
    def test_trims_leading_trailing_whitespace(self):
        assert _sanitize_query("  python basics  ") == "python basics"

    def test_collapses_internal_whitespace(self):
        assert _sanitize_query("python   for   beginners") == "python for beginners"

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError, match="must not be empty"):
            _sanitize_query("")

    def test_raises_on_whitespace_only(self):
        with pytest.raises(ValueError, match="must not be empty"):
            _sanitize_query("   ")

    def test_raises_when_exceeds_max_length(self):
        long_query = "a" * 201
        with pytest.raises(ValueError, match="at most 200 characters"):
            _sanitize_query(long_query)

    def test_accepts_exactly_200_chars(self):
        ok_query = "a" * 200
        result = _sanitize_query(ok_query)
        assert len(result) == 200


# ===========================================================================
# _dedupe_videos_by_id
# ===========================================================================

class TestDedupeVideosById:
    def _video(self, vid_id, title="Video"):
        return {"video_id": vid_id, "title": title}

    def test_removes_exact_duplicates(self):
        videos = [self._video("aaa"), self._video("aaa")]
        result = _dedupe_videos_by_id(videos)
        assert len(result) == 1

    def test_preserves_first_seen_order(self):
        videos = [self._video("aaa", "First"), self._video("bbb", "Second"), self._video("aaa", "Dupe")]
        result = _dedupe_videos_by_id(videos)
        assert [v["video_id"] for v in result] == ["aaa", "bbb"]
        assert result[0]["title"] == "First"  # first-seen wins

    def test_empty_list_returns_empty(self):
        assert _dedupe_videos_by_id([]) == []

    def test_skips_entries_with_no_video_id(self):
        videos = [{"video_id": None, "title": "No ID"}, self._video("bbb")]
        result = _dedupe_videos_by_id(videos)
        assert len(result) == 1
        assert result[0]["video_id"] == "bbb"


# ===========================================================================
# _error_payload
# ===========================================================================

class TestErrorPayload:
    def test_contains_required_keys(self):
        payload = _error_payload("search_youtube", "API quota exceeded")
        assert payload["success"] is False
        assert payload["tool"] == "search_youtube"
        assert payload["error"] == "API quota exceeded"
        assert "generated_at" in payload

    def test_extra_kwargs_are_included(self):
        payload = _error_payload("search_youtube", "bad query", query="python!")
        assert payload["query"] == "python!"


# ===========================================================================
# _format_video_item
# ===========================================================================

class TestFormatVideoItem:
    def _raw_item(self, video_id="abc123"):
        return {
            "id": {"videoId": video_id},
            "snippet": {
                "title": "Python for Beginners",
                "description": "Learn Python fast",
                "channelTitle": "Tech Channel",
                "channelId": "UC123",
                "publishedAt": "2024-01-01T00:00:00Z",
                "thumbnails": {
                    "high": {"url": "https://img/high.jpg"},
                    "medium": {"url": "https://img/medium.jpg"},
                    "default": {"url": "https://img/default.jpg"},
                },
            },
        }

    def test_maps_all_fields_correctly(self):
        result = _format_video_item(self._raw_item())
        assert result["video_id"] == "abc123"
        assert result["title"] == "Python for Beginners"
        assert result["url"] == "https://www.youtube.com/watch?v=abc123"
        assert result["channel_title"] == "Tech Channel"

    def test_thumbnail_falls_back_to_medium_when_high_missing(self):
        item = self._raw_item()
        del item["snippet"]["thumbnails"]["high"]
        result = _format_video_item(item)
        assert result["thumbnail_url"] == "https://img/medium.jpg"

    def test_url_is_none_when_video_id_missing(self):
        item = {"id": {}, "snippet": {"thumbnails": {}}}
        result = _format_video_item(item)
        assert result["url"] is None
        assert result["video_id"] is None


# ===========================================================================
# _fetch_wikipedia_summary  (httpx singleton mocked)
# ===========================================================================

class TestFetchWikipediaSummary:
    def test_returns_dict_on_200_response(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "title": "Python (programming language)",
            "extract": "Python is a high-level language.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Python"}},
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(_http_client, "get", return_value=mock_response):
            result = _fetch_wikipedia_summary("Python")

        assert result is not None
        assert result["title"] == "Python (programming language)"
        assert result["type"] == "wikipedia"
        assert "url" in result

    def test_returns_none_on_404(self):
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch.object(_http_client, "get", return_value=mock_response):
            result = _fetch_wikipedia_summary("NonExistentTopic12345")

        assert result is None

    def test_returns_none_on_network_error(self):
        import httpx
        with patch.object(_http_client, "get", side_effect=httpx.ConnectError("timeout")):
            result = _fetch_wikipedia_summary("Python")
        assert result is None


# ===========================================================================
# _format_youtube_http_error
# ===========================================================================

class TestFormatYoutubeHttpError:
    def test_extracts_message_from_valid_json_body(self):
        from googleapiclient.errors import HttpError
        body = json.dumps({"error": {"message": "API key not valid"}}).encode()
        resp = MagicMock()
        resp.status = 400
        err = HttpError(resp=resp, content=body)

        result = _format_youtube_http_error(err)
        assert result == "API key not valid"

    def test_falls_back_to_str_on_malformed_body(self):
        from googleapiclient.errors import HttpError
        resp = MagicMock()
        resp.status = 500
        err = HttpError(resp=resp, content=b"not json at all")

        result = _format_youtube_http_error(err)
        # Should not raise; returns a string
        assert isinstance(result, str)
