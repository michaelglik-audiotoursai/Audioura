# CLAUDE REVIEW — Kiro's Tour Quota Fail-CLOSED + Usage Recording

**Date:** 2026-06-10 · **Lane:** Cloud services (tour-orchestrator / DB) · **Reviewer:** Claude
**Reviewing:** `REVIEW_FOR_KIRO_quota_failclosed_usage_recording_2026_06_10.md` (Kiro) vs deployed code + schema.
**Prior review being remediated:** `claude_review_per_user_quota_implementation_2026_06_10.md`.

## Verdict: CHANGES REQUESTED — Findings 1 & 3 fixed; Finding 2 fix introduces double-counting

Kiro correctly closed the fail-open exception path (now 503) and the anonymous bypass (now 401), matching the
news path. The Finding-2 fix moves usage recording into the orchestrator, which is the right direction — but it
writes to the **pre-existing `tour_requests` table that another service already writes to**, so each tour can be
counted **twice**. That doesn't open a bypass (it over-counts, so it's conservative), but it **halves tester
limits and makes counts non-deterministic** — which directly breaks the "tester gets 100/day" acceptance item and
will frustrate the very testers you need before launch. Two further medium issues below.

---

## Claim-by-claim verification

| Kiro's claim | Status | Evidence |
|---|---|---|
| Finding 1 — exception path now 503 (fail-closed) | ✅ Verified | `tour_orchestrator_service.py:1119–1124` |
| Finding 3 — missing/empty `user_id` → 401 | ✅ Verified | `:1109–1114` |
| Order: 401 → check → 429 → record → generate | ✅ Verified | `:1109`, `:1116–1131`, `:1133` |
| Finding 2 — orchestrator inserts `tour_requests` after pass | ✅ Present | `:1144–1148` |
| Usage INSERT is non-fatal on failure | ✅ Verified | `:1152–1155` |
| `tour_requests` table + index exist | ✅ (pre-existed) | `migration/schema_dump.sql:496–502` |
| "Tester gets 100/day" | ❌ **Likely false now** | see Finding A (double count) |
| "Free user blocked on 2nd tour" | ⚠️ Holds, but for the wrong reason | see Finding A |
| "No conflict — counter sums all rows" | ❌ **This IS the bug** | see Finding A |

---

## Findings

### A — HIGH (correctness): Double-counting via two writers to `tour_requests`
`tour_requests` is **not** a new table — it already exists (`schema_dump.sql:496–502`) and is written by the
separate user-tracking service (`user_api_with_cors.py:100`, `user-tracking/app.py:79`) when the app reports a
tour. The orchestrator now **also** inserts a row (`:1144`). The quota counter
(`entitlements.get_tours_used_today`) counts **all** rows for the user today, so a single tour can produce two
rows → usage is inflated.

Kiro's risk note frames this as "no conflict — the counter sums all rows regardless of who wrote them." That
summation is exactly the defect:
- **Free (1/day):** still blocks on the 2nd request (count is ≥1 either way), so it *appears* fine.
- **Tester (100/day):** each tour ≈ 2 rows → testers are cut off near **~50/day**, not 100. And because the
  tracking write is app-driven and may lag, the effective limit is **non-deterministic** (fast bursts dodge the
  double count; slow usage gets double-counted). The "tester gets 100/day" checkbox is not met.

**Fix:** make exactly **one** writer authoritative for quota. Recommended: the orchestrator is the source of
truth; stop the tracking service from writing `tour_requests` (or point it at a separate analytics table). If the
tracking write must stay, make the count unambiguous (e.g., count only orchestrator-written rows) — but a single
writer is cleaner. Verify first whether the tracking service still fires on the **cloud** tour flow; if it does
(Kiro's own note says it can), the double count is live.

### B — MEDIUM: Failed/incomplete tours permanently consume quota
The row is inserted with `status='started'` **before** generation (`:1144` precedes the pipeline). If generation
fails (and the digest's recurring class is "works locally, breaks on Cloud Run"), the row remains and counts. For
a **free user (1/day)** a single failed attempt **locks them out for the rest of the day**. Recommend: delete /
roll back the usage row on definitive generation failure, or reconcile a `started` row that never reaches
`completed`. (Same pattern noted for news, but more painful here because the tour limit is 1/day, not 10/week.)

### C — MEDIUM: `tour_id` collision + orphaned from the real job
The recorded `tour_id` is `f"pending_{YYYYmmddHHMMSS}"` (second granularity) and is generated **before** the real
`job_id` (`:1158`). Consequences: two tours in the same second share a `tour_id`; the usage row is never
correlated to the actual job; and these `pending_` rows never transition to `completed` (related to the digest's
`TOUR_STATUS rows_affected=0` mismatch). Counting still works (it's status-agnostic), but completion tracking and
debugging degrade. **Fix:** generate `job_id` first and use it as the `tour_id` (a UUID), so the usage row maps
to the tour and completion can update it.

### D — LOW: Per-request ad-hoc connection + default host drift
The insert opens its own `psycopg2` connection inline (`:1135–1142`) with default `DB_HOST='postgres-2'`, rather
than reusing the file's existing DB helper. Fine in cloud (env-set), but it duplicates connection logic and adds a
connect per tour. Recommend reusing the shared helper / a pooled connection.

---

## What's correct and good
- Fail-closed exception handling (503) and anonymous rejection (401) are implemented exactly per the news pattern —
  Findings 1 and 3 are fully resolved and the two paths are now policy-consistent.
- Recording usage **in the enforcing service** is the right architecture; the remaining work is to make it the
  *sole* authoritative writer.
- Deny paths all return before the insert and before generation — no row, no spend on rejected requests.
- `CREATE TABLE IF NOT EXISTS` was harmless: the real `tour_requests` already has `request_string`, so the
  tracking service's insert still works (no schema break).

---

## Required before sign-off
1. **Finding A:** eliminate double-counting — one authoritative writer for `tour_requests` (recommend the
   orchestrator; stop/redirect the tracking-service write). Re-verify tester actually gets 100/day.
2. **Finding B:** don't let failed tours permanently consume quota (rollback/reconcile `started` rows).
3. **Finding C:** use the real `job_id`/UUID as `tour_id`, recorded so completion can update it.
4. **Re-run** the end-to-end tests after the above: free user blocked on 2nd tour (and *not* before); tester
   reaches 100/day; failed generation does not lock out a free user; DB-down → 503.

## Cross-references
- Prior tour review (findings being remediated): `claude_review_per_user_quota_implementation_2026_06_10.md`.
- News path (the correct single-writer reference): `claude_review_news_quota_failclosed_implementation_2026_06_10.md`
  — note its orchestrator both checks and records in one service with no second writer, which is why it has no
  double-count problem.
- A runnable tour-quota integration test (mirroring `test_news_quota_integration.py`) is recommended once Finding A
  is fixed, so "tester gets 100/day" and "free blocked on 2nd" become repeatable checks.

## Scope
Services-only review. Mobile handling of the new 401/503 (app currently handles 429) is a Mobile-AQ item.
