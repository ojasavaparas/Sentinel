"""Prometheus metrics for Sentinel system observability."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Incident analysis metrics
incidents_analyzed_total = Counter(
    "sentinel_incidents_analyzed_total",
    "Total number of incidents analyzed",
    ["severity"],
)

incident_duration_seconds = Histogram(
    "sentinel_incident_duration_seconds",
    "Time spent analyzing an incident",
    buckets=[1, 5, 10, 30, 60, 120],
)

# Agent metrics
agent_tokens_used_total = Counter(
    "sentinel_agent_tokens_used_total",
    "Total tokens consumed by agents",
    ["agent"],
)

agent_cost_usd_total = Counter(
    "sentinel_agent_cost_usd_total",
    "Total cost in USD by agent",
    ["agent"],
)

# Tool metrics
tool_call_duration_seconds = Histogram(
    "sentinel_tool_call_duration_seconds",
    "Tool call latency in seconds",
    ["tool"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

tool_calls_total = Counter(
    "sentinel_tool_calls_total",
    "Total number of tool calls",
    ["tool"],
)

# System metrics
active_incidents = Gauge(
    "sentinel_active_incidents",
    "Number of incidents currently being analyzed",
)

rag_searches_total = Counter(
    "sentinel_rag_searches_total",
    "Total number of RAG searches",
)


def record_incident(report) -> None:  # noqa: ANN001
    """Record metrics from a completed incident report."""
    incidents_analyzed_total.labels(severity=report.alert.severity).inc()
    incident_duration_seconds.observe(report.duration_seconds)

    for step in report.agent_trace:
        agent_tokens_used_total.labels(agent=step.agent_name).inc(step.tokens_used)
        agent_cost_usd_total.labels(agent=step.agent_name).inc(step.cost_usd)

        for tc in step.tool_calls:
            tool_calls_total.labels(tool=tc.tool_name).inc()
            tool_call_duration_seconds.labels(tool=tc.tool_name).observe(tc.latency_ms / 1000)
