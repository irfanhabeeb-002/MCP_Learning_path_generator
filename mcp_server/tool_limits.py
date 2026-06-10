"""
Server-side tool call limits for the Learning Path MCP server.

Each agent run is identified by the X-Agent-Run-Id header sent by the Streamlit
orchestrator. Limits are enforced in-process (per server instance).

Limits:
  - find_learning_resources: 1 call per run
  - search_youtube:          3 calls per run
"""

from __future__ import annotations

import threading
import time
from typing import Final

from fastmcp.server.dependencies import get_http_headers

AGENT_RUN_ID_HEADER: Final[str] = "x-agent-run-id"

TOOL_LIMITS: Final[dict[str, int]] = {
    "find_learning_resources": 1,
    "search_youtube": 3,
}

# Retain counters for 30 minutes, then allow garbage collection of stale runs.
_RUN_TTL_SECONDS: Final[int] = 30 * 60


class ToolCallLimiter:
    """Thread-safe, per-agent-run tool invocation counter."""

    def __init__(self) -> None:
        self._counts: dict[str, dict[str, int]] = {}
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def _purge_stale_runs(self, now: float) -> None:
        stale = [
            run_id
            for run_id, seen_at in self._last_seen.items()
            if now - seen_at > _RUN_TTL_SECONDS
        ]
        for run_id in stale:
            self._counts.pop(run_id, None)
            self._last_seen.pop(run_id, None)

    def check_and_increment(self, run_id: str, tool_name: str) -> tuple[bool, str | None]:
        """
        Return (allowed, error_message).

        Increments the counter when allowed. Rejects when the per-run limit is exceeded.
        """
        limit = TOOL_LIMITS.get(tool_name)
        if limit is None:
            return True, None

        now = time.monotonic()
        with self._lock:
            self._purge_stale_runs(now)
            self._last_seen[run_id] = now

            run_counts = self._counts.setdefault(run_id, {})
            current = run_counts.get(tool_name, 0)

            if current >= limit:
                return (
                    False,
                    (
                        f"Tool call limit reached for '{tool_name}' "
                        f"(maximum {limit} per learning path). "
                        "Use the videos and references already retrieved to "
                        "complete the learning path without additional searches."
                    ),
                )

            run_counts[tool_name] = current + 1

        return True, None


_limiter = ToolCallLimiter()


def get_agent_run_id() -> str:
    """
    Read the agent run ID from the inbound HTTP request.

    Falls back to 'anonymous' when the header is missing (still rate-limited as
    one shared bucket — acceptable for local/dev single-user usage).
    """
    headers = get_http_headers(include={AGENT_RUN_ID_HEADER, "X-Agent-Run-Id"})
    return (
        headers.get(AGENT_RUN_ID_HEADER)
        or headers.get("X-Agent-Run-Id")
        or "anonymous"
    )


def enforce_tool_limit(tool_name: str) -> tuple[bool, str | None]:
    """Check whether a tool call is allowed for the current agent run."""
    run_id = get_agent_run_id()
    return _limiter.check_and_increment(run_id, tool_name)
