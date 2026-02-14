"""Tests for simulated tools and the tool registry."""

from __future__ import annotations

import pytest

from tools.dependencies import get_service_dependencies
from tools.deployments import get_recent_deployments
from tools.log_search import search_logs
from tools.metrics import get_metrics
from tools.registry import ToolRegistry


# --- Log Search Tests ---


@pytest.mark.asyncio
async def test_search_logs_filters_by_service():
    results = await search_logs(service="payment-api")
    assert len(results) > 0
    assert all(log["service"] == "payment-api" for log in results)


@pytest.mark.asyncio
async def test_search_logs_filters_by_severity():
    results = await search_logs(service="payment-api", severity="ERROR")
    assert len(results) > 0
    assert all(log["level"] == "ERROR" for log in results)


@pytest.mark.asyncio
async def test_search_logs_filters_by_time_range():
    results = await search_logs(
        service="payment-api",
        time_start="2024-01-15T14:25:00Z",
        time_end="2024-01-15T14:35:00Z",
    )
    assert len(results) > 0
    for log in results:
        assert log["timestamp"] >= "2024-01-15T14:25:00Z"
        assert log["timestamp"] <= "2024-01-15T14:35:00Z"


@pytest.mark.asyncio
async def test_search_logs_filters_by_query():
    results = await search_logs(service="payment-api", query="connection timeout")
    assert len(results) > 0
    assert all("connection timeout" in log["message"].lower() for log in results)


@pytest.mark.asyncio
async def test_search_logs_sorted_by_timestamp():
    results = await search_logs(service="payment-api")
    timestamps = [log["timestamp"] for log in results]
    assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_search_logs_no_results_for_unknown_service():
    results = await search_logs(service="nonexistent-service")
    assert results == []


# --- Metrics Tests ---


@pytest.mark.asyncio
async def test_get_metrics_returns_data_for_service():
    results = await get_metrics(service="payment-api")
    assert len(results) > 0
    assert all(m["service"] == "payment-api" for m in results)


@pytest.mark.asyncio
async def test_get_metrics_filters_by_metric_name():
    results = await get_metrics(service="payment-api", metric_name="latency_p99")
    assert len(results) > 0
    assert all(m["metric_name"] == "latency_p99" for m in results)


@pytest.mark.asyncio
async def test_get_metrics_shows_latency_spike():
    results = await get_metrics(service="payment-api", metric_name="latency_p99")
    values = [m["value"] for m in results]
    # Should show normal baseline then spike
    assert min(values) < 200  # normal
    assert max(values) > 2000  # spike


@pytest.mark.asyncio
async def test_get_metrics_user_service_healthy():
    results = await get_metrics(service="user-service", metric_name="error_rate")
    assert len(results) > 0
    assert all(m["value"] < 1.0 for m in results)


# --- Deployments Tests ---


@pytest.mark.asyncio
async def test_get_deployments_returns_sorted_by_recency():
    results = await get_recent_deployments()
    assert len(results) > 0
    timestamps = [d["timestamp"] for d in results]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_get_deployments_filters_by_service():
    results = await get_recent_deployments(service="payment-api")
    assert len(results) > 0
    assert all(d["service"] == "payment-api" for d in results)


@pytest.mark.asyncio
async def test_get_deployments_respects_limit():
    results = await get_recent_deployments(limit=2)
    assert len(results) <= 2


@pytest.mark.asyncio
async def test_get_deployments_includes_suspect_deploy():
    results = await get_recent_deployments(service="payment-api")
    commits = [d["commit_hash"] for d in results]
    assert "a1bf3d2" in commits
    suspect = next(d for d in results if d["commit_hash"] == "a1bf3d2")
    assert "connection pool" in suspect["commit_message"].lower()


# --- Dependencies Tests ---


@pytest.mark.asyncio
async def test_get_dependencies_returns_correct_graph():
    result = await get_service_dependencies("payment-api")
    assert result["service"] == "payment-api"
    assert result["total_dependencies"] == 3
    dep_names = [d["name"] for d in result["dependencies"]]
    assert "postgres-primary" in dep_names
    assert "redis-cache" in dep_names
    assert "stripe-api" in dep_names


@pytest.mark.asyncio
async def test_get_dependencies_shows_degraded():
    result = await get_service_dependencies("payment-api")
    assert "postgres-primary" in result["degraded_dependencies"]


@pytest.mark.asyncio
async def test_get_dependencies_unknown_service():
    result = await get_service_dependencies("nonexistent-service")
    assert result["total_dependencies"] == 0
    assert "error" in result


# --- Tool Registry Tests ---


@pytest.mark.asyncio
async def test_registry_executes_and_returns_tool_call():
    registry = ToolRegistry()
    tool_call = await registry.execute(
        "search_logs",
        {"service": "payment-api", "severity": "ERROR"},
    )
    assert tool_call.tool_name == "search_logs"
    assert tool_call.latency_ms >= 0
    assert isinstance(tool_call.result, list)
    assert len(tool_call.result) > 0


@pytest.mark.asyncio
async def test_registry_returns_error_for_unknown_tool():
    registry = ToolRegistry()
    tool_call = await registry.execute("nonexistent_tool", {})
    assert "error" in tool_call.result


@pytest.mark.asyncio
async def test_registry_get_schemas():
    registry = ToolRegistry()
    schemas = registry.get_schemas()
    tool_names = [s["name"] for s in schemas]
    assert "search_logs" in tool_names
    assert "get_metrics" in tool_names
    assert "get_recent_deployments" in tool_names
    assert "get_service_dependencies" in tool_names
    assert "search_runbooks" in tool_names
