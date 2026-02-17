"""Tests for the FastAPI endpoints, MCP server tools, and Prometheus metrics."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from agent.models import IncidentReport, ToolCall

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(sample_report: IncidentReport, monkeypatch: pytest.MonkeyPatch):
    """Create a test client with mocked dependencies."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    from api import deps
    from api.main import app

    with TestClient(app) as c:
        deps._incident_store[sample_report.incident_id] = sample_report
        yield c

    deps._incident_store.clear()


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------


def test_health_check(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "chroma_db" in data
    assert "llm_provider" in data


# ---------------------------------------------------------------------------
# POST /api/v1/analyze
# ---------------------------------------------------------------------------


def test_post_analyze_returns_incident_report(client: TestClient):
    """POST /analyze with a valid alert should return an IncidentReport."""
    payload = {
        "service": "payment-api",
        "description": "CPU usage at 95%",
        "severity": "high",
        "timestamp": "2024-01-15T14:30:00Z",
        "metadata": {},
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"].startswith("INC-")
    assert "summary" in data
    assert "root_cause" in data
    assert "remediation_steps" in data
    assert "agent_trace" in data
    assert isinstance(data["total_tokens"], int)
    assert isinstance(data["duration_seconds"], float)


def test_post_analyze_invalid_severity(client: TestClient):
    """POST /analyze with invalid severity should return 422."""
    payload = {
        "service": "payment-api",
        "description": "Test",
        "severity": "INVALID",
        "timestamp": "2024-01-15T14:30:00Z",
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 422


def test_post_analyze_missing_required_field(client: TestClient):
    """POST /analyze missing required fields should return 422."""
    response = client.post("/api/v1/analyze", json={"service": "x"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# List Incidents
# ---------------------------------------------------------------------------


def test_list_incidents(client: TestClient):
    response = client.get("/api/v1/incidents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    ids = [d["incident_id"] for d in data]
    assert "INC-TEST1234" in ids


def test_list_incidents_filter_by_severity(client: TestClient):
    response = client.get("/api/v1/incidents?severity=critical")
    assert response.status_code == 200
    assert len(response.json()) >= 1

    response = client.get("/api/v1/incidents?severity=low")
    assert response.status_code == 200
    # Seed data has no low-severity incidents
    assert all(i["severity"] == "low" for i in response.json())


def test_list_incidents_respects_limit(client: TestClient):
    response = client.get("/api/v1/incidents?limit=1")
    assert response.status_code == 200
    assert len(response.json()) <= 1


# ---------------------------------------------------------------------------
# Get Incident
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Incident Trace
# ---------------------------------------------------------------------------


def test_get_incident_trace(client: TestClient):
    response = client.get("/api/v1/incidents/INC-TEST1234/trace")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    agent_names = [step["agent_name"] for step in data]
    assert agent_names == ["triage", "research", "remediation"]

    research_step = data[1]
    assert len(research_step["tool_calls"]) == 1
    assert research_step["tool_calls"][0]["tool_name"] == "get_metrics"


def test_get_trace_not_found(client: TestClient):
    response = client.get("/api/v1/incidents/INC-NONEXIST/trace")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Runbook Search
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Prometheus Metrics
# ---------------------------------------------------------------------------


def test_prometheus_metrics_endpoint(client: TestClient):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "sentinel_" in response.text or "python_" in response.text


def test_prometheus_metrics_contain_sentinel_metrics(client: TestClient):
    """The metrics endpoint should expose our custom sentinel_ metrics."""
    response = client.get("/metrics")
    text = response.text
    assert "sentinel_incident_analyses_total" in text or "sentinel_active_analyses" in text


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------


def test_mcp_server_tools_defined():
    from protocols.mcp_server import mcp

    assert mcp.name == "Sentinel"


# ---------------------------------------------------------------------------
# Metric Recording Functions
# ---------------------------------------------------------------------------


def test_record_tool_call():
    from monitoring.metrics import record_tool_call, sentinel_tool_calls_total

    record_tool_call("search_logs", 0.123)
    record_tool_call("get_metrics", 0.045)

    val = sentinel_tool_calls_total.labels(tool_name="search_logs")._value.get()
    assert val >= 1


def test_record_llm_call():
    from monitoring.metrics import record_llm_call, sentinel_llm_tokens_total

    record_llm_call("triage", input_tokens=500, output_tokens=200, cost=0.0045)

    input_counter = sentinel_llm_tokens_total.labels(
        direction="input", agent_name="triage",
    )
    input_val = input_counter._value.get()
    assert input_val >= 500
    output_counter = sentinel_llm_tokens_total.labels(
        direction="output", agent_name="triage",
    )
    output_val = output_counter._value.get()
    assert output_val >= 200


def test_record_rag_query():
    from monitoring.metrics import (
        record_rag_query,
        sentinel_rag_low_confidence_total,
    )

    before_low = sentinel_rag_low_confidence_total._value.get()
    record_rag_query([0.85, 0.72, 0.60])
    after_low = sentinel_rag_low_confidence_total._value.get()
    assert after_low == before_low

    record_rag_query([0.2, 0.1])
    after_low2 = sentinel_rag_low_confidence_total._value.get()
    assert after_low2 == before_low + 1


def test_record_rag_query_empty_scores():
    from monitoring.metrics import record_rag_query, sentinel_rag_queries_total

    before = sentinel_rag_queries_total._value.get()
    record_rag_query([])
    after = sentinel_rag_queries_total._value.get()
    assert after == before + 1


def test_record_analysis_complete(sample_report: IncidentReport):
    from monitoring.metrics import (
        record_analysis_complete,
        sentinel_human_approval_required_total,
        sentinel_incident_analyses_total,
    )

    before_approval = sentinel_human_approval_required_total._value.get()
    record_analysis_complete(sample_report)

    val = sentinel_incident_analyses_total.labels(severity="critical")._value.get()
    assert val >= 1

    after_approval = sentinel_human_approval_required_total._value.get()
    assert after_approval == before_approval + 1


# ---------------------------------------------------------------------------
# Decision Tracer Enhancements
# ---------------------------------------------------------------------------


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
            ToolCall(
                tool_name="get_metrics", arguments={},
                result={}, latency_ms=40.0, cost_usd=0.0,
            ),
            ToolCall(
                tool_name="search_logs", arguments={},
                result={}, latency_ms=30.0, cost_usd=0.0,
            ),
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


# ---------------------------------------------------------------------------
# Structured Logging
# ---------------------------------------------------------------------------


def test_configure_logging():
    from monitoring.logging import configure_logging

    configure_logging()


def test_configure_logging_json_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    from monitoring.logging import configure_logging

    configure_logging()
