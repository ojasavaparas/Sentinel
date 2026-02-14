"""Scenario: Kafka consumer lag causing event processing delays."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.llm_client import Response, TokenUsage
from agent.models import Alert
from evaluation.scenarios._base import EvalScenario

scenario = EvalScenario(
    name="kafka_consumer_lag",
    alert=Alert(
        service="notification-service",
        description="Kafka consumer lag exceeding 50,000 messages, processing delay > 30 minutes",
        severity="high",
        timestamp=datetime(2024, 6, 12, 9, 30, 0, tzinfo=UTC),
        metadata={"consumer_lag": 50000, "processing_delay_min": 30},
    ),
    expected_root_cause_keywords=[
        "Kafka", "consumer", "lag", "throughput", "partition",
    ],
    expected_remediation_keywords=[
        "scale", "consumer", "partition", "throughput",
    ],
    expected_affected_services=["notification-service"],
    min_confidence=0.6,
    mock_responses=[
        Response(
            content=json.dumps({
                "classification": "message-queue-lag",
                "affected_services": ["notification-service"],
                "priority": "P2",
                "summary": "notification-service Kafka consumer lag growing, events delayed.",
                "delegation_instructions": (
                    "Check consumer group offsets and"
                    " processing throughput."
                ),
            }),
            usage=TokenUsage(input_tokens=410, output_tokens=185),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "root_cause": (
                    "Spike in event volume combined with slow"
                    " downstream API calls reduced consumer"
                    " throughput below production rate."
                ),
                "confidence": 0.72,
                "evidence": ["Event volume 3x normal", "Downstream API p99 at 5s"],
                "affected_services": ["notification-service"],
            }),
            usage=TokenUsage(input_tokens=1300, output_tokens=360),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "remediation_steps": [
                    {
                        "step": 1,
                        "action": "Scale up consumer instances to match throughput",
                        "risk": "low",
                        "requires_approval": False,
                    },
                    {
                        "step": 2,
                        "action": "Add circuit breaker for slow downstream calls",
                        "risk": "medium",
                        "requires_approval": True,
                    },
                ],
                "requires_human_approval": True,
                "summary": "Scale consumers and protect against slow dependencies.",
            }),
            usage=TokenUsage(input_tokens=680, output_tokens=210),
            model="mock",
            stop_reason="end_turn",
        ),
    ],
)
