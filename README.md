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
