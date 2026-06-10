from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any, Callable, Optional


class ConfigurationError(Exception):
    """Raised when required environment variables are missing."""


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

AGENT_CONFIG = RunnableConfig(recursion_limit=RECURSION_LIMIT)


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
    contain tool calls (which may include raw MCP JSON).
    """
    messages = agent_state.get("messages", [])
    if not messages:
        raise ValueError("The agent did not return any messages.")

    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue

        text = _message_text(message)
        if not text:
            continue

        # Skip intermediate ReAct steps that are purely JSON tool payloads.
        if text.startswith("{") and text.endswith("}"):
            try:
                json.loads(text)
                continue
            except json.JSONDecodeError:
                pass

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


def run_agent_sync(
    user_goal: str = "",
    progress_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Run the agent synchronously and return only the final learning-path markdown.
    """
    agent_run_id = str(uuid.uuid4())

    async def _run() -> str:
        agent = await setup_agent_with_tools(
            agent_run_id=agent_run_id,
            progress_callback=progress_callback,
        )

        learning_path_prompt = f"User Goal: {user_goal}\n{user_goal_prompt}"

        if progress_callback:
            progress_callback("Researching videos and building your plan...")

        agent_state = await agent.ainvoke(
            {"messages": [HumanMessage(content=learning_path_prompt)]},
            config=AGENT_CONFIG,
        )

        if progress_callback:
            progress_callback("Finalizing your learning path...")

        return extract_final_learning_path(agent_state)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()
