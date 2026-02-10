# ADR-003: Multi-Agent Architecture

## Status
Accepted

## Context
We need to design the system that processes alerts and produces incident reports. Options: single monolithic agent, multi-agent pipeline, or a human-driven workflow.

## Decision
Use a three-agent pipeline: Triage → Research → Remediation.

## Rationale
- Separation of concerns: each agent has a focused role and prompt
- Easier to test, debug, and improve each agent independently
- Mirrors how human SRE teams work (triage, investigate, fix)
- Agent trace provides clear auditability of each phase
- Allows parallel improvements (e.g., improve research without touching triage)

## Consequences
- Inter-agent communication adds complexity (solved by A2A protocol)
- Higher total token usage than a single agent (acceptable trade-off for quality)
- Each agent can be swapped, upgraded, or specialized independently
