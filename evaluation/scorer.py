"""Scoring logic for evaluation scenarios."""

from __future__ import annotations

from dataclasses import dataclass

from agent.models import IncidentReport
from evaluation.scenarios._base import EvalScenario


@dataclass
class ScenarioScore:
    """Scoring breakdown for a single evaluated scenario."""

    scenario_name: str
    root_cause_match: float
    remediation_coverage: float
    confidence_calibration: float
    affected_services_accuracy: float
    total_score: float
    passed: bool


PASS_THRESHOLD = 0.60

# Weights
W_ROOT_CAUSE = 0.40
W_REMEDIATION = 0.30
W_CONFIDENCE = 0.15
W_SERVICES = 0.15


def _keyword_overlap(text: str, keywords: list[str]) -> float:
    """Fraction of keywords found (case-insensitive) in text."""
    if not keywords:
        return 1.0
    lower = text.lower()
    matched = sum(1 for kw in keywords if kw.lower() in lower)
    return matched / len(keywords)


def score_scenario(scenario: EvalScenario, report: IncidentReport) -> ScenarioScore:
    """Score a single scenario result against its expected outputs."""
    # 1. Root cause keyword match (40%)
    root_cause_match = _keyword_overlap(
        report.root_cause, scenario.expected_root_cause_keywords
    )

    # 2. Remediation keyword coverage (30%)
    remediation_text = " ".join(report.remediation_steps)
    remediation_coverage = _keyword_overlap(
        remediation_text, scenario.expected_remediation_keywords
    )

    # 3. Confidence calibration (15%) — closeness to min_confidence
    if report.confidence_score >= scenario.min_confidence:
        confidence_calibration = 1.0
    else:
        confidence_calibration = max(
            0.0, report.confidence_score / scenario.min_confidence
        )

    # 4. Affected services accuracy (15%)
    expected = {s.lower() for s in scenario.expected_affected_services}
    # Extract affected services from the alert (the report's alert.service)
    # and from remediation text or root cause
    found: set[str] = set()
    all_text = (report.root_cause + " " + " ".join(report.remediation_steps)).lower()
    for svc in expected:
        if svc in all_text or svc == report.alert.service.lower():
            found.add(svc)
    affected_services_accuracy = len(found) / len(expected) if expected else 1.0

    total = (
        W_ROOT_CAUSE * root_cause_match
        + W_REMEDIATION * remediation_coverage
        + W_CONFIDENCE * confidence_calibration
        + W_SERVICES * affected_services_accuracy
    )

    return ScenarioScore(
        scenario_name=scenario.name,
        root_cause_match=round(root_cause_match, 3),
        remediation_coverage=round(remediation_coverage, 3),
        confidence_calibration=round(confidence_calibration, 3),
        affected_services_accuracy=round(affected_services_accuracy, 3),
        total_score=round(total, 3),
        passed=total >= PASS_THRESHOLD,
    )
