"""Scenario: Memory leak in user-service."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.llm_client import Response, TokenUsage
from agent.models import Alert
from evaluation.scenarios._base import EvalScenario

scenario = EvalScenario(
    name="memory_leak",
    alert=Alert(
        service="user-service",
        description="Memory usage growing linearly, OOM kills every 6 hours",
        severity="high",
        timestamp=datetime(2024, 2, 10, 8, 0, 0, tzinfo=UTC),
        metadata={"heap_usage_mb": 1800, "oom_count_24h": 4},
    ),
    expected_root_cause_keywords=[
        "memory", "leak", "cache", "garbage collection", "heap",
    ],
    expected_remediation_keywords=[
        "restart", "memory limit", "profiler", "cache eviction",
    ],
    expected_affected_services=["user-service"],
    min_confidence=0.6,
    mock_responses=[
        Response(
            content=json.dumps({
                "classification": "resource-exhaustion",
                "affected_services": ["user-service"],
                "priority": "P2",
                "summary": "user-service experiencing gradual memory leak leading to OOM kills.",
                "delegation_instructions": "Check heap dumps and recent code changes.",
            }),
            usage=TokenUsage(input_tokens=400, output_tokens=180),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "root_cause": (
                    "Unbounded in-memory cache in user-service"
                    " growing without eviction policy,"
                    " causing OOM."
                ),
                "confidence": 0.78,
                "evidence": ["Heap grows 50MB/hour", "No cache TTL configured"],
                "affected_services": ["user-service"],
            }),
            usage=TokenUsage(input_tokens=1500, output_tokens=400),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "remediation_steps": [
                    {
                        "step": 1,
                        "action": "Add cache eviction with TTL of 15 minutes",
                        "risk": "medium",
                        "requires_approval": True,
                    },
                    {
                        "step": 2,
                        "action": "Restart user-service pods to reclaim memory",
                        "risk": "low",
                        "requires_approval": False,
                    },
                ],
                "requires_human_approval": True,
                "summary": "Add cache eviction and restart to reclaim memory.",
            }),
            usage=TokenUsage(input_tokens=800, output_tokens=250),
            model="mock",
            stop_reason="end_turn",
        ),
    ],
)
