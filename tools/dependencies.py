"""Service dependency graph — returns upstream dependencies and their health status."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parent.parent / "simulation" / "data" / "dependencies.json"


def _load_dependencies() -> list[dict[str, Any]]:
    with open(_DATA_PATH) as f:
        result: list[dict[str, Any]] = json.load(f)
        return result


async def get_service_dependencies(service: str) -> dict[str, Any]:
    """Retrieve the dependency tree for a given service.

    Args:
        service: Service name to look up.

    Returns:
        Dictionary with service name, its dependencies (name, type, health_status),
        and a summary of degraded dependencies.
    """
    all_deps = _load_dependencies()

    for entry in all_deps:
        if entry["service"] == service:
            degraded = [
                d["name"] for d in entry["dependencies"]
                if d["health_status"] != "healthy"
            ]
            return {
                "service": service,
                "dependencies": entry["dependencies"],
                "total_dependencies": len(entry["dependencies"]),
                "degraded_dependencies": degraded,
            }

    return {
        "service": service,
        "dependencies": [],
        "total_dependencies": 0,
        "degraded_dependencies": [],
        "error": f"Service '{service}' not found in dependency graph",
    }
