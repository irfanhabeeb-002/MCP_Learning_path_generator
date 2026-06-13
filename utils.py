from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any, Callable, Optional


class ConfigurationError(Exception):
    """Raised when required environment variables are missing."""


class AgentTimeoutError(Exception):
    """Raised when agent execution exceeds the configured time limit."""


try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # Allow import to succeed; env vars can still be set in the shell.
    pass

from langchain_core.messages import AIMessage
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from prompt import user_goal_prompt

DEFAULT_MCP_SERVER_URL = "http://127.0.0.1:8001/mcp"

# ReAct loop budget: 1 planning + up to 4 tool rounds + final answer ≈ 15 steps.
# 25 provides headroom without allowing runaway tool loops (old value: 100).
RECURSION_LIMIT = 25

# Hard ceiling on wall-clock agent time — prevents silent quota burn on hung runs.
DEFAULT_AGENT_TIMEOUT_SECONDS = 300

AGENT_CONFIG = RunnableConfig(recursion_limit=RECURSION_LIMIT)

# Keys that identify MCP tool JSON payloads (not final markdown).
_TOOL_JSON_MARKERS = frozenset({"success", "tool", "videos", "video_resources", "featured_videos"})


def _agent_timeout_seconds() -> int:
    raw = os.getenv("AGENT_TIMEOUT_SECONDS", str(DEFAULT_AGENT_TIMEOUT_SECONDS))
    try:
        timeout = int(raw)
    except ValueError as exc:
        raise ConfigurationError(
            f"AGENT_TIMEOUT_SECONDS must be an integer (got {raw!r})."
        ) from exc
    if timeout < 1:
        raise ConfigurationError("AGENT_TIMEOUT_SECONDS must be at least 1.")
    return timeout


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(
            f"{name} is not set. Add it to your .env file in the project root."
        )
    return value


def initialize_model() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=_require_env("GOOGLE_API_KEY"),
    )


def _get_mcp_tools_config(agent_run_id: str) -> dict:
    """Build MultiServerMCPClient config; run ID header enables server-side tool limits."""
    mcp_url = os.getenv("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL)
    return {
        "learning_path": {
            "url": mcp_url,
            "transport": "streamable_http",
            "headers": {"X-Agent-Run-Id": agent_run_id},
        }
    }


def _message_text(message: AIMessage) -> str:
    """Extract plain text from an AIMessage (string or multimodal content blocks)."""
    content = message.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts).strip()
    return ""


def _looks_like_tool_json(text: str) -> bool:
    """
    Return True when text parses as a structured MCP tool payload.

    Avoids treating arbitrary JSON-like markdown as intermediate ReAct noise.
    """
    if not text.startswith("{") or not text.endswith("}"):
        return False
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    return bool(_TOOL_JSON_MARKERS.intersection(payload.keys()))


def _is_intermediate_ai_message(message: AIMessage, text: str) -> bool:
    """Skip ReAct steps that only relay tool calls or raw tool JSON."""
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls and not text:
        return True
    if _looks_like_tool_json(text):
        return True
    return False


def _sanitize_learning_path_markdown(text: str) -> str:
    """Normalize the final model output for Streamlit markdown rendering."""
    text = text.strip()

    # Strip accidental markdown code fences wrapping the entire response.
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    return text


def extract_final_learning_path(agent_state: dict) -> str:
    """
    Return only the final AI-authored learning path from the LangGraph state.

    Skips human messages, tool messages, and intermediate AI messages that only
    contain tool calls or structured MCP JSON payloads.
    """
    messages = agent_state.get("messages", [])
    if not messages:
        raise ValueError("The agent did not return any messages.")

    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue

        text = _message_text(message)
        if not text or _is_intermediate_ai_message(message, text):
            continue

        return _sanitize_learning_path_markdown(text)

    raise ValueError("No learning path was generated. Please try again.")


async def setup_agent_with_tools(
    agent_run_id: str,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Any:
    """Set up the LangGraph ReAct agent with tools from the custom MCP server."""
    try:
        if progress_callback:
            progress_callback("Preparing your learning path...")

        tools_config = _get_mcp_tools_config(agent_run_id)

        if progress_callback:
            progress_callback("Connecting to learning resources...")

        # langchain-mcp-adapters >= 0.1.0: MultiServerMCPClient is NOT an async context
        # manager. get_tools() is the supported stateless pattern — each tool invocation
        # opens its own MCP session and cleans up afterward.
        mcp_client = MultiServerMCPClient(tools_config)

        if progress_callback:
            progress_callback("Loading available resources...")

        tools = await mcp_client.get_tools()

        if progress_callback:
            progress_callback("Starting AI assistant...")

        agent = create_react_agent(initialize_model(), tools)

        if progress_callback:
            progress_callback("Ready to build your plan...")

        return agent
    except ConfigurationError:
        raise
    except Exception as e:
        print(f"Error in setup_agent_with_tools: {e}")
        raise


async def _run_agent_async(
    user_goal: str,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """Async agent pipeline: setup → invoke (with timeout) → extract markdown."""
    agent_run_id = str(uuid.uuid4())
    timeout = _agent_timeout_seconds()

    agent = await setup_agent_with_tools(
        agent_run_id=agent_run_id,
        progress_callback=progress_callback,
    )

    learning_path_prompt = f"User Goal: {user_goal}\n{user_goal_prompt}"

    if progress_callback:
        progress_callback("Researching videos and building your plan...")

    agent_state = await asyncio.wait_for(
        agent.ainvoke(
            {"messages": [HumanMessage(content=learning_path_prompt)]},
            config=AGENT_CONFIG,
        ),
        timeout=timeout,
    )

    if progress_callback:
        progress_callback("Finalizing your learning path...")

    return extract_final_learning_path(agent_state)


def run_agent_sync(
    user_goal: str = "",
    progress_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Run the agent synchronously and return only the final learning-path markdown.

    Uses a dedicated event loop for Streamlit's synchronous execution model.
    Wall-clock time is capped by AGENT_TIMEOUT_SECONDS (default 300s) via
    asyncio.wait_for to prevent runaway token burn on hung agent loops.

    Note: This call blocks the Streamlit thread for the duration of the run.
    Progress callbacks may update placeholders mid-run, but the UI cannot be
    cancelled interactively until the timeout fires.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            _run_agent_async(user_goal, progress_callback)
        )
    except asyncio.TimeoutError as exc:
        timeout = _agent_timeout_seconds()
        raise AgentTimeoutError(
            f"Learning path generation timed out after {timeout} seconds. "
            "Try a shorter or simpler goal, then retry."
        ) from exc
    finally:
        loop.close()
