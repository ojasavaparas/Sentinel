# Emergency Deployment Rollback

**Severity:** Procedure — used during P1/P2 incidents when deployment correlation is confirmed
**Owner:** On-Call Lead
**Last Updated:** 2025-02-05

## Prerequisites
- Confirmed correlation between deployment and incident (within 60-minute window)
- On-call lead approval obtained (Slack: #incident-response)
- Rollback does NOT apply to database migrations — see separate procedure

## Rollback Steps

### 1. Identify the Target Revision
```bash
kubectl rollout history deployment/<service-name> -n production
```
Note the revision number before the problematic deployment.

### 2. Execute Rollback
```bash
kubectl rollout undo deployment/<service-name> -n production --to-revision=<N>
```
This is an atomic operation — Kubernetes will perform a rolling update back to the previous ReplicaSet.

### 3. Verify Rollback Success
```bash
# Check rollout status
kubectl rollout status deployment/<service-name> -n production --timeout=120s

# Verify the running image
kubectl get deployment/<service-name> -n production -o jsonpath='{.spec.template.spec.containers[0].image}'

# Check pod health
kubectl get pods -n production -l app=<service-name> -o wide
```
All pods should be Running with 0 restarts. Confirm the image tag matches the target revision.

### 4. Validate Service Recovery
- Check P99 latency returns to baseline within 5 minutes
- Verify error rate drops below 0.1%
- Confirm health check endpoints return 200
```bash
curl -s https://<service-name>.internal/health | jq .
```

### 5. Post-Rollback Actions
- Lock the deployment pipeline for the affected service
- Notify the deploying engineer with the incident link
- Create a post-incident ticket for root cause analysis
- Do NOT re-deploy until the fix has been reviewed and approved

## GitOps Rollback (if using ArgoCD)
```bash
argocd app rollback <app-name> --revision <N>
argocd app sync <app-name> --prune
```

## Escalation
- If rollback fails or pods do not stabilize, escalate to Platform Engineering.
- If the rollback is for a database-coupled service, involve the DBA before proceeding.
