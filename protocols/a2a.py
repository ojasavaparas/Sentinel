"""Agent-to-agent communication — in-process message bus following A2A patterns."""

from __future__ import annotations

import uuid
from typing import Any, Literal

import structlog

from agent.models import AgentMessage

logger = structlog.get_logger()


class MessageBus:
    """In-process message bus for agent-to-agent communication."""

    def __init__(self) -> None:
        self._messages: list[AgentMessage] = []

    def send(
        self,
        from_agent: str,
        to_agent: str,
        message_type: Literal["delegate", "respond", "escalate"],
        content: dict[str, Any],
        trace_id: str,
    ) -> AgentMessage:
        """Send a message between agents."""
        msg = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            trace_id=trace_id,
        )
        self._messages.append(msg)

        logger.info(
            "a2a_message",
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            trace_id=trace_id,
        )

        return msg

    def get_messages(self, trace_id: str) -> list[AgentMessage]:
        """Get all messages for a given trace."""
        return [m for m in self._messages if m.trace_id == trace_id]

    def get_messages_for_agent(self, agent_name: str, trace_id: str) -> list[AgentMessage]:
        """Get all messages sent to a specific agent for a trace."""
        return [
            m for m in self._messages
            if m.to_agent == agent_name and m.trace_id == trace_id
        ]


def new_trace_id() -> str:
    """Generate a unique trace ID for correlating agent messages."""
    return f"trace-{uuid.uuid4().hex[:12]}"
