"""
Shared pytest fixtures for tests/test_utils.py.

All external dependencies (LangChain, LangGraph, MCP client) are mocked
here so no network calls are ever made.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


# ---------------------------------------------------------------------------
# AIMessage factory helpers
# ---------------------------------------------------------------------------

def make_ai_message(content, tool_calls=None):
    """Return an AIMessage with optional tool_calls."""
    msg = AIMessage(content=content)
    if tool_calls:
        msg.tool_calls = tool_calls
    return msg


def make_tool_message(content="tool result"):
    """Return a ToolMessage (not an AIMessage — should be skipped)."""
    return ToolMessage(content=content, tool_call_id="abc123")


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=False)
def clean_env(monkeypatch):
    """Remove test-sensitive env vars before each test that requests this fixture."""
    for var in ("GOOGLE_API_KEY", "AGENT_TIMEOUT_SECONDS", "MCP_SERVER_URL"):
        monkeypatch.delenv(var, raising=False)
