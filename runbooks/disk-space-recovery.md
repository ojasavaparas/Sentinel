# Disk Space Recovery Procedures

**Severity:** P1 if < 5% free, P2 if < 15% free
**Owner:** Infrastructure Team
**Last Updated:** 2025-01-10

## Symptoms
- Disk usage alerts firing (threshold: 85% warning, 95% critical)
- Services failing to write logs or temp files
- Database refusing writes with "No space left on device"
- Pod evictions due to ephemeral storage limits

## Investigation Steps

### 1. Identify the Affected Volume
```bash
kubectl exec -n production <pod-name> -- df -h
```
Determine which mount point is full: `/`, `/var/log`, `/data`, or `/tmp`.

### 2. Find Large Files and Directories
```bash
kubectl exec -n production <pod-name> -- du -sh /* 2>/dev/null | sort -rh | head -20
```
Common offenders: application logs, core dumps, temp files, unrotated archives.

### 3. Check Log Rotation
```bash
kubectl exec -n production <pod-name> -- ls -lah /var/log/app/
```
If individual log files exceed 500MB, log rotation is misconfigured. Verify logrotate config includes `maxsize 100M`, `rotate 5`, and `compress`.

### 4. Clean Up Safely
```bash
# Truncate active log files (safe — doesn't break file handles)
kubectl exec -n production <pod-name> -- truncate -s 0 /var/log/app/application.log

# Remove old temp files (older than 7 days)
kubectl exec -n production <pod-name> -- find /tmp -type f -mtime +7 -delete

# Clear package manager cache
kubectl exec -n production <pod-name> -- apt-get clean
```

### 5. Expand Volume (if cleanup insufficient)
```bash
# For AWS EBS volumes
aws ec2 modify-volume --volume-id <vol-id> --size 100
# Then resize filesystem
kubectl exec -n production <pod-name> -- resize2fs /dev/xvda1
```

### 6. Prevent Recurrence
- Ensure log rotation is configured on all services
- Set ephemeral storage limits in pod specs: `ephemeral-storage: 10Gi`
- Add disk usage monitoring with alerts at 75% and 90%

## Escalation
- If database volumes are affected, escalate immediately to the DBA on-call.
- If volume expansion requires infrastructure changes, notify the Cloud Platform team.
