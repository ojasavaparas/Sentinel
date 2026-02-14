"""Research agent — investigates incidents by calling tools and correlating findings."""

from __future__ import annotations

import json
from typing import Any

import structlog

from agent.llm_client import LLMClient, TokenUsage
from agent.models import ToolCall
from agent.prompts import RESEARCH_SYSTEM_PROMPT
from monitoring.tracer import DecisionTracer
from tools.registry import ToolRegistry

logger = structlog.get_logger()

MAX_TOOL_CALLS = 8


class ResearchAgent:
    """The detective — deep investigation with multiple tool calls."""

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
        triage_result: dict[str, Any],
        trace_id: str,
    ) -> dict[str, Any]:
        """Investigate the incident using all available tools."""
        all_schemas = self._tools.get_schemas()

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"INVESTIGATION REQUEST FROM TRIAGE AGENT:\n\n"
                    f"Classification: {triage_result.get('classification', 'unknown')}\n"
                    f"Priority: {triage_result.get('priority', 'P1')}\n"
                    f"Affected Services: {', '.join(triage_result.get('affected_services', []))}\n"
                    f"Triage Summary: {triage_result.get('summary', '')}\n\n"
                    f"DELEGATION INSTRUCTIONS:\n"
                    f"{triage_result.get('delegation_instructions', 'Investigate the incident thoroughly.')}\n\n"
                    f"Use your tools systematically to investigate. Check logs, metrics, "
                    f"deployments, and runbooks. Build a complete picture of what happened."
                ),
            }
        ]

        total_usage = TokenUsage()
        all_tool_calls: list[ToolCall] = []
        tool_call_count = 0

        # Tool-calling loop — max 8 tool calls
        while tool_call_count < MAX_TOOL_CALLS:
            response = await self._llm.chat(
                messages=[{"role": "system", "content": RESEARCH_SYSTEM_PROMPT}] + messages,
                tools=all_schemas,
            )
            total_usage.input_tokens += response.usage.input_tokens
            total_usage.output_tokens += response.usage.output_tokens

            # If no tool calls, we have the final analysis
            if not response.tool_calls:
                break

            # Process tool calls
            tool_results_content: list[dict[str, Any]] = []
            for tc in response.tool_calls:
                tool_call = await self._tools.execute(tc["name"], tc["input"])
                all_tool_calls.append(tool_call)
                tool_call_count += 1
                tool_results_content.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": json.dumps(tool_call.result, default=str),
                })

                # Log each tool call as a step
                self._tracer.log_step(
                    trace_id=trace_id,
                    agent_name="research",
                    action=f"tool_call:{tc['name']}",
                    reasoning=f"Called {tc['name']} with {json.dumps(tc['input'])}",
                    tool_calls=[tool_call],
                    tokens_used=0,
                    cost_usd=0.0,
                )

            # Build assistant message with tool use blocks
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

            # If we've hit the limit, ask for final analysis
            if tool_call_count >= MAX_TOOL_CALLS:
                messages.append({
                    "role": "user",
                    "content": (
                        "You have reached the maximum number of tool calls. "
                        "Based on all the data you have gathered, provide your final analysis now."
                    ),
                })
                response = await self._llm.chat(
                    messages=[{"role": "system", "content": RESEARCH_SYSTEM_PROMPT}] + messages,
                )
                total_usage.input_tokens += response.usage.input_tokens
                total_usage.output_tokens += response.usage.output_tokens
                break

        # Calculate cost
        cost = (total_usage.input_tokens * 3.0 + total_usage.output_tokens * 15.0) / 1_000_000

        # Log the final research step
        self._tracer.log_step(
            trace_id=trace_id,
            agent_name="research",
            action="research_findings",
            reasoning=response.content,
            tool_calls=[],
            tokens_used=total_usage.total_tokens,
            cost_usd=cost,
        )

        # Parse the JSON response
        try:
            result = json.loads(response.content)
        except json.JSONDecodeError:
            content = response.content
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(content[start:end])
            else:
                result = {
                    "timeline": [],
                    "root_cause": response.content,
                    "confidence": 0.5,
                    "evidence": [],
                    "relevant_runbooks": [],
                    "affected_services": triage_result.get("affected_services", []),
                }

        logger.info(
            "research_complete",
            root_cause=result.get("root_cause", "")[:100],
            confidence=result.get("confidence"),
            tool_calls_made=tool_call_count,
        )

        return result
