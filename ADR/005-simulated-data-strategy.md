# ADR-005: Simulated Data Strategy

## Status
Accepted

## Context
Sentinel's agents investigate incidents by calling tools that query logs, metrics, deployment history, and service dependencies. In a production environment, these tools would connect to real observability platforms (CloudWatch, Datadog, PagerDuty, Kubernetes API). For development, testing, and demos, we need realistic data that exercises the full agent pipeline without requiring access to production infrastructure or paid observability services.

The options were: (1) mock the LLM to return pre-scripted responses (fast but doesn't test real reasoning), (2) use a sandbox observability stack with synthetic traffic generators, or (3) use static data files that simulated tools return deterministically.

## Decision
Use static JSON files in `simulation/data/` containing pre-authored log entries, metric time-series, deployment records, and dependency graphs. Implement simulated tool functions that load and filter this data, matching the exact function signatures and return types that production implementations would use.

## Reasoning
Static simulation data provides the best balance of realism and reproducibility. Each incident scenario is a curated set of data files that tell a coherent story — the logs show errors starting after a deployment, the metrics show a latency spike correlated with connection pool exhaustion, and the dependency graph shows downstream impact. Agents see realistic data and must do genuine reasoning to connect the dots.

Because the data is deterministic, the same alert input always produces the same tool outputs, making the system fully reproducible for testing and demos. Adding a new incident scenario means creating a new set of JSON files — no code changes required.

The tool interface boundary is the key architectural constraint: `search_logs`, `get_metrics`, `get_recent_deployments`, `get_service_dependencies`, and `search_runbooks` all have stable function signatures and return types. Production implementations would swap the data source (e.g., query CloudWatch instead of reading a JSON file) without changing the interface.

## Trade-offs
- **Not dynamic**: Simulated data is frozen in time. Agents cannot discover truly novel patterns or handle scenarios not pre-authored in the data files.
- **Maintenance overhead**: Each new incident scenario requires crafting realistic, internally consistent data across multiple files (logs, metrics, deploys, dependencies).
- **No load testing**: Static data cannot simulate realistic latency, rate limiting, or partial failures from real observability APIs.

## Consequences
- Development and testing require zero external infrastructure — just `make demo` to run a full analysis.
- The test suite (84 tests) uses `MockClient` for LLM responses and simulated tools for data, achieving full coverage without API calls or network access.
- Demo scenarios are reproducible and can be version-controlled alongside the codebase.
- Swapping to production tool implementations requires only replacing the async functions in `tools/` — the `ToolRegistry` interface, agent prompts, and orchestration logic remain unchanged.
