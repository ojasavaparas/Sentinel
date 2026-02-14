"""Scenario: Failed deployment causing 5xx errors."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.llm_client import Response, TokenUsage
from agent.models import Alert
from evaluation.scenarios._base import EvalScenario

scenario = EvalScenario(
    name="deployment_failure",
    alert=Alert(
        service="checkout-service",
        description="HTTP 500 rate jumped from 0.1% to 15% after deployment",
        severity="critical",
        timestamp=datetime(2024, 3, 5, 16, 45, 0, tzinfo=UTC),
        metadata={"error_rate_pct": 15.0, "last_deploy": "abc123"},
    ),
    expected_root_cause_keywords=[
        "deployment", "error", "500", "regression", "config",
    ],
    expected_remediation_keywords=[
        "rollback", "deploy", "canary", "revert",
    ],
    expected_affected_services=["checkout-service"],
    min_confidence=0.8,
    mock_responses=[
        Response(
            content=json.dumps({
                "classification": "deployment-regression",
                "affected_services": ["checkout-service"],
                "priority": "P1",
                "summary": "checkout-service error rate spiked after deployment abc123.",
                "delegation_instructions": "Check deployment diff and error logs.",
            }),
            usage=TokenUsage(input_tokens=450, output_tokens=190),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "root_cause": (
                    "Deployment abc123 introduced a null pointer"
                    " in payment validation, causing 500"
                    " errors on checkout."
                ),
                "confidence": 0.95,
                "evidence": [
                    "Error rate correlated with deploy time",
                    "NullPointerException in logs",
                ],
                "affected_services": ["checkout-service"],
            }),
            usage=TokenUsage(input_tokens=1800, output_tokens=450),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "remediation_steps": [
                    {
                        "step": 1,
                        "action": "Rollback deployment abc123 immediately",
                        "risk": "low",
                        "requires_approval": True,
                    },
                    {
                        "step": 2,
                        "action": "Fix null pointer bug and redeploy with canary",
                        "risk": "medium",
                        "requires_approval": True,
                    },
                ],
                "requires_human_approval": True,
                "summary": "Rollback the bad deployment, then fix and redeploy safely.",
            }),
            usage=TokenUsage(input_tokens=900, output_tokens=280),
            model="mock",
            stop_reason="end_turn",
        ),
    ],
)
