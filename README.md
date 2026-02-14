# Sentinel

Multi-agent AI system for automated production incident analysis. Sentinel investigates production incidents the same way a senior SRE would — checking logs, metrics, deployments, and runbooks — and delivers a root cause analysis with recommended fixes in seconds instead of minutes.

## Architecture

Sentinel uses a three-agent pipeline:

1. **Triage Agent** — Classifies incoming alerts, assesses severity, and identifies the blast radius across dependent services.
2. **Research Agent** — Investigates by calling tools (log search, metrics, deployment history, runbook search) and correlates findings to identify root cause.
3. **Remediation Agent** — Proposes fixes based on research findings and operational runbooks, flagging high-risk actions for human approval.

## Tech Stack

- **Claude API** (Anthropic) — LLM reasoning engine for all agents
- **ChromaDB** — Vector database for RAG over operational runbooks
- **FastAPI** — REST API for triggering and querying incident analyses
- **Streamlit** — Dashboard for visualizing agent traces and incident reports
- **MCP** — Model Context Protocol server for AI tool interoperability
- **Prometheus / Grafana** — System observability and cost tracking

## Quick Start

```bash
# Setup
make setup
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Ingest runbooks into vector store
make ingest

# Start the API server
make run

# Run the demo scenario
make demo
```

## API Server

```bash
make api   # Start FastAPI server on port 8000
```

Endpoints:
- `POST /api/v1/analyze` — Run full incident analysis pipeline
- `GET /api/v1/incidents` — List recent incidents
- `GET /api/v1/incidents/{id}` — Get full incident report
- `GET /api/v1/incidents/{id}/trace` — Get agent decision trace
- `POST /api/v1/runbooks/search` — Search runbooks via RAG
- `GET /api/v1/health` — Health check
- `GET /metrics` — Prometheus metrics

## MCP Server

Sentinel exposes its capabilities via the [Model Context Protocol](https://modelcontextprotocol.io/) so any MCP-compatible AI client can use it as a tool provider.

```bash
make mcp   # Start the MCP server
```

### Claude Desktop Configuration

Add this to your Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "sentinel": {
      "command": "/path/to/Sentinel/.venv/bin/python",
      "args": ["-m", "protocols.mcp_server"],
      "cwd": "/path/to/Sentinel",
      "env": {
        "ANTHROPIC_API_KEY": "your-api-key",
        "LLM_PROVIDER": "anthropic"
      }
    }
  }
}
```

Replace `/path/to/Sentinel` with the actual path to your project directory.

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `analyze_incident` | Run the full Triage → Research → Remediation pipeline on an incident |
| `search_runbooks` | Search operational runbooks via vector similarity |
| `get_service_health` | Get current health metrics for a service |

### Available MCP Resources

| Resource | Description |
|----------|-------------|
| `runbook://{filename}` | Read a specific runbook by filename |
| `runbook://index` | List all available runbooks |

## Development

```bash
make test        # Run tests
make lint        # Run ruff linter
make typecheck   # Run mypy type checker
```

## Docker

```bash
make docker-up   # Start all services (API, dashboard, Prometheus, Grafana)
make docker-down # Stop all services
```

## Project Structure

```
Sentinel/
├── agent/          # Multi-agent orchestrator and individual agents
├── rag/            # RAG engine (ChromaDB + sentence-transformers)
├── tools/          # Simulated observability tools (logs, metrics, deploys)
├── protocols/      # MCP server and A2A communication
├── api/            # FastAPI REST API
├── dashboard/      # Streamlit dashboard
├── monitoring/     # Prometheus metrics, tracing, cost tracking
├── runbooks/       # Operational runbook markdown files
├── simulation/     # Simulated incident data
├── tests/          # Test suite
└── ADR/            # Architecture Decision Records
```

## Architecture Decision Records

See [ADR/](ADR/) for key design decisions:
- [001 — Raw API over LangChain](ADR/001-raw-api-over-langchain.md)
- [002 — ChromaDB over Pinecone](ADR/002-chroma-over-pinecone.md)
- [003 — Multi-Agent Architecture](ADR/003-multi-agent-architecture.md)
- [004 — MCP and A2A Protocols](ADR/004-mcp-and-a2a-protocols.md)
- [005 — Simulated Data Strategy](ADR/005-simulated-data-strategy.md)
