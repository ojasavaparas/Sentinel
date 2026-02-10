"""LLM abstraction layer with Anthropic and mock implementations."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import anthropic
import structlog

logger = structlog.get_logger()


@dataclass
class TokenUsage:
    """Token counts from an LLM response."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class Response:
    """Standardized LLM response."""

    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    stop_reason: str = ""


@runtime_checkable
class LLMClient(Protocol):
    """Protocol defining the interface for LLM clients."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Response: ...


class AnthropicClient:
    """LLM client backed by the Anthropic Claude API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ["ANTHROPIC_API_KEY"]
        self._model = model or os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")
        self._client = anthropic.AsyncAnthropic(api_key=self._api_key)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Response:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        api_response = await self._client.messages.create(**kwargs)

        content_text = ""
        tool_calls: list[dict[str, Any]] = []
        for block in api_response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

        usage = TokenUsage(
            input_tokens=api_response.usage.input_tokens,
            output_tokens=api_response.usage.output_tokens,
        )

        logger.info(
            "anthropic_api_call",
            model=self._model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )

        return Response(
            content=content_text,
            tool_calls=tool_calls,
            usage=usage,
            model=self._model,
            stop_reason=api_response.stop_reason or "",
        )


class MockClient:
    """Mock LLM client that returns pre-scripted responses for testing."""

    def __init__(self, responses: list[Response] | None = None) -> None:
        self._responses: list[Response] = responses or []
        self._call_index: int = 0
        self.call_history: list[dict[str, Any]] = []

    def add_response(self, response: Response) -> None:
        self._responses.append(response)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Response:
        self.call_history.append({"messages": messages, "tools": tools})

        if self._call_index < len(self._responses):
            response = self._responses[self._call_index]
            self._call_index += 1
            return response

        return Response(
            content="Mock response (no scripted response available)",
            usage=TokenUsage(input_tokens=10, output_tokens=10),
            model="mock",
            stop_reason="end_turn",
        )


def create_client(provider: str | None = None) -> LLMClient:
    """Factory function to create the appropriate LLM client based on config."""
    provider = provider or os.environ.get("LLM_PROVIDER", "anthropic")

    if provider == "anthropic":
        return AnthropicClient()
    elif provider == "mock":
        return MockClient()
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
