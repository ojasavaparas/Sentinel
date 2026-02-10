"""Multi-agent orchestrator — coordinates triage, research, and remediation agents."""

# TODO: Implement SentinelOrchestrator class
# - Accept an Alert and run it through the agent pipeline
# - Triage → Research → Remediation
# - Track full agent trace (AgentStep list) across the pipeline
# - Return a complete IncidentReport
# - Use A2A protocol for inter-agent communication
# - Enforce human-in-the-loop for dangerous remediation actions
