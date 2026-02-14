"""Scenario: Disk space exhaustion on logging volume."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.llm_client import Response, TokenUsage
from agent.models import Alert
from evaluation.scenarios._base import EvalScenario

scenario = EvalScenario(
    name="disk_space_exhaustion",
    alert=Alert(
        service="logging-service",
        description="Disk usage at 95%, write failures detected, log ingestion stalled",
        severity="critical",
        timestamp=datetime(2024, 7, 8, 3, 0, 0, tzinfo=UTC),
        metadata={"disk_usage_pct": 95, "write_errors_per_min": 200},
    ),
    expected_root_cause_keywords=[
        "disk", "space", "log rotation", "volume", "storage",
    ],
    expected_remediation_keywords=[
        "cleanup", "log rotation", "disk", "expand", "volume",
    ],
    expected_affected_services=["logging-service"],
    min_confidence=0.8,
    mock_responses=[
        Response(
            content=json.dumps({
                "classification": "resource-exhaustion",
                "affected_services": ["logging-service"],
                "priority": "P1",
                "summary": "logging-service disk nearly full causing write failures.",
                "delegation_instructions": "Check disk usage and log rotation config.",
            }),
            usage=TokenUsage(input_tokens=390, output_tokens=165),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "root_cause": (
                    "Log rotation misconfigured after infra"
                    " change \u2014 logs not being rotated,"
                    " filling disk in 48 hours."
                ),
                "confidence": 0.88,
                "evidence": ["No logrotate runs in 48h", "Single log file >200GB"],
                "affected_services": ["logging-service"],
            }),
            usage=TokenUsage(input_tokens=1100, output_tokens=320),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "remediation_steps": [
                    {
                        "step": 1,
                        "action": "Clean up old log files to reclaim disk space",
                        "risk": "low",
                        "requires_approval": False,
                    },
                    {
                        "step": 2,
                        "action": "Fix log rotation configuration",
                        "risk": "low",
                        "requires_approval": False,
                    },
                    {
                        "step": 3,
                        "action": "Expand disk volume if needed",
                        "risk": "medium",
                        "requires_approval": True,
                    },
                ],
                "requires_human_approval": True,
                "summary": "Clean logs, fix rotation, expand disk if needed.",
            }),
            usage=TokenUsage(input_tokens=720, output_tokens=240),
            model="mock",
            stop_reason="end_turn",
        ),
    ],
)
