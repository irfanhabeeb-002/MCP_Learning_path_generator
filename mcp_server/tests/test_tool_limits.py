"""
Unit tests for mcp_server/tool_limits.py — 7 tests.

We test ToolCallLimiter directly (bypassing FastMCP's HTTP context)
by instantiating the class ourselves and calling check_and_increment.
The get_http_headers dependency only matters for enforce_tool_limit(),
which we test separately via monkeypatching.

Run:
    source mcp_server/.venv/bin/activate
    pytest mcp_server/tests/test_tool_limits.py -v
"""

import time
import pytest
from unittest.mock import patch

# fastmcp.server.dependencies stub (same as in test_tools.py)
import sys
from unittest.mock import MagicMock as _MagicMock

_dep_module = _MagicMock()
_dep_module.get_http_headers = _MagicMock(return_value={"x-agent-run-id": "test-run"})
sys.modules.setdefault("fastmcp.server.dependencies", _dep_module)

from tool_limits import ToolCallLimiter, TOOL_LIMITS, enforce_tool_limit


# ===========================================================================
# ToolCallLimiter.check_and_increment
# ===========================================================================

class TestCheckAndIncrement:
    def setup_method(self):
        """Fresh limiter for every test — no shared state."""
        self.limiter = ToolCallLimiter()

    def test_first_call_is_allowed(self):
        allowed, err = self.limiter.check_and_increment("run-1", "search_youtube")
        assert allowed is True
        assert err is None

    def test_call_at_limit_is_rejected(self):
        limit = TOOL_LIMITS["search_youtube"]   # == 3
        for _ in range(limit):
            allowed, _ = self.limiter.check_and_increment("run-1", "search_youtube")
            assert allowed is True

        # The (limit + 1)-th call must be rejected
        allowed, err = self.limiter.check_and_increment("run-1", "search_youtube")
        assert allowed is False
        assert "limit" in err.lower()

    def test_find_learning_resources_limit_is_1(self):
        allowed, _ = self.limiter.check_and_increment("run-1", "find_learning_resources")
        assert allowed is True

        allowed, err = self.limiter.check_and_increment("run-1", "find_learning_resources")
        assert allowed is False

    def test_different_run_ids_are_independent(self):
        limit = TOOL_LIMITS["search_youtube"]
        for _ in range(limit):
            self.limiter.check_and_increment("run-A", "search_youtube")

        # run-A is exhausted, but run-B starts fresh
        allowed, err = self.limiter.check_and_increment("run-B", "search_youtube")
        assert allowed is True
        assert err is None

    def test_unknown_tool_is_always_allowed(self):
        # A tool not in TOOL_LIMITS should never be blocked
        for _ in range(100):
            allowed, err = self.limiter.check_and_increment("run-1", "some_future_tool")
            assert allowed is True


# ===========================================================================
# Stale run purge
# ===========================================================================

class TestStalePurge:
    def test_stale_runs_are_cleaned_up(self):
        limiter = ToolCallLimiter()

        # Exhaust limit for run-old
        limit = TOOL_LIMITS["search_youtube"]
        for _ in range(limit):
            limiter.check_and_increment("run-old", "search_youtube")

        # Backdate the last-seen timestamp past the TTL
        with limiter._lock:
            limiter._last_seen["run-old"] = time.monotonic() - (31 * 60)

        # Trigger purge by making any new call; run-old should be evicted
        limiter.check_and_increment("run-trigger", "search_youtube")

        with limiter._lock:
            assert "run-old" not in limiter._counts

    def test_fresh_run_is_not_purged(self):
        limiter = ToolCallLimiter()
        limiter.check_and_increment("run-fresh", "search_youtube")

        # Not old enough to purge
        with limiter._lock:
            limiter._last_seen["run-fresh"] = time.monotonic() - 60  # 1 minute ago

        limiter.check_and_increment("run-trigger", "search_youtube")

        with limiter._lock:
            assert "run-fresh" in limiter._counts


# ===========================================================================
# enforce_tool_limit  (via mocked get_agent_run_id)
# ===========================================================================

class TestEnforceToolLimit:
    def test_delegates_to_limiter_with_correct_run_id(self, monkeypatch):
        import tool_limits

        # Reset the global limiter so there's no stale state
        tool_limits._limiter = ToolCallLimiter()

        monkeypatch.setattr(tool_limits, "get_agent_run_id", lambda: "injected-run-id")

        allowed, err = enforce_tool_limit("search_youtube")
        assert allowed is True

        # Confirm the run ID was tracked
        with tool_limits._limiter._lock:
            assert "injected-run-id" in tool_limits._limiter._counts
