"""
Learning Path Generator — custom MCP server (FastMCP).

Exposes YouTube and learning-resource tools over Streamable HTTP so the
Streamlit + LangGraph app can connect via MultiServerMCPClient instead of Pipedream.

Run locally:
    cd mcp_server
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    export YOUTUBE_API_KEY="your-key"
    python server.py

MCP endpoint (default): http://127.0.0.1:8001/mcp
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

from tools import register_tools

# Load project-root .env so YOUTUBE_API_KEY is available when run from mcp_server/.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------------------------------------------------------------------------
# Logging — INFO by default; override with LOG_LEVEL=DEBUG
# ---------------------------------------------------------------------------
# Log to stderr so stdout remains clean if stdio transport is ever used for debugging.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP application
# ---------------------------------------------------------------------------

# Step 1: Create the MCP server with a name and instructions for connected clients.
# Instructions help LLM clients understand when to use each tool (optional but useful).
mcp = FastMCP(
    name="Learning Path Generator MCP",
    instructions=(
        "Tools for building personalized learning paths. "
        "Use search_youtube to find individual educational videos. "
        "Use find_learning_resources to gather a broader set of categorized resources "
        "for a topic before planning a multi-day curriculum."
    ),
)

# Step 2: Register tool functions defined in tools.py onto this server instance.
register_tools(mcp)

# Exported for `fastmcp run server.py` and test harnesses that import `mcp`.
__all__ = ["mcp"]


def _env_int(name: str, default: int) -> int:
    """Parse an integer environment variable with a safe fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default


if __name__ == "__main__":
    # Step 3: Read network settings from the environment (production-friendly).
    host = os.getenv("MCP_HOST", "127.0.0.1")
    # Default 8001 — must match utils.DEFAULT_MCP_SERVER_URL and .env.example
    port = _env_int("MCP_PORT", 8001)
    path = os.getenv("MCP_PATH", "/mcp")

    logger.info(
        "Starting Learning Path Generator MCP server "
        "(transport=streamable-http, host=%s, port=%s, path=%s)",
        host,
        port,
        path,
    )

    # Step 4: Start the Streamable HTTP transport (compatible with langchain-mcp-adapters
    # when configured as transport "streamable_http" and url http://HOST:PORT/mcp).
    #
    # FastMCP accepts "streamable-http" (hyphen). The underlying protocol is the MCP
    # Streamable HTTP spec — same family Pipedream and LangChain clients expect.
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        path=path,
    )
