# ADR-001: Raw Anthropic API over LangChain

## Status
Accepted

## Context
We need to integrate an LLM for agent reasoning. Options include using the raw Anthropic SDK or a framework like LangChain.

## Decision
Use the Anthropic Python SDK directly instead of LangChain.

## Rationale
- Full control over prompt construction and tool-use flow
- No framework abstractions hiding token usage or API behavior
- Easier to debug and trace exactly what the LLM sees and returns
- Smaller dependency footprint
- LangChain adds complexity without proportional value for our use case

## Consequences
- We own the orchestration logic (tool routing, message formatting)
- More code to write upfront, but more transparent and maintainable
