"""Tests for agent orchestration and individual agents using MockClient."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

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

# ---------------------------------------------------------------------------
# Helper response builders
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


def _tool_call_response(tool_name: str, tool_input: dict) -> Response:
    """Response that requests a tool call."""
    return Response(
        content="Let me check that.",
        tool_calls=[{
            "id": f"toolu_{tool_name}_1",
            "name": tool_name,
            "input": tool_input,
        }],
        usage=TokenUsage(input_tokens=200, output_tokens=100),
        model="mock",
        stop_reason="tool_use",
    )


# ---------------------------------------------------------------------------
# Triage Agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_triage_agent_classifies_alert(
    sample_alert: Alert, tracer: DecisionTracer, tool_registry: ToolRegistry,
):
    mock = MockClient(responses=[_triage_response()])
    agent = TriageAgent(mock, tool_registry, tracer)
    trace_id = new_trace_id()
    tracer.start_trace(trace_id)

    result = await agent.run(sample_alert, trace_id)

    assert result["classification"] == "resource-exhaustion"
    assert "payment-api" in result["affected_services"]
    assert result["priority"] == "P1"
    assert len(tracer.get_trace(trace_id)) > 0


@pytest.mark.asyncio
async def test_triage_agent_with_tool_calls(
    sample_alert: Alert, tracer: DecisionTracer, tool_registry: ToolRegistry,
):
    """Triage agent should handle tool call → result → final response loop."""
    mock = MockClient(responses=[
        _tool_call_response("get_metrics", {"service": "payment-api"}),
        _triage_response(),  # Final response after seeing tool result
    ])
    agent = TriageAgent(mock, tool_registry, tracer)
    trace_id = new_trace_id()
    tracer.start_trace(trace_id)

    result = await agent.run(sample_alert, trace_id)

    assert result["classification"] == "resource-exhaustion"
    # Should have recorded the step with tool calls
    trace = tracer.get_trace(trace_id)
    assert len(trace) == 1
    assert len(trace[0].tool_calls) == 1
    assert trace[0].tool_calls[0].tool_name == "get_metrics"


@pytest.mark.asyncio
async def test_triage_max_iterations_respected(
    sample_alert: Alert, tracer: DecisionTracer, tool_registry: ToolRegistry,
):
    """Triage should stop after max_iterations (4) even if LLM keeps requesting tools."""
    # 4 tool-call responses + 1 fallback (MockClient returns default after scripted run out)
    responses = [
        _tool_call_response("get_metrics", {"service": "payment-api"})
        for _ in range(5)
    ]
    mock = MockClient(responses=responses)
    agent = TriageAgent(mock, tool_registry, tracer)
    trace_id = new_trace_id()
    tracer.start_trace(trace_id)

    result = await agent.run(sample_alert, trace_id)

    # Should still return a result (fallback to unknown classification)
    assert "classification" in result or "summary" in result
    # MockClient should have been called at most 4 times (max_iterations)
    assert len(mock.call_history) <= 4


# ---------------------------------------------------------------------------
# Research Agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_agent_produces_findings(
    tracer: DecisionTracer, tool_registry: ToolRegistry,
):
    mock = MockClient(responses=[_research_response()])
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
async def test_research_agent_calls_tools(tracer: DecisionTracer, tool_registry: ToolRegistry):
    """Research agent should make tool calls and log them as trace steps."""
    mock = MockClient(responses=[
        _tool_call_response("search_logs", {"service": "payment-api", "severity": "ERROR"}),
        _tool_call_response("get_metrics", {"service": "payment-api"}),
        _research_response(),
    ])
    agent = ResearchAgent(mock, tool_registry, tracer)
    trace_id = new_trace_id()
    tracer.start_trace(trace_id)

    triage_result = {
        "classification": "resource-exhaustion",
        "affected_services": ["payment-api"],
        "priority": "P1",
        "summary": "Pool issue",
        "delegation_instructions": "Investigate",
    }

    result = await agent.run(triage_result, trace_id)

    assert result["confidence"] > 0.8
    # Should have tool call steps + final findings step
    trace = tracer.get_trace(trace_id)
    tool_steps = [s for s in trace if s.action.startswith("tool_call:")]
    assert len(tool_steps) == 2
    assert trace[-1].action == "research_findings"


@pytest.mark.asyncio
async def test_research_agent_max_tool_calls(tracer: DecisionTracer, tool_registry: ToolRegistry):
    """Research agent should stop after MAX_TOOL_CALLS (8) and request final analysis."""
    # 9 tool responses + 1 final response (forced after limit)
    responses = [
        _tool_call_response("get_metrics", {"service": "payment-api"})
        for _ in range(9)
    ]
    responses.append(_research_response())
    mock = MockClient(responses=responses)
    agent = ResearchAgent(mock, tool_registry, tracer)
    trace_id = new_trace_id()
    tracer.start_trace(trace_id)

    triage_result = {
        "classification": "resource-exhaustion",
        "affected_services": ["payment-api"],
        "priority": "P1",
        "summary": "Issue",
        "delegation_instructions": "Investigate",
    }

    await agent.run(triage_result, trace_id)

    # Should have exactly 8 tool call steps (MAX_TOOL_CALLS)
    trace = tracer.get_trace(trace_id)
    tool_steps = [s for s in trace if s.action.startswith("tool_call:")]
    assert len(tool_steps) == 8


# ---------------------------------------------------------------------------
# Remediation Agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remediation_agent_requires_approval(
    tracer: DecisionTracer, tool_registry: ToolRegistry,
):
    mock = MockClient(responses=[_remediation_response()])
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
    approval_steps = [s for s in result["remediation_steps"] if s.get("requires_approval")]
    assert len(approval_steps) >= 1


@pytest.mark.asyncio
async def test_remediation_forces_approval_when_missing(
    tracer: DecisionTracer, tool_registry: ToolRegistry,
):
    """If the LLM response doesn't include requires_human_approval, it defaults to True."""
    no_approval_resp = Response(
        content=json.dumps({
            "remediation_steps": [
                {"step": 1, "action": "Restart service", "risk": "low"},
            ],
            "summary": "Just restart.",
        }),
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        model="mock",
        stop_reason="end_turn",
    )
    mock = MockClient(responses=[no_approval_resp])
    agent = RemediationAgent(mock, tool_registry, tracer)
    trace_id = new_trace_id()
    tracer.start_trace(trace_id)

    research = {
        "root_cause": "test", "confidence": 0.5, "evidence": [],
        "timeline": [], "relevant_runbooks": [],
        "affected_services": ["x"],
    }
    result = await agent.run(research, trace_id)

    assert result["requires_human_approval"] is True


