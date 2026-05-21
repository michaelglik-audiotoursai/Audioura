# REMINDER LIST — Must Complete Before Production Release

**Purpose:** Items that MUST be addressed before Audioura has paying customers.  
**Owner:** Services Amazon-Q  
**Last updated:** 2026-05-21  
**Branch context:** Items discovered during `Tours_Step_Maps` review sessions.

---

## 1. ACTIVE_JOBS — Lock + TTL + Restart Recovery

**Source:** Claude code-improvements review §1.1  
**Priority:** HIGH — must fix before production  
**Files:** `generate_tour_text_service.py`, `tour_generation_modernized.py`

**Problem:**  
`ACTIVE_JOBS = {}` is process-local, unbounded, and lock-free. Three failure modes:

1. **Container restart** — any in-flight or queued job vanishes silently. Mobile app polls `/status/<job_id>` forever with no error response. User sees an infinite spinner.
2. **Memory leak** — no eviction. Long-running container accumulates one entry per request forever (including full prompt strings and coordinates). Eventually OOMs the process.
3. **Race condition** — Flask request thread and background thread both write to the same dict. A sequence like `status = "error"` then `error = str(e)` is two writes; a status reader can observe the intermediate state.

**Recommended fix:**
```python
from threading import Lock
from cachetools import TTLCache   # pip install cachetools

ACTIVE_JOBS = TTLCache(maxsize=1000, ttl=3600)  # evict after 1 hour
_JOBS_LOCK = Lock()

def _update_job(job_id, **fields):
    with _JOBS_LOCK:
        if job_id in ACTIVE_JOBS:
            ACTIVE_JOBS[job_id].update(fields)
```

Also: write a JSON snapshot to disk on every state transition (`queued → processing → completed/error`). On container startup, read the snapshot and mark any `processing` jobs as `error: service_restarted`. Mobile app then gets a clean error it can display instead of polling forever.

**Scope:** Own dedicated session — touches ~30 read/write sites across both service files.

---

## 2. MAX_TOTAL_STOPS Cost Guard

**Source:** Claude code-improvements review §1.1 / cost discussion  
**Priority:** HIGH — must fix before public access  
**Files:** `generate_tour_text_service.py`

**Problem:**  
There is currently no upper bound on `total_stops`. A single request for 50 stops could cost $0.20+. If the API is ever exposed without authentication, a bot could generate 1000 tours and cost $200 in an hour.

**Current cost estimate per tour (gpt-3.5-turbo, 2024 pricing):**
- PHASE 1 intent: ~$0.0006
- PHASE 3A names: ~$0.0012
- PHASE 3B details: ~$0.003
- PHASE 5 descriptions (5–10 stops): ~$0.0075–$0.015
- Coords fallback + Part C: ~$0.001 (occasional)
- **Total: ~$0.012–$0.020 per standard 3–5 stop tour**

**Recommended fix (add to service wrapper, not generator):**
```python
# In generate_tour_text_service.py, before spawning the background thread:
GPT_COST_PER_STOP_ESTIMATE = 0.004   # conservative per-stop estimate in USD
MAX_TOTAL_STOPS_FREE = 15            # hard cap for unauthenticated / free tier users
MAX_TOTAL_STOPS_PAID = 30            # leeway for paying customers

# Determine cap based on user tier (implement with auth when ready):
max_stops = MAX_TOTAL_STOPS_PAID if is_paying_customer(request) else MAX_TOTAL_STOPS_FREE
if total_stops > max_stops:
    return jsonify({"error": f"Maximum {max_stops} stops allowed"}), 400

# Log estimated cost pre-flight:
estimated_cost = total_stops * GPT_COST_PER_STOP_ESTIMATE
ACTIVE_JOBS[job_id]["estimated_cost_usd"] = estimated_cost
```

**Caveat:** Paying customers should be allowed more leeway — `MAX_TOTAL_STOPS_PAID = 30` (or configurable per subscription tier). The cap for free/unauthenticated users is the critical guard. Exact tier thresholds are a product decision.

**Note:** No change to `generate_tour_text()` return signature needed — estimate is calculated in the service wrapper from `total_stops` alone.

---

## 3. Category-Aware PHASE 5 Description Prompts

**Source:** Claude code-improvements review §2.7 / user direction  
**Priority:** HIGH — required for acceptable tour quality at launch  
**Files:** `generate_tour_text.py` (PHASE 5 description generation)

**Problem:**  
The current PHASE 5 description prompt says "walking tour" and asks for "artistic significance / artist / creative process" regardless of `tour_category`. Restaurant tours get descriptions that talk about the restaurant's "artist." Museum tours get walking-tour framing. More fundamentally: the current OpenAI API output produces tours with fancy words and very little meaning — every stop sounds the same, generic, and unmemorable.

**Architecture decision (implement now, fill content later):**  
The `PROMPT_TEMPLATES` dict keyed by `tour_category` must be established in the code now, even if all four entries contain the same generic prompt today. When content work happens, it is a fill-in-the-dict operation with zero pipeline changes.

