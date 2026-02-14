# TLS Certificate Expiry Remediation

**Severity:** P1 if expired, P2 if expiring within 7 days
**Owner:** Security Engineering
**Last Updated:** 2025-01-18

## Symptoms
- TLS handshake failures (SSL_ERROR_EXPIRED_CERT_KEY_USAGE)
- Browser showing "Your connection is not private" errors
- Downstream services failing with certificate verification errors
- cert-manager alerts firing for expiring certificates

## Investigation Steps

### 1. Check Certificate Expiry
```bash
# From the cluster
kubectl get certificate -n production -o wide

# Direct inspection
echo | openssl s_client -servername <domain> -connect <domain>:443 2>/dev/null | openssl x509 -noout -dates
```
If `notAfter` is in the past, the certificate has expired. If within 7 days, it is expiring soon.

### 2. Identify the Certificate Source
Determine how the certificate is managed:
- **cert-manager**: Check the Certificate and Issuer resources
- **AWS ACM**: Check the ACM console or `aws acm describe-certificate`
- **Manual**: Check the Kubernetes secret directly

```bash
kubectl describe certificate <cert-name> -n production
kubectl describe issuer <issuer-name> -n production
```

### 3. cert-manager Renewal (Automated)
```bash
# Force renewal
kubectl delete certificate <cert-name> -n production
# cert-manager will recreate it automatically

# Or trigger manual renewal
cmctl renew <cert-name> -n production
```
Verify the new certificate is issued:
```bash
kubectl get certificate <cert-name> -n production -w
```
Status should transition to `Ready: True` within 2-5 minutes.

### 4. Manual Certificate Rotation
```bash
# Create new secret with updated cert
kubectl create secret tls <secret-name> -n production \
  --cert=new-cert.pem --key=new-key.pem --dry-run=client -o yaml | kubectl apply -f -

# Restart ingress controller to pick up new cert
kubectl rollout restart deployment/ingress-nginx-controller -n ingress-nginx
```

### 5. Verify Fix
```bash
echo | openssl s_client -servername <domain> -connect <domain>:443 2>/dev/null | openssl x509 -noout -dates -subject
curl -vI https://<domain> 2>&1 | grep "expire date"
```
Confirm the new expiry date is 90 days in the future (Let's Encrypt) or 1 year (commercial CA).

## Prevention
- Set cert-manager renewal threshold to 30 days before expiry
- Add monitoring alerts at 30, 14, and 7 days before expiry
- Audit all certificates monthly with `cmctl status certificate --all-namespaces`

## Escalation
- If cert-manager cannot issue (rate limits, DNS issues), escalate to Security Engineering.
- If a wildcard certificate is affected, declare SEV-1 — multiple services will be impacted.
