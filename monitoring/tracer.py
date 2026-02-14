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
    ) -> AgentStep:
        """Log a single agent step in the trace."""
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

        logger.info(
            "agent_step",
            trace_id=trace_id,
            agent=agent_name,
            action=action,
            tool_count=len(step.tool_calls),
            tokens=tokens_used,
        )

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
                    }
                    for tc in step.tool_calls
                ],
                "tokens_used": step.tokens_used,
                "cost_usd": step.cost_usd,
                "timestamp": step.timestamp.isoformat(),
            })
        return json.dumps(data, indent=2)
