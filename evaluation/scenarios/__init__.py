"""Evaluation scenarios — each defines an alert, expected outputs, and mock responses."""

from __future__ import annotations

from evaluation.scenarios._base import EvalScenario
from evaluation.scenarios.certificate_expiry import scenario as _certificate_expiry
from evaluation.scenarios.cpu_spike import scenario as _cpu_spike
from evaluation.scenarios.database_replication_lag import scenario as _db_replication_lag
from evaluation.scenarios.deployment_failure import scenario as _deployment_failure
from evaluation.scenarios.disk_space_exhaustion import scenario as _disk_space
from evaluation.scenarios.dns_resolution_failure import scenario as _dns_failure
from evaluation.scenarios.kafka_consumer_lag import scenario as _kafka_lag
from evaluation.scenarios.memory_leak import scenario as _memory_leak
from evaluation.scenarios.payment_api_pool_exhaustion import scenario as _pool_exhaustion
from evaluation.scenarios.rate_limiting import scenario as _rate_limiting

ALL_SCENARIOS: list[EvalScenario] = [
    _pool_exhaustion,
    _memory_leak,
    _deployment_failure,
    _certificate_expiry,
    _dns_failure,
    _kafka_lag,
    _disk_space,
    _cpu_spike,
    _rate_limiting,
    _db_replication_lag,
]


def load_all_scenarios() -> list[EvalScenario]:
    """Return every registered evaluation scenario."""
    return list(ALL_SCENARIOS)