@pytest.mark.asyncio
async def test_remediation_with_runbook_tool_call(
    tracer: DecisionTracer, tool_registry: ToolRegistry,
):
    """Remediation agent should be able to search runbooks."""
    mock = MockClient(responses=[
        _tool_call_response("search_runbooks", {"query": "deployment rollback"}),
        _remediation_response(),
    ])
    agent = RemediationAgent(mock, tool_registry, tracer)
    trace_id = new_trace_id()
    tracer.start_trace(trace_id)

    research_result = {
        "root_cause": "Bad deployment",
        "confidence": 0.9,
        "evidence": [],
        "timeline": [],
        "relevant_runbooks": [],
        "affected_services": ["payment-api"],
    }

    result = await agent.run(research_result, trace_id)
    assert result["requires_human_approval"] is True


# ---------------------------------------------------------------------------
# Orchestrator (IncidentAnalyzer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_full_pipeline(sample_alert: Alert):
    mock = MockClient(responses=[
        _triage_response(),
        _research_response(),
        _remediation_response(),
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
async def test_orchestrator_handles_agent_error_gracefully(sample_alert: Alert):
    """If an agent raises an exception, the orchestrator catches it and still returns a report."""
    mock = MockClient(responses=[
        _triage_response(),
    ])
    # After triage, no more responses → research will get a non-JSON mock response
    # which will cause a JSONDecodeError, but the fallback handler should catch it

    analyzer = IncidentAnalyzer(llm_client=mock)
    report = await analyzer.analyze(sample_alert)

    # Should still produce a report (with defaults where agents failed)
    assert report.incident_id.startswith("INC-")
    assert report.duration_seconds >= 0


@pytest.mark.asyncio
async def test_orchestrator_timeout_handled(sample_alert: Alert):
    """If the pipeline takes too long, the orchestrator should handle the timeout."""

    class SlowClient:
        async def chat(self, messages, tools=None):
            await asyncio.sleep(999)
            return _triage_response()

    analyzer = IncidentAnalyzer(llm_client=SlowClient())

    # Patch the timeout to be very short
    with patch("agent.core.ANALYSIS_TIMEOUT_SECONDS", 0.01):
        report = await analyzer.analyze(sample_alert)

    assert report.incident_id.startswith("INC-")
    # Should have a timeout step in the trace
    timeout_steps = [s for s in report.agent_trace if s.action == "timeout"]
    assert len(timeout_steps) == 1


@pytest.mark.asyncio
async def test_agent_trace_is_recorded(sample_alert: Alert):
    mock = MockClient(responses=[
        _triage_response(),
        _research_response(),
        _remediation_response(),
    ])

    analyzer = IncidentAnalyzer(llm_client=mock)
    report = await analyzer.analyze(sample_alert)

    agent_names = [step.agent_name for step in report.agent_trace]
    assert "triage" in agent_names
    assert "research" in agent_names
    assert "remediation" in agent_names


@pytest.mark.asyncio
async def test_agent_messages_logged_to_trace(sample_alert: Alert):
    """The orchestrator should record agent steps that include tokens and cost."""
    mock = MockClient(responses=[
        _triage_response(),
        _research_response(),
        _remediation_response(),
    ])

    analyzer = IncidentAnalyzer(llm_client=mock)
    report = await analyzer.analyze(sample_alert)

    # At least the final step from each agent should have tokens > 0
    for name in ("triage", "research", "remediation"):
        agent_steps = [s for s in report.agent_trace if s.agent_name == name]
        assert len(agent_steps) >= 1
        # The final step for each agent should have tokens
        final_step = [s for s in agent_steps if s.tokens_used > 0]
        assert len(final_step) >= 1, f"{name} should have a step with tokens"


# ---------------------------------------------------------------------------
# Message Bus
# ---------------------------------------------------------------------------


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
async def test_message_bus_filters_by_agent():
    bus = MessageBus()
    trace_id = new_trace_id()

    bus.send("triage", "research", "delegate", {}, trace_id)
    bus.send("research", "remediation", "delegate", {}, trace_id)

    research_msgs = bus.get_messages_for_agent("research", trace_id)
    assert len(research_msgs) == 1
    assert research_msgs[0].from_agent == "triage"


# ---------------------------------------------------------------------------
# Decision Tracer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decision_tracer_exports_json():
    tracer = DecisionTracer()
    trace_id = new_trace_id()
    tracer.start_trace(trace_id)

    tracer.log_step(trace_id, "triage", "classify", "Testing", tokens_used=100, cost_usd=0.001)
    tracer.log_step(
        trace_id, "research", "investigate", "Investigating",
        tokens_used=500, cost_usd=0.005,
    )

    exported = tracer.export_trace_json(trace_id)
    data = json.loads(exported)
    assert len(data) == 2
    assert data[0]["agent_name"] == "triage"
    assert tracer.get_total_tokens(trace_id) == 600
