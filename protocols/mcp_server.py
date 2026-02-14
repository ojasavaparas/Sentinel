"""MCP server — exposes Sentinel capabilities via Model Context Protocol."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from agent.core import IncidentAnalyzer
from agent.llm_client import create_client
from agent.models import Alert
from rag.engine import RAGEngine
from rag.ingest import COLLECTION_NAME, ingest_runbooks
from tools.metrics import get_metrics

# Initialize the MCP server
mcp = FastMCP(
    "Sentinel",
    instructions="AI-powered production incident analysis system",
)

# Lazy-initialized singletons
_rag_engine: RAGEngine | None = None
_analyzer: IncidentAnalyzer | None = None


def _ensure_runbooks() -> None:
    """Ingest runbooks if not already done."""
    import chromadb

    persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_data")
    client = chromadb.PersistentClient(path=persist_dir)
    try:
        collection = client.get_collection(COLLECTION_NAME)
        if collection.count() == 0:
            raise ValueError("empty")
    except Exception:
        ingest_runbooks()


def _get_rag_engine() -> RAGEngine:
    global _rag_engine
    if _rag_engine is None:
        _ensure_runbooks()
        _rag_engine = RAGEngine()
    return _rag_engine


def _get_analyzer() -> IncidentAnalyzer:
    global _analyzer
    if _analyzer is None:
        llm_client = create_client()
        rag_engine = _get_rag_engine()
        _analyzer = IncidentAnalyzer(llm_client=llm_client, rag_engine=rag_engine)
    return _analyzer


# --- MCP Tools ---


@mcp.tool()
async def analyze_incident(
    service: str,
    description: str,
    severity: str = "high",
) -> str:
    """Analyze a production incident using the Sentinel multi-agent pipeline.

    Runs three AI agents (Triage → Research → Remediation) to investigate the
    incident, identify root cause, and propose fixes. Returns a full incident
    report with evidence and remediation steps.

    Args:
        service: The affected service name (e.g. 'payment-api')
        description: Description of the incident symptoms
        severity: Alert severity: critical, high, medium, or low
    """
    analyzer = _get_analyzer()

    alert = Alert(
        service=service,
        description=description,
        severity=severity,
        timestamp=datetime.now(UTC),
        metadata={},
    )

    report = await analyzer.analyze(alert)

    return json.dumps(
        {
            "incident_id": report.incident_id,
            "summary": report.summary,
            "root_cause": report.root_cause,
            "confidence_score": report.confidence_score,
            "remediation_steps": report.remediation_steps,
            "requires_human_approval": report.requires_human_approval,
            "duration_seconds": report.duration_seconds,
            "total_tokens": report.total_tokens,
            "total_cost_usd": report.total_cost_usd,
        },
        indent=2,
    )


@mcp.tool()
async def search_runbooks(query: str) -> str:
    """Search operational runbooks for troubleshooting procedures and remediation steps.

    Uses vector similarity search over your team's runbook documentation to find
    relevant procedures, commands, and escalation paths.

    Args:
        query: Describe the issue or topic to search for
            (e.g. 'database connection pool exhaustion')
    """
    engine = _get_rag_engine()
    results = await engine.search(query, top_k=3)

    output = []
    for r in results:
        output.append({
            "title": r.title,
            "source_file": r.source_file,
            "confidence": r.confidence,
            "similarity_score": r.similarity_score,
            "content": r.content,
        })

    return json.dumps(output, indent=2)


@mcp.tool()
async def get_service_health(service: str) -> str:
    """Get current health metrics for a service.

    Returns the latest metrics including CPU usage, memory, latency, error rate,
    and database connection pool utilization.

    Args:
        service: The service name to check (e.g. 'payment-api', 'order-service')
    """
    metrics = await get_metrics(service=service)

    if not metrics:
        return json.dumps({"error": f"No metrics found for service '{service}'"})

    # Group by metric name, take the latest value
    latest: dict[str, dict] = {}
    for m in metrics:
        name = m["metric_name"]
        if name not in latest or m["timestamp"] > latest[name]["timestamp"]:
            latest[name] = m

    return json.dumps(
        {
            "service": service,
            "metrics": [
                {
                    "metric": v["metric_name"],
                    "value": v["value"],
                    "unit": v["unit"],
                    "timestamp": v["timestamp"],
                }
                for v in latest.values()
            ],
        },
        indent=2,
    )


# --- MCP Resources ---


@mcp.resource("runbook://{filename}")
async def get_runbook(filename: str) -> str:
    """Read an operational runbook by filename."""
    runbook_path = Path(__file__).resolve().parent.parent / "runbooks" / filename
    if not runbook_path.exists():
        return f"Runbook not found: {filename}"
    return runbook_path.read_text(encoding="utf-8")


# List available runbooks as resources
@mcp.resource("runbook://index")
async def list_runbooks() -> str:
    """List all available operational runbooks."""
    runbook_dir = Path(__file__).resolve().parent.parent / "runbooks"
    if not runbook_dir.exists():
        return "No runbooks directory found"

    files = sorted(runbook_dir.glob("*.md"))
    return json.dumps(
        [{"filename": f.name, "title": f.stem.replace("-", " ").title()} for f in files],
        indent=2,
    )


if __name__ == "__main__":
    mcp.run()
