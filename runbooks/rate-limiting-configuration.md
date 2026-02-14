# Rate Limiting Configuration and Troubleshooting

**Severity:** P2 if legitimate traffic is being dropped, P3 for tuning
**Owner:** API Platform Team
**Last Updated:** 2025-02-03

## Symptoms
- Clients receiving HTTP 429 Too Many Requests responses
- Sudden drop in successful request rate without infrastructure issues
- API gateway logs showing rate limit exceeded for specific clients or endpoints
- Customer complaints about intermittent failures

## Investigation Steps

### 1. Identify What Is Being Rate Limited
```bash
# Check rate limit metrics
curl -s http://localhost:9090/api/v1/query?query=rate(http_responses_total{status="429"}[5m])
```
Determine if the 429s are per-client, per-endpoint, or global. Check response headers for rate limit info:
```bash
curl -I https://api.example.com/v1/resource -H "Authorization: Bearer <token>"
# Look for: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
```

### 2. Review Current Rate Limit Configuration
```bash
# If using Envoy/Istio rate limiting
kubectl get configmap rate-limit-config -n production -o yaml

# If using API gateway (Kong)
curl -s http://kong-admin.internal:8001/plugins?name=rate-limiting | jq '.data[] | {route: .route.id, config: .config}'
```

### 3. Check if Traffic Is Legitimate
Review the request patterns for the rate-limited client:
- Is a single client sending 10x normal traffic? (possible bug in client code)
- Is traffic evenly distributed? (possible DDoS or bot traffic)
- Did a new integration go live without notifying the API team?

### 4. Adjust Rate Limits
```bash
# Increase limit for a specific client (Kong example)
curl -X PATCH http://kong-admin.internal:8001/plugins/<plugin-id> \
  -d "config.minute=1000" -d "config.hour=50000"

# Update Envoy rate limit config
kubectl edit configmap rate-limit-config -n production
kubectl rollout restart deployment/ratelimit -n production
```

### 5. Emergency Bypass (temporary)
If legitimate traffic is being blocked during an incident:
```bash
# Add client to allowlist
kubectl annotate ingress <ingress-name> -n production \
  nginx.ingress.kubernetes.io/configuration-snippet="if ($http_x_api_key = '<client-key>') { set $limit_rate 0; }"
```
Remove the bypass within 24 hours and implement a proper limit increase.

## Prevention
- Require all new API integrations to declare expected traffic volume
- Set rate limits at 2x expected peak traffic
- Implement graduated rate limiting (warn at 80%, throttle at 100%)

## Escalation
- If rate limiting is masking a DDoS attack, escalate to Security Engineering.
- If a key customer is affected, notify the account team immediately.
