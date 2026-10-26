# SUBMISSION — LOCAL-777: "Tours left" counts refused/failed requests

**Branch:** `LOCAL-777-allowance-completed-only`
**Base:** `subscribed` @ `572a4844` (verified `git merge-base --is-ancestor 572a4844 HEAD` → 0)

## Problem

On the Plan screen, "new tours left today / this month" counted **every**
`tour_requests` row for the device, with no `status` filter. So a request that
was still in flight (`status='started'`) or that was **refused/failed**
(`status='failed'`) reduced the displayed allowance. On GCloud_Storied
(TestFlight 79, USER-41659366, Free/L2 = 1/day, 3/month), one refused request
made the screen read **"0 new tours left today · 1 this month"** — telling the
user they couldn't generate when the real gate would still let them.

The real gate — `subscription_levels._count_fresh_generations()` — already
counts **delivered only** (`source='orchestrator' AND status='completed'`,
D613 / LOCAL-595B). The display and the free-plan counter were out of step
with it.

## One shared definition of "a tour that counts"

`status='completed'`, the same predicate `_count_fresh_generations` uses:

```sql
WHERE secret_id = %s AND source = 'orchestrator'
  AND status = 'completed' AND <scope>
```

Applied to every display/gate counter that was missing it.

## Counters found (grep of `COUNT(*) FROM tour_requests`) and classification

| file:line | counter | role | action |
|---|---|---|---|
| `user-tracking/entitlements_api.py` `_allowances_left` (today) | `tours_today_left` | **display** | **FIXED** — added `status='completed'` |
| `user-tracking/entitlements_api.py` `_allowances_left` (month) | `tours_this_month_left` | **display** | **FIXED** — added `status='completed'` |
| `entitlements.py` `get_tours_used_today` | free-plan daily gate (`_check_tour_quota_free`) | **gate** | **FIXED** — added `status='completed'` |
| `subscription_levels.py` `_count_fresh_generations` | the real L2/Tester gate | gate | already completed-only (the canonical predicate — untouched) |
| `translation-service/subscription_levels.py` `_count_fresh_generations` | mirror of the above | gate | already completed-only — untouched |
| `local595_orchestrator_stub.py` | test stub | test | already completed-only — untouched |
| `user-tracking/app_fixed_final.py:232` | admin `/users` all-time "total records" | admin audit | **out of scope** — all-time total with no source/date/status filter; not a "tours left" counter. Changing it would alter the meaning of an audit total. |

`get_tours_used_today` still gates: it is called by `_check_tour_quota_free`
(`entitlements.py`) to deny a free user over the daily cap. The fix keeps that
gate working while making it agree with the display and with the levels gate.

No rows were touched (no sweep of stale `started` rows — LEAD ruling). With the
completed-only predicate those rows simply don't count.

## Tests

**New (red-first):** `tests/test_local777_allowance_completed_only.py` — seeds
the ticket scenario {completed today, failed today, started 9 days ago, refused
today} and asserts, for the same rows, that the **display**
(`entitlements_api._allowances_left`), the **free-plan gate**
(`entitlements.get_tours_used_today`) and the **real gate**
(`subscription_levels._count_fresh_generations`) all count exactly **1** (the
single completed row): today-left = 0 (cap 1 − 1), month-left = 2 (cap 3 − 1),
and display-used == gate-used. Before the fix 4 of 5 failed (display/free-gate
counted 3); after the fix **5/5 pass**.

**Existing suites — green on base and branch:**

| suite | result (base == branch) |
|---|---|
| `test_local595_enforcement.py` | 31 passed |
| `test_local595_api.py` | 10 passed |
| `test_local595_edit_gate.py` | 8 passed |
| `test_local595_anniversary.py` | 18 passed |
| `test_local597_by_reference.py` | 9 passed |
| `test_local597_guard.py` | 13 passed |
| `test_local604_plan.py` | 21 passed |

