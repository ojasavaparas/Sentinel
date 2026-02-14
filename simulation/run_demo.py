"""Demo script — runs a full incident analysis on a sample payment-api alert."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.core import IncidentAnalyzer
from agent.llm_client import create_client
from agent.models import Alert
from rag.engine import RAGEngine
from rag.ingest import ingest_runbooks


def ensure_runbooks_ingested() -> None:
    """Ingest runbooks if the ChromaDB collection doesn't exist yet."""
    chroma_dir = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_data")
    if not Path(chroma_dir).exists() or not any(Path(chroma_dir).iterdir()):
        print("Ingesting runbooks into vector store...")
        ingest_runbooks()
        print()
    else:
        print("Runbooks already ingested, skipping.\n")


def print_section(title: str) -> None:
    width = 70
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


async def run_demo() -> None:
    """Run the full Sentinel demo."""
    print_section("SENTINEL — Incident Analysis Demo")

    # 1. Ensure runbooks are ingested
    ensure_runbooks_ingested()

    # 2. Create the sample alert
    alert = Alert(
        service="payment-api",
        description=(
            "P99 latency spike to 2100ms, normal baseline 180ms. "
            "Error rate increased from 0.1% to 15%. "
            "Started approximately 30 minutes after latest deployment."
        ),
        severity="critical",
        timestamp=datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC),
        metadata={
            "current_p99_ms": 2100,
            "baseline_p99_ms": 180,
            "error_rate_percent": 15.0,
        },
    )

    print_section("INCOMING ALERT")
    print(f"  Service:     {alert.service}")
    print(f"  Severity:    {alert.severity}")
    print(f"  Timestamp:   {alert.timestamp.isoformat()}")
    print(f"  Description: {alert.description}")

    # 3. Initialize the analyzer
    llm_client = create_client()
    rag_engine = RAGEngine()
    analyzer = IncidentAnalyzer(llm_client=llm_client, rag_engine=rag_engine)

    # 4. Run analysis
    print_section("RUNNING ANALYSIS")
    print("  Triage Agent → Research Agent → Remediation Agent")
    print("  Processing...\n")

    report = await analyzer.analyze(alert)

    # 5. Print the report
    print_section("INCIDENT REPORT")
    print(f"  Incident ID:           {report.incident_id}")
    print(f"  Summary:               {report.summary}")
    print(f"  Root Cause:            {report.root_cause}")
    print(f"  Confidence:            {report.confidence_score:.0%}")
    print(f"  Requires Approval:     {report.requires_human_approval}")
    print(f"  Duration:              {report.duration_seconds}s")
    print(f"  Total Tokens:          {report.total_tokens:,}")
    print(f"  Total Cost:            ${report.total_cost_usd:.4f}")

    print_section("REMEDIATION STEPS")
    for i, step in enumerate(report.remediation_steps, 1):
        print(f"  {i}. {step}")

    print_section("AGENT DECISION TRACE")
    for step in report.agent_trace:
        tool_info = ""
        if step.tool_calls:
            tool_names = [tc.tool_name for tc in step.tool_calls]
            tool_info = f" | Tools: {', '.join(tool_names)}"
        print(f"  [{step.agent_name}] {step.action}{tool_info}")
        if step.tokens_used:
            print(f"           Tokens: {step.tokens_used:,} | Cost: ${step.cost_usd:.4f}")

    print_section("FULL REPORT JSON")
    report_dict = report.model_dump(mode="json")
    # Truncate agent trace reasoning for readability
    for step in report_dict.get("agent_trace", []):
        if len(step.get("reasoning", "")) > 200:
            step["reasoning"] = step["reasoning"][:200] + "..."
    print(json.dumps(report_dict, indent=2, default=str))

    print("\n" + "=" * 70)
    print("  Demo complete.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_demo())
