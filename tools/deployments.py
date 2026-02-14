"""Simulated deployment history tool — returns recent deploys from simulated data."""

from __future__ import annotations

import json
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent.parent / "simulation" / "data" / "deployments.json"


def _load_deployments() -> list[dict]:
    with open(_DATA_PATH) as f:
        return json.load(f)


async def get_recent_deployments(
    service: str | None = None,
    limit: int = 5,
) -> list[dict]:
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

    # Sort by timestamp descending (most recent first)
    deployments.sort(key=lambda x: x["timestamp"], reverse=True)

    return deployments[:limit]
