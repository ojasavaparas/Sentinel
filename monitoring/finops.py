"""FinOps cost tracking — monitors LLM token usage and cost per incident."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# Claude Sonnet pricing (per token)
CLAUDE_SONNET_INPUT = 3.0 / 1_000_000
CLAUDE_SONNET_OUTPUT = 15.0 / 1_000_000


def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate the dollar cost for a given number of input/output tokens."""
    return input_tokens * CLAUDE_SONNET_INPUT + output_tokens * CLAUDE_SONNET_OUTPUT


@dataclass
class AnalysisCost:
    """Accumulated cost data for a single incident analysis."""

    incident_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_cost: float = 0.0
    by_agent: dict[str, float] = field(default_factory=dict)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    tool_call_count: int = 0


class CostTracker:
    """Tracks per-incident LLM cost across the agent pipeline."""

    def __init__(self) -> None:
        self._analyses: dict[str, AnalysisCost] = {}

    def record_analysis(
        self,
        incident_id: str,
        agent_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Accumulate token usage and cost for one agent within an analysis."""
        cost = calculate_cost(input_tokens, output_tokens)

        if incident_id not in self._analyses:
            self._analyses[incident_id] = AnalysisCost(incident_id=incident_id)

        entry = self._analyses[incident_id]
        entry.total_cost += cost
        entry.total_input_tokens += input_tokens
        entry.total_output_tokens += output_tokens
        entry.by_agent[agent_name] = entry.by_agent.get(agent_name, 0.0) + cost

    def record_tool_calls(self, incident_id: str, count: int) -> None:
        """Increment the tool call count for an analysis."""
        if incident_id in self._analyses:
            self._analyses[incident_id].tool_call_count += count

    def get_analysis_cost(self, incident_id: str) -> dict:
        """Return cost breakdown for a single analysis."""
        entry = self._analyses.get(incident_id)
        if entry is None:
            return {"total": 0.0, "by_agent": {}, "tool_call_count": 0}

        return {
            "total": round(entry.total_cost, 6),
            "by_agent": {k: round(v, 6) for k, v in entry.by_agent.items()},
            "tool_call_count": entry.tool_call_count,
        }

    def get_cost_summary(self, last_n_hours: int = 24) -> dict:
        """Return aggregate cost summary for recent analyses."""
        cutoff = datetime.now(timezone.utc).timestamp() - last_n_hours * 3600
        recent = [
            a for a in self._analyses.values()
            if a.timestamp.timestamp() >= cutoff
        ]

        if not recent:
            return {
                "total_cost": 0.0,
                "avg_cost_per_analysis": 0.0,
                "most_expensive_analysis": None,
                "total_analyses": 0,
            }

        total_cost = sum(a.total_cost for a in recent)
        most_expensive = max(recent, key=lambda a: a.total_cost)

        return {
            "total_cost": round(total_cost, 6),
            "avg_cost_per_analysis": round(total_cost / len(recent), 6),
            "most_expensive_analysis": {
                "incident_id": most_expensive.incident_id,
                "cost": round(most_expensive.total_cost, 6),
            },
            "total_analyses": len(recent),
        }
