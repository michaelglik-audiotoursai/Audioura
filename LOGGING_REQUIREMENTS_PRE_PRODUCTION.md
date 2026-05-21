# Logging Requirements — Pre-Production Requirement

**Status:** NOT IMPLEMENTED — must be done before paying customers  
**Source:** Claude code-improvements review (`claude_response_code_improvements.md` §3.2)  
**Affects:** `generate_tour_text.py`, `generate_tour_text_service.py`, `tour_generation_modernized.py`, all other services

---

## Why this matters

The current codebase has ~200 `print()` calls across `generate_tour_text.py` alone. For a production service this is unacceptable:

1. **No severity levels** — a PHASE 3C rejection and a debug coordinate print look identical to a log aggregator.
2. **No job_id correlation** — when two tours generate simultaneously, their log lines interleave with no way to separate them.
3. **No machine-parseable fields** — finding all PHASE 3C rejections from yesterday requires grepping raw text.
4. **No monitoring integration** — CloudWatch, Datadog, ELK, etc. cannot alert on error rates or cost spikes without structured fields.
5. **No self-diagnosis** — Services Amazon-Q analyzing a production incident cannot reconstruct what happened to a specific tour without job_id-correlated logs.

---

## Requirements

### R1 — Replace `print()` with Python `logging` module
- All `print(f"...")` calls replaced with `logger.info(...)`, `logger.warning(...)`, `logger.error(...)`
- Logger name = module name (`generate_tour_text`, `generate_tour_text_service`, etc.)
- Log level controlled by `LOG_LEVEL` environment variable (default `INFO`)

### R2 — Structured JSON log format
Each log line must be a single JSON object with at minimum:
```json
{
  "timestamp": "2026-05-21T14:32:01.123Z",
  "level": "INFO",
  "service": "generate_tour_text",
  "job_id": "abc-123",
  "event": "phase_3c_removed",
  "poi_name": "Sudbury Town Hall",
  "address": "322 Concord Rd, Sudbury, MA 01776",
  "location": "walking tour in Arlington, MA"
}
```

### R3 — job_id threaded through all pipeline phases
`generate_tour_text()` must accept `job_id` as a parameter and pass it to every log call. The service wrapper already has `job_id` — it must pass it into the generator.

### R4 — Key events that MUST be logged as structured fields

| Event name | Level | Key fields |
|---|---|---|
| `tour_generation_start` | INFO | job_id, location, tour_type, total_stops |
| `phase_1_intent` | INFO | job_id, venue_name, poi_type, theme_type |
| `phase_3a_candidates` | INFO | job_id, count, names[] |
| `phase_3c_removed` | WARNING | job_id, poi_name, address, location |
| `phase_3c_all_rejected` | ERROR | job_id, location, count |
| `part_c_replacement` | INFO | job_id, attempt, needed, survived |
| `coords_cluster_detected` | WARNING | job_id, coord, count, total_stops |
| `phase_5_description` | INFO | job_id, stop_num, poi_name, word_count, tokens, cost_usd |
| `phase_55b_removed` | WARNING | job_id, poi_name, reason |
| `tour_generation_complete` | INFO | job_id, actual_stops, total_tokens, total_cost_usd |
| `tour_generation_error` | ERROR | job_id, phase, error_message, traceback |

### R5 — Cost logged per tour
`total_cost_usd` and `total_tokens` logged in `tour_generation_complete` event. Enables cost monitoring and alerting.

### R6 — Error alerting
`logger.error(...)` calls must be routable to an alerting channel (CloudWatch alarm, PagerDuty, Slack webhook). The specific tool is TBD but the log structure must support it.

### R7 — Log retention
Minimum 30 days retention for production logs. Enables post-incident analysis.

---

## Implementation approach (when ready)

```python
# At top of each service file:
import logging
import json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log = {
            'timestamp': self.formatTime(record, '%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            'level': record.levelname,
            'service': record.name,
            'event': record.getMessage(),
        }
        if hasattr(record, 'extra'):
            log.update(record.extra)
        if record.exc_info:
            log['traceback'] = self.formatException(record.exc_info)
        return json.dumps(log)

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Usage:
logger.warning('phase_3c_removed', extra={
    'job_id': job_id,
    'poi_name': p['name'],
    'address': p['address'],
    'location': location,
})
```

---

## Monitoring tools to evaluate (TBD)

- **AWS CloudWatch Logs** — natural fit if deploying to AWS ECS/EC2; log groups per service, metric filters for error rates and cost
- **Datadog** — richer dashboards, APM tracing across services
- **ELK Stack (self-hosted)** — full control, higher ops burden
- **Grafana + Loki** — lightweight, good for Docker-based deployments

Decision deferred until deployment target is confirmed.

---

## Estimated effort

- Replacing all `print()` calls: ~1 day per service file
- Adding `job_id` threading: ~0.5 day
- JSON formatter + log level config: ~0.5 day
- Monitoring tool setup: 1–3 days depending on tool
- **Total: 3–5 days of focused work**

This is a sprint, not a side-fix. Schedule as a dedicated logging sprint before beta launch.
