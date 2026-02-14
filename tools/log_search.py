"""Simulated log search tool — filters and returns log entries from simulated data."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parent.parent / "simulation" / "data" / "logs.json"


def _load_logs() -> list[dict[str, Any]]:
    with open(_DATA_PATH) as f:
        result: list[dict[str, Any]] = json.load(f)
        return result


async def search_logs(
    service: str,
    severity: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Search simulated logs with optional filters.

    Args:
        service: Service name to filter by (required).
        severity: Log level filter (INFO, WARN, ERROR).
        time_start: ISO timestamp lower bound (inclusive).
        time_end: ISO timestamp upper bound (inclusive).
        query: Substring to match against the log message.

    Returns:
        Matching log entries sorted by timestamp.
    """
    logs = _load_logs()

    # Filter by service
    results = [log for log in logs if log["service"] == service]

    # Filter by severity
    if severity:
        results = [log for log in results if log["level"] == severity.upper()]

    # Filter by time range
    if time_start:
        start_dt = datetime.fromisoformat(time_start.replace("Z", "+00:00"))
        results = [
            log for log in results
            if datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00")) >= start_dt
        ]

    if time_end:
        end_dt = datetime.fromisoformat(time_end.replace("Z", "+00:00"))
        results = [
            log for log in results
            if datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00")) <= end_dt
        ]

    # Filter by query substring
    if query:
        query_lower = query.lower()
        results = [log for log in results if query_lower in log["message"].lower()]

    # Sort by timestamp
    results.sort(key=lambda x: x["timestamp"])

    return results
