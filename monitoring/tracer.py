"""Decision trace logger — records every agent decision for auditability."""

# TODO: Implement DecisionTracer
# - Log each AgentStep with structured logging (structlog)
# - Record: agent name, action taken, reasoning, tools called, tokens used, cost
# - Support exporting trace as JSON for dashboard consumption
# - Correlate all steps by incident_id / trace_id
