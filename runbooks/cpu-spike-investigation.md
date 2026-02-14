# CPU Spike Investigation Playbook

**Severity:** P2 if sustained > 80% for 10 minutes, P1 if causing request failures
**Owner:** Platform Engineering
**Last Updated:** 2025-01-22

## Symptoms
- CPU utilization exceeding 80% sustained across multiple pods
- Request latency increasing due to CPU throttling
- Horizontal Pod Autoscaler (HPA) scaling to maximum replicas
- Thread pool exhaustion warnings in application logs

## Investigation Steps

### 1. Identify Affected Pods
```bash
kubectl top pods -n production -l app=<service-name> --sort-by=cpu
```
Determine if the spike is across all pods (systemic) or a single pod (localized issue like an infinite loop).

### 2. Check if Traffic-Correlated
```bash
curl -s http://localhost:9090/api/v1/query?query=rate(http_requests_total{service="<service-name>"}[5m])
```
If traffic increased proportionally with CPU, the service may need horizontal scaling. If CPU spiked without traffic increase, the cause is internal.

### 3. Profile the Application
For JVM services:
```bash
kubectl exec -n production <pod-name> -- jstack 1 > /tmp/thread_dump.txt
kubectl exec -n production <pod-name> -- jstack 1 > /tmp/thread_dump_2.txt  # 10 seconds later
```
Compare the two dumps. Threads in the same position indicate a hot loop or blocked thread.

For Python services:
```bash
kubectl exec -n production <pod-name> -- py-spy dump --pid 1
```

### 4. Check for Runaway Processes
```bash
kubectl exec -n production <pod-name> -- ps aux --sort=-%cpu | head -10
```
Look for unexpected processes consuming CPU (cron jobs, background workers, zombie processes).

### 5. Review Recent Code Changes
Check if new regex patterns, serialization logic, or algorithmic changes were deployed. Inefficient regex is a common cause of CPU spikes (ReDoS patterns).

### 6. Immediate Mitigation
```bash
# Scale horizontally to distribute load
kubectl scale deployment/<service-name> -n production --replicas=<N>

# If a single pod is stuck, delete it
kubectl delete pod <pod-name> -n production
```

## Escalation
- If CPU spike is caused by a code defect, notify the service owner for an emergency fix.
- If HPA is at max replicas and latency is still degraded, escalate to Platform Engineering to increase node pool capacity.
