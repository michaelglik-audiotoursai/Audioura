##### READY FOR REVIEW

## LOCAL-92: Subscribed has no runnable deployment

### Summary

Created `docker-compose-subscribed.yml` — a first-class, isolated deployment
of the Subscribed billing stack that runs alongside the shared containers
without collision.

---

### Files Changed

| File | Change |
|------|--------|
| `docker-compose-subscribed.yml` | **NEW** — Isolated compose bringing up `subscribed-orchestrator` (port 5102) and `subscribed-generator` (port 5100) on the `development_default` network, sharing Postgres |
| `DECISIONS.md` | **APPEND** — Added D24: shared containers stay on storied; subscribed gets its own compose |
| `SUBSCRIBED_DESIGN.md` | **APPEND** — Documented the isolated deployment, quick commands, and constraints |
| `SUBMISSION_LOCAL-92.md` | **NEW** — This file |

---

### Evidence

#### 1. Stack comes up; `GET /wallet/<user>` returns 200 with contract shape

```
$ curl -s http://localhost:5102/wallet/acceptance_test_user | python3 -m json.tool
{
    "balance_usd": 0.0,
    "cost_stop_progress": null,
    "low_balance": false,
    "period_end": "2026-09-01T00:00:00+00:00",
    "period_spend_usd": 0.0,
    "period_start": "2026-08-01T00:00:00+00:00",
    "plan": "free"
}
```

#### 2. Shared containers untouched — BEFORE, AFTER bring-up, AFTER tear-down

All three snapshots show identical container IDs:

```
audioura-tour-generator-1       1f13d008c6d2    audioura-tour-generator
audioura-tour-orchestrator-1    4e1aee599b20    audioura-tour-orchestrator
audioura-map-delivery-1         fb3491c10c39    audioura-map-delivery
```

#### 3. E2E test passes 10/10 including step 10

```
ORCHESTRATOR_URL=http://localhost:5102 python3 tests/test_local82_subscribed_e2e.py

Total: 10 | PASS: 10 | FAIL: 0

Step 10: API reconciliation: 2 txns, balance $-3.0 — PASS
  (descriptions_ok=True, reconciles=True)
```

Step 10 specifically: `GET /wallet/{user}` returned 200, `GET /wallet/{user}/transactions?limit=200` returned 200, balance reconciles with ledger.

#### 4. Tear-down leaves no containers

```
$ docker ps --format "{{.Names}}" | grep subscribed
(none)
```

#### 5. Michael's app path works after tear-down

```
$ tours-near: [1, 12, 14, 17, 21, 24, 27, 28, 29]
$ download-tour/29: HTTP 200, 7,408,370 bytes
```

#### 6. audio_tours row count preserved

```
Before: 55 (task claim) / 56 (actual at start of work)
After:  56
No DELETE FROM audio_tours executed.
```

---

### Design Decisions

- **Port 5102/5100**: Chosen to be well outside the master range (5000–5030)
  and close to 5100 for easy recognition as "subscribed variants."
- **Joins `development_default` external network**: Allows the subscribed
  containers to reach `postgres-2`, `translation-service`, `user-api-2`, etc.
  without duplicating them.
- **Python-based healthchecks**: `python:3.9-slim` does not include `curl`;
  healthchecks use `urllib.request.urlopen()` instead.
- **No Dockerfile changes**: Both `Dockerfile.orchestrator` and
  `Dockerfile.generator` are unchanged. The subscribed compose simply builds
  them with a different `GIT_SHA` tag for identification.
- **OPENAI_API_KEY / SERP_API_KEY**: Passed via environment variables from the
  shell. Missing keys produce a warning but don't prevent startup (cached
  operations still work).

---

### Limitations

1. **`/wallet/<user>/change-tier` endpoint will 500** if called via HTTP —
   `tier_change.py` and `fake_payment_provider.py` are not copied into the
   orchestrator image. The test exercises tier changes via direct Python
   imports (not HTTP), so this doesn't affect test results. A future task
   could add a `Dockerfile.orchestrator-subscribed` with additional COPY
   statements if HTTP tier-change is needed.
2. **Generator requires API keys for fresh generation** — without
   `OPENAI_API_KEY`, new tour generation will fail. Cached tours and billing
   operations work without it.
3. **`docker-compose-master.yml` not modified** — by design. The subscribed
   compose is a parallel file, not an override.

---

### Commit

```
Branch: kiro/local92-subscribed-container
Commit: bea78fa
Ahead of subscribed by: 1
```
