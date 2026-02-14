# Kafka Consumer Lag Resolution

**Severity:** P2 if lag > 100k messages, P1 if lag is growing unbounded
**Owner:** Data Platform Team
**Last Updated:** 2025-01-25

## Symptoms
- Consumer group lag exceeding threshold (alert at 50k messages, critical at 200k)
- Delayed event processing (stale data in downstream systems)
- Consumer pods showing high CPU but low throughput
- Rebalancing loops in consumer logs

## Investigation Steps

### 1. Check Current Consumer Lag
```bash
kafka-consumer-groups --bootstrap-server kafka.internal:9092 \
  --describe --group <consumer-group-name>
```
Note the LAG column for each partition. Healthy lag should be < 1000 per partition.

### 2. Verify Consumer Health
```bash
kubectl get pods -n production -l app=<consumer-service> -o wide
kubectl logs -n production -l app=<consumer-service> --tail=100 | grep -i "rebalance\|error\|exception"
```
Look for repeated rebalancing events — this causes consumers to stop processing during rebalance.

### 3. Check Producer Throughput
```bash
kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list kafka.internal:9092 --topic <topic> --time -1
```
If producer rate suddenly increased, consumers may need to scale horizontally.

### 4. Identify Slow Processing
Check average message processing time. If individual messages take > 100ms, the consumer cannot keep up with the producer rate:
```bash
curl -s http://localhost:9090/api/v1/query?query=kafka_consumer_process_duration_seconds_p99
```

### 5. Remediation Options

**Scale consumers (fastest fix):**
```bash
kubectl scale deployment/<consumer-service> -n production --replicas=<N>
```
Ensure replicas ≤ number of partitions (extra replicas will be idle).

**Increase consumer throughput:**
- Raise `max.poll.records` from default 500 to 1000
- Increase `fetch.max.bytes` if messages are large
- Enable batch processing if the consumer processes one-at-a-time

**Reset offsets (data loss — last resort):**
```bash
kafka-consumer-groups --bootstrap-server kafka.internal:9092 \
  --group <group> --topic <topic> --reset-offsets --to-latest --execute
```
This skips unprocessed messages. Requires team lead approval.

## Escalation
- If lag is growing despite scaling, escalate to the Data Platform team.
- If offset reset is needed, require approval from the service owner and data team lead.
