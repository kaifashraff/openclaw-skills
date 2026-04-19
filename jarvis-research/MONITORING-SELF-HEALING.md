# Monitoring, Observability & Self-Healing Systems

## 7.4 Grafana Dashboard Configuration

```json
{
 "dashboard": {
 "title": "OpenClaw AGI Health Dashboard",
 "panels": [
 { "title": "System Health", "type": "row" },
 { "title": "CPU Usage", "type": "graph", "targets": [{"expr": "system_cpu_usage"}] },
 { "title": "Memory Usage", "type": "graph", "targets": [{"expr": "system_memory_usage"}] },
 { "title": "Agent Status", "type": "table", "targets": [{"expr": "openclaw_agent_status"}] },
 { "title": "Tool Executions", "type": "graph", "targets": [{"expr": "rate(openclaw_tool_executions_total[5m])"}] }
 ]
 }
}
```

## 7.5 Alerting Rules

```yaml
groups:
- name: openclaw.alerts
 rules:
 - alert: HighCPUUsage
   expr: system_cpu_usage > 90
   for: 5m
   labels:
     severity: critical
   annotations:
     summary: "High CPU usage detected"
     description: "CPU usage is {{ $value }}%"

 - alert: AgentFailure
   expr: increase(openclaw_agent_errors_total[1h]) > 5
   labels:
     severity: warning
   annotations:
     summary: "Agent experiencing repeated failures"
     description: "Agent {{ $labels.agent_name }} has failed {{ $value }} times in the last hour"

 - alert: ToolErrorRate
   expr: rate(openclaw_tool_errors_total[5m]) / rate(openclaw_tool_executions_total[5m]) > 0.1
   labels:
     severity: critical
   annotations:
     summary: "High tool error rate"
     description: "Error rate is {{ $value | printf \"%.1f%%\" }}"
```

## 8. Self-Healing Systems: Automatic Recovery

### 8.1 Circuit Breaker Pattern

```python
class CircuitBreaker:
    def __init__(self, max_failures=3, reset_timeout=60):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure = 0
        self.state = "closed"  # closed, open, half-open

    def call(self, func):
        if self.state == "open":
            if time.time() - self.last_failure > self.reset_timeout:
                self.state = "half-open"
            else:
                raise Exception("Circuit breaker is open")

        try:
            result = func()
            if self.state == "half-open":
                self.state = "closed"
                self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure = time.time()
            if self.failures >= self.max_failures:
                self.state = "open"
            raise e
```

### 8.2 System Metrics Collection

```python
self.metrics["system"]["cpu"].set(psutil.cpu_percent())
self.metrics["system"]["memory"].set(memory.used / 1024 / 1024)
self.metrics["system"]["disk"].set(disk.percent)
self.metrics["services"]["gateway"].set(1 if self.check_service("openclaw-gateway") else 0)
self.metrics["services"]["agents"].set(len(self.get_active_agents()))
```

### 8.3 Recovery Scripts

```bash
#!/bin/bash
# recovery-scripts/restart-gateway.sh
LOG_FILE="/var/log/openclaw/gateway.log"
MAX_RETRIES=3
RETRY_DELAY=10
```

## Key Components
1. **Metrics Collection** — CPU, Memory, Disk, Services, Agent status
2. **Grafana Dashboard** — Visual monitoring with panels
3. **Alerting Rules** — Prometheus-style alerts for CPU, Agent failures, Tool errors
4. **Circuit Breaker** — Prevents cascading failures
5. **Recovery Scripts** — Automatic restart on failure

## 8.3 Gateway Recovery Script
```bash
#!/bin/bash
retry_count=0
while [ $retry_count -lt $MAX_RETRIES ]; do
  openclaw gateway stop >> "$LOG_FILE" 2>&1
  if ! pgrep -f "openclaw gateway" > /dev/null; then
    openclaw gateway start >> "$LOG_FILE" 2>&1
    sleep 5
    if pgrep -f "openclaw gateway" > /dev/null; then
      echo "[$(date)] Gateway restarted successfully" >> "$LOG_FILE"
      exit 0
    fi
  fi
  retry_count=$((retry_count + 1))
  sleep $RETRY_DELAY
done
exit 1
```

## 8.4 Auto-Scaling
```python
class AgentAutoScaler:
    def check_system_load(self):
        cpu = psutil.cpu_percent(interval=5)
        memory = psutil.virtual_memory().percent
        return cpu, memory

    def scale_agents(self, current_agents):
        cpu, memory = self.check_system_load()
        if cpu > 70 or memory > 80:
            return "scaled_up"
        return "no_change"
```

## 9. Real-Time Data Streams (Redis)

### Event Stream Architecture
- Kafka-like event stream using Redis
- Publish/subscribe pattern
- Real-time market data processing
