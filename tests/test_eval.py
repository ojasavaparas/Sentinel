"""Tests for the evaluation suite — scorer, scenario loading, and report generation."""

from __future__ import annotations

from datetime import UTC, datetime

from agent.models import Alert, IncidentReport
from evaluation.report import generate_report
from evaluation.runner import EvalRun, ScenarioResult, run_scenario
from evaluation.scenarios import load_all_scenarios
from evaluation.scenarios._base import EvalScenario
from evaluation.scorer import score_scenario

# ---------------------------------------------------------------------------
# Scorer Tests
# ---------------------------------------------------------------------------


def _make_scenario(**overrides) -> EvalScenario:
    defaults = {
        "name": "test-scenario",
        "alert": Alert(
            service="test-svc",
            description="test alert",
            severity="high",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        "expected_root_cause_keywords": ["database", "timeout"],
        "expected_remediation_keywords": ["restart", "scale"],
        "expected_affected_services": ["test-svc"],
        "min_confidence": 0.7,
    }
    defaults.update(overrides)
    return EvalScenario(**defaults)


def _make_report(**overrides) -> IncidentReport:
    defaults = {
        "incident_id": "INC-TEST",
        "alert": Alert(
            service="test-svc",
            description="test alert",
            severity="high",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        "summary": "Test summary",
        "root_cause": "Database connection timeout caused by pool exhaustion",
        "confidence_score": 0.85,
        "remediation_steps": ["Restart the service", "Scale up pods"],
        "total_tokens": 1000,
        "total_cost_usd": 0.01,
        "duration_seconds": 5.0,
        "requires_human_approval": True,
    }
    defaults.update(overrides)
    return IncidentReport(**defaults)


def test_scorer_perfect_match():
    """When all keywords match and confidence is above threshold, score should be high."""
    scenario = _make_scenario()
    report = _make_report()
    score = score_scenario(scenario, report)

    assert score.root_cause_match >= 0.5
    assert score.confidence_calibration == 1.0
    assert score.total_score >= 0.6
    assert score.passed is True


def test_scorer_no_match():
    """When no keywords match, score should be low."""
    scenario = _make_scenario()
    report = _make_report(
        root_cause="Everything is fine, no issues found",
        remediation_steps=["Do nothing"],
        confidence_score=0.1,
    )
    score = score_scenario(scenario, report)

    assert score.root_cause_match < 0.5
    assert score.total_score < 0.6
    assert score.passed is False


def test_scorer_confidence_calibration_below_threshold():
    """Confidence below min_confidence should penalize the score."""
    scenario = _make_scenario(min_confidence=0.9)
    report = _make_report(confidence_score=0.45)
    score = score_scenario(scenario, report)

    assert score.confidence_calibration == 0.5


def test_scorer_empty_keywords():
    """Empty keyword lists should give 1.0 for that component."""
    scenario = _make_scenario(
        expected_root_cause_keywords=[],
        expected_remediation_keywords=[],
    )
    report = _make_report()
    score = score_scenario(scenario, report)

    assert score.root_cause_match == 1.0
    assert score.remediation_coverage == 1.0


# ---------------------------------------------------------------------------
# Scenario Loading Tests
# ---------------------------------------------------------------------------


def test_load_all_scenarios_returns_ten():
    """Should load exactly 10 scenarios."""
    scenarios = load_all_scenarios()
    assert len(scenarios) == 10


def test_all_scenarios_have_mock_responses():
    """Every scenario must have at least 3 mock responses (triage, research, remediation)."""
    for scenario in load_all_scenarios():
        assert len(scenario.mock_responses) >= 3, f"{scenario.name} has < 3 mock responses"


# ---------------------------------------------------------------------------
# Report Generation Tests
# ---------------------------------------------------------------------------


def test_report_generates_markdown(tmp_path):
    """Report should generate a valid markdown file."""
    scenario = _make_scenario()
    report = _make_report()
    score = score_scenario(scenario, report)

    run = EvalRun(
        mode="mock",
        results=[
            ScenarioResult(
                scenario=scenario,
                report=report,
                score=score,
                duration_seconds=1.0,
            ),
        ],
        total_duration_seconds=1.0,
    )

    path = generate_report(run, output_dir=str(tmp_path))
    content = open(path).read()

    assert "Sentinel Evaluation Report" in content
    assert "test-scenario" in content
    assert "PASS" in content or "FAIL" in content


# ---------------------------------------------------------------------------
# Runner Tests
# ---------------------------------------------------------------------------


async def test_run_scenario_mock_mode():
    """Running a scenario in mock mode should produce a scored result."""
    scenarios = load_all_scenarios()
    result = await run_scenario(scenarios[0], mode="mock")

    assert result.error is None
    assert result.report.incident_id.startswith("INC-")
    assert result.score.total_score > 0
    assert result.duration_seconds >= 0
