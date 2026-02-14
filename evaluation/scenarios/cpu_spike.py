"""Scenario: CPU spike caused by runaway regex in request parsing."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.llm_client import Response, TokenUsage
from agent.models import Alert
from evaluation.scenarios._base import EvalScenario

scenario = EvalScenario(
    name="cpu_spike",
    alert=Alert(
        service="search-service",
        description="CPU utilization at 98% across all pods, request latency 10x normal",
        severity="critical",
        timestamp=datetime(2024, 8, 22, 15, 0, 0, tzinfo=UTC),
        metadata={"cpu_pct": 98, "latency_multiplier": 10},
    ),
    expected_root_cause_keywords=[
        "CPU", "regex", "parsing", "runaway", "compute",
    ],
    expected_remediation_keywords=[
        "scale", "fix regex", "CPU", "optimize", "limit",
    ],
    expected_affected_services=["search-service"],
    min_confidence=0.7,
    mock_responses=[
        Response(
            content=json.dumps({
                "classification": "resource-exhaustion",
                "affected_services": ["search-service"],
                "priority": "P1",
                "summary": "search-service CPU saturated causing severe latency degradation.",
                "delegation_instructions": "Profile CPU usage and check recent code changes.",
            }),
            usage=TokenUsage(input_tokens=430, output_tokens=180),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "root_cause": (
                    "Runaway regex in query parsing causing"
                    " catastrophic backtracking on certain"
                    " search inputs, spiking CPU."
                ),
                "confidence": 0.82,
                "evidence": [
                    "CPU profiler shows 90% in regex engine",
                    "Issue triggered by specific query pattern",
                ],
                "affected_services": ["search-service"],
            }),
            usage=TokenUsage(input_tokens=1600, output_tokens=420),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "remediation_steps": [
                    {
                        "step": 1,
                        "action": "Scale up search-service pods to absorb CPU load",
                        "risk": "low",
                        "requires_approval": False,
                    },
                    {
                        "step": 2,
                        "action": "Fix regex to prevent catastrophic backtracking",
                        "risk": "medium",
                        "requires_approval": True,
                    },
                    {
                        "step": 3,
                        "action": "Add request timeout limits",
                        "risk": "low",
                        "requires_approval": False,
                    },
                ],
                "requires_human_approval": True,
                "summary": "Scale up, fix the regex, and add timeouts.",
            }),
            usage=TokenUsage(input_tokens=850, output_tokens=260),
            model="mock",
            stop_reason="end_turn",
        ),
    ],
)
