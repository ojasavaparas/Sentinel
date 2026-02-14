"""CLI entry point: python -m evaluation."""

from __future__ import annotations

import asyncio
import os
import sys

from evaluation.report import generate_report
from evaluation.runner import run_all


def main() -> None:
    mode = os.environ.get("EVAL_MODE", "mock")
    print(f"Running Sentinel evaluation suite in {mode.upper()} mode...")

    run = asyncio.run(run_all(mode=mode))

    # Print summary
    print(f"\nResults: {len(run.results)} scenarios")
    print(f"  Mean accuracy: {run.mean_score:.1%}")
    print(f"  Pass rate:     {run.pass_rate:.0%}")
    print(f"  Total cost:    ${run.total_cost:.4f}")
    print(f"  Duration:      {run.total_duration_seconds:.1f}s")

    for r in run.results:
        status = "PASS" if r.score.passed else "FAIL"
        print(f"  [{status}] {r.score.scenario_name}: {r.score.total_score:.0%}")

    # Generate report
    path = generate_report(run)
    print(f"\nReport written to: {path}")

    # Exit with error if any scenario failed
    if run.pass_rate < 1.0:
        failed = sum(1 for r in run.results if not r.score.passed)
        print(f"\n{failed} scenario(s) below 60% threshold.")
        sys.exit(1)


if __name__ == "__main__":
    main()
