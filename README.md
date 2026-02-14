# Sentinel

**Multi-agent AI system for automated production incident analysis.**

## What This Is

Sentinel investigates production incidents the same way a senior SRE would — checking logs, metrics, deployments, and runbooks — and delivers a root cause analysis with recommended fixes in seconds instead of minutes. It uses a three-agent pipeline (Triage → Research → Remediation) orchestrated via an A2A message bus, with RAG-powered runbook search and full decision tracing for auditability.

## Architecture

```
                          ┌─────────────────────────────────┐
                          │         Incoming Alert           │
                          │   (PagerDuty / Prometheus / API) │
                          └───────────────┬─────────────────┘
                                          │
                                          ▼
                          ┌───────────────────────────────┐
                          │        Triage Agent            │
                          │  Classify · Severity · Blast   │
                          │  Tools: metrics, dependencies  │
                          └───────────────┬───────────────┘
                                          │ A2A: delegate
                                          ▼
                          ┌───────────────────────────────┐
                          │       Research Agent           │
                          │  Investigate · Correlate       │
                          │  Tools: logs, metrics, deploys,│
                          │         runbooks (RAG)         │
                          └───────────────┬───────────────┘
                                          │ A2A: delegate
                                          ▼
                          ┌───────────────────────────────┐
                          │      Remediation Agent         │
                          │  Propose fixes · Flag risky    │
                          │  Tools: runbooks (RAG)         │
                          └───────────────┬───────────────┘
                                          │ A2A: escalate
                                          ▼
                          ┌───────────────────────────────┐
                          │       Human Approval           │
                          │  Review · Approve · Execute    │
                          └───────────────────────────────┘

  ┌──────────────┐    ┌──────────────┐    ┌───────────────┐
  │   ChromaDB   │    │  Prometheus  │    │  MCP Server   │
  │  (RAG store) │    │  + Grafana   │    │ (tool interop)│
  └──────────────┘    └──────────────┘    └───────────────┘
```

## Key Design Decisions

- **Raw Anthropic SDK over LangChain** — Full control over prompts and tool-use flow without framework abstractions ([ADR-001](ADR/001-raw-api-over-langchain.md))
- **ChromaDB over Pinecone** — Local-first vector store with zero cost for development, sufficient for runbook-scale corpora ([ADR-002](ADR/002-chroma-over-pinecone.md))
- **Three-agent pipeline** — Separation of concerns mirrors how SRE teams actually work: triage, investigate, fix ([ADR-003](ADR/003-multi-agent-architecture.md))
- **MCP + A2A protocols** — MCP for external AI tool interop, custom A2A for typed internal agent messaging ([ADR-004](ADR/004-mcp-and-a2a-protocols.md))
- **Simulated data for development** — Reproducible incident scenarios via static JSON, tool interfaces match production contracts ([ADR-005](ADR/005-simulated-data-strategy.md))

## Tech Stack

| Component | Technology | Why |
|-----------|------------|-----|
| LLM | Claude API (Anthropic) | Native tool-use support, strong reasoning for multi-step investigation |
| Vector DB | ChromaDB | Local, zero-cost, embedded Python API, persistent storage |
| API | FastAPI | Async-native, auto-generated OpenAPI docs, Pydantic integration |
| Dashboard | Streamlit | Rapid prototyping for agent trace visualization |
| Protocols | MCP + custom A2A | MCP for external AI interop, A2A for typed agent messaging |
| Observability | Prometheus + Grafana | Industry-standard metrics, token/cost tracking per agent |
| Infrastructure | AWS CDK (ECS Fargate) | Single-command deploy, auto-scaling, HTTPS via ALB + ACM |
| RAG | sentence-transformers | Local embeddings, no external API dependency |

## Quick Start

```bash
git clone https://github.com/your-org/Sentinel.git
cd Sentinel

# Create virtualenv and install dependencies
make setup

# Configure environment
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Ingest runbooks into ChromaDB
make ingest

# Run the demo scenario
make demo
```

## Running the Full Stack

```bash
docker-compose up -d
```

| Service | Port | URL |
|---------|------|-----|
| Sentinel API | 8000 | `http://localhost:8000` |
| ChromaDB | 8001 | `http://localhost:8001` |
| Prometheus | 9090 | `http://localhost:9090` |
| Grafana | 3000 | `http://localhost:3000` (admin/admin) |

## MCP Integration

