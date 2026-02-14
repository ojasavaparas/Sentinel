"""Markdown report generator for evaluation results."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from evaluation.runner import EvalRun


def generate_report(run: EvalRun, output_dir: str = "evaluation/results") -> str:
    """Generate a markdown report and write it to disk. Returns the file path."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filepath = out / f"eval_{run.mode}_{ts}.md"

    lines: list[str] = []
    lines.append(f"# Sentinel Evaluation Report — {run.mode.upper()} mode")
    lines.append(f"**Date:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"**Scenarios:** {len(run.results)}")
    lines.append(f"**Duration:** {run.total_duration_seconds:.1f}s")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Mean Accuracy | {run.mean_score:.1%} |")
    lines.append(f"| Pass Rate (>60%) | {run.pass_rate:.0%} |")
    lines.append(f"| Total Cost | ${run.total_cost:.4f} |")
    lines.append(f"| Total Duration | {run.total_duration_seconds:.1f}s |")
    lines.append("")

    # Per-scenario table
    lines.append("## Per-Scenario Results")
    lines.append("")
    lines.append(
        "| Scenario | Root Cause | Remediation | Confidence | Services | "
        "**Total** | Pass |"
    )
    lines.append("|----------|-----------|-------------|------------|----------|-------|------|")

    for r in run.results:
        s = r.score
        status = "PASS" if s.passed else "FAIL"
        lines.append(
            f"| {s.scenario_name} | {s.root_cause_match:.0%} | "
            f"{s.remediation_coverage:.0%} | {s.confidence_calibration:.0%} | "
            f"{s.affected_services_accuracy:.0%} | **{s.total_score:.0%}** | "
            f"{status} |"
        )

    lines.append("")

    # Errors
    errors = [r for r in run.results if r.error]
    if errors:
        lines.append("## Errors")
        lines.append("")
        for r in errors:
            lines.append(f"- **{r.scenario.name}**: {r.error}")
        lines.append("")

    content = "\n".join(lines) + "\n"
    filepath.write_text(content)

    return str(filepath)
