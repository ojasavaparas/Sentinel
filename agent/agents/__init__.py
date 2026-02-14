"""Individual agent implementations — triage, research, and remediation."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from LLM output, stripping markdown code fences."""
    # Strip ```json ... ``` or ``` ... ``` wrappers
    stripped = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")

    # Try parsing the stripped text directly
    try:
        return json.loads(stripped)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, ValueError):
        pass

    # Fall back to extracting the outermost { ... }
    start = stripped.find("{")
    end = stripped.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(stripped[start:end])  # type: ignore[no-any-return]
        except (json.JSONDecodeError, ValueError):
            pass

    return None