Sentinel exposes its capabilities via the [Model Context Protocol](https://modelcontextprotocol.io/) so any MCP-compatible AI client can use it as a tool provider.

### Claude Desktop Configuration

Add this to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

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

### MCP Tools & Resources

| Type | Name | Description |
|------|------|-------------|
| Tool | `analyze_incident` | Run the full Triage → Research → Remediation pipeline |
| Tool | `search_runbooks` | Search operational runbooks via vector similarity |
| Tool | `get_service_health` | Get current health metrics for a service |
| Resource | `runbook://{filename}` | Read a specific runbook by filename |
| Resource | `runbook://index` | List all available runbooks |

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/analyze` | Run full incident analysis pipeline |
| `GET` | `/api/v1/incidents` | List recent incidents (supports `?severity=` filter) |
| `GET` | `/api/v1/incidents/{id}` | Get full incident report with agent trace |
| `GET` | `/api/v1/incidents/{id}/trace` | Get just the decision trace |
| `POST` | `/api/v1/runbooks/search` | Search runbooks via RAG |
| `GET` | `/api/v1/health` | Health check (ChromaDB, LLM status) |
| `GET` | `/metrics` | Prometheus metrics endpoint |

## Sample Analysis

```
Incident: INC-3A7F20B1
Service:  payment-api
Severity: critical

┌─ Triage ──────────────────────────────────────────────────┐
│ Classification: latency                                    │
│ Priority:       P1                                         │
│ Blast Radius:   payment-api → order-service → checkout-web │
│ Delegation:     "Investigate payment-api latency spike,    │
│                  check recent deploys and DB pool usage"   │
└───────────────────────────────────────────────────────────┘
       │
       ▼
┌─ Research ────────────────────────────────────────────────┐
│ Root Cause: Database connection pool exhaustion following  │
│   deployment v2.3.1 at 14:02 UTC. New ORM query bypassed  │
│   connection pooling, causing pool saturation (48/50) and  │
│   cascading P99 latency spike from 200ms to 2400ms.       │
│ Confidence: 0.92                                           │
│ Evidence:                                                  │
│   - Deploy v2.3.1 at 14:02 correlates with latency spike  │
│   - DB pool usage jumped from 12/50 to 48/50 at 14:15     │
│   - ERROR logs: "connection pool timeout" x47 in 10min     │
│   - Runbook: "DB Connection Pool Exhaustion" matches       │
└───────────────────────────────────────────────────────────┘
       │
       ▼
┌─ Remediation ─────────────────────────────────────────────┐
│ 1. [HIGH RISK] Rollback to v2.3.0        → Needs approval │
│ 2. [LOW RISK]  Increase pool size 50→100 → Needs approval │
│ 3. [LOW RISK]  Add pool monitoring alert → Auto-approved   │
└───────────────────────────────────────────────────────────┘

Agent Trace: 3 agents · 6 tool calls · 4,200 tokens · $0.018 · 8.3s
```

## What I'd Do Differently in Production

- **Streaming agent output** — SSE or WebSocket so the dashboard shows thinking in real-time rather than waiting for the full pipeline
- **Persistent incident store** — Replace the in-memory dict with PostgreSQL; current implementation loses data on restart
- **Real tool integrations** — Swap simulated tools for CloudWatch, Datadog, PagerDuty, and GitHub Deployments APIs
- **Evaluation harness** — Build a labeled dataset of incidents with known root causes to measure agent accuracy and regression-test prompt changes
- **Guardrails and retry logic** — Add structured output validation (Pydantic), LLM retry with exponential backoff, and circuit breakers on tool calls
- **Multi-tenancy** — Scope incidents, runbooks, and metrics per team/org rather than a single shared namespace
- **Fine-tuned prompts per incident type** — Specialize agent prompts for latency vs. error-rate vs. deployment-failure rather than one generic prompt

## Cost

| Item | Cost |
|------|------|
| Claude API (per analysis) | ~$0.01–0.03 (3 agents, ~4k tokens total) |
| ChromaDB | Free (local, open-source) |
| Prometheus + Grafana | Free (open-source, self-hosted) |
| AWS ECS Fargate (if deployed) | ~$1–2/day (0.5 vCPU, 1 GB RAM, scales to zero) |
| Development cost | $0 beyond API key — all components are open-source |

## Project Structure

```
Sentinel/
├── agent/              # Multi-agent orchestrator and pipeline
│   ├── agents/         # Individual agent implementations (triage, research, remediation)
│   ├── core.py         # IncidentAnalyzer — orchestrates the three-agent pipeline
│   ├── llm_client.py   # LLM abstraction (Anthropic + mock for testing)
│   ├── models.py       # Pydantic models (Alert, IncidentReport, AgentStep, etc.)
│   └── prompts.py      # System prompts for each agent
├── rag/                # RAG engine (ChromaDB + sentence-transformers)
├── tools/              # Simulated observability tools (logs, metrics, deploys, deps)
├── protocols/          # MCP server and A2A agent communication
├── api/                # FastAPI REST API
├── dashboard/          # Streamlit visualization dashboard
├── monitoring/         # Prometheus metrics, decision tracing, FinOps cost tracking
├── runbooks/           # Operational runbook markdown files
├── simulation/         # Simulated incident data (JSON scenarios)
├── infra/              # AWS CDK stack (ECS Fargate, ALB, ECR, Route 53)
├── tests/              # Test suite (84 tests)
└── ADR/                # Architecture Decision Records
```

## Architecture Decision Records

| ADR | Decision |
|-----|----------|
| [001](ADR/001-raw-api-over-langchain.md) | Raw Anthropic SDK over LangChain |
| [002](ADR/002-chroma-over-pinecone.md) | ChromaDB over Pinecone |
| [003](ADR/003-multi-agent-architecture.md) | Multi-agent pipeline architecture |
| [004](ADR/004-mcp-and-a2a-protocols.md) | MCP and A2A protocols |
| [005](ADR/005-simulated-data-strategy.md) | Simulated data strategy |
