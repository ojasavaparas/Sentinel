# Database Connection Pool Exhaustion

**Severity:** P1 — causes cascading failures across dependent services
**Owner:** Database Reliability Team
**Last Updated:** 2025-02-01

## Symptoms
- Connection pool utilization > 90%
- Spike in database timeout errors (SQLSTATE 08006)
- New connections being refused or queuing indefinitely
- Service latency increases proportional to pool saturation

## Investigation Steps

### 1. Check Pool Utilization Metrics
```bash
curl -s http://localhost:9090/api/v1/query?query=hikari_connections_active/hikari_connections_max
```
Normal utilization should be 30-60%. Anything above 85% indicates exhaustion risk.

### 2. Identify Long-Running Queries
```sql
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE (now() - pg_stat_activity.query_start) > interval '30 seconds'
ORDER BY duration DESC;
```
Kill any queries running longer than 5 minutes that are not known batch jobs.

### 3. Verify Connection Timeout Settings
Check the application configuration for connection pool settings:
- `maximumPoolSize`: should be 20-50 per pod depending on service
- `connectionTimeout`: should be 10000ms (10 seconds)
- `idleTimeout`: should be 300000ms (5 minutes)
- `maxLifetime`: should be 1800000ms (30 minutes)

### 4. Check for Connection Leaks
Look for connections in `idle` state that have been open for more than `maxLifetime`. This indicates the application is not properly closing connections.

### 5. Immediate Remediation
```bash
# Scale pool size temporarily
kubectl set env deployment/<service-name> POOL_MAX_SIZE=80 -n production

# Or restart affected pods to release leaked connections
kubectl rollout restart deployment/<service-name> -n production
```

### 6. Review Recent Config Changes
Check if pool settings, timeout values, or database connection strings were modified in the last 24 hours. Configuration drift is the most common root cause.

## Escalation
- If pool exhaustion persists after remediation, escalate to the DBA on-call.
- If multiple services are affected, declare a SEV-1 incident.
