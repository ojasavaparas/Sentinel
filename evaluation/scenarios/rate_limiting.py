"""Scenario: Rate limiting misconfiguration causing legitimate request drops."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.llm_client import Response, TokenUsage
from agent.models import Alert
from evaluation.scenarios._base import EvalScenario

scenario = EvalScenario(
    name="rate_limiting",
    alert=Alert(
        service="api-gateway",
        description="HTTP 429 responses spiked to 40% of all requests, legitimate users affected",
        severity="high",
        timestamp=datetime(2024, 9, 3, 12, 0, 0, tzinfo=UTC),
        metadata={"429_rate_pct": 40, "affected_users": 15000},
    ),
    expected_root_cause_keywords=[
        "rate limit", "429", "throttle", "config", "threshold",
    ],
    expected_remediation_keywords=[
        "rate limit", "increase", "threshold", "config", "allowlist",
    ],
    expected_affected_services=["api-gateway"],
    min_confidence=0.7,
    mock_responses=[
        Response(
            content=json.dumps({
                "classification": "misconfiguration",
                "affected_services": ["api-gateway"],
                "priority": "P2",
                "summary": "api-gateway rate limiter too aggressive, blocking legitimate traffic.",
                "delegation_instructions": "Check rate limit configuration and recent changes.",
            }),
            usage=TokenUsage(input_tokens=400, output_tokens=170),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "root_cause": (
                    "Rate limit threshold reduced from 1000"
                    " to 100 req/min per user in recent config"
                    " change, blocking normal traffic."
                ),
                "confidence": 0.90,
                "evidence": ["Config change deployed 2h ago", "Rate limit set to 100 req/min"],
                "affected_services": ["api-gateway"],
            }),
            usage=TokenUsage(input_tokens=1300, output_tokens=350),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "remediation_steps": [
                    {
                        "step": 1,
                        "action": "Revert rate limit config to 1000 req/min",
                        "risk": "low",
                        "requires_approval": True,
                    },
                    {
                        "step": 2,
                        "action": "Add monitoring alert for rate limit config changes",
                        "risk": "low",
                        "requires_approval": False,
                    },
                ],
                "requires_human_approval": True,
                "summary": "Revert rate limit config and add change monitoring.",
            }),
            usage=TokenUsage(input_tokens=700, output_tokens=220),
            model="mock",
            stop_reason="end_turn",
        ),
    ],
)
