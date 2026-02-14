# High Latency Troubleshooting

**Severity:** P1 if P99 > 5x baseline, P2 if P99 > 2x baseline
**Owner:** Platform Engineering
**Last Updated:** 2025-01-15

## Symptoms
- P99 latency exceeding normal baseline (typically 150-250ms for API services)
- Increased error rates (HTTP 504 Gateway Timeout)
- Upstream services reporting degraded performance

## Investigation Steps

### 1. Check Recent Deployments
```bash
kubectl rollout history deployment/<service-name> -n production
```
If a deployment occurred within the last 60 minutes, it is the most likely cause. Proceed to the rollback procedure if correlation is strong.

### 2. Verify Database Connection Pool Utilization
```bash
curl -s http://localhost:9090/api/v1/query?query=db_pool_active_connections/db_pool_max_connections
```
If pool utilization exceeds 85%, the pool is near saturation. Check for long-running queries or connection leaks.

### 3. Check Downstream Dependency Health
Query the service dependency map and verify each downstream service is healthy:
```bash
curl -s http://service-mesh.internal/api/v1/dependencies/<service-name>/health
```
A degraded downstream service will cause latency to propagate upstream.

### 4. Review CPU and Memory Metrics
```bash
kubectl top pods -n production -l app=<service-name>
```
CPU > 80% sustained or memory > 90% can cause garbage collection pauses and request queuing.

### 5. Check for Lock Contention
Review database slow query logs for queries exceeding 500ms. Look for table-level locks or row-level deadlocks in `pg_stat_activity`.

### 6. Consider Rollback
If investigation points to a recent deployment, execute the rollback procedure (see: deployment-rollback-procedure.md). Requires on-call lead approval.

## Escalation
- If unresolved after 15 minutes, escalate to the service owner.
- If affecting revenue-critical path, page the VP of Engineering.
