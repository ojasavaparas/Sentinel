"""Service dependency graph — maps services to their upstream/downstream dependencies."""

# TODO: Implement get_dependencies(service) -> dependency info
# - Define a static service dependency graph (e.g. payment-api -> database, cache, order-service)
# - Return upstream dependencies (what this service depends on)
# - Return downstream dependents (what depends on this service)
# - Used by triage agent to assess blast radius
