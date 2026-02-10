# ADR-004: MCP and A2A Protocols

## Status
Accepted

## Context
We need: (1) a way for external AI tools to use Sentinel as a tool, and (2) a way for our internal agents to communicate with each other.

## Decision
- Use MCP (Model Context Protocol) to expose Sentinel's capabilities externally
- Use a custom A2A (Agent-to-Agent) message protocol for internal communication

## Rationale
- MCP is an emerging standard for AI tool interoperability — adopting it early enables integration with Claude Desktop, other MCP clients
- A2A keeps inter-agent messaging simple, typed, and traceable
- Both protocols use our Pydantic models for type safety

## Consequences
- MCP server adds an additional interface to maintain
- A2A protocol is custom — may need to evolve as standards emerge
- Both are optional layers; the core pipeline works without them
