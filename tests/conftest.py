"""Shared test fixtures for Sentinel tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent.llm_client import MockClient, Response, TokenUsage
from agent.models import AgentStep, Alert, IncidentReport, ToolCall
from monitoring.tracer import DecisionTracer
from rag.engine import RAGEngine
from rag.ingest import ingest_runbooks
from tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Pre-scripted LLM responses
# ---------------------------------------------------------------------------


def _triage_response() -> Response:
    return Response(
        content=json.dumps({
            "classification": "resource-exhaustion",
            "affected_services": ["payment-api", "order-service"],
            "priority": "P1",
            "summary": (
                "Payment-api experiencing connection pool "
                "exhaustion causing cascading latency."
            ),
            "delegation_instructions": (
                "Check payment-api ERROR logs for DB timeouts, check deployment history, "
                "search runbooks for connection pool exhaustion."
            ),
        }),
        usage=TokenUsage(input_tokens=500, output_tokens=200),
        model="mock",
        stop_reason="end_turn",
    )


def _research_response() -> Response:
    return Response(
        content=json.dumps({
            "timeline": [
                {"timestamp": "2024-01-15T14:00:00Z", "event": "Deployment a1bf3d2 applied"},
                {"timestamp": "2024-01-15T14:25:00Z", "event": "First DB timeout errors"},
                {"timestamp": "2024-01-15T14:30:00Z", "event": "Connection pool fully exhausted"},
            ],
            "root_cause": (
                "Deployment a1bf3d2 by sarah.chen changed DB connection pool settings, "
                "causing pool exhaustion 30 minutes after deploy."
            ),
            "confidence": 0.92,
            "evidence": [
                "DB connection pool at 98% capacity",
                "Deploy a1bf3d2 changed pool settings at 14:00",
                "ERROR logs show SQLSTATE 08006 timeout errors starting 14:25",
            ],
            "relevant_runbooks": [
                "Database Connection Pool Exhaustion",
                "Emergency Deployment Rollback",
            ],
            "affected_services": ["payment-api", "order-service"],
        }),
        usage=TokenUsage(input_tokens=2000, output_tokens=500),
        model="mock",
        stop_reason="end_turn",
    )


def _remediation_response() -> Response:
    return Response(
        content=json.dumps({
            "remediation_steps": [
                {
                    "step": 1,
                    "action": "Roll back deployment a1bf3d2 to previous revision",
                    "risk": "high",
                    "requires_approval": True,
                    "rationale": "Deploy directly caused pool exhaustion",
                    "runbook_reference": "Emergency Deployment Rollback",
                },
                {
                    "step": 2,
                    "action": "Monitor connection pool metrics for recovery",
                    "risk": "low",
                    "requires_approval": False,
                    "rationale": "Verify pool utilization returns to normal",
                },
            ],
            "requires_human_approval": True,
            "summary": "Roll back the problematic deployment and monitor for recovery.",
        }),
        usage=TokenUsage(input_tokens=1000, output_tokens=300),
        model="mock",
        stop_reason="end_turn",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_alert() -> Alert:
    """Standard payment-api latency spike alert."""
    return Alert(
        service="payment-api",
        description="P99 latency spike to 2100ms, normal baseline 180ms",
        severity="critical",
        timestamp=datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC),
        metadata={"current_p99_ms": 2100},
    )


@pytest.fixture
def mock_llm_client() -> MockClient:
    """MockClient pre-loaded with triage → research → remediation responses."""
    return MockClient(responses=[
        _triage_response(),
        _research_response(),
        _remediation_response(),
    ])


@pytest.fixture
def tracer() -> DecisionTracer:
    """Fresh DecisionTracer instance."""
    return DecisionTracer()


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """ToolRegistry with all simulated tools (no RAG engine)."""
    return ToolRegistry()


@pytest.fixture
def rag_engine(tmp_path: Path) -> RAGEngine:
    """RAGEngine with ingested test runbooks in a temp directory."""
    runbook_dir = tmp_path / "runbooks"
    runbook_dir.mkdir()

    (runbook_dir / "database-connection-pool-exhaustion.md").write_text(
        "# Database Connection Pool Exhaustion\n\n"
        "## Symptoms\n"
        "Connection pool utilization above 90%. Spike in database timeout errors. "
        "New connections being refused or queuing indefinitely. "
        "Service latency increases proportional to pool saturation.\n\n"
        "## Investigation Steps\n"
        "### 1. Check Pool Utilization Metrics\n"
        "Query the connection pool dashboard. Normal utilization should be 30-60%. "
        "Anything above 85% indicates exhaustion risk.\n\n"
        "### 2. Identify Long-Running Queries\n"
        "Check pg_stat_activity for queries running longer than 30 seconds. "
        "Kill any queries running longer than 5 minutes.\n"
    )

    (runbook_dir / "high-latency-troubleshooting.md").write_text(
        "# High Latency Troubleshooting\n\n"
        "## Symptoms\n"
        "P99 latency exceeding normal baseline. Increased HTTP 504 errors. "
        "Upstream services reporting degraded performance.\n\n"
        "## Investigation Steps\n"
        "### 1. Check Recent Deployments\n"
        "If a deployment occurred within the last 60 minutes, it is the most likely cause. "
        "Proceed to rollback if correlation is strong.\n\n"
        "### 2. Verify Database Connection Pool\n"
        "If pool utilization exceeds 85%, the pool is near saturation.\n"
    )

    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()

    ingest_runbooks(
        runbook_dir=str(runbook_dir),
        chroma_persist_dir=str(chroma_dir),
    )
    return RAGEngine(chroma_persist_dir=str(chroma_dir))


@pytest.fixture
def sample_report(sample_alert: Alert) -> IncidentReport:
    """Complete IncidentReport for use in API tests."""
    return IncidentReport(
        incident_id="INC-TEST1234",
        alert=sample_alert,
        summary="DB connection pool exhaustion caused by bad deploy",
        root_cause="Deployment a1bf3d2 misconfigured connection pool",
        confidence_score=0.92,
        remediation_steps=[
            "Roll back deployment a1bf3d2 to previous revision",
            "Monitor connection pool metrics for recovery",
        ],
        requires_human_approval=True,
        agent_trace=[
            AgentStep(
                agent_name="triage",
                action="classify",
                reasoning="Resource exhaustion pattern detected",
                tool_calls=[],
                tokens_used=500,
                cost_usd=0.001,
                timestamp=datetime(2024, 1, 15, 14, 30, 1, tzinfo=UTC),
            ),
            AgentStep(
                agent_name="research",
                action="investigate",
                reasoning="Correlated deploy with pool exhaustion",
                tool_calls=[
                    ToolCall(
                        tool_name="get_metrics",
                        arguments={"service": "payment-api"},
                        result={},
                        latency_ms=45.0,
                        cost_usd=0.0,
                    ),
                ],
                tokens_used=2000,
                cost_usd=0.005,
                timestamp=datetime(2024, 1, 15, 14, 30, 5, tzinfo=UTC),
            ),
            AgentStep(
                agent_name="remediation",
                action="propose_fix",
                reasoning="Rollback is safest option",
                tool_calls=[],
                tokens_used=1000,
                cost_usd=0.003,
                timestamp=datetime(2024, 1, 15, 14, 30, 8, tzinfo=UTC),
            ),
        ],
        duration_seconds=7.5,
        total_tokens=3500,
        total_cost_usd=0.009,
    )