```python
# TODO: PRODUCTION — replace each entry with category-specific story-driven prompts.
# Goals per category:
#   walking:    memorable local history, human stories, cultural connections, related facts
#   restaurant: cuisine origin, chef story, signature dishes, neighborhood food culture
#   museum:     exhibit context, historical significance, connections to broader world events
#   specialized: connection to theme (book/movie/product), scene/setting significance
PROMPT_TEMPLATES = {
    'walking':     _GENERIC_DESCRIPTION_PROMPT,   # replace before launch
    'restaurant':  _GENERIC_DESCRIPTION_PROMPT,   # replace before launch
    'museum':      _GENERIC_DESCRIPTION_PROMPT,   # replace before launch
    'specialized': _GENERIC_DESCRIPTION_PROMPT,   # replace before launch
}
description_prompt = PROMPT_TEMPLATES.get(tour_category, _GENERIC_DESCRIPTION_PROMPT).format(
    poi_name=poi_name, location=location, tour_type=tour_type,
    theme_name=intent.get('theme_name', '') if intent else ''
)
```

**Content work required before launch:**  
Each prompt template needs to produce tours that are:
- Story-driven, not encyclopedic
- Different voice and structure per stop (not every stop starting the same way)
- Include related facts about people, cultures, historical connections
- Pleasant to listen to as audio (short sentences, natural speech rhythm)
- Memorable — something the listener will remember and tell others

This is a significant content/prompt-engineering effort. Schedule as a dedicated sprint with human review of generated tours across all four categories.

---

## 4. Structured Logging with job_id Correlation

**Source:** Claude code-improvements review §3.2 / user direction  
**Priority:** HIGH — required before production monitoring  
**Files:** All service files (~200 `print()` calls in `generate_tour_text.py` alone)  
**Full requirements:** See `LOGGING_REQUIREMENTS_PRE_PRODUCTION.md`

**Summary of problem:**  
~200 `print()` calls with no severity levels, no job_id correlation, no machine-parseable fields. When two tours generate simultaneously, their log lines interleave with no way to separate them. Cannot alert on error rates, cost spikes, or PHASE 3C rejection patterns without structured logs.

**Key requirements (full spec in linked doc):**
- Replace all `print()` with Python `logging` module (INFO / WARNING / ERROR levels)
- JSON-formatted log lines with `job_id`, `event`, and relevant fields
- `job_id` threaded through all pipeline phases
- Key events: `phase_3c_removed`, `tour_generation_complete` (with cost), `tour_generation_error`
- Log level controlled by `LOG_LEVEL` environment variable

**Monitoring tools to evaluate:** AWS CloudWatch Logs, Datadog, Grafana+Loki, ELK  
**Estimated effort:** 3–5 days dedicated sprint  
**Decision:** Tool selection deferred until deployment target confirmed.

---

## 5. Authentication and API Security

**Source:** General production readiness  
**Priority:** HIGH — required before any public exposure  
**Files:** All service endpoints

**Items:**
- API key / JWT authentication on all service endpoints
- Rate limiting per user/IP
- CORS restricted to known origins (currently wide open — `CORS(app)` with no `origins=`)
- `FLASK_DEBUG=False` in production (currently hardcoded `debug=True` — Werkzeug RCE risk)
- HTTPS termination (currently plain HTTP inside Docker network)

**Note:** `debug=True` and open CORS are trivial one-line fixes scheduled for the next services session. Auth and rate limiting are a larger effort.

---

## 6. `attachment_filename` → `download_name` (Flask 2.2 compat)

**Source:** Claude code-improvements review §1.3  
**Priority:** MEDIUM — breaks silently on next Flask dependency bump  
**Files:** `generate_tour_text_service.py:189`

**Problem:**
```python
return send_file(output_path, as_attachment=True, attachment_filename=job["output_file"])
```
`attachment_filename` was removed in Flask 2.2. Current container is pinned to an older version — works today, breaks on next `pip install --upgrade`.

**Fix:** `download_name=job["output_file"]`  
**Scheduled:** Next services session (trivial).

---

## Summary Table

| # | Item | Priority | Effort | Scheduled |
|---|------|----------|--------|-----------|
| 1 | ACTIVE_JOBS lock + TTL + restart recovery | HIGH | Medium (own session) | Before beta |
| 2 | MAX_TOTAL_STOPS cost guard + tier-based cap | HIGH | Small | Next session |
| 3 | Category-aware PHASE 5 prompts (PROMPT_TEMPLATES arch) | HIGH | Large (content sprint) | Before launch |
| 4 | Structured logging + job_id correlation | HIGH | Large (logging sprint) | Before beta |
| 5 | Auth, rate limiting, CORS, debug=False, HTTPS | HIGH | Large (security sprint) | Before public |
| 6 | `attachment_filename` → `download_name` | MEDIUM | Trivial | Next session |
