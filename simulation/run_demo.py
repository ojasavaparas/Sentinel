"""Demo script — runs a full incident analysis on a sample payment-api alert."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.core import IncidentAnalyzer
from agent.llm_client import (
    MockClient,
    Response,
    TokenUsage,
    create_client,
)
from agent.models import Alert
from rag.engine import RAGEngine
from rag.ingest import ingest_runbooks

# ---------------------------------------------------------------------------
# Pre-scripted demo responses (used when no API key is available)
# ---------------------------------------------------------------------------

_TRIAGE_RESULT = {
    "classification": "resource-exhaustion",
    "affected_services": ["payment-api", "order-service"],
    "priority": "P1",
    "summary": (
        "Payment-api experiencing database connection pool "
        "exhaustion causing P99 latency spike to 2100ms and "
        "15% error rate. Cascading impact on downstream "
        "order-service detected."
    ),
    "delegation_instructions": (
        "Investigate payment-api ERROR logs for database "
        "timeout patterns. Check recent deployments within "
        "the last 60 minutes for configuration changes. "
        "Query db_connection_pool metrics for utilization "
        "trend. Search runbooks for connection pool "
        "exhaustion remediation procedures."
    ),
}

_RESEARCH_RESULT = {
    "timeline": [
        {
            "timestamp": "2024-01-15T14:00:00Z",
            "event": (
                "Deployment a1bf3d2 applied to "
                "payment-api by sarah.chen"
            ),
        },
        {
            "timestamp": "2024-01-15T14:15:00Z",
            "event": (
                "DB connection pool utilization "
                "begins climbing (30% to 75%)"
            ),
        },
        {
            "timestamp": "2024-01-15T14:25:00Z",
            "event": (
                "First SQLSTATE 08006 timeout errors "
                "appear in payment-api logs"
            ),
        },
        {
            "timestamp": "2024-01-15T14:28:00Z",
            "event": (
                "Connection pool reaches 98% capacity "
                "— new connections queueing"
            ),
        },
        {
            "timestamp": "2024-01-15T14:30:00Z",
            "event": (
                "P99 latency spikes to 2100ms, "
                "error rate reaches 15%"
            ),
        },
    ],
    "root_cause": (
        "Deployment a1bf3d2 by sarah.chen at 14:00 UTC "
        "modified the database connection pool configuration, "
        "reducing max_connections from 50 to 10. Under normal "
        "traffic load, the reduced pool was exhausted within "
        "30 minutes, causing connection timeouts (SQLSTATE "
        "08006) and cascading latency spikes across "
        "payment-api and downstream order-service."
    ),
    "confidence": 0.95,
    "evidence": [
        (
            "Deployment a1bf3d2 at 14:00 UTC is the only "
            "change in the 2-hour window before the incident"
        ),
        (
            "DB connection pool utilization jumped from "
            "30% to 98% starting 15 minutes post-deploy"
        ),
        (
            "47 SQLSTATE 08006 connection timeout errors "
            "logged between 14:25 and 14:30"
        ),
        (
            "Latency increase directly correlates with "
            "pool utilization increase"
        ),
        (
            "Runbook 'Database Connection Pool Exhaustion' "
            "matches all observed symptoms"
        ),
    ],
    "relevant_runbooks": [
        "Database Connection Pool Exhaustion",
        "High Latency Troubleshooting",
    ],
    "affected_services": ["payment-api", "order-service"],
}

_REMEDIATION_RESULT = {
    "remediation_steps": [
        {
            "step": 1,
            "action": (
                "Roll back deployment a1bf3d2 to "
                "previous stable revision"
            ),
            "risk": "high",
            "requires_approval": True,
            "rationale": (
                "Deployment a1bf3d2 directly caused pool "
                "exhaustion by misconfiguring max_connections. "
                "Rollback restores the working configuration."
            ),
            "runbook_reference": "Emergency Deployment Rollback",
        },
        {
            "step": 2,
            "action": (
                "Monitor db_connection_pool metric — "
                "verify utilization drops below 40% "
                "within 10 minutes"
            ),
            "risk": "low",
            "requires_approval": False,
            "rationale": (
                "Post-rollback, existing connections will "
                "drain and pool utilization should normalize. "
                "If not recovered in 10 minutes, escalate."
            ),
        },
        {
            "step": 3,
            "action": (
                "Add Prometheus alert for "
                "db_connection_pool > 80% utilization"
            ),
            "risk": "low",
            "requires_approval": False,
            "rationale": (
                "No existing alert caught the pool climbing "
                "from 30% to 98%. A threshold at 80% would "
                "provide 10-15 minutes of early warning."
            ),
        },
    ],
    "requires_human_approval": True,
    "summary": (
        "Immediate rollback of deployment a1bf3d2 required "
        "to restore database connection pool settings. "
        "Post-rollback monitoring to verify recovery, "
        "followed by adding preventive alerting."
    ),
}


def _build_demo_responses() -> list[Response]:
    """Build pre-scripted LLM responses for an impressive demo.

    Returns 5 responses in order:
      1. Triage classification (no tool calls)
      2. Research tool calls (search_logs, deployments, metrics, runbooks)
      3. Research final findings
      4. Remediation tool call (search_runbooks)
      5. Remediation final proposal
    """
    model = "claude-sonnet-4-5-20250929"

    return [
        # 1. Triage — classify the alert
        Response(
            content=json.dumps(_TRIAGE_RESULT),
            usage=TokenUsage(input_tokens=650, output_tokens=280),
            model=model,
            stop_reason="end_turn",
        ),
        # 2. Research — call 4 tools to investigate
        Response(
            content="",
            usage=TokenUsage(input_tokens=1200, output_tokens=180),
            model=model,
            stop_reason="tool_use",
            tool_calls=[
                {
                    "id": "toolu_01logs",
                    "name": "search_logs",
                    "input": {
                        "service": "payment-api",
                        "severity": "ERROR",
                    },
                },
                {
                    "id": "toolu_02deploys",
                    "name": "get_recent_deployments",
                    "input": {"service": "payment-api"},
                },
                {
                    "id": "toolu_03metrics",
                    "name": "get_metrics",
                    "input": {
                        "service": "payment-api",
                        "metric_name": "db_connection_pool",
                    },
                },
                {
                    "id": "toolu_04runbooks",
                    "name": "search_runbooks",
                    "input": {
                        "query": (
                            "database connection pool exhaustion"
                        ),
                    },
                },
            ],
        ),
        # 3. Research — final analysis after reviewing tool results
        Response(
            content=json.dumps(_RESEARCH_RESULT),
            usage=TokenUsage(input_tokens=2800, output_tokens=520),
            model=model,
            stop_reason="end_turn",
        ),
        # 4. Remediation — search runbooks for rollback procedure
        Response(
            content="",
            usage=TokenUsage(input_tokens=1500, output_tokens=120),
            model=model,
            stop_reason="tool_use",
            tool_calls=[
                {
                    "id": "toolu_05runbooks",
                    "name": "search_runbooks",
                    "input": {
                        "query": (
                            "emergency deployment rollback "
                            "procedure"
                        ),
                    },
                },
            ],
        ),
        # 5. Remediation — final proposal with steps
        Response(
            content=json.dumps(_REMEDIATION_RESULT),
            usage=TokenUsage(input_tokens=1800, output_tokens=380),
            model=model,
            stop_reason="end_turn",
        ),
    ]


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------


def ensure_runbooks_ingested() -> None:
    """Ingest runbooks if the ChromaDB collection doesn't exist yet."""
    chroma_dir = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_data")
    if not Path(chroma_dir).exists() or not any(Path(chroma_dir).iterdir()):
        print("Ingesting runbooks into vector store...")
        ingest_runbooks()
        print()
    else:
        print("Runbooks already ingested, skipping.\n")


