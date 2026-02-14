"""Remediation agent — proposes fixes based on research findings and runbooks."""

from __future__ import annotations

import json
from typing import Any

import structlog

from agent.llm_client import LLMClient, TokenUsage
from agent.models import ToolCall
from agent.prompts import REMEDIATION_SYSTEM_PROMPT
from monitoring.tracer import DecisionTracer
from tools.registry import ToolRegistry

logger = structlog.get_logger()


class RemediationAgent:
    """Proposes remediation — never executes, always requires human approval for risky actions."""

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
        research_result: dict[str, Any],
        trace_id: str,
    ) -> dict[str, Any]:
        """Propose remediation steps based on research findings."""
        # Remediation agent can search runbooks for additional procedures
        runbook_schemas = [
            s for s in self._tools.get_schemas()
            if s["name"] == "search_runbooks"
        ]

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"RESEARCH FINDINGS:\n\n"
                    f"Root Cause: {research_result.get('root_cause', 'Unknown')}\n"
                    f"Confidence: {research_result.get('confidence', 0.0)}\n\n"
                    f"Evidence:\n"
                    + "\n".join(f"- {e}" for e in research_result.get("evidence", []))
                    + f"\n\nTimeline:\n"
                    + "\n".join(
                        f"- {t.get('timestamp', '?')}: {t.get('event', '?')}"
                        for t in research_result.get("timeline", [])
                    )
                    + f"\n\nRelevant Runbooks: {', '.join(research_result.get('relevant_runbooks', []))}\n"
                    f"Affected Services: {', '.join(research_result.get('affected_services', []))}\n\n"
                    f"Based on these findings, propose specific remediation steps. "
                    f"You may search runbooks for additional procedures if needed."
                ),
            }
        ]

        total_usage = TokenUsage()
        all_tool_calls: list[ToolCall] = []
        max_iterations = 3

        for _ in range(max_iterations):
            response = await self._llm.chat(
                messages=[{"role": "system", "content": REMEDIATION_SYSTEM_PROMPT}] + messages,
                tools=runbook_schemas if runbook_schemas else None,
            )
            total_usage.input_tokens += response.usage.input_tokens
            total_usage.output_tokens += response.usage.output_tokens

            if not response.tool_calls:
                break

            # Process tool calls (only search_runbooks)
            tool_results_content: list[dict[str, Any]] = []
            for tc in response.tool_calls:
                tool_call = await self._tools.execute(tc["name"], tc["input"])
                all_tool_calls.append(tool_call)
                tool_results_content.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": json.dumps(tool_call.result, default=str),
                })

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

        # Calculate cost
        cost = (total_usage.input_tokens * 3.0 + total_usage.output_tokens * 15.0) / 1_000_000

        # Record LLM metrics for this agent run
        from monitoring.metrics import record_llm_call

        record_llm_call("remediation", total_usage.input_tokens, total_usage.output_tokens, cost)

        # Log the remediation step
        self._tracer.log_step(
            trace_id=trace_id,
            agent_name="remediation",
            action="remediation_proposal",
            reasoning=response.content,
            tool_calls=all_tool_calls,
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
                    "remediation_steps": [
                        {
                            "step": 1,
                            "action": "Manual investigation required",
                            "risk": "medium",
                            "requires_approval": True,
                            "rationale": response.content,
                        }
                    ],
                    "requires_human_approval": True,
                    "summary": response.content,
                }

        # Ensure human approval flag is set
        if "requires_human_approval" not in result:
            result["requires_human_approval"] = True

        logger.info(
            "remediation_complete",
            num_steps=len(result.get("remediation_steps", [])),
            requires_approval=result.get("requires_human_approval"),
        )

        return result
