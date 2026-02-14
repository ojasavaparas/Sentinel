"""Decision trace logger — records every agent decision for auditability."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

from agent.models import AgentStep, ToolCall

logger = structlog.get_logger()


class DecisionTracer:
    """Records and retrieves the full decision trace for an incident analysis."""

    def __init__(self) -> None:
        self._traces: dict[str, list[AgentStep]] = {}

    def start_trace(self, trace_id: str) -> None:
        """Initialize a new trace."""
        self._traces[trace_id] = []
        logger.info("trace_started", trace_id=trace_id)

    def log_step(
        self,
        trace_id: str,
        agent_name: str,
        action: str,
        reasoning: str,
        tool_calls: list[ToolCall] | None = None,
        tokens_used: int = 0,
        cost_usd: float = 0.0,
        duration_ms: float | None = None,
    ) -> AgentStep:
        """Log a single agent step in the trace.

        Args:
            duration_ms: Optional elapsed time in milliseconds for this step.
        """
        step = AgentStep(
            agent_name=agent_name,
            action=action,
            reasoning=reasoning,
            tool_calls=tool_calls or [],
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            timestamp=datetime.now(timezone.utc),
        )

        if trace_id not in self._traces:
            self._traces[trace_id] = []

        self._traces[trace_id].append(step)

        log_kwargs: dict[str, Any] = {
            "trace_id": trace_id,
            "agent": agent_name,
            "action": action,
            "tool_count": len(step.tool_calls),
            "tokens": tokens_used,
        }
        if duration_ms is not None:
            log_kwargs["duration_ms"] = round(duration_ms, 2)

        logger.info("agent_step", **log_kwargs)

        return step

    def get_trace(self, trace_id: str) -> list[AgentStep]:
        """Get all steps for a trace in order."""
        return self._traces.get(trace_id, [])

    def get_total_tokens(self, trace_id: str) -> int:
        """Sum all tokens used across a trace."""
        return sum(step.tokens_used for step in self.get_trace(trace_id))

    def get_total_cost(self, trace_id: str) -> float:
        """Sum all costs across a trace."""
        return sum(step.cost_usd for step in self.get_trace(trace_id))

    def export_trace_json(self, trace_id: str) -> str:
        """Export the full trace as a JSON string for dashboard consumption."""
        steps = self.get_trace(trace_id)
        data: list[dict[str, Any]] = []
        for step in steps:
            data.append({
                "agent_name": step.agent_name,
                "action": step.action,
                "reasoning": step.reasoning,
                "tool_calls": [
                    {
                        "tool_name": tc.tool_name,
                        "arguments": tc.arguments,
                        "latency_ms": tc.latency_ms,
                        "result": tc.result,
                    }
                    for tc in step.tool_calls
                ],
                "tokens_used": step.tokens_used,
                "cost_usd": step.cost_usd,
                "timestamp": step.timestamp.isoformat(),
            })
        return json.dumps(data, indent=2, default=str)

    def export_trace_for_dashboard(self, trace_id: str) -> dict[str, Any]:
        """Export a richer trace structure with per-agent summaries.

        Returns a dict suitable for Grafana/dashboard consumption with
        overall totals and per-agent breakdowns of tokens, cost, and tool calls.
        """
        steps = self.get_trace(trace_id)

        agent_summaries: dict[str, dict[str, Any]] = {}
        for step in steps:
            name = step.agent_name
            if name not in agent_summaries:
                agent_summaries[name] = {
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "tool_call_count": 0,
                    "steps": 0,
                }
            summary = agent_summaries[name]
            summary["total_tokens"] += step.tokens_used
            summary["total_cost"] += step.cost_usd
            summary["tool_call_count"] += len(step.tool_calls)
            summary["steps"] += 1

        # Round cost values
        for summary in agent_summaries.values():
            summary["total_cost"] = round(summary["total_cost"], 6)

        return {
            "trace_id": trace_id,
            "total_tokens": self.get_total_tokens(trace_id),
            "total_cost": round(self.get_total_cost(trace_id), 6),
            "total_steps": len(steps),
            "agents": agent_summaries,
            "steps": json.loads(self.export_trace_json(trace_id)),
        }
