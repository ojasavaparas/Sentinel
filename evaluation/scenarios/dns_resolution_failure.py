"""Scenario: DNS resolution failure causing service connectivity issues."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.llm_client import Response, TokenUsage
from agent.models import Alert
from evaluation.scenarios._base import EvalScenario

scenario = EvalScenario(
    name="dns_resolution_failure",
    alert=Alert(
        service="inventory-service",
        description=(
            "DNS resolution failures for downstream"
            " dependencies, NXDOMAIN errors"
        ),
        severity="high",
        timestamp=datetime(2024, 5, 20, 11, 15, 0, tzinfo=UTC),
        metadata={"nxdomain_count": 500, "affected_domains": ["db.internal", "cache.internal"]},
    ),
    expected_root_cause_keywords=[
        "DNS", "resolution", "NXDOMAIN", "CoreDNS", "nameserver",
    ],
    expected_remediation_keywords=[
        "DNS", "restart", "CoreDNS", "nameserver", "config",
    ],
    expected_affected_services=["inventory-service"],
    min_confidence=0.7,
    mock_responses=[
        Response(
            content=json.dumps({
                "classification": "network-dns",
                "affected_services": ["inventory-service"],
                "priority": "P1",
                "summary": "inventory-service unable to resolve internal DNS names.",
                "delegation_instructions": "Check CoreDNS pods and DNS configuration.",
            }),
            usage=TokenUsage(input_tokens=420, output_tokens=175),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "root_cause": (
                    "CoreDNS pods crashed due to OOM, causing"
                    " NXDOMAIN errors for all internal"
                    " service discovery."
                ),
                "confidence": 0.85,
                "evidence": [
                    "CoreDNS pods in CrashLoopBackOff",
                    "NXDOMAIN errors correlate with pod restarts",
                ],
                "affected_services": ["inventory-service"],
            }),
            usage=TokenUsage(input_tokens=1400, output_tokens=380),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "remediation_steps": [
                    {
                        "step": 1,
                        "action": "Restart CoreDNS pods with increased memory limits",
                        "risk": "medium",
                        "requires_approval": True,
                    },
                    {
                        "step": 2,
                        "action": "Add DNS caching sidecar to critical services",
                        "risk": "low",
                        "requires_approval": False,
                    },
                ],
                "requires_human_approval": True,
                "summary": "Restart CoreDNS with more memory and add DNS caching.",
            }),
            usage=TokenUsage(input_tokens=750, output_tokens=230),
            model="mock",
            stop_reason="end_turn",
        ),
    ],
)
