"""Scenario: Payment API connection pool exhaustion."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.llm_client import Response, TokenUsage
from agent.models import Alert
from evaluation.scenarios._base import EvalScenario

scenario = EvalScenario(
    name="payment_api_pool_exhaustion",
    alert=Alert(
        service="payment-api",
        description="P99 latency spike to 2100ms, normal baseline 180ms",
        severity="critical",
        timestamp=datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC),
        metadata={"current_p99_ms": 2100},
    ),
    expected_root_cause_keywords=[
        "connection pool", "exhaustion", "deployment", "database", "timeout",
    ],
    expected_remediation_keywords=[
        "rollback", "pool", "monitor", "deployment",
    ],
    expected_affected_services=["payment-api", "order-service"],
    min_confidence=0.7,
    mock_responses=[
        Response(
            content=json.dumps({
                "classification": "resource-exhaustion",
                "affected_services": ["payment-api", "order-service"],
                "priority": "P1",
                "summary": (
                    "Payment-api experiencing connection pool"
                    " exhaustion causing cascading latency."
                ),
                "delegation_instructions": "Check payment-api ERROR logs for DB timeouts.",
            }),
            usage=TokenUsage(input_tokens=500, output_tokens=200),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "timeline": [
                    {"timestamp": "2024-01-15T14:00:00Z", "event": "Deployment a1bf3d2 applied"},
                    {"timestamp": "2024-01-15T14:25:00Z", "event": "First DB timeout errors"},
                ],
                "root_cause": (
                    "Deployment a1bf3d2 changed DB connection"
                    " pool settings, causing pool exhaustion."
                ),
                "confidence": 0.92,
                "evidence": ["DB connection pool at 98% capacity"],
                "affected_services": ["payment-api", "order-service"],
            }),
            usage=TokenUsage(input_tokens=2000, output_tokens=500),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "remediation_steps": [
                    {
                        "step": 1,
                        "action": "Rollback deployment a1bf3d2",
                        "risk": "high",
                        "requires_approval": True,
                    },
                    {
                        "step": 2,
                        "action": "Monitor connection pool metrics",
                        "risk": "low",
                        "requires_approval": False,
                    },
                ],
                "requires_human_approval": True,
                "summary": "Rollback the problematic deployment and monitor for recovery.",
            }),
            usage=TokenUsage(input_tokens=1000, output_tokens=300),
            model="mock",
            stop_reason="end_turn",
        ),
    ],
)
