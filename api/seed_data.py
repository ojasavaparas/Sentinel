"""Seed incidents so the dashboard isn't empty on first visit."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import UTC, datetime

from agent.models import AgentStep, Alert, IncidentReport, ToolCall


def get_seed_incidents() -> list[IncidentReport]:
    return [
        # --- Incident 1: 3 days ago, critical DB pool exhaustion ---
        IncidentReport(
            incident_id="INC-7f3a1e92",
            alert=Alert(
                service="payment-api",
                description="P99 latency spike to 2.1s, error rate at 15.2%",
                severity="critical",
                timestamp=datetime(2025, 2, 11, 14, 30, 0, tzinfo=UTC),
            ),
            summary="Database connection pool exhaustion on payment-api caused by a deployment that reduced max pool size from 50 to 10. Cascading failures affected order-service and checkout-service downstream.",
            root_cause="Deployment a1bf3d2 changed DB connection pool max_size from 50 to 10 in payment-api config. Under normal load (~40 concurrent connections), the pool saturated within minutes, causing connection timeouts and 500 errors.",
            confidence_score=0.92,
            remediation_steps=[
                "Revert payment-api config to restore max_pool_size=50 (kubectl rollback deployment/payment-api)",
                "Scale payment-api horizontally to 4 replicas to drain queued requests",
                "Add connection pool utilization alert at 80% threshold to prevent recurrence",
                "Implement config validation in CI to flag pool size changes below minimum baseline",
            ],
            agent_trace=[
                AgentStep(
                    agent_name="triage",
                    action="triage_classification",
                    reasoning="Critical latency incident on revenue-impacting service. P99 at 2.1s (10x normal). Error rate 15.2%. DB pool at 98% utilization. Classification: resource-exhaustion, Priority: P1.",
                    tool_calls=[
                        ToolCall(tool_name="get_service_dependencies", arguments={"service": "payment-api"}, result={"dependencies": ["postgres-primary", "redis-cache"]}, latency_ms=1.2, cost_usd=0.0),
                        ToolCall(tool_name="get_metrics", arguments={"service": "payment-api", "time_start": "2025-02-11T14:00:00Z", "time_end": "2025-02-11T14:45:00Z"}, result={"p99_latency_ms": 2100, "error_rate": 0.152}, latency_ms=2.1, cost_usd=0.0),
                    ],
                    tokens_used=4079,
                    cost_usd=0.018,
                    timestamp=datetime(2025, 2, 11, 14, 31, 12, tzinfo=UTC),
                ),
                AgentStep(
                    agent_name="research",
                    action="research_findings",
                    reasoning="Correlated latency spike with deployment a1bf3d2 at 14:12. Config diff shows max_pool_size changed from 50 to 10. Pool utilization hit 100% by 14:18. All errors are connection timeout exceptions from the DB driver.",
                    tool_calls=[
                        ToolCall(tool_name="search_logs", arguments={"service": "payment-api", "severity": "ERROR"}, result={"count": 847, "top_error": "ConnectionPoolExhausted"}, latency_ms=3.4, cost_usd=0.0),
                        ToolCall(tool_name="get_deployments", arguments={"service": "payment-api", "limit": 5}, result={"deployments": [{"sha": "a1bf3d2", "time": "14:12"}]}, latency_ms=1.8, cost_usd=0.0),
                        ToolCall(tool_name="get_metrics", arguments={"service": "postgres-primary"}, result={"active_connections": 10, "max_connections": 10}, latency_ms=2.0, cost_usd=0.0),
                    ],
                    tokens_used=8250,
                    cost_usd=0.062,
                    timestamp=datetime(2025, 2, 11, 14, 32, 45, tzinfo=UTC),
                ),
                AgentStep(
                    agent_name="remediation",
                    action="remediation_proposal",
                    reasoning="Root cause confirmed: config regression in deployment a1bf3d2. Immediate fix is config rollback. Proposing 4-step remediation with safeguards against recurrence.",
                    tool_calls=[
                        ToolCall(tool_name="search_runbooks", arguments={"query": "database connection pool exhaustion"}, result={"top_result": "database-connection-pool-exhaustion.md"}, latency_ms=15.3, cost_usd=0.0),
                    ],
                    tokens_used=3420,
                    cost_usd=0.025,
                    timestamp=datetime(2025, 2, 11, 14, 33, 58, tzinfo=UTC),
                ),
            ],
            total_tokens=15749,
            total_cost_usd=0.105,
            duration_seconds=87.3,
            requires_human_approval=True,
        ),
        # --- Incident 2: yesterday morning, high severity Kafka lag ---
        IncidentReport(
            incident_id="INC-b24c09d1",
            alert=Alert(
                service="order-service",
                description="Kafka consumer lag exceeding 500k messages",
                severity="high",
                timestamp=datetime(2025, 2, 13, 10, 48, 0, tzinfo=UTC),
            ),
            summary="Kafka consumer group for order-service fell behind by 500k+ messages after inventory-service entered maintenance mode, causing retry storms that blocked consumer threads.",
            root_cause="inventory-service went into maintenance mode at 10:30 without updating the dependency status. order-service consumer retried failed inventory checks with exponential backoff, but the retry queue filled up and blocked partition consumption.",
            confidence_score=0.78,
            remediation_steps=[
                "Increase consumer thread pool from 4 to 12 to process backlog",
                "Add circuit breaker on inventory-service calls with 5s timeout and fallback",
                "Reset consumer group offset to latest for non-critical partitions to skip stale messages",
            ],
            agent_trace=[
                AgentStep(
                    agent_name="triage",
                    action="triage_classification",
                    reasoning="Kafka consumer lag on order-service. Classification: message-queue-lag, Priority: P2. Orders will be delayed but not lost.",
                    tool_calls=[
                        ToolCall(tool_name="get_metrics", arguments={"service": "order-service"}, result={"consumer_lag": 512000, "throughput_per_sec": 50}, latency_ms=1.8, cost_usd=0.0),
                    ],
                    tokens_used=2900,
                    cost_usd=0.013,
                    timestamp=datetime(2025, 2, 13, 10, 49, 5, tzinfo=UTC),
                ),
                AgentStep(
                    agent_name="research",
                    action="research_findings",
                    reasoning="Lag started at 10:32, two minutes after inventory-service maintenance. Consumer threads blocked on retry loops. No consumer crashes, just throughput collapse.",
                    tool_calls=[
                        ToolCall(tool_name="search_logs", arguments={"service": "order-service", "query": "retry"}, result={"count": 48000, "top_error": "RetryExhausted: inventory-service returned 503"}, latency_ms=4.5, cost_usd=0.0),
                        ToolCall(tool_name="get_service_dependencies", arguments={"service": "order-service"}, result={"dependencies": ["inventory-service", "kafka-cluster"]}, latency_ms=0.9, cost_usd=0.0),
                    ],
                    tokens_used=5600,
                    cost_usd=0.042,
                    timestamp=datetime(2025, 2, 13, 10, 50, 22, tzinfo=UTC),
                ),
                AgentStep(
                    agent_name="remediation",
                    action="remediation_proposal",
                    reasoning="Consumer lag caused by retry storms. Need circuit breaker and increased parallelism to drain backlog.",
                    tool_calls=[],
                    tokens_used=2200,
                    cost_usd=0.016,
                    timestamp=datetime(2025, 2, 13, 10, 51, 10, tzinfo=UTC),
                ),
            ],
            total_tokens=10700,
            total_cost_usd=0.071,
            duration_seconds=55.8,
            requires_human_approval=True,
        ),
        # --- Incident 3: earlier today, medium severity memory leak ---
        IncidentReport(
            incident_id="INC-e8f502a6",
            alert=Alert(
                service="notification-service",
                description="Memory usage at 92%, OOMKill events detected",
                severity="medium",
                timestamp=datetime(2025, 2, 14, 8, 20, 0, tzinfo=UTC),
            ),
            summary="Memory leak in notification-service caused by unbounded in-memory template cache. Each unique notification template variant was cached without eviction, growing to 2.1GB over 5 days since last restart.",
            root_cause="Template rendering engine caches compiled templates keyed by (template_id, locale, variant). With 200+ A/B test variants added last sprint, the cache grew unbounded from ~50MB to 2.1GB over 5 days without an eviction policy.",
            confidence_score=0.82,
            remediation_steps=[
                "Restart notification-service pods to immediately reclaim memory",
                "Add LRU eviction with max_size=500 entries to the template cache",
                "Set memory limit alert at 80% with auto-restart at 90%",
            ],
            agent_trace=[
                AgentStep(
                    agent_name="triage",
                    action="triage_classification",
                    reasoning="Memory at 92% with OOMKill events. Classification: resource-exhaustion (memory leak). Priority: P3. Service still functional but at risk of OOMKill.",
                    tool_calls=[
                        ToolCall(tool_name="get_metrics", arguments={"service": "notification-service"}, result={"memory_percent": 92, "oom_kills_24h": 3}, latency_ms=1.3, cost_usd=0.0),
                    ],
                    tokens_used=2400,
                    cost_usd=0.011,
                    timestamp=datetime(2025, 2, 14, 8, 21, 8, tzinfo=UTC),
                ),
                AgentStep(
                    agent_name="research",
                    action="research_findings",
                    reasoning="Memory growth is linear over 5 days since last deploy. Heap dump shows template cache at 2.1GB. 200+ new A/B variants added last sprint multiplied cache entries.",
                    tool_calls=[
                        ToolCall(tool_name="search_logs", arguments={"service": "notification-service", "severity": "WARN"}, result={"count": 45, "top_error": "High memory utilization: 92%"}, latency_ms=2.9, cost_usd=0.0),
                        ToolCall(tool_name="get_deployments", arguments={"service": "notification-service", "limit": 3}, result={"deployments": [{"sha": "f8c2a11", "time": "Feb 9"}]}, latency_ms=1.4, cost_usd=0.0),
                    ],
                    tokens_used=4800,
                    cost_usd=0.036,
                    timestamp=datetime(2025, 2, 14, 8, 22, 31, tzinfo=UTC),
                ),
                AgentStep(
                    agent_name="remediation",
                    action="remediation_proposal",
                    reasoning="Memory leak from unbounded cache. Restart for immediate relief, then add LRU eviction.",
                    tool_calls=[],
                    tokens_used=1800,
                    cost_usd=0.013,
                    timestamp=datetime(2025, 2, 14, 8, 23, 15, tzinfo=UTC),
                ),
            ],
            total_tokens=9000,
            total_cost_usd=0.060,
            duration_seconds=48.2,
            requires_human_approval=False,
        ),
    ]
