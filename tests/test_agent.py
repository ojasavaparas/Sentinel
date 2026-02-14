"""Tests for agent orchestration and individual agents using MockClient."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agent.agents.remediation import RemediationAgent
from agent.agents.research import ResearchAgent
from agent.agents.triage import TriageAgent
from agent.core import IncidentAnalyzer
from agent.llm_client import MockClient, Response, TokenUsage
from agent.models import Alert
from monitoring.tracer import DecisionTracer
from protocols.a2a import MessageBus, new_trace_id
from tools.registry import ToolRegistry


@pytest.fixture
def sample_alert() -> Alert:
    return Alert(
        service="payment-api",
        description="P99 latency spike to 2100ms, normal baseline 180ms",
        severity="critical",
        timestamp=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
        metadata={"current_p99_ms": 2100},
    )


@pytest.fixture
def tracer() -> DecisionTracer:
    return DecisionTracer()


@pytest.fixture
def tool_registry() -> ToolRegistry:
    return ToolRegistry()


def _make_triage_response() -> Response:
    return Response(
        content=json.dumps({
            "classification": "resource-exhaustion",
            "affected_services": ["payment-api", "order-service"],
            "priority": "P1",
            "summary": "Payment-api experiencing connection pool exhaustion causing cascading latency.",
            "delegation_instructions": "Check payment-api ERROR logs for DB timeouts, check deployment history, search runbooks for connection pool exhaustion.",
        }),
        usage=TokenUsage(input_tokens=500, output_tokens=200),
        model="mock",
        stop_reason="end_turn",
    )


def _make_research_response() -> Response:
    return Response(
        content=json.dumps({
            "timeline": [
                {"timestamp": "2024-01-15T14:00:00Z", "event": "Deployment a1bf3d2 applied"},
                {"timestamp": "2024-01-15T14:25:00Z", "event": "First DB timeout errors"},
                {"timestamp": "2024-01-15T14:30:00Z", "event": "Connection pool fully exhausted"},
            ],
            "root_cause": "Deployment a1bf3d2 by sarah.chen changed DB connection pool settings, causing pool exhaustion 30 minutes after deploy.",
            "confidence": 0.92,
            "evidence": [
                "DB connection pool at 98% capacity",
                "Deploy a1bf3d2 changed pool settings at 14:00",
                "ERROR logs show SQLSTATE 08006 timeout errors starting 14:25",
            ],
            "relevant_runbooks": ["Database Connection Pool Exhaustion", "Emergency Deployment Rollback"],
            "affected_services": ["payment-api", "order-service"],
        }),
        usage=TokenUsage(input_tokens=2000, output_tokens=500),
        model="mock",
        stop_reason="end_turn",
    )


def _make_remediation_response() -> Response:
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


@pytest.mark.asyncio
async def test_triage_agent_classifies_alert(sample_alert: Alert, tracer: DecisionTracer, tool_registry: ToolRegistry):
    mock = MockClient(responses=[_make_triage_response()])
    agent = TriageAgent(mock, tool_registry, tracer)
    trace_id = new_trace_id()
    tracer.start_trace(trace_id)

    result = await agent.run(sample_alert, trace_id)

    assert result["classification"] == "resource-exhaustion"
    assert "payment-api" in result["affected_services"]
    assert result["priority"] == "P1"
    assert len(tracer.get_trace(trace_id)) > 0


@pytest.mark.asyncio
async def test_research_agent_produces_findings(tracer: DecisionTracer, tool_registry: ToolRegistry):
    mock = MockClient(responses=[_make_research_response()])
    agent = ResearchAgent(mock, tool_registry, tracer)
    trace_id = new_trace_id()
    tracer.start_trace(trace_id)

    triage_result = {
        "classification": "resource-exhaustion",
        "affected_services": ["payment-api"],
        "priority": "P1",
        "summary": "Connection pool issue",
        "delegation_instructions": "Investigate DB timeouts",
    }

    result = await agent.run(triage_result, trace_id)

    assert result["confidence"] > 0.8
    assert "a1bf3d2" in result["root_cause"]
    assert len(result["timeline"]) > 0


@pytest.mark.asyncio
async def test_remediation_agent_requires_approval(tracer: DecisionTracer, tool_registry: ToolRegistry):
    mock = MockClient(responses=[_make_remediation_response()])
    agent = RemediationAgent(mock, tool_registry, tracer)
    trace_id = new_trace_id()
    tracer.start_trace(trace_id)

    research_result = {
        "root_cause": "Deployment caused pool exhaustion",
        "confidence": 0.92,
        "evidence": ["pool at 98%"],
        "timeline": [],
        "relevant_runbooks": ["Emergency Deployment Rollback"],
        "affected_services": ["payment-api"],
    }

    result = await agent.run(research_result, trace_id)

    assert result["requires_human_approval"] is True
    assert len(result["remediation_steps"]) >= 1
    # At least one step should require approval (the rollback)
    approval_steps = [s for s in result["remediation_steps"] if s.get("requires_approval")]
    assert len(approval_steps) >= 1


@pytest.mark.asyncio
async def test_orchestrator_full_pipeline(sample_alert: Alert):
    mock = MockClient(responses=[
        _make_triage_response(),
        _make_research_response(),
        _make_remediation_response(),
    ])

    analyzer = IncidentAnalyzer(llm_client=mock)
    report = await analyzer.analyze(sample_alert)

    assert report.incident_id.startswith("INC-")
    assert report.alert == sample_alert
    assert report.confidence_score > 0.8
    assert report.requires_human_approval is True
    assert len(report.remediation_steps) >= 1
    assert report.total_tokens > 0
    assert report.duration_seconds >= 0


@pytest.mark.asyncio
async def test_agent_trace_is_recorded(sample_alert: Alert):
    mock = MockClient(responses=[
        _make_triage_response(),
        _make_research_response(),
        _make_remediation_response(),
    ])

    analyzer = IncidentAnalyzer(llm_client=mock)
    report = await analyzer.analyze(sample_alert)

    # Should have at least one step per agent
    agent_names = [step.agent_name for step in report.agent_trace]
    assert "triage" in agent_names
    assert "research" in agent_names
    assert "remediation" in agent_names


@pytest.mark.asyncio
async def test_message_bus_tracks_messages():
    bus = MessageBus()
    trace_id = new_trace_id()

    bus.send("triage", "research", "delegate", {"test": True}, trace_id)
    bus.send("research", "remediation", "delegate", {"findings": True}, trace_id)

    msgs = bus.get_messages(trace_id)
    assert len(msgs) == 2
    assert msgs[0].from_agent == "triage"
    assert msgs[1].to_agent == "remediation"


@pytest.mark.asyncio
async def test_decision_tracer_exports_json():
    tracer = DecisionTracer()
    trace_id = new_trace_id()
    tracer.start_trace(trace_id)

    tracer.log_step(trace_id, "triage", "classify", "Testing", tokens_used=100, cost_usd=0.001)
    tracer.log_step(trace_id, "research", "investigate", "Investigating", tokens_used=500, cost_usd=0.005)

    exported = tracer.export_trace_json(trace_id)
    data = json.loads(exported)
    assert len(data) == 2
    assert data[0]["agent_name"] == "triage"
    assert tracer.get_total_tokens(trace_id) == 600