def print_section(title: str) -> None:
    width = 70
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def _create_demo_client() -> MockClient | object:
    """Create the LLM client for the demo.

    Uses live Claude if ANTHROPIC_API_KEY is set,
    otherwise falls back to pre-scripted mock responses.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if provider != "mock" and api_key:
        print("  Mode: Live Claude API")
        return create_client()

    print(
        "  Mode: Pre-scripted demo "
        "(set ANTHROPIC_API_KEY for live Claude)"
    )
    return MockClient(responses=_build_demo_responses())


async def run_demo() -> None:
    """Run the full Sentinel demo."""
    print_section("SENTINEL — Incident Analysis Demo")

    # 1. Ensure runbooks are ingested
    ensure_runbooks_ingested()

    # 2. Create the sample alert
    alert = Alert(
        service="payment-api",
        description=(
            "P99 latency spike to 2100ms, normal baseline 180ms. "
            "Error rate increased from 0.1% to 15%. "
            "Started approximately 30 minutes after "
            "latest deployment."
        ),
        severity="critical",
        timestamp=datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC),
        metadata={
            "current_p99_ms": 2100,
            "baseline_p99_ms": 180,
            "error_rate_percent": 15.0,
        },
    )

    print_section("INCOMING ALERT")
    print(f"  Service:     {alert.service}")
    print(f"  Severity:    {alert.severity}")
    print(f"  Timestamp:   {alert.timestamp.isoformat()}")
    print(f"  Description: {alert.description}")

    # 3. Initialize the analyzer
    llm_client = _create_demo_client()
    rag_engine = RAGEngine()
    analyzer = IncidentAnalyzer(
        llm_client=llm_client, rag_engine=rag_engine,
    )

    # 4. Run analysis
    print_section("RUNNING ANALYSIS")
    print("  Triage Agent → Research Agent → Remediation Agent")
    print("  Processing...\n")

    report = await analyzer.analyze(alert)

    # 5. Print the report
    print_section("INCIDENT REPORT")
    print(f"  Incident ID:           {report.incident_id}")
    print(f"  Summary:               {report.summary}")
    print(f"  Root Cause:            {report.root_cause}")
    print(f"  Confidence:            {report.confidence_score:.0%}")
    print(f"  Requires Approval:     {report.requires_human_approval}")
    print(f"  Duration:              {report.duration_seconds}s")
    print(f"  Total Tokens:          {report.total_tokens:,}")
    print(f"  Total Cost:            ${report.total_cost_usd:.4f}")

    print_section("REMEDIATION STEPS")
    for i, step in enumerate(report.remediation_steps, 1):
        print(f"  {i}. {step}")

    print_section("AGENT DECISION TRACE")
    for step in report.agent_trace:
        tool_info = ""
        if step.tool_calls:
            names = [tc.tool_name for tc in step.tool_calls]
            tool_info = f" | Tools: {', '.join(names)}"
        print(
            f"  [{step.agent_name}] "
            f"{step.action}{tool_info}"
        )
        if step.tokens_used:
            print(
                f"           Tokens: {step.tokens_used:,} "
                f"| Cost: ${step.cost_usd:.4f}"
            )

    print_section("FULL REPORT JSON")
    report_dict = report.model_dump(mode="json")
    # Truncate agent trace reasoning for readability
    for step in report_dict.get("agent_trace", []):
        reasoning = step.get("reasoning", "")
        if len(reasoning) > 200:
            step["reasoning"] = reasoning[:200] + "..."
    print(json.dumps(report_dict, indent=2, default=str))

    print("\n" + "=" * 70)
    print("  Demo complete.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_demo())
