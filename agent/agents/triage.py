"""Triage agent — classifies incoming alerts and assesses severity and blast radius."""

from __future__ import annotations

import json
from typing import Any

import structlog

from agent.agents import extract_json
from agent.llm_client import LLMClient, TokenUsage
from agent.models import Alert, ToolCall
from agent.prompts import TRIAGE_SYSTEM_PROMPT
from monitoring.tracer import DecisionTracer
from tools.registry import ToolRegistry

logger = structlog.get_logger()

# Triage agent only uses these tools for fast assessment
TRIAGE_TOOL_NAMES = {"get_metrics", "get_service_dependencies"}


class TriageAgent:
    """First responder — classifies alerts and delegates investigation."""

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        tracer: DecisionTracer,
    ) -> None:
        self._llm = llm_client
        self._tools = tool_registry
        self._tracer = tracer

    async def run(
        self,
        alert: Alert,
        trace_id: str,
    ) -> dict[str, Any]:
        """Run triage on an alert and return classification + delegation instructions."""
        # Filter tool schemas to only triage-relevant tools
        triage_schemas = [
            s for s in self._tools.get_schemas()
            if s["name"] in TRIAGE_TOOL_NAMES
        ]

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"ALERT RECEIVED:\n"
                    f"Service: {alert.service}\n"
                    f"Severity: {alert.severity}\n"
                    f"Description: {alert.description}\n"
                    f"Timestamp: {alert.timestamp.isoformat()}\n"
                    f"Metadata: {json.dumps(alert.metadata)}\n\n"
                    f"Perform initial triage. Check metrics and dependencies for {alert.service}, "
                    f"then provide your classification and delegation instructions."
                ),
            }
        ]

        total_usage = TokenUsage()
        all_tool_calls: list[ToolCall] = []
        max_iterations = 4

        for _ in range(max_iterations):
            response = await self._llm.chat(
                messages=[{"role": "system", "content": TRIAGE_SYSTEM_PROMPT}] + messages,
                tools=triage_schemas,
            )
            total_usage.input_tokens += response.usage.input_tokens
            total_usage.output_tokens += response.usage.output_tokens

            # If no tool calls, we have the final response
            if not response.tool_calls:
                break

            # Process tool calls
            tool_results_content: list[dict[str, Any]] = []
            for tc in response.tool_calls:
                tool_call = await self._tools.execute(tc["name"], tc["input"])
                all_tool_calls.append(tool_call)
                tool_results_content.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": json.dumps(tool_call.result, default=str),
                })

            # Add assistant message with tool use, then tool results
            assistant_blocks: list[dict[str, Any]] = []
            if response.content:
                assistant_blocks.append({"type": "text", "text": response.content})
            for tc in response.tool_calls:
                assistant_blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })

            messages.append({"role": "assistant", "content": assistant_blocks})
            messages.append({"role": "user", "content": tool_results_content})

        # Calculate cost (Claude Sonnet pricing: $3/MTok input, $15/MTok output)
        cost = (total_usage.input_tokens * 3.0 + total_usage.output_tokens * 15.0) / 1_000_000

        # Record LLM metrics for this agent run
        from monitoring.metrics import record_llm_call

        record_llm_call("triage", total_usage.input_tokens, total_usage.output_tokens, cost)

        # Log the triage step
        self._tracer.log_step(
            trace_id=trace_id,
            agent_name="triage",
            action="triage_classification",
            reasoning=response.content,
            tool_calls=all_tool_calls,
            tokens_used=total_usage.total_tokens,
            cost_usd=cost,
        )

        # Parse the JSON response
        result = extract_json(response.content)
        if result is None:
            result = {
                "classification": "unknown",
                "affected_services": [alert.service],
                "priority": "P1",
                "summary": response.content,
                "delegation_instructions": (
                    f"Investigate {alert.service} for {alert.description}"
                ),
            }

        logger.info(
            "triage_complete",
            classification=result.get("classification"),
            priority=result.get("priority"),
            affected_services=result.get("affected_services"),
        )

        return result
