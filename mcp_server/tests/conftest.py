"""
Shared pytest fixtures for mcp_server tests.

Adds mcp_server/ to sys.path so that `from tools import ...` and
`from tool_limits import ...` resolve correctly when running pytest
from the project root with the mcp_server/.venv activated.
"""

import sys
import os
from pathlib import Path

# Make mcp_server/ importable as a package root
MCP_SERVER_DIR = Path(__file__).resolve().parent.parent  # .../mcp_server/
if str(MCP_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_DIR))

import pytest
