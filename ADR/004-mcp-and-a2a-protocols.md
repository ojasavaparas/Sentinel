# ADR-004: MCP and A2A Protocols

## Status
Accepted

## Context
Sentinel has two distinct communication needs: (1) external interoperability — allowing AI tools like Claude Desktop to use Sentinel as a tool provider, and (2) internal agent messaging — a structured way for the triage, research, and remediation agents to pass results to each other with full traceability.

For external interop, the emerging standard is the Model Context Protocol (MCP), which defines how AI clients discover and invoke tools exposed by servers. For internal messaging, options included direct function calls, a shared state dict, or a typed message-passing protocol.

## Decision
- Use **MCP** (Model Context Protocol) to expose Sentinel's capabilities as tools and resources for external AI clients.
- Use a custom **A2A** (Agent-to-Agent) message protocol for internal pipeline communication, built on Pydantic models.

## Reasoning
MCP is an open standard gaining adoption across AI tooling (Claude Desktop, Cursor, Windsurf). By implementing an MCP server, Sentinel becomes usable from any MCP-compatible client without custom integration work. The MCP server exposes three tools (`analyze_incident`, `search_runbooks`, `get_service_health`) and two resources (`runbook://{filename}`, `runbook://index`), making the full system accessible to external AI agents.

For internal communication, a typed message bus provides better traceability than passing dicts between function calls. Each `AgentMessage` records the sender, receiver, message type (delegate/respond/escalate), content payload, and trace ID. This makes the inter-agent flow visible in the dashboard and debuggable in logs — you can see exactly what the triage agent told the research agent to investigate.

Using Pydantic models for both protocols ensures type safety and serialization consistency across the system.

## Trade-offs
- **MCP maintenance burden**: The MCP server is an additional interface that must stay in sync with the core API. Changes to the analysis pipeline must be reflected in both the REST API and MCP tools.
- **A2A is custom**: Our agent-to-agent protocol is not based on an external standard. If a widely-adopted A2A standard emerges, we may need to migrate.
- **MCP adds a dependency**: The `mcp` Python package must be installed. This is a lightweight dependency but adds to the surface area.

## Consequences
- Claude Desktop users can analyze incidents by simply calling the `analyze_incident` tool in conversation.
- The A2A message bus provides a complete audit trail of inter-agent communication per trace ID.
- Both protocols are optional layers — the core pipeline works without the MCP server, and the A2A bus could be replaced with direct function calls without changing agent logic.
- The MCP server runs as a separate process (`python -m protocols.mcp_server`) and can be started independently of the REST API.
