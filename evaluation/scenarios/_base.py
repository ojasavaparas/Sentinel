"""Base dataclass for evaluation scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.llm_client import Response
from agent.models import Alert


@dataclass
class EvalScenario:
    """A single evaluation scenario with expected outputs and optional mock responses."""

    name: str
    alert: Alert
    expected_root_cause_keywords: list[str]
    expected_remediation_keywords: list[str]
    expected_affected_services: list[str]
    min_confidence: float = 0.5
    mock_responses: list[Response] = field(default_factory=list)
