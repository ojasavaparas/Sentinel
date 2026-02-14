"""Scenario: Database replication lag causing stale reads."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.llm_client import Response, TokenUsage
from agent.models import Alert
from evaluation.scenarios._base import EvalScenario

scenario = EvalScenario(
    name="database_replication_lag",
    alert=Alert(
        service="order-service",
        description="Read replicas lagging 45 seconds behind primary, stale data served to users",
        severity="high",
        timestamp=datetime(2024, 10, 18, 7, 30, 0, tzinfo=UTC),
        metadata={"replication_lag_seconds": 45, "affected_reads_pct": 30},
    ),
    expected_root_cause_keywords=[
        "replication", "lag", "replica", "primary", "database",
    ],
    expected_remediation_keywords=[
        "replication", "replica", "read routing", "primary",
    ],
    expected_affected_services=["order-service"],
    min_confidence=0.6,
    mock_responses=[
        Response(
            content=json.dumps({
                "classification": "database-degradation",
                "affected_services": ["order-service"],
                "priority": "P2",
                "summary": "order-service read replicas behind primary, users seeing stale data.",
                "delegation_instructions": "Check replication status and write throughput.",
            }),
            usage=TokenUsage(input_tokens=400, output_tokens=175),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "root_cause": (
                    "Bulk data migration on primary database"
                    " saturated replication bandwidth, causing"
                    " replicas to fall behind."
                ),
                "confidence": 0.75,
                "evidence": ["Bulk write job started 1h ago", "Replication bandwidth at 100%"],
                "affected_services": ["order-service"],
            }),
            usage=TokenUsage(input_tokens=1400, output_tokens=370),
            model="mock",
            stop_reason="end_turn",
        ),
        Response(
            content=json.dumps({
                "remediation_steps": [
                    {
                        "step": 1,
                        "action": "Throttle bulk migration job to reduce write pressure",
                        "risk": "medium",
                        "requires_approval": True,
                    },
                    {
                        "step": 2,
                        "action": "Temporarily route critical reads to primary",
                        "risk": "low",
                        "requires_approval": True,
                    },
                ],
                "requires_human_approval": True,
                "summary": "Throttle migration and route critical reads to primary.",
            }),
            usage=TokenUsage(input_tokens=750, output_tokens=230),
            model="mock",
            stop_reason="end_turn",
        ),
    ],
)
