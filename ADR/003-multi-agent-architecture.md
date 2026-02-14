# ADR-003: Multi-Agent Architecture

## Status
Accepted

## Context
Sentinel processes production alerts and produces incident reports with root cause analysis and remediation recommendations. The core design question was how to structure the AI reasoning: (1) a single monolithic agent that does everything in one prompt, (2) a multi-agent pipeline with specialized roles, or (3) a human-driven workflow where the LLM assists at each step.

A single agent would be simpler but would require a very long system prompt covering triage, investigation, and remediation — making it harder to debug, test, and improve individual capabilities. A human-driven workflow would be more accurate but defeats the goal of automated analysis.

## Decision
Use a three-agent sequential pipeline: Triage Agent → Research Agent → Remediation Agent. Each agent has a focused system prompt, a restricted tool set, and communicates via an A2A message bus.

## Reasoning
This architecture mirrors how human SRE teams actually respond to incidents: a first responder triages the alert, an investigator digs into logs and metrics, and a remediation lead proposes fixes. Each agent has a clear responsibility boundary:

- **Triage**: Fast classification using only metrics and dependency tools. Produces delegation instructions for Research.
- **Research**: Deep investigation using all tools (logs, metrics, deployments, runbooks). Builds an evidence-based timeline and root cause.
- **Remediation**: Proposes fixes grounded in research findings and runbook procedures. Flags high-risk actions for human approval.

Separation of concerns means each agent can be tested, debugged, and improved independently. A prompt change to improve remediation quality cannot regress triage accuracy. Token budgets are naturally bounded per agent rather than competing in a single context window.

## Trade-offs
- **Higher total token usage**: Three separate LLM calls (with system prompts each time) cost more tokens than a single call. Acceptable given the quality improvement from focused prompts.
- **Sequential latency**: The pipeline runs sequentially (~8-15 seconds total). A parallel architecture could be faster but would lose the benefit of each agent building on the previous one's output.
- **Inter-agent coupling**: Agents depend on the output schema of the previous agent. Changes to triage output format require updating the research agent's input parsing.

## Consequences
- The `IncidentAnalyzer` orchestrator is simple: call three agents in sequence, pass results forward, build the final report.
- Each agent's decision trace is logged separately, providing clear auditability of which agent made which conclusions.
- Adding a fourth agent (e.g., a "Verification Agent" that validates remediation steps) requires only adding a new class and updating the pipeline — no changes to existing agents.
- The A2A message bus records every inter-agent message for debugging and dashboard visualization.
