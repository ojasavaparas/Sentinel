# DNS Resolution Failure Troubleshooting

**Severity:** P1 — DNS failures cause widespread service-to-service communication breakdown
**Owner:** Infrastructure / Networking Team
**Last Updated:** 2025-01-28

## Symptoms
- Services logging "Name or service not known" or "Temporary failure in name resolution"
- Intermittent connection failures between services
- CoreDNS pods showing elevated error rates or restarts
- Service mesh reporting upstream connection failures

## Investigation Steps

### 1. Test DNS from Affected Pod
```bash
kubectl exec -n production <pod-name> -- nslookup <target-service>.production.svc.cluster.local
kubectl exec -n production <pod-name> -- nslookup google.com
```
If internal names fail but external names resolve, the issue is with CoreDNS or cluster DNS config. If both fail, the node's DNS is broken.

### 2. Check CoreDNS Health
```bash
kubectl get pods -n kube-system -l k8s-app=kube-dns
kubectl logs -n kube-system -l k8s-app=kube-dns --tail=50
```
Look for: REFUSED errors, SERVFAIL responses, OOMKill events, or crash loops. Healthy CoreDNS should show < 1% error rate.

### 3. Check CoreDNS Metrics
```bash
curl -s http://localhost:9090/api/v1/query?query=coredns_dns_responses_total{rcode="SERVFAIL"}
```
A spike in SERVFAIL responses indicates CoreDNS cannot resolve queries — likely an upstream DNS issue or resource exhaustion.

### 4. Verify resolv.conf
```bash
kubectl exec -n production <pod-name> -- cat /etc/resolv.conf
```
Should contain:
- `nameserver 10.96.0.10` (cluster DNS IP)
- `search production.svc.cluster.local svc.cluster.local cluster.local`
- `options ndots:5`

If `ndots` is wrong or nameserver IP is incorrect, the pod's DNS config is broken.

### 5. Remediation
```bash
# Restart CoreDNS if it's in a bad state
kubectl rollout restart deployment/coredns -n kube-system

# If CoreDNS is resource-starved, scale it
kubectl scale deployment/coredns -n kube-system --replicas=4

# Clear DNS cache on nodes (if using systemd-resolved)
ssh <node> "sudo systemd-resolve --flush-caches"
```

### 6. Check for DNS Rate Limiting
If running NodeLocal DNSCache, verify it's healthy on affected nodes:
```bash
kubectl get pods -n kube-system -l k8s-app=node-local-dns -o wide | grep <node-name>
```

## Escalation
- DNS failures are high severity. If not resolved in 10 minutes, escalate to Infrastructure.
- If the issue is with external DNS (Route53, Cloud DNS), escalate to the Cloud Platform team.
