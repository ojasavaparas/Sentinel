"""Simulated metrics retrieval tool — returns time-series data from simulated data."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parent.parent / "simulation" / "data" / "metrics.json"


def _load_metrics() -> list[dict[str, Any]]:
    with open(_DATA_PATH) as f:
        result: list[dict[str, Any]] = json.load(f)
        return result


async def get_metrics(
    service: str,
    metric_name: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve simulated metrics for a service.

    Args:
        service: Service name to filter by (required).
        metric_name: Specific metric (latency_p99, cpu_usage, error_rate, etc.).
        time_start: ISO timestamp lower bound (inclusive).
        time_end: ISO timestamp upper bound (inclusive).

    Returns:
        Matching metric data points sorted by timestamp.
    """
    metrics = _load_metrics()

    results = [m for m in metrics if m["service"] == service]

    if metric_name:
        results = [m for m in results if m["metric_name"] == metric_name]

    if time_start:
        start_dt = datetime.fromisoformat(time_start.replace("Z", "+00:00"))
        results = [
            m for m in results
            if datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00")) >= start_dt
        ]

    if time_end:
        end_dt = datetime.fromisoformat(time_end.replace("Z", "+00:00"))
        results = [
            m for m in results
            if datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00")) <= end_dt
        ]

    results.sort(key=lambda x: x["timestamp"])

    return results
