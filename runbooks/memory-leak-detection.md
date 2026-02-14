# Memory Leak Detection and Remediation

**Severity:** P2 initially, escalates to P1 if OOMKilled events occur
**Owner:** Platform Engineering
**Last Updated:** 2025-01-20

## Symptoms
- Steadily increasing memory usage over hours/days without corresponding traffic increase
- OOMKilled events in pod logs
- Gradual latency degradation followed by sudden pod restarts
- Sawtooth memory pattern in Grafana (grow, crash, restart, repeat)

## Investigation Steps

### 1. Confirm Memory Growth Pattern
```bash
kubectl top pods -n production -l app=<service-name> --sort-by=memory
```
Compare current usage against baseline. A healthy service should stabilize within 10 minutes of startup.

### 2. Check OOMKilled Events
```bash
kubectl get events -n production --field-selector reason=OOMKilling --sort-by=.lastTimestamp
```
Frequent OOMKills (more than 2 in 1 hour) confirm an active memory leak.

### 3. Capture Heap Dump (Java/JVM Services)
```bash
kubectl exec -n production <pod-name> -- jmap -dump:live,format=b,file=/tmp/heap.hprof 1
kubectl cp production/<pod-name>:/tmp/heap.hprof ./heap.hprof
```
Analyze with Eclipse MAT or VisualVM. Look for retained objects with unexpectedly high counts.

### 4. Check for Common Leak Sources
- Unbounded caches without TTL or max size
- Event listeners not being deregistered
- Connection objects (HTTP, DB) not properly closed in error paths
- Thread-local variables accumulating data

### 5. Immediate Mitigation
```bash
# Increase memory limits temporarily to buy investigation time
kubectl set resources deployment/<service-name> -n production --limits=memory=4Gi

# Set up automatic restart on memory threshold
kubectl set env deployment/<service-name> HEAP_LIMIT_RESTART=3584m -n production
```

### 6. Long-Term Fix
Identify the leaking code path from the heap dump analysis, fix, and deploy. Always include a memory regression test.

## Escalation
- If OOMKills affect user-facing traffic, escalate immediately to P1.
- If leak source cannot be identified within 2 hours, pull in the service owner.
