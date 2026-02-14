"""Evaluation runner — executes scenarios in mock or live mode."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from agent.core import IncidentAnalyzer
from agent.llm_client import LLMClient, MockClient, create_client
from agent.models import IncidentReport
from evaluation.scenarios import load_all_scenarios
from evaluation.scenarios._base import EvalScenario
from evaluation.scorer import ScenarioScore, score_scenario


@dataclass
class ScenarioResult:
    """Result of running a single evaluation scenario."""

    scenario: EvalScenario
    report: IncidentReport
    score: ScenarioScore
    duration_seconds: float
    error: str | None = None


@dataclass
class EvalRun:
    """Full evaluation run with aggregate statistics."""

    mode: str
    results: list[ScenarioResult] = field(default_factory=list)
    total_duration_seconds: float = 0.0

    @property
    def mean_score(self) -> float:
        scores = [r.score.total_score for r in self.results if r.error is None]
        return sum(scores) / len(scores) if scores else 0.0

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        passed = sum(1 for r in self.results if r.score.passed and r.error is None)
        return passed / len(self.results)

    @property
    def total_cost(self) -> float:
        return sum(r.report.total_cost_usd for r in self.results if r.error is None)


async def run_scenario(scenario: EvalScenario, mode: str) -> ScenarioResult:
    """Run a single scenario and score it."""
    start = time.perf_counter()
    error = None

    client: LLMClient
    if mode == "mock":
        client = MockClient(responses=list(scenario.mock_responses))
    else:
        client = create_client("anthropic")

    analyzer = IncidentAnalyzer(llm_client=client)

    try:
        report = await analyzer.analyze(scenario.alert)
    except Exception as e:
        error = str(e)
        # Build a minimal report so scoring still works
        report = IncidentReport(
            incident_id="EVAL-ERROR",
            alert=scenario.alert,
            summary="",
            root_cause="",
            confidence_score=0.0,
            remediation_steps=[],
            total_tokens=0,
            total_cost_usd=0.0,
            duration_seconds=0.0,
            requires_human_approval=True,
        )

    duration = time.perf_counter() - start
    score = score_scenario(scenario, report)

    return ScenarioResult(
        scenario=scenario,
        report=report,
        score=score,
        duration_seconds=round(duration, 2),
        error=error,
    )


async def run_all(mode: str = "mock") -> EvalRun:
    """Run all registered scenarios and return aggregate results."""
    scenarios = load_all_scenarios()
    start = time.perf_counter()

    results: list[ScenarioResult] = []
    for scenario in scenarios:
        result = await run_scenario(scenario, mode)
        results.append(result)

    total_duration = time.perf_counter() - start

    return EvalRun(
        mode=mode,
        results=results,
        total_duration_seconds=round(total_duration, 2),
    )
