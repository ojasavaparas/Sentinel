"""Tests for FinOps cost tracking."""

from __future__ import annotations

from datetime import datetime

from monitoring.finops import (
    CLAUDE_SONNET_INPUT,
    CLAUDE_SONNET_OUTPUT,
    AnalysisCost,
    CostTracker,
    calculate_cost,
)

# ---------------------------------------------------------------------------
# Cost Calculation
# ---------------------------------------------------------------------------


def test_calculate_cost_known_values():
    """Verify cost calculation for known token counts."""
    cost = calculate_cost(input_tokens=1_000_000, output_tokens=0)
    assert cost == 3.0  # $3 per 1M input tokens

    cost = calculate_cost(input_tokens=0, output_tokens=1_000_000)
    assert cost == 15.0  # $15 per 1M output tokens


def test_calculate_cost_mixed_tokens():
    cost = calculate_cost(input_tokens=500, output_tokens=200)
    expected = 500 * CLAUDE_SONNET_INPUT + 200 * CLAUDE_SONNET_OUTPUT
    assert abs(cost - expected) < 1e-10


def test_calculate_cost_zero_tokens():
    assert calculate_cost(0, 0) == 0.0


# ---------------------------------------------------------------------------
# CostTracker — record_analysis
# ---------------------------------------------------------------------------


def test_record_analysis_creates_entry():
    tracker = CostTracker()
    tracker.record_analysis("INC-001", "triage", 500, 200)

    cost = tracker.get_analysis_cost("INC-001")
    assert cost["total"] > 0
    assert "triage" in cost["by_agent"]
    assert cost["by_agent"]["triage"] > 0


def test_record_analysis_accumulates_agents():
    tracker = CostTracker()
    tracker.record_analysis("INC-001", "triage", 500, 200)
    tracker.record_analysis("INC-001", "research", 2000, 500)
    tracker.record_analysis("INC-001", "remediation", 1000, 300)

    cost = tracker.get_analysis_cost("INC-001")
    assert len(cost["by_agent"]) == 3
    assert cost["total"] == round(
        cost["by_agent"]["triage"]
        + cost["by_agent"]["research"]
        + cost["by_agent"]["remediation"],
        6,
    )


def test_record_analysis_same_agent_twice():
    """Calling record_analysis for the same agent accumulates."""
    tracker = CostTracker()
    tracker.record_analysis("INC-001", "triage", 500, 200)
    tracker.record_analysis("INC-001", "triage", 300, 100)

    cost = tracker.get_analysis_cost("INC-001")
    expected_triage = calculate_cost(500, 200) + calculate_cost(300, 100)
    assert abs(cost["by_agent"]["triage"] - round(expected_triage, 6)) < 1e-10


def test_record_tool_calls():
    tracker = CostTracker()
    tracker.record_analysis("INC-001", "triage", 500, 200)
    tracker.record_tool_calls("INC-001", 3)

    cost = tracker.get_analysis_cost("INC-001")
    assert cost["tool_call_count"] == 3


def test_record_tool_calls_nonexistent_incident():
    """Calling record_tool_calls for an unknown incident is a no-op."""
    tracker = CostTracker()
    tracker.record_tool_calls("INC-MISSING", 5)
    cost = tracker.get_analysis_cost("INC-MISSING")
    assert cost["total"] == 0.0
    assert cost["tool_call_count"] == 0


# ---------------------------------------------------------------------------
# CostTracker — get_analysis_cost
# ---------------------------------------------------------------------------


def test_get_analysis_cost_missing_incident():
    tracker = CostTracker()
    cost = tracker.get_analysis_cost("INC-MISSING")
    assert cost == {"total": 0.0, "by_agent": {}, "tool_call_count": 0}


# ---------------------------------------------------------------------------
# CostTracker — get_cost_summary
# ---------------------------------------------------------------------------


def test_get_cost_summary_empty():
    tracker = CostTracker()
    summary = tracker.get_cost_summary()
    assert summary["total_cost"] == 0.0
    assert summary["avg_cost_per_analysis"] == 0.0
    assert summary["most_expensive_analysis"] is None
    assert summary["total_analyses"] == 0


def test_get_cost_summary_single_analysis():
    tracker = CostTracker()
    tracker.record_analysis("INC-001", "triage", 500, 200)
    tracker.record_analysis("INC-001", "research", 2000, 500)

    summary = tracker.get_cost_summary()
    assert summary["total_analyses"] == 1
    assert summary["total_cost"] > 0
    assert summary["avg_cost_per_analysis"] == summary["total_cost"]
    assert summary["most_expensive_analysis"]["incident_id"] == "INC-001"


def test_get_cost_summary_multiple_analyses():
    tracker = CostTracker()
    tracker.record_analysis("INC-001", "triage", 500, 200)
    tracker.record_analysis("INC-002", "triage", 1000, 400)
    tracker.record_analysis("INC-002", "research", 5000, 2000)

    summary = tracker.get_cost_summary()
    assert summary["total_analyses"] == 2
    assert summary["most_expensive_analysis"]["incident_id"] == "INC-002"
    assert summary["total_cost"] == round(
        tracker.get_analysis_cost("INC-001")["total"]
        + tracker.get_analysis_cost("INC-002")["total"],
        6,
    )


def test_get_cost_summary_respects_time_window():
    """Analyses outside the time window should be excluded."""
    tracker = CostTracker()
    tracker.record_analysis("INC-001", "triage", 500, 200)

    # Recent analysis should appear in a 24-hour window
    summary_24h = tracker.get_cost_summary(last_n_hours=24)
    assert summary_24h["total_analyses"] == 1

    # Zero-hour window should exclude everything
    summary_0h = tracker.get_cost_summary(last_n_hours=0)
    assert summary_0h["total_analyses"] == 0


# ---------------------------------------------------------------------------
# AnalysisCost dataclass
# ---------------------------------------------------------------------------


def test_analysis_cost_defaults():
    ac = AnalysisCost(incident_id="INC-001")
    assert ac.total_cost == 0.0
    assert ac.by_agent == {}
    assert ac.total_input_tokens == 0
    assert ac.total_output_tokens == 0
    assert ac.tool_call_count == 0
    assert isinstance(ac.timestamp, datetime)
