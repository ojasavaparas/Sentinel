"""Tool definitions and router — maps tool names to implementations."""

from __future__ import annotations

import time
from typing import Any

import structlog

from agent.models import ToolCall
from rag.engine import RAGEngine
from tools.dependencies import get_service_dependencies
from tools.deployments import get_recent_deployments
from tools.log_search import search_logs
from tools.metrics import get_metrics

logger = structlog.get_logger()

# Tool schemas for LLM tool-use (Claude API format)
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_logs",
        "description": (
            "Search application logs for a specific service. Use this to find error messages, "
            "warnings, and trace the timeline of an incident. You can filter by severity level, "
            "time range, and keyword. Always start by searching "
            "for ERROR logs to identify failures."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": (
                        "The service name to search logs for "
                        "(e.g. 'payment-api', 'order-service')"
                    ),
                },
                "severity": {
                    "type": "string",
                    "enum": ["INFO", "WARN", "ERROR"],
                    "description": (
                        "Filter by log level. Use ERROR to find "
                        "failures, WARN for degradation signals."
                    ),
                },
                "time_start": {
                    "type": "string",
                    "description": (
                        "ISO 8601 timestamp for the start of the "
                        "search window (e.g. '2024-01-15T14:00:00Z')"
                    ),
                },
                "time_end": {
                    "type": "string",
                    "description": "ISO 8601 timestamp for the end of the search window",
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Substring to search for in log messages "
                        "(e.g. 'timeout', 'connection pool')"
                    ),
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "get_metrics",
        "description": (
            "Retrieve time-series metrics for a service. Use this to check CPU usage, memory, "
            "latency (P99), error rates, database connection pool utilization, and request rates. "
            "Compare values across time to identify when degradation started."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "The service name to get metrics for",
                },
                "metric_name": {
                    "type": "string",
                    "enum": [
                        "latency_p99", "cpu_usage", "error_rate",
                        "db_connection_pool", "memory_usage",
                        "request_rate",
                    ],
                    "description": (
                        "Specific metric to retrieve. If omitted, "
                        "returns all metrics for the service."
                    ),
                },
                "time_start": {
                    "type": "string",
                    "description": "ISO 8601 timestamp for the start of the time range",
                },
                "time_end": {
                    "type": "string",
                    "description": "ISO 8601 timestamp for the end of the time range",
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "get_recent_deployments",
        "description": (
            "Get recent deployment history for a service or all services. Use this to check if a "
            "recent deployment correlates with the start of an incident. Look for deployments that "
            "occurred within 60 minutes before the incident started."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": (
                        "Service name to filter deployments for. "
                        "Omit to see all recent deployments."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of deployments to return (default: 5)",
                    "default": 5,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_service_dependencies",
        "description": (
            "Get the dependency graph for a service — what databases, caches, external APIs, "
            "and internal services it depends on, along with their current health status. "
            "Use this to assess blast radius and identify if a "
            "downstream dependency is causing issues."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "The service name to get the dependency tree for",
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "search_runbooks",
        "description": (
            "Search operational runbooks for troubleshooting procedures, remediation steps, "
            "and best practices. Returns relevant runbook chunks with similarity scores "
            "indicating confidence. Use this to find the recommended remediation procedure "
            "after identifying the root cause."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query describing the issue "
                        "or topic to find runbooks for"
                    ),
                },
            },
            "required": ["query"],
        },
    },
]


class ToolRegistry:
    """Routes tool calls to their implementations and tracks execution."""

    def __init__(self, rag_engine: RAGEngine | None = None) -> None:
        self._rag_engine = rag_engine

    def get_schemas(self) -> list[dict[str, Any]]:
        """Return all tool schemas for LLM tool-use."""
        return TOOL_SCHEMAS

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolCall:
        """Execute a tool by name and return a ToolCall record with timing."""
        start = time.perf_counter()

        handler = self._handlers.get(tool_name)
        if handler:
            result = await handler(self, arguments)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        latency_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "tool_call",
            tool=tool_name,
            arguments=arguments,
            latency_ms=round(latency_ms, 2),
        )

        # Record Prometheus metrics for this tool call
        from monitoring.metrics import record_tool_call

        record_tool_call(tool_name, latency_ms / 1000)

        # For runbook searches, record RAG retrieval scores
        if tool_name == "search_runbooks" and isinstance(result, dict):
            rag_results = result.get("results", [])
            scores = [r["similarity_score"] for r in rag_results if "similarity_score" in r]
            if scores:
                from monitoring.metrics import record_rag_query

                record_rag_query(scores)

        return ToolCall(
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            latency_ms=round(latency_ms, 2),
            cost_usd=0.0,
        )

    async def _handle_search_logs(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        return await search_logs(
            service=arguments["service"],
            severity=arguments.get("severity"),
            time_start=arguments.get("time_start"),
            time_end=arguments.get("time_end"),
            query=arguments.get("query"),
        )

    async def _handle_get_metrics(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        return await get_metrics(
            service=arguments["service"],
            metric_name=arguments.get("metric_name"),
            time_start=arguments.get("time_start"),
            time_end=arguments.get("time_end"),
        )

    async def _handle_get_deployments(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        return await get_recent_deployments(
            service=arguments.get("service"),
            limit=arguments.get("limit", 5),
        )

    async def _handle_get_dependencies(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return await get_service_dependencies(
            service=arguments["service"],
        )

    async def _handle_search_runbooks(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._rag_engine is None:
            return {"error": "RAG engine not initialized"}

        query = arguments.get("query", "")
        results = await self._rag_engine.search(query)

        return {
            "results": [
                {
                    "content": r.content,
                    "source_file": r.source_file,
                    "title": r.title,
                    "similarity_score": r.similarity_score,
                    "confidence": r.confidence,
                }
                for r in results
            ],
            "num_results": len(results),
        }

    _handlers = {
        "search_logs": _handle_search_logs,
        "get_metrics": _handle_get_metrics,
        "get_recent_deployments": _handle_get_deployments,
        "get_service_dependencies": _handle_get_dependencies,
        "search_runbooks": _handle_search_runbooks,
    }
