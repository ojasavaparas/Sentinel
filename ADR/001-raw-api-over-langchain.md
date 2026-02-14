# ADR-001: Raw Anthropic API over LangChain

## Status
Accepted

## Context
Sentinel requires an LLM to power its agent reasoning — classifying incidents, calling tools, correlating findings, and proposing remediations. The two main integration approaches were: (1) use a framework like LangChain/LlamaIndex that provides agent abstractions, tool routing, and memory management out of the box, or (2) use the Anthropic Python SDK directly and build the orchestration layer ourselves.

LangChain is the most popular LLM framework and offers pre-built agent types, tool schemas, and output parsers. However, it introduces a significant abstraction layer between our code and the actual API calls, making it harder to understand token consumption, debug prompt issues, and control the exact message format sent to the model.

## Decision
Use the Anthropic Python SDK (`anthropic`) directly. Build custom orchestration logic for tool routing, message formatting, and multi-turn conversations within each agent.

## Reasoning
Claude's native tool-use API provides structured tool calls and results as first-class message types — there is no need for a framework to wrap this. By owning the orchestration code, we can: construct prompts exactly as needed for each agent role, track token usage at every API call boundary, and debug by inspecting the raw messages the model sees and returns. The dependency footprint stays small (one SDK), and we avoid framework-specific patterns that would complicate onboarding or future model swaps.

LangChain's abstractions (AgentExecutor, output parsers, callback handlers) add indirection that obscures what the LLM actually receives. For a system that needs precise auditability — every agent decision must be traceable — this opacity is a liability rather than a convenience.

## Trade-offs
- **More upfront code**: We write our own tool-calling loop, message assembly, and JSON parsing. LangChain provides this for free.
- **No built-in memory**: Conversation history management is manual. Acceptable since our agents are stateless per-analysis.
- **Framework ecosystem**: We forgo LangChain's integrations (vector stores, document loaders). We use ChromaDB and sentence-transformers directly instead.

## Consequences
- We own ~200 lines of orchestration logic across three agent files and the core orchestrator.
- Token tracking and cost calculation are precise because we control every API call.
- Swapping models (e.g., to GPT-4 or Gemini) requires only changing the `LLMClient` implementation, not unwinding a framework.
- New developers must read our agent code rather than LangChain docs, but the code is simpler and more transparent.
