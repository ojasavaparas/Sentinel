# ADR-005: Simulated Data Strategy

## Status
Accepted

## Context
We need log, metric, and deployment data for the agent to investigate. In production this would come from real observability tools (CloudWatch, Datadog, PagerDuty). For development and demos, we need realistic simulated data.

## Decision
Use static JSON files in simulation/data/ and simulated tool implementations that return this data.

## Rationale
- Enables development and testing without access to production infrastructure
- Reproducible scenarios — same input always produces same investigation
- Easy to add new incident scenarios by creating new data files
- Tool interface is identical to what production implementations would use

## Consequences
- Simulated tools must be swapped for real integrations in production
- Tool interface (function signatures, return types) must be stable
- Demo scenarios are limited to pre-created data sets
