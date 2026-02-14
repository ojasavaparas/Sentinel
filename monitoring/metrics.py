"""Prometheus metrics for Sentinel system observability."""

from __future__ import annotations

from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge, Histogram

if TYPE_CHECKING:
    from agent.models import IncidentReport

# --- Incident analysis metrics ---

sentinel_incident_analyses_total = Counter(
    "sentinel_incident_analyses_total",
    "Total number of incident analyses completed",
    ["severity"],
)

sentinel_incident_analysis_duration_seconds = Histogram(
    "sentinel_incident_analysis_duration_seconds",
    "Time spent analyzing an incident end-to-end",
    buckets=[1, 5, 10, 30, 60, 120],
)

# --- Agent metrics ---

sentinel_agent_steps_total = Counter(
    "sentinel_agent_steps_total",
    "Total number of agent steps executed",
    ["agent_name"],
)

# --- Tool metrics ---

sentinel_tool_calls_total = Counter(
    "sentinel_tool_calls_total",
    "Total number of tool calls",
    ["tool_name"],
)

sentinel_tool_call_duration_seconds = Histogram(
    "sentinel_tool_call_duration_seconds",
    "Tool call latency in seconds",
    ["tool_name"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

# --- LLM token / cost metrics ---

sentinel_llm_tokens_total = Counter(
    "sentinel_llm_tokens_total",
    "Total LLM tokens consumed",
    ["direction", "agent_name"],
)

sentinel_llm_cost_dollars_total = Counter(
    "sentinel_llm_cost_dollars_total",
    "Total LLM cost in USD",
    ["agent_name"],
)

# --- RAG metrics ---

sentinel_rag_queries_total = Counter(
    "sentinel_rag_queries_total",
    "Total number of RAG vector searches",
)

sentinel_rag_retrieval_score = Histogram(
    "sentinel_rag_retrieval_score",
    "Distribution of RAG retrieval similarity scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

sentinel_rag_low_confidence_total = Counter(
    "sentinel_rag_low_confidence_total",
    "Total RAG queries where top result had low confidence (< 0.4)",
)

# --- System metrics ---

sentinel_active_analyses = Gauge(
    "sentinel_active_analyses",
    "Number of incident analyses currently in progress",
)

sentinel_human_approval_required_total = Counter(
    "sentinel_human_approval_required_total",
    "Total analyses that required human approval",
)


# --- Helper functions ---


def record_tool_call(tool_name: str, duration_seconds: float) -> None:
    """Record a single tool call: increment counter and observe latency histogram."""
    sentinel_tool_calls_total.labels(tool_name=tool_name).inc()
    sentinel_tool_call_duration_seconds.labels(tool_name=tool_name).observe(duration_seconds)


def record_llm_call(
    agent_name: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
) -> None:
    """Record LLM token usage and cost for an agent run."""
    sentinel_llm_tokens_total.labels(direction="input", agent_name=agent_name).inc(input_tokens)
    sentinel_llm_tokens_total.labels(direction="output", agent_name=agent_name).inc(output_tokens)
    sentinel_llm_cost_dollars_total.labels(agent_name=agent_name).inc(cost)


def record_rag_query(scores: list[float]) -> None:
    """Record a RAG query: increment counter, observe score histogram, track low confidence."""
    sentinel_rag_queries_total.inc()
    for score in scores:
        sentinel_rag_retrieval_score.observe(score)
    if scores and max(scores) < 0.4:
        sentinel_rag_low_confidence_total.inc()


def record_analysis_complete(report: IncidentReport) -> None:
    """Record metrics from a completed incident analysis report."""
    sentinel_incident_analyses_total.labels(severity=report.alert.severity).inc()
    sentinel_incident_analysis_duration_seconds.observe(report.duration_seconds)

    if report.requires_human_approval:
        sentinel_human_approval_required_total.inc()

    # Count agent steps and record per-step metrics
    for step in report.agent_trace:
        sentinel_agent_steps_total.labels(agent_name=step.agent_name).inc()
