"""
Unit tests for utils.py — 20 tests, zero real API calls.

Run:
    source venv/bin/activate
    pytest tests/test_utils.py -v
"""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

# Module under test
import utils
from utils import (
    ConfigurationError,
    AgentTimeoutError,
    _require_env,
    _agent_timeout_seconds,
    _looks_like_tool_json,
    _is_intermediate_ai_message,
    _sanitize_learning_path_markdown,
    _message_text,
    extract_final_learning_path,
    run_agent_sync,
)


# ===========================================================================
# _require_env
# ===========================================================================

class TestRequireEnv:
    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("SOME_KEY", "my-secret")
        assert _require_env("SOME_KEY") == "my-secret"

    def test_raises_when_missing(self, monkeypatch):
        monkeypatch.delenv("SOME_KEY", raising=False)
        with pytest.raises(ConfigurationError, match="SOME_KEY"):
            _require_env("SOME_KEY")

    def test_raises_when_blank(self, monkeypatch):
        monkeypatch.setenv("SOME_KEY", "   ")
        with pytest.raises(ConfigurationError, match="SOME_KEY"):
            _require_env("SOME_KEY")


# ===========================================================================
# _agent_timeout_seconds
# ===========================================================================

class TestAgentTimeoutSeconds:
    def test_returns_default_300(self, monkeypatch):
        monkeypatch.delenv("AGENT_TIMEOUT_SECONDS", raising=False)
        assert _agent_timeout_seconds() == 300

    def test_parses_valid_int_from_env(self, monkeypatch):
        monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "120")
        assert _agent_timeout_seconds() == 120

    def test_raises_on_non_integer_string(self, monkeypatch):
        monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "fast")
        with pytest.raises(ConfigurationError, match="must be an integer"):
            _agent_timeout_seconds()

    def test_raises_when_less_than_1(self, monkeypatch):
        monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "0")
        with pytest.raises(ConfigurationError, match="at least 1"):
            _agent_timeout_seconds()


# ===========================================================================
# _looks_like_tool_json
# ===========================================================================

class TestLooksLikeToolJson:
    def test_valid_tool_json_with_success_key(self):
        text = json.dumps({"success": True, "videos": [], "tool": "search_youtube"})
        assert _looks_like_tool_json(text) is True

    def test_plain_markdown_is_not_tool_json(self):
        assert _looks_like_tool_json("## Day 1\n**Topic:** Python") is False

    def test_malformed_json_returns_false(self):
        assert _looks_like_tool_json("{not valid json}") is False

    def test_json_without_marker_keys_returns_false(self):
        # Valid JSON dict but no keys from _TOOL_JSON_MARKERS
        assert _looks_like_tool_json('{"foo": "bar"}') is False

    def test_json_array_returns_false(self):
        # Must start with { and end with } — an array does not qualify
        assert _looks_like_tool_json('[{"success": true}]') is False


# ===========================================================================
# _sanitize_learning_path_markdown
# ===========================================================================

class TestSanitizeLearningPathMarkdown:
    def test_strips_leading_trailing_whitespace(self):
        result = _sanitize_learning_path_markdown("   ## Day 1\n   ")
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_strips_top_level_code_fence(self):
        text = "```markdown\n## Day 1\n**Topic:** Python\n```"
        result = _sanitize_learning_path_markdown(text)
        assert not result.startswith("```")
        assert "## Day 1" in result

    def test_preserves_inner_code_blocks(self):
        # Outer fence removed, but inner ```python block stays
        text = "```\n## Day 1\n```python\nprint('hello')\n```\n```"
        result = _sanitize_learning_path_markdown(text)
        assert "```python" in result

    def test_plain_markdown_returned_unchanged(self):
        text = "## Day 1\n**Topic:** Python Basics"
        assert _sanitize_learning_path_markdown(text) == text


# ===========================================================================
# extract_final_learning_path
# ===========================================================================

class TestExtractFinalLearningPath:
    def _make_ai(self, content, tool_calls=None):
        msg = AIMessage(content=content)
        if tool_calls is not None:
            msg.tool_calls = tool_calls  # type: ignore[assignment]
        return msg

    def test_returns_last_real_ai_message(self):
        state = {
            "messages": [
                HumanMessage(content="learn python"),
                self._make_ai("## Python Learning Path\n**Day 1** ..."),
            ]
        }
        result = extract_final_learning_path(state)
        assert "Python Learning Path" in result

    def test_raises_on_empty_messages(self):
        with pytest.raises(ValueError, match="did not return any messages"):
            extract_final_learning_path({"messages": []})

    def test_skips_tool_json_intermediate_message(self):
        tool_json = json.dumps({"success": True, "videos": [], "tool": "search_youtube"})
        final = "## Day 1\n**Topic:** Python"
        state = {
            "messages": [
                HumanMessage(content="learn python"),
                self._make_ai(tool_json),           # intermediate — should be skipped
                self._make_ai(final),               # final — should be returned
            ]
        }
        result = extract_final_learning_path(state)
        assert result == final

    def test_skips_message_with_tool_calls_and_no_text(self):
        intermediate = self._make_ai("", tool_calls=[{"id": "1", "name": "search_youtube", "args": {}}])
        final = self._make_ai("## Real Learning Path")
        state = {"messages": [intermediate, final]}
        result = extract_final_learning_path(state)
        assert "Real Learning Path" in result

    def test_raises_when_all_messages_are_intermediate(self):
        tool_json = json.dumps({"success": False, "tool": "search_youtube"})
        state = {"messages": [self._make_ai(tool_json)]}
        with pytest.raises(ValueError, match="No learning path was generated"):
            extract_final_learning_path(state)


# ===========================================================================
# run_agent_sync  (fully mocked — zero real calls)
# ===========================================================================

class TestRunAgentSync:
    """
    run_agent_sync wraps _run_agent_async in a new event loop.
    We patch _run_agent_async to avoid any real LLM / MCP calls.
    """

    def test_returns_string_on_success(self, monkeypatch):
        expected = "## Python Learning Path\nDay 1 ..."
        async def fake_run(user_goal, progress_callback=None):
            return expected

        monkeypatch.setattr(utils, "_run_agent_async", fake_run)
        result = run_agent_sync(user_goal="learn python")
        assert result == expected

    def test_raises_agent_timeout_error_on_asyncio_timeout(self, monkeypatch):
        async def fake_run(user_goal, progress_callback=None):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(utils, "_run_agent_async", fake_run)
        with pytest.raises(AgentTimeoutError, match="timed out"):
            run_agent_sync(user_goal="learn python")

    def test_propagates_configuration_error(self, monkeypatch):
        async def fake_run(user_goal, progress_callback=None):
            raise ConfigurationError("GOOGLE_API_KEY is not set.")

        monkeypatch.setattr(utils, "_run_agent_async", fake_run)
        with pytest.raises(ConfigurationError, match="GOOGLE_API_KEY"):
            run_agent_sync(user_goal="learn python")
