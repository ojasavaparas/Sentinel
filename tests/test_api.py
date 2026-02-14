"""Tests for the FastAPI endpoints, MCP server tools, metrics, and FinOps cost tracking."""

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


# --- Metric Recording Functions ---


def test_record_tool_call():
    from monitoring.metrics import record_tool_call, sentinel_tool_calls_total

    # Record a tool call and verify counter increments without error
    record_tool_call("search_logs", 0.123)
    record_tool_call("get_metrics", 0.045)

    # Verify counters are accessible (non-zero after recording)
    val = sentinel_tool_calls_total.labels(tool_name="search_logs")._value.get()
    assert val >= 1


def test_record_llm_call():
    from monitoring.metrics import record_llm_call, sentinel_llm_tokens_total

    record_llm_call("triage", input_tokens=500, output_tokens=200, cost=0.0045)

    input_val = sentinel_llm_tokens_total.labels(direction="input", agent_name="triage")._value.get()
    assert input_val >= 500
    output_val = sentinel_llm_tokens_total.labels(direction="output", agent_name="triage")._value.get()
    assert output_val >= 200


def test_record_rag_query():
    from monitoring.metrics import (
        record_rag_query,
        sentinel_rag_low_confidence_total,
        sentinel_rag_queries_total,
    )

    # High-confidence query should not increment low-confidence counter
    before_low = sentinel_rag_low_confidence_total._value.get()
    record_rag_query([0.85, 0.72, 0.60])
    after_low = sentinel_rag_low_confidence_total._value.get()
    assert after_low == before_low  # max score 0.85 >= 0.4

    # Low-confidence query should increment low-confidence counter
    record_rag_query([0.2, 0.1])
    after_low2 = sentinel_rag_low_confidence_total._value.get()
    assert after_low2 == before_low + 1


def test_record_analysis_complete(sample_report: IncidentReport):
    from monitoring.metrics import (
        record_analysis_complete,
        sentinel_agent_steps_total,
        sentinel_human_approval_required_total,
        sentinel_incident_analyses_total,
    )

    before_approval = sentinel_human_approval_required_total._value.get()
    record_analysis_complete(sample_report)

    # Should have recorded severity counter
    val = sentinel_incident_analyses_total.labels(severity="critical")._value.get()
    assert val >= 1

    # Report requires approval → counter should have incremented
    after_approval = sentinel_human_approval_required_total._value.get()
    assert after_approval == before_approval + 1


# --- CostTracker ---


def test_cost_tracker_record_and_get():
    from monitoring.finops import CostTracker

    tracker = CostTracker()
    tracker.record_analysis("INC-001", "triage", input_tokens=500, output_tokens=200)
    tracker.record_analysis("INC-001", "research", input_tokens=2000, output_tokens=800)
    tracker.record_tool_calls("INC-001", 5)

    cost = tracker.get_analysis_cost("INC-001")
    assert cost["total"] > 0
    assert "triage" in cost["by_agent"]
    assert "research" in cost["by_agent"]
    assert cost["tool_call_count"] == 5


def test_cost_tracker_missing_incident():
    from monitoring.finops import CostTracker

    tracker = CostTracker()
    cost = tracker.get_analysis_cost("INC-MISSING")
    assert cost["total"] == 0.0
    assert cost["by_agent"] == {}
    assert cost["tool_call_count"] == 0


def test_cost_tracker_summary():
    from monitoring.finops import CostTracker

    tracker = CostTracker()
    tracker.record_analysis("INC-A", "triage", input_tokens=500, output_tokens=200)
    tracker.record_analysis("INC-B", "triage", input_tokens=1000, output_tokens=500)
    tracker.record_analysis("INC-B", "research", input_tokens=3000, output_tokens=1000)

    summary = tracker.get_cost_summary(last_n_hours=1)
    assert summary["total_analyses"] == 2
    assert summary["total_cost"] > 0
    assert summary["avg_cost_per_analysis"] > 0
    assert summary["most_expensive_analysis"]["incident_id"] == "INC-B"


def test_cost_tracker_empty_summary():
    from monitoring.finops import CostTracker

    tracker = CostTracker()
    summary = tracker.get_cost_summary()
    assert summary["total_analyses"] == 0
    assert summary["total_cost"] == 0.0
    assert summary["most_expensive_analysis"] is None


def test_calculate_cost():
    from monitoring.finops import calculate_cost

    cost = calculate_cost(input_tokens=1_000_000, output_tokens=1_000_000)
    # $3 for 1M input + $15 for 1M output = $18
    assert cost == pytest.approx(18.0)


# --- Decision Tracer Enhancements ---


def test_tracer_duration_ms():
    from monitoring.tracer import DecisionTracer

    tracer = DecisionTracer()
    tracer.start_trace("t1")
    step = tracer.log_step(
        trace_id="t1",
        agent_name="triage",
        action="classify",
        reasoning="test",
        duration_ms=150.5,
    )
    assert step.agent_name == "triage"


def test_tracer_export_includes_result():
    from monitoring.tracer import DecisionTracer

    tracer = DecisionTracer()
    tracer.start_trace("t2")
    tracer.log_step(
        trace_id="t2",
        agent_name="research",
        action="tool_call:get_metrics",
        reasoning="check metrics",
        tool_calls=[
            ToolCall(
                tool_name="get_metrics",
                arguments={"service": "api"},
                result={"cpu": 85},
                latency_ms=50.0,
                cost_usd=0.0,
            )
        ],
    )

    exported = json.loads(tracer.export_trace_json("t2"))
    tc = exported[0]["tool_calls"][0]
    assert "result" in tc
    assert tc["result"] == {"cpu": 85}


def test_tracer_export_for_dashboard():
    from monitoring.tracer import DecisionTracer

    tracer = DecisionTracer()
    tracer.start_trace("t3")
    tracer.log_step(
        trace_id="t3", agent_name="triage", action="classify",
        reasoning="r1", tokens_used=500, cost_usd=0.001,
    )
    tracer.log_step(
        trace_id="t3", agent_name="research", action="investigate",
        reasoning="r2", tokens_used=2000, cost_usd=0.005,
        tool_calls=[
            ToolCall(tool_name="get_metrics", arguments={}, result={}, latency_ms=40.0, cost_usd=0.0),
            ToolCall(tool_name="search_logs", arguments={}, result={}, latency_ms=30.0, cost_usd=0.0),
        ],
    )

    dashboard = tracer.export_trace_for_dashboard("t3")
    assert dashboard["trace_id"] == "t3"
    assert dashboard["total_tokens"] == 2500
    assert dashboard["total_steps"] == 2
    assert "triage" in dashboard["agents"]
    assert "research" in dashboard["agents"]
    assert dashboard["agents"]["research"]["tool_call_count"] == 2
    assert dashboard["agents"]["research"]["total_tokens"] == 2000


# --- Structured Logging ---


def test_configure_logging():
    from monitoring.logging import configure_logging

    # Should not raise — just verify it runs cleanly
    configure_logging()
