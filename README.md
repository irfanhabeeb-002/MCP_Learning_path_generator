<div align="center">

# AI Learning Path Generator

### An agentic AI system that turns a natural-language learning goal into a structured, day-wise study plan — backed by real YouTube videos discovered through a custom MCP server.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.58-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2-1C3C3C)](https://langchain-ai.github.io/langgraph/)
[![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash-4285F4?logo=google&logoColor=white)](https://aistudio.google.com/)
[![FastMCP](https://img.shields.io/badge/FastMCP-3.3-0EA5E9)](https://gofastmcp.com/)
[![MCP](https://img.shields.io/badge/Model%20Context%20Protocol-MCP-6366F1)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**[Live Demo](https://mcp-learningpath-generator.streamlit.app/)** · **[Repository](https://github.com/irfanhabeeb-002/MCP_Learning_path_generator)** · **[Report Bug](https://github.com/irfanhabeeb-002/MCP_Learning_path_generator/issues)**

</div>

---

## Project Overview

**AI Learning Path Generator** is a production-style **Python AI project** that turns a natural-language learning goal into a structured, day-wise study plan backed by real YouTube educational content. Instead of hard-coding API integrations inside the agent, the system exposes capabilities through a **Model Context Protocol (MCP) server** — a pattern increasingly used in **agentic AI** systems to separate reasoning from tool execution.

Users describe what they want to learn. A **LangGraph ReAct agent** powered by **Gemini 2.5 Flash** plans the curriculum, calls MCP tools to discover videos, and returns a polished markdown learning path. Credentials live in environment variables; the Streamlit UI collects only the learning goal.

> Built as a portfolio-grade demonstration of **AI workflow automation**, **MCP server design**, and **personalized learning roadmap** generation.

---

## Problem Statement

Creating a structured learning plan is time-consuming. Learners must:

- Break a broad goal into a logical daily sequence
- Find trustworthy, level-appropriate video content
- Avoid duplicate or low-quality resources
- Assemble everything into a readable format

Traditional approaches — manual curation, static course lists, or monolithic LLM prompts without tool access — produce inconsistent results, hallucinated URLs, or unstructured output. Hard-wiring YouTube and other APIs directly into the agent couples orchestration logic to external services and makes tools harder to reuse, test, or swap.

---

## Solution

This project decouples the **AI agent** from **external integrations** using MCP:

| Layer | Responsibility |
|-------|----------------|
| **Streamlit UI** | Collects the learning goal, shows progress, renders markdown output |
| **LangGraph ReAct Agent** | Plans days, selects tools, synthesizes the final learning path |
| **Gemini 2.5 Flash** | Reasoning and natural-language generation |
| **Custom FastMCP Server** | Exposes typed tools over Streamable HTTP |
| **YouTube Data API** | Authoritative video search and metadata |

The agent never invents video URLs. Tools return **structured JSON**; the model formats human-readable markdown for the user. **Server-side tool call limits** prevent runaway searches and protect API quota.

---

## Features

- **Personalized learning roadmaps** — Day-wise topics, objectives, and one recommended video per day
- **LangGraph ReAct agent** — Tool-augmented reasoning with controlled recursion (`recursion_limit=25`)
- **Gemini 2.5 Flash orchestration** — Fast, cost-effective planning and synthesis
- **System-prompt injection** — Agent instructions passed via `create_react_agent(prompt=SystemMessage(...))` for reliable instruction-following
- **Custom FastMCP server** — Self-hosted MCP tools over **Streamable HTTP** transport
- **YouTube Data API integration** — Education-biased search (category 27) with structured video metadata
- **Broad resource discovery** — `find_learning_resources` aggregates 3 angled searches + Wikipedia summaries
- **Tool call limiting** — Enforced server-side: 1 × `find_learning_resources`, 3 × `search_youtube` per run
- **Per-run UUID correlation** — `X-Agent-Run-Id` header links agent session to MCP rate limits
- **Clean response pipeline** — Extracts only the final AI markdown; no tool JSON in the UI
- **Double-trigger guard** — `st.rerun()` pattern ensures the generate button is disabled before the blocking agent call starts
- **Timeout + progress feedback** — UI shows countdown and auto-cancels via `asyncio.wait_for`
- **Environment-based configuration** — `GOOGLE_API_KEY`, `YOUTUBE_API_KEY`, `MCP_SERVER_URL` via `.env`

---

## User Interface & Screenshots

Here is the step-by-step visual workflow of the **AI Learning Path Generator**:

### 1. Home — Goal Input (Empty State)
The initial landing page displays the welcome header, quick usage guidelines, an empty text input field, and the generation button.
<p align="center">
  <img src="docs/images/home.png" alt="1. Empty Goal Input State" width="90%" style="border-radius: 8px; border: 1px solid #e2e8f0; box-shadow: 0 4px 12px rgba(0,0,0,0.05);" />
</p>

### 2. Goal Entered — Ready to Generate
Once you enter a learning goal (e.g., *"I want to learn Python basics in 3 days"*), the form registers the input and readies the application for generation.
<p align="center">
  <img src="docs/images/home_with_goal.png" alt="2. Goal Entered State" width="90%" style="border-radius: 8px; border: 1px solid #e2e8f0; box-shadow: 0 4px 12px rgba(0,0,0,0.05);" />
</p>

### 3. Learning Path Generated — Result
After processing, the screen displays the structured day-by-day roadmap containing custom objectives and clickable, curated YouTube resource video links.
<p align="center">
  <img src="docs/images/home_with_result.png" alt="3. Generated Learning Path Results" width="90%" style="border-radius: 8px; border: 1px solid #e2e8f0; box-shadow: 0 4px 12px rgba(0,0,0,0.1);" />
</p>

---

## Architecture Diagram

### High-level system view

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER (Browser)                                  │
│                   Learning Goal + Generate Button                       │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    STREAMLIT APP  (app.py)                              │
│   • st.rerun() double-trigger guard                                     │
│   • Progress bar (Setup → Integration → Generation)                     │
│   • Markdown-only result rendering                                      │
│   • No credentials in UI — loads .env via python-dotenv                 │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                 LANGGRAPH REACT AGENT  (utils.py)                       │
│   • create_react_agent(Gemini 2.5 Flash, MCP tools, prompt=SystemMsg)  │
│   • asyncio.wait_for() — AGENT_TIMEOUT_SECONDS hard ceiling             │
│   • extract_final_learning_path() — strips tool messages / JSON        │
│   • X-Agent-Run-Id header for per-run tool budgets                      │
└───────────────┬─────────────────────────────────────┬───────────────────┘
                │                                     │
                ▼                                     ▼
┌───────────────────────────┐       ┌───────────────────────────────────┐
│   GEMINI 2.5 FLASH        │       │   MultiServerMCPClient            │
│   Google AI Studio        │       │   transport: streamable_http      │
│   Planning + synthesis    │       │   url: MCP_SERVER_URL             │
└───────────────────────────┘       └─────────────────┬─────────────────┘
                                                      │
                                                      ▼
                                    ┌───────────────────────────────────┐
                                    │   FASTMCP SERVER  (mcp_server/)   │
                                    │   Streamable HTTP @ /mcp          │
                                    │   YouTube client singleton        │
                                    │   httpx client singleton          │
                                    │  ┌─────────────────────────────┐  │
                                    │  │ find_learning_resources     │  │
                                    │  │ search_youtube              │  │
                                    │  │ tool_limits.py (enforced)   │  │
                                    │  └─────────────────────────────┘  │
                                    └─────────────────┬─────────────────┘
                                                      │
                              ┌───────────────────────┼───────────────────┐
                              ▼                       ▼                   ▼
                    YouTube Data API v3        Wikipedia REST API   Structured JSON
                    (video search)             (reference links)    tool responses
```

### Component diagram (Mermaid)

```mermaid
flowchart TB
    subgraph Client["Presentation Layer"]
        UI["Streamlit UI<br/>app.py"]
    end

    subgraph Orchestration["Agent Layer"]
        Agent["LangGraph ReAct Agent<br/>utils.py"]
        LLM["Gemini 2.5 Flash<br/>ChatGoogleGenerativeAI"]
        Prompt["System Prompt<br/>prompt.py → SystemMessage"]
    end

    subgraph MCP["MCP Layer"]
        ClientMCP["MultiServerMCPClient<br/>streamable_http"]
        Server["FastMCP Server<br/>mcp_server/server.py"]
        Limits["Tool Call Limiter<br/>tool_limits.py"]
        T1["find_learning_resources"]
        T2["search_youtube"]
    end

    subgraph External["External APIs"]
        YT["YouTube Data API v3"]
        Wiki["Wikipedia REST API"]
    end

    UI --> Agent
    Prompt --> Agent
    LLM --> Agent
    Agent --> ClientMCP
    ClientMCP -->|"HTTP + X-Agent-Run-Id"| Server
    Server --> Limits
    Limits --> T1
    Limits --> T2
    T1 --> YT
    T1 --> Wiki
    T2 --> YT
    Agent -->|"markdown only"| UI
```

---

## MCP Architecture

This project implements the **Model Context Protocol (MCP)** — an open standard for connecting AI applications to external tools and data sources. Rather than relying on third-party MCP hosts, the repository ships a **custom MCP server** built with **FastMCP**.

### Why a custom MCP server?

| Approach | Trade-off |
|----------|-----------|
| **Third-party MCP proxies** | Fast setup, but opaque tool catalogs, vendor lock-in, per-integration URLs |
| **Custom FastMCP server** | Full control over tools, schemas, rate limits, and deployment |

### Transport: Streamable HTTP

The MCP server exposes tools at:

```text
http://127.0.0.1:8001/mcp
```

The LangGraph app connects via `langchain-mcp-adapters` using `transport: "streamable_http"`, the same protocol family used by production MCP deployments. This enables:

- Network-separated agent and tool processes
- Multiple concurrent clients
- Standard HTTP infrastructure (load balancers, health checks, auth headers)

### MCP client configuration

```python
{
    "learning_path": {
        "url": "http://127.0.0.1:8001/mcp",
        "transport": "streamable_http",
        "headers": {"X-Agent-Run-Id": "<uuid-per-run>"},
    }
}
```

The `X-Agent-Run-Id` header ties tool invocations to a single learning-path generation run, enabling **server-side rate limiting**. FastMCP normalises all header names to lowercase internally — the server reads `x-agent-run-id`.

---

## Agent Workflow

The **LangGraph ReAct agent** follows a plan → act → observe → synthesize loop:

```mermaid
sequenceDiagram
    participant U as User
    participant S as Streamlit
    participant A as LangGraph Agent
    participant G as Gemini 2.5 Flash
    participant M as MCP Server
    participant Y as YouTube API

    U->>S: Enter learning goal
    S->>S: st.rerun() — disable button before blocking call
    S->>A: run_agent_sync(goal)
    A->>G: Plan day-wise structure (system prompt)
    G->>A: Internal plan
    A->>M: find_learning_resources(topic)
    M->>Y: Multi-angle searches (3×)
    Y-->>M: Video metadata (JSON)
    M-->>A: Structured JSON response
    opt Gap filling (≤3 calls)
        A->>M: search_youtube(query)
        M->>Y: Targeted search
        Y-->>M: Video metadata
        M-->>A: Structured JSON
    end
    A->>G: Select videos + format markdown
    G-->>A: Final learning path
    A->>S: extract_final_learning_path()
    S->>U: Render markdown only
```

### Prompt-driven steps

1. **Plan** — Derive exact day count and topics from the user goal; default to 5 days if unstated
2. **Discover** — Call `find_learning_resources` once, then `search_youtube` only if needed
3. **Select** — Choose one video per day from tool results (no invented URLs; no hallucinated channels)
4. **Format** — Emit standardized markdown: Goal, Duration, Day N, Further Reading, Recommended Channels
5. **Deliver** — Return only the markdown learning path as the final message

---

## Technology Stack

| Category | Technology | Version | Role |
|----------|------------|---------|------|
| **Frontend** | [Streamlit](https://streamlit.io/) | 1.58 | Web UI, progress bar, markdown rendering |
| **Agent framework** | [LangGraph](https://langchain-ai.github.io/langgraph/) | 1.2 | ReAct agent graph (`create_react_agent`) |
| **LLM** | [Gemini 2.5 Flash](https://aistudio.google.com/) | — | Reasoning and content generation |
| **LLM SDK** | `langchain-google-genai` | 4.2 | Gemini ↔ LangChain integration |
| **Agent core** | `langchain` / `langchain-core` | 1.3 / 1.4 | Message types, runnables, config |
| **MCP client** | `langchain-mcp-adapters` | 0.2 | `MultiServerMCPClient` |
| **MCP server** | [FastMCP](https://gofastmcp.com/) | 3.3 | Tool registration, Streamable HTTP |
| **MCP protocol** | `mcp` | 1.27 | Underlying MCP wire protocol (transitive) |
| **Video data** | YouTube Data API v3 | — | Authoritative search and metadata |
| **HTTP client** | `httpx` | 0.28 | Wikipedia REST API (singleton client) |
| **Reference data** | Wikipedia REST API | — | Supplemental reading links |
| **Config** | `python-dotenv` | 1.2 | Environment variable loading |
| **Language** | Python | 3.11+ | End-to-end implementation |

---

## Project Structure

```text
MCP_Learning_path_generator/
│
├── app.py                      # Streamlit frontend — progress UX, double-trigger guard
├── utils.py                    # Agent setup, MCP client, response extraction, timeout
├── prompt.py                   # SystemMessage prompt — duration rules, anti-hallucination
├── requirements.txt            # App layer deps (~=X.Y.Z three-component pins)
├── .env.example                # Environment variable template
│
├── docs/
│   └── images/                 # Screenshots for README
│
└── mcp_server/
    ├── server.py               # FastMCP entrypoint (streamable-http transport)
    ├── tools.py                # search_youtube, find_learning_resources + singletons
    ├── tool_limits.py          # Per-run tool call enforcement (thread-safe, 30-min TTL)
    └── requirements.txt        # MCP server deps (~=X.Y.Z three-component pins)
```

---

## Installation

Two processes are required and run in **separate virtual environments**. The app layer and MCP server have different dependency trees; keeping them separate prevents version conflicts.

### Prerequisites

- Python 3.11 or later
- [Google AI Studio API key](https://aistudio.google.com/) (Gemini 2.5 Flash)
- [YouTube Data API v3 key](https://console.cloud.google.com/) with YouTube Data API v3 enabled

### 1. Clone the repository

```bash
git clone https://github.com/irfanhabeeb-002/MCP_Learning_path_generator.git
cd MCP_Learning_path_generator
```

### 2. Set up the Streamlit app environment

```bash
python3.11 -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

### 3. Set up the MCP server environment (separate venv)

```bash
python3.11 -m venv mcp_server/.venv
source mcp_server/.venv/bin/activate   # macOS / Linux
# mcp_server\.venv\Scripts\activate    # Windows

pip install -r mcp_server/requirements.txt
```

> **Why two virtual environments?**  
> The MCP server uses `fastmcp`, `uvicorn`, and `google-api-python-client` — packages not needed by the Streamlit app. The app uses `streamlit`, `langchain`, and `langgraph` — not needed by the server. Separate envs eliminate cross-dependency conflicts and mirror the production pattern where each process runs in its own container.

---

## Configuration

Copy the environment template and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`. **Never commit `.env` to version control** — it is in `.gitignore`.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_API_KEY` | Yes | — | Google AI Studio key for Gemini 2.5 Flash |
| `YOUTUBE_API_KEY` | Yes | — | YouTube Data API v3 key (MCP server only) |
| `MCP_SERVER_URL` | No | `http://127.0.0.1:8001/mcp` | MCP server endpoint for the agent |
| `MCP_HOST` | No | `127.0.0.1` | MCP server bind host |
| `MCP_PORT` | No | `8001` | MCP server bind port |
| `YOUTUBE_MAX_RESULTS` | No | `10` | Max videos per YouTube search (1–50) |
| `LOG_LEVEL` | No | `INFO` | MCP server log verbosity |
| `AGENT_TIMEOUT_SECONDS` | No | `300` | Hard ceiling on agent wall-clock time |

---

## Running Locally

### Terminal 1 — MCP server

```bash
cd mcp_server
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows

python server.py
```

Expected output:

```text
INFO: Starting MCP server 'Learning Path Generator MCP'
INFO: Uvicorn running on http://127.0.0.1:8001
```

### Terminal 2 — Streamlit application

```bash
# From project root, with venv active
source venv/bin/activate       # macOS / Linux
streamlit run app.py
```

Open **http://localhost:8501**, enter a learning goal, and click **Generate Learning Path**.

### Example goals

- *"I want to learn Python basics in 5 days"*
- *"Create a 7-day introduction to machine learning"*
- *"Help me learn React hooks in 3 days"*

---

## Docker

The project uses a multi-container architecture:

- Streamlit container
- FastMCP server container

Both services communicate over an internal Docker bridge network.

### Build and run

```bash
docker compose up --build
```

### Detached mode

```bash
docker compose up -d
```

### Stop

```bash
docker compose down
```

Docker preserves the same two-process architecture used during development.

---

## YouTube API Quota

The YouTube Data API v3 free tier grants **10,000 units/day**. Each `search.list` call costs **100 units**.

| Operation | Calls | Units |
|-----------|-------|-------|
| `find_learning_resources` | 3 searches | 300 |
| `search_youtube` (max) | 3 searches | 300 |
| **Worst case per run** | **6 searches** | **600** |
| **Free tier budget** | — | **10,000/day** |
| **Max full runs/day** | **~16** | — |

For a portfolio demo this is fine. For production, add a response cache (Redis or `functools.lru_cache` keyed on sanitized query) to reduce unit spend significantly.

---

## MCP Server Design

The custom **FastMCP server** is intentionally minimal: two focused tools instead of a sprawling third-party catalog. This keeps latency, quota usage, and agent confusion low.

### Design principles

1. **Structured JSON responses** — Every tool returns `{ success, tool, ... }` for reliable agent parsing
2. **Education-biased search** — YouTube queries prefer category 27 (Education) with `safeSearch=strict`
3. **Server-side guardrails** — Tool limits enforced in `tool_limits.py`, not only in prompts
4. **Singleton clients** — YouTube API client and `httpx.Client` built once per process; no per-call discovery fetches
5. **Separation of concerns** — YouTube credentials stay on the MCP server; Gemini credentials stay in the agent layer
6. **Streamable HTTP** — Production-aligned transport for remote deployment

### Tool limit enforcement

```text
Agent run starts → UUID generated → sent as X-Agent-Run-Id header
        │
        ▼
Each tool call → tool_limits.py reads header (lowercase normalised by FastMCP)
        │
        ├── Within limit → increment counter → execute tool
        └── Exceeded     → return { success: false, error: "..." } gracefully
```

---

## Tool Architecture

### `find_learning_resources(topic: str)` — max **1** call per run

Performs three angled YouTube searches (beginner, tutorial, advanced), deduplicates results by `video_id`, and optionally attaches a Wikipedia summary.

**Response shape (simplified):**

```json
{
  "success": true,
  "tool": "find_learning_resources",
  "topic": "python basics",
  "video_resources": {
    "getting_started": [...],
    "tutorials": [...],
    "deep_dives": [...]
  },
  "featured_videos": [...],
  "reference_links": [{ "title": "...", "url": "...", "type": "wikipedia" }],
  "suggested_focus_areas": ["Getting Started", "Tutorials"]
}
```

### `search_youtube(query: str)` — max **3** calls per run

Targeted YouTube Data API search for a specific day or topic gap.

**Response shape (simplified):**

```json
{
  "success": true,
  "tool": "search_youtube",
  "query": "python variables beginner tutorial",
  "result_count": 10,
  "videos": [
    {
      "video_id": "...",
      "title": "...",
      "channel_title": "...",
      "url": "https://www.youtube.com/watch?v=...",
      "description": "...",
      "thumbnail_url": "..."
    }
  ]
}
```

---

## Learning Path Generation Flow

```text
 User Goal
     │
     ▼
┌─────────────┐
│ 1. PLAN     │  Agent derives exact N days, topics, objectives (no tools)
└──────┬──────┘
       ▼
┌─────────────┐
│ 2. DISCOVER │  find_learning_resources (1×) + search_youtube (0–3×)
└──────┬──────┘
       ▼
┌─────────────┐
│ 3. SELECT   │  One video per day from JSON tool results; no invented URLs
└──────┬──────┘
       ▼
┌─────────────┐
│ 4. FORMAT   │  Markdown: Goal, Duration, Day 1…N, Further Reading
└──────┬──────┘
       ▼
┌─────────────┐
│ 5. DELIVER  │  extract_final_learning_path() → Streamlit markdown
└─────────────┘
```

**Output sections:** `# Title` · `## Goal` · `## Duration` · `## Day N` · `## Further Reading` · `## Recommended Channels`

---

## Why MCP Instead of Traditional APIs

| Traditional inline API calls | MCP-based architecture |
|------------------------------|------------------------|
| API logic embedded in agent code | Tools live in a dedicated MCP server |
| Hard to reuse across agents or IDEs | Standard protocol; tools consumable by any MCP client |
| Prompt-only rate discipline | Server-enforced tool call limits |
| Tight coupling to SDKs | Swap or extend tools without rewriting the agent |
| Opaque integration surface | Typed tools with JSON schemas and descriptions |

MCP is particularly valuable for **agentic AI** systems where the set of capabilities grows over time. This project demonstrates the pattern at a manageable scope: two well-defined tools, one HTTP endpoint, one LangGraph agent.

---

## Technical Highlights

- **`create_react_agent(prompt=SystemMessage(...))`** — System instructions injected into the system-role slot for reliable constraint-following, not appended to the human message
- **`asyncio.wait_for` timeout** — `AGENT_TIMEOUT_SECONDS` (default 300s) caps wall-clock agent time; displayed in the UI so users know the expected wait
- **`st.rerun()` double-trigger guard** — Goal stashed in `pending_goal` session state; `is_generating=True` + `st.rerun()` forces a re-render with the button disabled before the blocking call starts
- **Section header fix** — `prev_section` captured before `st.session_state.last_section` is overwritten; was always `False` before
- **YouTube client singleton** — `build()` called once per process; eliminates up to 5 extra discovery-document fetches per generation run
- **`httpx.Client` singleton** — TCP connection pool reused across Wikipedia calls; timeout reduced 10s → 5s
- **`extract_final_learning_path()`** — Reverse-walks message history; skips tool JSON and tool-call-only steps to return only the final markdown
- **`ConfigurationError`** — Fails fast when `.env` is incomplete; no silent partial setup
- **Per-run UUID correlation** — `X-Agent-Run-Id` header links agent session to MCP rate limits; FastMCP normalises to lowercase — only lowercase form is valid in `tool_limits.py`
- **Thread-safe in-memory limiter** — 30-minute TTL on run counters; `threading.Lock` for correctness under concurrent requests
- **No credentials in Streamlit UI** — Portfolio-ready security posture for demos and interviews

---

## Testing

The project includes automated unit tests for both the Streamlit application layer and the MCP server.

### Main application

```bash
pytest tests/
```

### MCP server

```bash
pytest mcp_server/tests/
```

### Coverage

- **52 unit tests**
- **No real API calls** during tests
- External services mocked using `pytest-mock` and `monkeypatch`
- Environment-variable testing
- Tool limiter and response sanitization tests

Test execution completes in under 2 seconds.

---

## Future Roadmap

- [ ] **Deploy MCP server** to cloud (Cloud Run, Fly.io, Railway) with HTTPS and API key authentication
- [ ] **Response caching** — Redis cache keyed on sanitized YouTube queries to reduce quota spend below 100 units/run
- [ ] **Playlist and export** — Generate YouTube playlists or downloadable PDF/Markdown exports
- [ ] **Persistent storage** — Save and revisit past learning paths (SQLite / Postgres)
- [ ] **Additional MCP tools** — Google Drive export, Notion pages, flashcard generation
- [ ] **Structured output mode** — Gemini JSON schema for stricter markdown section validation
- [ ] **Redis-backed rate limits** — Replace in-memory `ToolCallLimiter` for multi-instance MCP server deployments
- [ ] **CI pipeline** — Lint, type-check (`mypy --strict`), and integration tests against mocked YouTube responses
- [ ] **Async cancel** — Background thread + `threading.Event` for true mid-run cancellation in Streamlit

---

## CI/CD

GitHub Actions automatically runs:

1. Main pytest suite
2. MCP server pytest suite
3. Docker image builds

Every push and pull request is validated before deployment.

Streamlit Cloud provides automatic deployment after successful pushes.

### DevOps diagram

```mermaid
flowchart TD
    A[Push to GitHub] --> B[GitHub Actions]
    B --> C[Main pytest suite]
    B --> D[MCP pytest suite]
    C --> E[Docker build]
    D --> E
    E --> F[Streamlit Cloud Deployment]
```

---

## Contributing

Contributions are welcome. Please open an issue or pull request on [GitHub](https://github.com/irfanhabeeb-002/MCP_Learning_path_generator).

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Install both dependency sets (see Installation above)
4. Make your changes with tests where applicable
5. Push and open a Pull Request

---

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with LangGraph · Gemini 2.5 Flash · FastMCP · Streamlit**

If this project helped you, consider giving it a ⭐ on [GitHub](https://github.com/irfanhabeeb-002/MCP_Learning_path_generator).

</div>
