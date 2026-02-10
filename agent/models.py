"""Pydantic models for the Sentinel incident analysis system."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Alert(BaseModel):
    """Incoming alert from a monitoring system."""

    service: str
    description: str
    severity: Literal["critical", "high", "medium", "low"]
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """Record of a single tool invocation by an agent."""

    tool_name: str
    arguments: dict[str, Any]
    result: Any
    latency_ms: float
    cost_usd: float


class AgentStep(BaseModel):
    """A single reasoning + action step taken by an agent."""

    agent_name: str
    action: str
    reasoning: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tokens_used: int
    cost_usd: float
    timestamp: datetime


class IncidentReport(BaseModel):
    """Complete report produced after investigating an incident."""

    incident_id: str
    alert: Alert
    summary: str
    root_cause: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    remediation_steps: list[str]
    agent_trace: list[AgentStep] = Field(default_factory=list)
    total_tokens: int
    total_cost_usd: float
    duration_seconds: float
    requires_human_approval: bool


class AgentMessage(BaseModel):
    """Message passed between agents via the A2A protocol."""

    from_agent: str
    to_agent: str
    message_type: Literal["delegate", "respond", "escalate"]
    content: dict[str, Any]
    trace_id: str
