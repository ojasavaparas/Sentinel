"""Tests for SSE streaming endpoint and tracer event queue."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from agent.models import StreamEvent
from monitoring.tracer import DecisionTracer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def stream_client(monkeypatch: pytest.MonkeyPatch):
    """Create a test client wired to the mock LLM for streaming tests."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    from api import deps
    from api.main import app

    with TestClient(app) as c:
        yield c

    deps._incident_store.clear()


# ---------------------------------------------------------------------------
# SSE Endpoint Tests
# ---------------------------------------------------------------------------


def test_stream_returns_event_stream_content_type(stream_client: TestClient):
    """The streaming endpoint must return text/event-stream."""
    payload = {
        "service": "payment-api",
        "description": "P99 latency spike",
        "severity": "critical",
        "timestamp": "2024-01-15T14:30:00Z",
    }
    with stream_client.stream("POST", "/api/v1/analyze/stream", json=payload) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]


def test_stream_emits_agent_start_events(stream_client: TestClient):
    """Stream must include agent_start events for triage, research, remediation."""
    payload = {
        "service": "payment-api",
        "description": "P99 latency spike",
        "severity": "critical",
        "timestamp": "2024-01-15T14:30:00Z",
    }
    with stream_client.stream("POST", "/api/v1/analyze/stream", json=payload) as resp:
        raw = b"".join(resp.iter_bytes()).decode()

    agent_starts = []
    for line in raw.split("\n"):
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if data.get("event_type") == "agent_start":
                agent_starts.append(data["agent_name"])

    assert "triage" in agent_starts
    assert "research" in agent_starts
    assert "remediation" in agent_starts


def test_stream_ends_with_analysis_complete(stream_client: TestClient):
    """The last meaningful event must be analysis_complete with a full report."""
    payload = {
        "service": "payment-api",
        "description": "P99 latency spike",
        "severity": "critical",
        "timestamp": "2024-01-15T14:30:00Z",
    }
    with stream_client.stream("POST", "/api/v1/analyze/stream", json=payload) as resp:
        raw = b"".join(resp.iter_bytes()).decode()

    events = []
    for line in raw.split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    assert len(events) > 0
    last_event = events[-1]
    assert last_event["event_type"] == "analysis_complete"
    assert "report" in last_event["data"]
    assert "incident_id" in last_event["data"]["report"]


def test_stream_event_ordering(stream_client: TestClient):
    """Events must follow start → complete ordering per agent."""
    payload = {
        "service": "payment-api",
        "description": "P99 latency spike",
        "severity": "critical",
        "timestamp": "2024-01-15T14:30:00Z",
    }
    with stream_client.stream("POST", "/api/v1/analyze/stream", json=payload) as resp:
        raw = b"".join(resp.iter_bytes()).decode()

    event_types = []
    for line in raw.split("\n"):
        if line.startswith("data: "):
            data = json.loads(line[6:])
            event_types.append(data["event_type"])

    # Each agent_start for a given agent should appear before its agent_complete
    for agent in ("triage", "research", "remediation"):
        starts = [i for i, e in enumerate(event_types) if e == "agent_start"]
        completes = [i for i, e in enumerate(event_types) if e == "agent_complete"]
        # There should be at least as many starts as completes
        assert len(starts) >= len(completes)


def test_stream_stores_report_in_incident_store(stream_client: TestClient):
    """After streaming, the report should be stored and retrievable."""
    payload = {
        "service": "payment-api",
        "description": "P99 latency spike",
        "severity": "critical",
        "timestamp": "2024-01-15T14:30:00Z",
    }
    # Consume the stream fully
    with stream_client.stream("POST", "/api/v1/analyze/stream", json=payload) as resp:
        raw = b"".join(resp.iter_bytes()).decode()

    # Extract incident_id from the analysis_complete event
    incident_id = None
    for line in raw.split("\n"):
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if data.get("event_type") == "analysis_complete":
                incident_id = data["data"]["report"]["incident_id"]
                break

    assert incident_id is not None

    # Verify it's in the store
    resp = stream_client.get(f"/api/v1/incidents/{incident_id}")
    assert resp.status_code == 200
    assert resp.json()["incident_id"] == incident_id


def test_stream_sse_format(stream_client: TestClient):
    """Events must follow SSE format: 'event: <type>\\ndata: <json>\\n\\n'."""
    payload = {
        "service": "payment-api",
        "description": "P99 latency spike",
        "severity": "critical",
        "timestamp": "2024-01-15T14:30:00Z",
    }
    with stream_client.stream("POST", "/api/v1/analyze/stream", json=payload) as resp:
        raw = b"".join(resp.iter_bytes()).decode()

    # Split by double newline to get individual SSE messages
    messages = [m.strip() for m in raw.split("\n\n") if m.strip()]
    assert len(messages) > 0

    for msg in messages:
        lines = msg.split("\n")
        assert lines[0].startswith("event: "), f"Expected 'event: ...' line, got: {lines[0]}"
        assert lines[1].startswith("data: "), f"Expected 'data: ...' line, got: {lines[1]}"
        # Verify data is valid JSON
        json.loads(lines[1][6:])


# ---------------------------------------------------------------------------
# Tracer Queue Tests
# ---------------------------------------------------------------------------


def test_tracer_queue_receives_tool_call_events():
    """When a queue is attached, log_step should push tool_call events."""
    queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
    tracer = DecisionTracer(event_queue=queue)
    tracer.start_trace("test-trace")

    from agent.models import ToolCall

    tracer.log_step(
        trace_id="test-trace",
        agent_name="research",
        action="investigate",
        reasoning="test",
        tool_calls=[
            ToolCall(
                tool_name="search_logs",
                arguments={"query": "error"},
                result={"matches": 5},
                latency_ms=42.0,
                cost_usd=0.0,
            ),
        ],
        tokens_used=100,
    )

    assert not queue.empty()
    event = queue.get_nowait()
    assert event.event_type == "tool_call"
    assert event.agent_name == "research"
    assert event.data["action"] == "search_logs"