**`tests/service_layer_dry_run/test_entitlements_gate.py`:** three tour tests
seeded a row relying on the DB default `status='started'` and expected it to
count as a used tour — i.e. they encoded the **old buggy contract**. Their
seeds were changed to `status='completed'` (matching the news seeds already in
the same file and the canonical predicate). `test_tour_quota_exceeded_free`
and `test_tour_quota_healthy_returns_exact_count` now pass.

**Pre-existing failures (present on base `572a4844`, NOT caused by this change
— confirmed by stashing the edits and re-running):**
- `test_entitlements_gate.py::test_tour_quota_refusal_via_http` — a
  `@pytest.mark.service` test that drives the orchestrator in-process; it fails
  with `relation "device_entitlement" does not exist` in that client's DB, well
  before the counter under test is reached.
- `billing_dry_run/test_entitlements.py::test_get_news_used_period` —
  `UniqueViolation` on `article_id=art-dryrun-4` (news seeding; nothing to do
  with `tour_requests`).
- `test_local67_entitlement_gate.py` — 13 errors, missing `test_users` fixture.

## Live test (own containers, ≈ $0)

Isolated stack `docker-compose.local777-proof.yml`, project `-p local777`, OWN
postgres volume, **spare ports 55434 (pg) / 55003 (user-api)**. The user-api is
built from `./user-tracking` (so it carries the edited `entitlements_api.py`)
and serves the real HTTP `GET /entitlements/me`. The shared `audioura-*` and
`development-postgres-2-1` containers were never touched. DB seeded from
migrations 010 + 012 at init; 015 + 016 applied to the running DB for the full
`/me` payload (l2_seats tables + `plans.display_name`/`hidden`).

Test device `L777-live-c693611c`, level L2 (1/day, 3/month), via real HTTP:

```
BEFORE (0 requests):               allowances_left = {tours_today_left: 1, tours_this_month_left: 3}
make ONE refused by_reference req  (writes a status='failed' tour_requests row)
AFTER (1 refused request):         allowances_left = {tours_today_left: 1, tours_this_month_left: 3}   ← UNCHANGED
```

Positive control (counter still works): add ONE `status='completed'` tour →
`{tours_today_left: 0, tours_this_month_left: 2}`; the `failed` row is still
ignored.

**Rows written (all to the OWN local777 DB; live/shared DB untouched):**
2 `tour_requests`, 1 `device_entitlement`, 1 `users`. Budget ≈ $0 (no
generation, no external API calls). Stack torn down with `down -v`.

## Reproduce the live test

```bash
docker compose -p local777 -f docker-compose.local777-proof.yml up -d --build
# migrations 015 + 016 applied to the running DB for the full /me payload:
#   docker cp migration/sql/015_l2_seats_queue.sql        local777-postgres-2-1:/tmp/015.sql
#   docker cp migration/sql/016_plan_display_level_codes.sql local777-postgres-2-1:/tmp/016.sql
#   docker exec local777-postgres-2-1 psql -U admin -d audiotours_test -f /tmp/015.sql
#   docker exec local777-postgres-2-1 psql -U admin -d audiotours_test -f /tmp/016.sql
# seed an L2 device, GET /entitlements/me, insert a status='failed' row, GET again.
docker compose -p local777 -f docker-compose.local777-proof.yml down -v
```

> The compose file mounts `./local777-initdb` (copies of migrations 010 + 012)
> as the DB init dir; that directory is a disposable build artifact and is **not
> committed**. Recreate it with:
> `mkdir -p local777-initdb && cp migration/sql/010_create_subscribed_database.sql local777-initdb/01_010.sql && cp migration/sql/012_subscription_levels.sql local777-initdb/02_012.sql`

## Files changed

- `user-tracking/entitlements_api.py` — `_allowances_left`: `status='completed'` on the today and month counts.
- `entitlements.py` — `get_tours_used_today`: `status='completed'`.
- `tests/test_local777_allowance_completed_only.py` — new red-first test (display == gate == completed-only).
- `tests/service_layer_dry_run/test_entitlements_gate.py` — three tour seeds → `status='completed'` (old contract fixed).
- `docker-compose.local777-proof.yml` — isolated proof harness for the live test.
