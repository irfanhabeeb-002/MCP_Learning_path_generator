# Learning Path Generator with Model Context Protocol (MCP)

A Streamlit application that generates personalized, day-wise learning paths using a **LangGraph ReAct agent**, **Gemini 2.5 Flash**, and a **custom FastMCP server** for curated YouTube resources.

Repository: [github.com/irfanhabeeb-002/MCP_Learning_path_generator](https://github.com/irfanhabeeb-002/MCP_Learning_path_generator)

### Live demo

```
https://mcp-learningpath-generator.streamlit.app
```

## Features

- Generate personalized, day-wise learning paths from a natural-language goal
- Curated YouTube video recommendations via a custom MCP server
- LangGraph ReAct agent with Gemini 2.5 Flash orchestration
- Server-side tool call limits to control API usage
- Real-time progress tracking in Streamlit
- Environment-based configuration (no API keys in the UI)

## Architecture

```
Streamlit (app.py)
    └── LangGraph ReAct Agent (utils.py)
            ├── Gemini 2.5 Flash
            └── MultiServerMCPClient
                    └── Custom FastMCP Server (mcp_server/)
                            ├── find_learning_resources
                            └── search_youtube
                                    └── YouTube Data API v3
```

## Prerequisites

- Python 3.10+
- [Google AI Studio API key](https://aistudio.google.com/) (Gemini)
- [YouTube Data API v3 key](https://console.cloud.google.com/) (video search)

## Installation

1. Clone the repository:

```bash
git clone https://github.com/irfanhabeeb-002/MCP_Learning_path_generator.git
cd MCP_Learning_path_generator
```

2. Create and activate a virtual environment:

```bash
python3.11 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Install MCP server dependencies:

```bash
pip install -r mcp_server/requirements.txt
```

## Configuration

Copy the example environment file and add your keys:

```bash
cp .env.example .env
```

Required variables in `.env`:

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Google AI Studio key for Gemini |
| `YOUTUBE_API_KEY` | YouTube Data API v3 key |
| `MCP_SERVER_URL` | MCP endpoint (default: `http://127.0.0.1:8001/mcp`) |

## Running locally

**Terminal 1 — start the MCP server:**

```bash
cd mcp_server
python server.py
```

**Terminal 2 — start Streamlit:**

```bash
streamlit run app.py
```

Open `http://localhost:8501`, enter a learning goal, and click **Generate Learning Path**.

## Usage

1. Enter a learning goal (e.g. *"I want to learn Python basics in 5 days"*)
2. Click **Generate Learning Path**
3. Review the day-wise plan with recommended YouTube videos

No API keys or URLs are entered in the UI — configuration is loaded from `.env`.

## Project structure

```
MCP_Learning_path_generator/
├── app.py                 # Streamlit frontend
├── utils.py               # Agent orchestration, MCP client, response extraction
├── prompt.py              # Agent system prompt
├── requirements.txt       # App dependencies
├── .env.example           # Environment variable template
└── mcp_server/
    ├── server.py          # FastMCP HTTP server entrypoint
    ├── tools.py           # search_youtube, find_learning_resources
    ├── tool_limits.py     # Per-run tool call limits
    └── requirements.txt   # MCP server dependencies
```

## MCP tools

| Tool | Limit per run | Description |
|------|---------------|-------------|
| `find_learning_resources` | 1 | Broad discovery with categorized YouTube results + Wikipedia links |
| `search_youtube` | 3 | Targeted search for a specific topic or day |

## License

MIT (or your preferred license — update as needed)
