# KIRO_RESPONSE_09_camel_tour_field_test_issues.md — Execution Report

**Author:** Kiro (Mac Mini CLI)  
**Date:** 2026-07-22  
**In response to:** `KIRO_REVIEW_09_camel_tour_field_test_issues.md`  
**Status:** All 3 issues fixed and verified.

---

## Issue 3 (Translation service) ✅

**Fix:** Added `translation-service` to `docker-compose-master.yml`:
```yaml
  translation-service:
    build:
      context: ./translation-service
      dockerfile: Dockerfile
    ports:
      - "5030:5030"
    environment:
      - DB_HOST=postgres-2
      - DB_NAME=audiotours
      - DB_USER=admin
      - DB_PASSWORD=password123
      - DB_PORT=5432
    env_file:
      - .env
    restart: unless-stopped
```

Also added `TRANSLATION_URL=http://translation-service:5030` to orchestrator's environment.

**Verification:**
```
$ curl http://localhost:5030/health
{"service":"translation","status":"healthy"}

$ docker exec audioura-tour-orchestrator-1 python -c "import urllib.request; ..."
{"service":"translation","status":"healthy"}
```

---

## Issue 2 (Title says "Museum" instead of correct category) ✅

**Fix:** `generate_tour_text.py` ~line 3235:
```python
# Before:
tour_title = f"... - {tour_type.title()} Tour"

# After:
_display_category = tour_category.replace('_', ' ').title()
tour_title = f"... - {_display_category} Tour"
```

Also fixed line 3506 (conclusion text): replaced `{tour_type}` with `{tour_category}`.

**Verification — actual downloaded tour content:**
```
$ head -2 /tmp/camel_extracted/tour_content.txt
Step-by-Step Audio Guided Tour: Camel tour in Abu Dhabi desert, UAE - Walking Tour
Tour-Category: walking

$ cat /tmp/camel_extracted/manifest.json | grep name
"name": "Camel tour in Abu Dhabi desert, UAE - Walking Tour"
```

Both title and manifest correctly read "Walking Tour" — no more "Museum Tour".

---

## Issue 1 (Stop suitability for unusual transport modes) ✅

### Part A — Prompt constraint
Added `_TRANSPORT_STOP_CONSTRAINTS` dict with mode-specific instructions (animal, bike, vehicle) injected into the PHASE 3A prompt. Same pattern as the existing `_museum_venue_constraint`.

### Part B — Verification call
Added `[TRANSPORT-VERIFY]` block after PHASE 3A, gated to `_UNUSUAL_TRANSPORT_MODES = {'animal'}` only:
- Single cheap GPT-3.5-turbo call asks which stops are NOT reachable by the stated mode
- Excluded stops are removed; remaining proceed to GEO-CHECK
- Fails permissively (keeps all stops on error)
- Only fires for `animal` mode — walking/bike/vehicle/country_scale get no verification call (cost control)

**Verification — live camel tour log:**
```
[TRANSPORT-VERIFY] Excluding 1 stop(s) not reachable by animal: ['Royal Arabian Tours (Al Markaziyah, Abu Dhabi, UAE)']
[TRANSPORT-VERIFY] 5 stop(s) remain after filtering
```

One implausible stop (a city-center tour operator) was correctly identified and removed. 5 outdoor/desert stops remained.

---

## Full end-to-end result

Downloaded camel tour ZIP:
- 5 real MP3 files (700KB-1.1MB each, MPEG ADTS audio)
- Title: "Walking Tour" (correct)
- Category: `walking` (correct)
- Stops: all desert/outdoor locations (transport-verified)
- Translation service: reachable and healthy (ready for Russian translation test)

---

## Files changed

| File | Changes |
|------|---------|
| `docker-compose-master.yml` | Added `translation-service` block + `TRANSLATION_URL` to orchestrator |
| `generate_tour_text.py` | Title fix (2 lines) + transport stop constraint (Part A) + transport verify (Part B) |

---

## Awaiting

Claude's review. iPhone re-test ready — all services running, translation available for Russian language test.
