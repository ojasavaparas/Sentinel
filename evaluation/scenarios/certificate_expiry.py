"""Scenario: TLS certificate expiry causing connection failures."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.llm_client import Response, TokenUsage
from agent.models import Alert
from evaluation.scenarios._base import EvalScenario

scenario = EvalScenario(
    name="certificate_expiry",
    alert=Alert(
        service="api-gateway",
        description="SSL handshake failures increasing, certificate expires in 2 hours",
        severity="critical",
        timestamp=datetime(2024, 4, 1, 22, 0, 0, tzinfo=UTC),
        metadata={"cert_expiry": "2024-04-02T00:00:00Z", "handshake_failures_per_min": 150},
    ),
    expected_root_cause_keywords=[
        "certificate", "expiry", "TLS", "SSL", "renewal",
    ],
    expected_remediation_keywords=[
        "renew", "certificate", "auto-renewal", "certbot",
    ],
    expected_affected_services=["api-gateway"],
    min_confidence=0.9,
    mock_responses=[
        Response(
            content=json.dumps({
                "classification": "certificate-expiry",
                "affected_services": ["api-gateway"],
                "priority": "P1",
                "summary": (
                    "api-gateway TLS certificate expiring"
                    " imminently causing SSL handshake"
                    " failures."
                ),
                "delegation_instructions": "Verify certificate expiry and renewal status.",
            }),
            usage=TokenUsage(input_tokens=380, output_tokens=170),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "root_cause": (
                    "TLS certificate for api-gateway expired,"
                    " auto-renewal failed due to DNS challenge"
                    " misconfiguration."
                ),
                "confidence": 0.97,
                "evidence": [
                    "Certificate expiry matches failure onset",
                    "Certbot logs show DNS challenge error",
                ],
                "affected_services": ["api-gateway"],
            }),
            usage=TokenUsage(input_tokens=1200, output_tokens=350),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "remediation_steps": [
                    {
                        "step": 1,
                        "action": "Manually renew TLS certificate via certbot",
                        "risk": "low",
                        "requires_approval": True,
                    },
                    {
                        "step": 2,
                        "action": "Fix DNS challenge configuration for auto-renewal",
                        "risk": "low",
                        "requires_approval": False,
                    },
                ],
                "requires_human_approval": True,
                "summary": "Renew certificate immediately and fix auto-renewal.",
            }),
            usage=TokenUsage(input_tokens=700, output_tokens=220),
            model="mock",
            stop_reason="end_turn",
        ),
    ],
)
