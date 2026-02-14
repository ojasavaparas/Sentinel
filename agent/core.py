"""Multi-agent orchestrator — coordinates triage, research, and remediation agents."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import structlog

from agent.agents.remediation import RemediationAgent
from agent.agents.research import ResearchAgent
from agent.agents.triage import TriageAgent
from agent.llm_client import LLMClient
from agent.models import Alert, IncidentReport, StreamEvent
from monitoring.finops import CostTracker
from monitoring.metrics import record_analysis_complete
from monitoring.tracer import DecisionTracer
from protocols.a2a import MessageBus, new_trace_id
from rag.engine import RAGEngine
from tools.registry import ToolRegistry

# Module-level singleton so cost data persists across analyses
_cost_tracker = CostTracker()

logger = structlog.get_logger()

ANALYSIS_TIMEOUT_SECONDS = 120


class IncidentAnalyzer:
    """Orchestrates the three-agent pipeline: Triage → Research → Remediation."""

    def __init__(
        self,
        llm_client: LLMClient,
        rag_engine: RAGEngine | None = None,
    ) -> None:
        self._llm = llm_client
        self._tracer = DecisionTracer()
        self._message_bus = MessageBus()
        self._tool_registry = ToolRegistry(rag_engine=rag_engine)

        # Initialize agents
        self._triage = TriageAgent(llm_client, self._tool_registry, self._tracer)
        self._research = ResearchAgent(llm_client, self._tool_registry, self._tracer)
        self._remediation = RemediationAgent(llm_client, self._tool_registry, self._tracer)

    async def analyze(self, alert: Alert) -> IncidentReport:
        """Run the full analysis pipeline on an alert."""
        incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        trace_id = new_trace_id()
        start_time = time.perf_counter()

        logger.info(
            "analysis_started",
            incident_id=incident_id,
            trace_id=trace_id,
            service=alert.service,
            severity=alert.severity,
        )

        self._tracer.start_trace(trace_id)

        triage_result: dict[str, Any] = {}
        research_result: dict[str, Any] = {}
        remediation_result: dict[str, Any] = {}

        try:
            # Wrap the entire pipeline in a timeout
            triage_result, research_result, remediation_result = await asyncio.wait_for(
                self._run_pipeline(alert, trace_id),
                timeout=ANALYSIS_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.error(
                "analysis_timeout",
                incident_id=incident_id,
                timeout=ANALYSIS_TIMEOUT_SECONDS,
            )
            self._tracer.log_step(
                trace_id=trace_id,
                agent_name="orchestrator",
                action="timeout",
                reasoning=f"Analysis exceeded {ANALYSIS_TIMEOUT_SECONDS}s timeout",
            )
        except Exception as e:
            logger.error("analysis_error", incident_id=incident_id, error=str(e))
            self._tracer.log_step(
                trace_id=trace_id,
                agent_name="orchestrator",
                action="error",
                reasoning=f"Analysis failed: {e}",
            )

        duration = time.perf_counter() - start_time
        report = self._build_report(
            incident_id, alert, trace_id, duration,
            triage_result, research_result, remediation_result,
        )

        logger.info(
            "analysis_complete",
            incident_id=incident_id,
            duration_seconds=report.duration_seconds,
            total_tokens=report.total_tokens,
            total_cost_usd=round(report.total_cost_usd, 4),
            requires_approval=report.requires_human_approval,
        )

        return report

    def _build_report(
        self,
        incident_id: str,
        alert: Alert,
        trace_id: str,
        duration: float,
        triage_result: dict[str, Any],
        research_result: dict[str, Any],
        remediation_result: dict[str, Any],
    ) -> IncidentReport:
        """Build an IncidentReport from pipeline results."""
        remediation_steps = [
            step.get("action", str(step))
            for step in remediation_result.get("remediation_steps", [])
        ]

        report = IncidentReport(
            incident_id=incident_id,
            alert=alert,
            summary=triage_result.get("summary", "Analysis incomplete"),
            root_cause=research_result.get("root_cause", "Could not determine root cause"),
            confidence_score=min(1.0, max(0.0, research_result.get("confidence", 0.0))),
            remediation_steps=remediation_steps,
            agent_trace=self._tracer.get_trace(trace_id),
            total_tokens=self._tracer.get_total_tokens(trace_id),
            total_cost_usd=self._tracer.get_total_cost(trace_id),
            duration_seconds=round(duration, 2),
            requires_human_approval=remediation_result.get("requires_human_approval", True),
        )

        # Record Prometheus metrics
        record_analysis_complete(report)

        # Record FinOps cost data per agent from the trace
        for step in report.agent_trace:
            if step.tokens_used > 0:
                _cost_tracker.record_analysis(
                    incident_id=incident_id,
                    agent_name=step.agent_name,
                    input_tokens=step.tokens_used // 2,  # approximate split
                    output_tokens=step.tokens_used - step.tokens_used // 2,
                )
            if step.tool_calls:
                _cost_tracker.record_tool_calls(incident_id, len(step.tool_calls))

        return report

    async def analyze_stream(self, alert: Alert) -> AsyncIterator[StreamEvent]:
        """Run the analysis pipeline, yielding SSE events as agents progress."""
        incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        trace_id = new_trace_id()
        start_time = time.perf_counter()

        event_queue: asyncio.Queue[StreamEvent] = asyncio.Queue()

        # Create a separate tracer with the event queue for streaming
        stream_tracer = DecisionTracer(event_queue=event_queue)
        stream_tracer.start_trace(trace_id)

        # Build streaming-aware agents sharing the same LLM and tools
        triage = TriageAgent(self._llm, self._tool_registry, stream_tracer)
        research = ResearchAgent(self._llm, self._tool_registry, stream_tracer)
        remediation = RemediationAgent(self._llm, self._tool_registry, stream_tracer)

        logger.info(
            "stream_analysis_started",
            incident_id=incident_id,
            trace_id=trace_id,
            service=alert.service,
        )

        triage_result: dict[str, Any] = {}
        research_result: dict[str, Any] = {}
        remediation_result: dict[str, Any] = {}
        pipeline_error: Exception | None = None

        async def _streaming_pipeline() -> None:
            nonlocal triage_result, research_result, remediation_result, pipeline_error
            try:
                # Triage
                event_queue.put_nowait(StreamEvent(
                    event_type="agent_start", agent_name="triage",
                ))
                triage_result = await triage.run(alert, trace_id)
                event_queue.put_nowait(StreamEvent(
                    event_type="agent_complete", agent_name="triage",
                    data={"tokens_used": stream_tracer.get_total_tokens(trace_id)},
                ))

                self._message_bus.send(
                    from_agent="triage", to_agent="research",
                    message_type="delegate", content=triage_result, trace_id=trace_id,
                )

                # Research
                event_queue.put_nowait(StreamEvent(
                    event_type="agent_start", agent_name="research",
                ))
                research_result = await research.run(triage_result, trace_id)
                event_queue.put_nowait(StreamEvent(
                    event_type="agent_complete", agent_name="research",
                    data={"tokens_used": stream_tracer.get_total_tokens(trace_id)},
                ))

                self._message_bus.send(
                    from_agent="research", to_agent="remediation",
                    message_type="delegate", content=research_result, trace_id=trace_id,
                )

                # Remediation
                event_queue.put_nowait(StreamEvent(
                    event_type="agent_start", agent_name="remediation",
                ))
                remediation_result = await remediation.run(research_result, trace_id)
                event_queue.put_nowait(StreamEvent(
                    event_type="agent_complete", agent_name="remediation",
                    data={"tokens_used": stream_tracer.get_total_tokens(trace_id)},
                ))

                self._message_bus.send(
                    from_agent="remediation", to_agent="orchestrator",
                    message_type=(
                        "respond"
                        if not remediation_result.get("requires_human_approval")
                        else "escalate"
                    ),
                    content=remediation_result, trace_id=trace_id,
                )
            except Exception as e:
                pipeline_error = e
                event_queue.put_nowait(StreamEvent(
                    event_type="error", data={"message": str(e)},
                ))
            finally:
                # Sentinel value to signal completion
                event_queue.put_nowait(StreamEvent(event_type="error", data={"_done": True}))

        task = asyncio.create_task(_streaming_pipeline())

        # Yield events as they arrive from the queue
        while True:
            event = await event_queue.get()
            if event.data.get("_done"):
                break
            yield event

        await task  # ensure task is fully done

        duration = time.perf_counter() - start_time

        if pipeline_error is not None:
            stream_tracer.log_step(
                trace_id=trace_id, agent_name="orchestrator",
                action="error", reasoning=f"Analysis failed: {pipeline_error}",
            )

        # Use the stream_tracer to build the report (it has all the steps)
        # Temporarily swap tracers to build report
        original_tracer = self._tracer
        self._tracer = stream_tracer
        report = self._build_report(
            incident_id, alert, trace_id, duration,
            triage_result, research_result, remediation_result,
        )
        self._tracer = original_tracer

        yield StreamEvent(
            event_type="analysis_complete",
            data={"report": report.model_dump(mode="json")},
        )
        # Stash the report on self so the caller can retrieve it
        self._last_stream_report = report

    async def _run_pipeline(
        self,
        alert: Alert,
        trace_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Run the three-agent pipeline sequentially."""
        # Step 1: Triage
        logger.info("pipeline_step", step="triage", trace_id=trace_id)
        triage_result = await self._triage.run(alert, trace_id)

        self._message_bus.send(
            from_agent="triage",
            to_agent="research",
            message_type="delegate",
            content=triage_result,
            trace_id=trace_id,
        )

        # Step 2: Research
        logger.info("pipeline_step", step="research", trace_id=trace_id)
        research_result = await self._research.run(triage_result, trace_id)

        self._message_bus.send(
            from_agent="research",
            to_agent="remediation",
            message_type="delegate",
            content=research_result,
            trace_id=trace_id,
        )

        # Step 3: Remediation
        logger.info("pipeline_step", step="remediation", trace_id=trace_id)
        remediation_result = await self._remediation.run(research_result, trace_id)

        self._message_bus.send(
            from_agent="remediation",
            to_agent="orchestrator",
            message_type=(
                "respond"
                if not remediation_result.get("requires_human_approval")
                else "escalate"
            ),
            content=remediation_result,
            trace_id=trace_id,
        )

        return triage_result, research_result, remediation_result
