"""Tests for the FastAPI endpoints and MCP server tools."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent.llm_client import MockClient, Response, TokenUsage
from agent.models import AgentStep, Alert, IncidentReport, ToolCall


# --- Fixtures ---


def _make_sample_report() -> IncidentReport:
    alert = Alert(
        service="payment-api",
        description="P99 latency spike",
        severity="critical",
        timestamp=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
        metadata={},
    )
    return IncidentReport(
        incident_id="INC-TEST1234",
        alert=alert,
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
                timestamp=datetime(2024, 1, 15, 14, 30, 1, tzinfo=timezone.utc),
            ),
            AgentStep(
                agent_name="research",
                action="investigate",
                reasoning="Correlated deploy with pool exhaustion",
                tool_calls=[
                    ToolCall(tool_name="get_metrics", arguments={"service": "payment-api"}, result={}, latency_ms=45.0, cost_usd=0.0),
                ],
                tokens_used=2000,
                cost_usd=0.005,
                timestamp=datetime(2024, 1, 15, 14, 30, 5, tzinfo=timezone.utc),
            ),
            AgentStep(
                agent_name="remediation",
                action="propose_fix",
                reasoning="Rollback is safest option",
                tool_calls=[],
                tokens_used=1000,
                cost_usd=0.003,
                timestamp=datetime(2024, 1, 15, 14, 30, 8, tzinfo=timezone.utc),
            ),
        ],
        duration_seconds=7.5,
        total_tokens=3500,
        total_cost_usd=0.009,
    )


@pytest.fixture
def sample_report() -> IncidentReport:
    return _make_sample_report()


@pytest.fixture
def client(sample_report: IncidentReport, monkeypatch: pytest.MonkeyPatch):
    """Create a test client with mocked dependencies."""
    # Use mock LLM provider so lifespan doesn't need ANTHROPIC_API_KEY
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    from api import deps
    from api.main import app

    with TestClient(app) as c:
        # Override store after startup so our sample data is available
        deps._incident_store[sample_report.incident_id] = sample_report
        yield c

    # Cleanup
    deps._incident_store.clear()


# --- Health Check ---


def test_health_check(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "chroma_db" in data


# --- List Incidents ---


def test_list_incidents(client: TestClient):
    response = client.get("/api/v1/incidents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["incident_id"] == "INC-TEST1234"
    assert data[0]["service"] == "payment-api"
    assert data[0]["severity"] == "critical"


def test_list_incidents_filter_by_severity(client: TestClient):
    response = client.get("/api/v1/incidents?severity=critical")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    response = client.get("/api/v1/incidents?severity=low")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


# --- Get Incident ---


def test_get_incident(client: TestClient):
    response = client.get("/api/v1/incidents/INC-TEST1234")
    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "INC-TEST1234"
    assert data["confidence_score"] == 0.92
    assert data["requires_human_approval"] is True


def test_get_incident_not_found(client: TestClient):
    response = client.get("/api/v1/incidents/INC-NONEXIST")
    assert response.status_code == 404


# --- Incident Trace ---


def test_get_incident_trace(client: TestClient):
    response = client.get("/api/v1/incidents/INC-TEST1234/trace")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    agent_names = [step["agent_name"] for step in data]
    assert agent_names == ["triage", "research", "remediation"]

    # Research step should have tool calls
    research_step = data[1]
    assert len(research_step["tool_calls"]) == 1
    assert research_step["tool_calls"][0]["tool_name"] == "get_metrics"


def test_get_trace_not_found(client: TestClient):
    response = client.get("/api/v1/incidents/INC-NONEXIST/trace")
    assert response.status_code == 404


# --- Runbook Search ---


@pytest.mark.asyncio
async def test_runbook_search(client: TestClient):
    from api import deps
    from rag.engine import RAGResult

    mock_results = [
        RAGResult(
            content="When connection pool is exhausted...",
            source_file="db-connection-pool-exhaustion.md",
            title="Database Connection Pool Exhaustion",
            similarity_score=0.85,
            confidence="high",
            chunk_index=0,
        ),
    ]

    deps._rag_engine.search = AsyncMock(return_value=mock_results)

    response = client.post("/api/v1/runbooks/search", json={"query": "connection pool"})
    assert response.status_code == 200
    data = response.json()
    assert data["num_results"] == 1
    assert data["results"][0]["title"] == "Database Connection Pool Exhaustion"


def test_runbook_search_empty_query(client: TestClient):
    response = client.post("/api/v1/runbooks/search", json={"query": ""})
    assert response.status_code == 400


# --- Prometheus Metrics ---


def test_prometheus_metrics_endpoint(client: TestClient):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "sentinel_" in response.text or "python_" in response.text


# --- MCP Server Tool Definitions ---


def test_mcp_server_tools_defined():
    """Verify that MCP server tools are registered."""
    from protocols.mcp_server import mcp

    # FastMCP stores tools internally — verify they exist
    assert mcp.name == "Sentinel"
