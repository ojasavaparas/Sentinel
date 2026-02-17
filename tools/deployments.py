"""Simulated deployment history tool — returns recent deploys from simulated data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parent.parent / "simulation" / "data" / "deployments.json"


def _load_deployments() -> list[dict[str, Any]]:
    with open(_DATA_PATH) as f:
        result: list[dict[str, Any]] = json.load(f)
        return result


async def get_recent_deployments(
    service: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve recent deployments, optionally filtered by service.

    Args:
        service: Service name to filter by (optional, returns all if None).
        limit: Maximum number of deployments to return (default 5).

    Returns:
        Deployments sorted by most recent first.
    """
    deployments = _load_deployments()

    if service:
        deployments = [d for d in deployments if d["service"] == service]

    deployments.sort(key=lambda x: x["timestamp"], reverse=True)

    return deployments[:limit]
