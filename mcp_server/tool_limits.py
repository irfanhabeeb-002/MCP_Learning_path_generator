"""
Server-side tool call limits for the Learning Path MCP server.

Each agent run is identified by the X-Agent-Run-Id header sent by the Streamlit
orchestrator. Limits are enforced in-process (per server instance).

Limits:
  - find_learning_resources: 1 call per run
  - search_youtube:          3 calls per run

Header normalisation note:
  FastMCP's get_http_headers() stores ALL header names in lowercase before
  returning them. The constant AGENT_RUN_ID_HEADER must therefore be lowercase.
  The include= set passed to get_http_headers is also lowercased internally, so
  only the lowercase form needs to be provided.

Multi-user / deployment warning:
  When the X-Agent-Run-Id header is absent (e.g. a direct curl request, a
  misconfigured client, or any non-Streamlit caller) all such requests fall into
  the shared 'anonymous' bucket. User A's tool calls count against User B's
  limit for the same 30-minute TTL window.

  This is acceptable for a localhost single-user demo. For a public or
  multi-user deployment add authentication (e.g. API key validation) and
  ensure every client sends a unique X-Agent-Run-Id per generation run.
"""

from __future__ import annotations

import threading
import time
from typing import Final

from fastmcp.server.dependencies import get_http_headers

# FastMCP normalises all header names to lowercase before returning them.
# This constant MUST be lowercase — a mixed-case form would never match.
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

    FastMCP normalises all header names to lowercase, so only the lowercase
    constant is included and looked up. The mixed-case form "X-Agent-Run-Id"
    would never appear as a dict key and must not be used here.

    Falls back to 'anonymous' when the header is absent — still rate-limited
    as one shared bucket (see module docstring for multi-user implications).
    """
    # include= accepts any case; FastMCP lowercases internally before filtering.
    headers = get_http_headers(include={AGENT_RUN_ID_HEADER})
    return headers.get(AGENT_RUN_ID_HEADER) or "anonymous"


def enforce_tool_limit(tool_name: str) -> tuple[bool, str | None]:
    """Check whether a tool call is allowed for the current agent run."""
    run_id = get_agent_run_id()
    return _limiter.check_and_increment(run_id, tool_name)
