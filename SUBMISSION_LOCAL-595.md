# SUBMISSION — LOCAL-595: Subscription levels, part 1

**Branch:** `LOCAL-595-subscription-levels`  **Base:** `subscribed` (b87b93a)
**Agent:** Mac Mini Kiro
**Design of record:** `SUBSCRIPTION_LEVELS.md` (D613, ClickUp wdvrdayu5a)

## Scope

Schema + per-device allowance state + enforcement for the L1/L2/L3/L4/Tester
model, structured refusals (LOCAL-580 contract), the `/entitlements/*` and
`/purchases/verify` API, migration of existing local users, tests, and a live
check. Out of scope (left for 596/597/598): the L2 queue/seats, the
by-reference generation path, and the app + real IAP. L2 generate therefore
refuses with `by_reference_unavailable` until 597.

The wallet / PPU / Unlimited model is **superseded, not removed**: its tables
and functions stay in place and no new decision routes through them.

---

## Deliverable 1 — Schema (`migration/sql/012_subscription_levels.sql`)

Additive and idempotent (`ALTER … ADD COLUMN IF NOT EXISTS`, `INSERT … ON
CONFLICT`, `CREATE … IF NOT EXISTS`; no DELETE/DROP).

- **`plans`** gains one column per number in the levels table:
  `tours_per_month, fresh_per_pack, edits_per_pack, ops_per_pack, max_stops,
  max_new_stops_per_edit, by_reference_only, referrals_allowed, referral_period,
  seat_cap, can_sell, price_usd, inactivity_days`. The old quota columns and the
  `free/ppu/unlimited` rows are untouched.
- Rows `l1, l2, l3, l4, tester` seeded with the exact values from the doc. Every
  number is a column — the code holds no tier constants.
- **`device_entitlement`** (`user_id, level, pack_started_at, anniversary_at,
  fresh_used, edits_used, ops_used, last_activity_at`) — per-device state.
- **`purchases`** (`transaction_id UNIQUE, store, product, user_id, amount,
  verified_at, raw_status`) — server-side ledger, no personal data.

Verified idempotent against `audiotours_test` (applied twice; second run is a
no-op). The five rows read back exactly:

| plan | per_day | per_month | fresh/pack | edits/pack | ops/pack | max_stops | new/edit | by_ref | referrals | period | can_sell | price | inactivity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| l1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | f | 0 | — | f | 0 | — |
| l2 | 1 | 3 | — | — | — | 5 | 0 | t | 0 | — | f | 0 | 7 |
| l3 | 999 | — | 5 | 5 | — | 10 | 10 | f | 3 | lifetime | f | 10 | — |
| l4 | 999 | — | — | — | 25 | 25 | 10 | f | 5 | month | t | 25 | — |
| tester | 10 | 50 | — | — | — | 5 | 5 | f | 3 | month | f | 0 | — |

(`seat_cap` = 100 on l2 per the doc; NULL elsewhere.)

---

## Deliverable 2 — Enforcement (`subscription_levels.py`, wired via `entitlements.py`)

One decision point the orchestrator and editing service call:

```
check_operation(user_id, op, requested_stops=0, new_stops=0) -> allow | refusal
```

- `op ∈ generate / edit_add_stops / edit_text / listen / download /
  translate_reuse`.
- `edit_text / listen / download / translate_reuse` are **always allowed** at
  every level and never touch an allowance (re-voicing/listening is free).
- Counts per **day** and **month** (L2/Tester, from `tour_requests`), and per
  **pack** (`fresh_used` for L3, `ops_used` for L4). **L4 counts new + edit in
  one `ops` pool.**
- `max_stops` is clamped on allow; a request over it is refused with
  `stops_over_plan` (a stop list is a promise — matches the orchestrator's
  existing behaviour).
- Refusals use the **LOCAL-580 contract**: `error_code`, `error`, `message`,
  `suggestion`. error_codes emitted: `plan_limit_daily, plan_limit_monthly,
  pack_exhausted, level_cannot_generate, stops_over_plan, renewal_due,
  by_reference_unavailable`. Fail-closed on any internal error.
- `consume(user_id, op, new_stops)` bumps the pack counters after a gated op
  actually proceeds (re-exported as `consume_operation`).

**Wiring**
- `tour_orchestrator_service.py` generate path now calls
  `check_operation(user_id, 'generate', requested_stops=total_stops)`, returns
  the structured refusal with HTTP 429, clamps to `clamped_stops`, and calls
  `consume_operation` after the `tour_requests` row is written.
- `tour_editing_phase2.py` `_bulk_save_core` counts stops with `action='add'`;
  when `new_stops > 0` and a `user_id` is present it calls
  `check_operation('edit_add_stops', new_stops=N)` (429 on refusal) then
  `consume_operation`. A zero-new-stop save is a text-only edit — never gated.

---

## Deliverable 3 — Anniversary arithmetic

`add_one_calendar_month(payment_date)` = payment date + 1 calendar month,
clamped to the month's last day. Verified:
Jan 31 → Feb 28 (and Feb 29 in a leap year), May 31 → Jun 30, May 1 → Jun 1,
Jun 1 → Jul 1, Jun 13 → Jul 13 (Michael's example), Dec → Jan (year roll).

`is_renewal_due` is **inclusive** at the anniversary instant. At/after the
anniversary `check_operation` returns `renewal_due` for generate/edit while
**listening stays allowed**. `warn_renewal` is true within the 3 days before.
A device with no anniversary (never bought a pack) is never due and never
warned. The `/entitlements/me` and `/entitlements/app-open` payloads expose
`renewal_prompt` and `warn_renewal`.

---

## Deliverable 4 — API (`user-tracking/entitlements_api.py`, blueprint on the user-api)

Auth is the existing referral pattern: `X-API-Key == GATEWAY_API_KEY`.

- `GET /entitlements/me?user_id=…` → level, `allowances_left`, `anniversary_at`,
  `warn_renewal`, `renewal_prompt`, `can_sell`.
- `POST /entitlements/app-open {user_id}` → records activity; returns the same
  payload (with `renewal_prompt`).
- `POST /entitlements/lapse {user_id}` → drops to L1 (clears pack + counters).
- `POST /purchases/verify {store, transaction_id, product, user_id}` → verifies
  through an `IAPVerifier` interface; the **sandbox stub** is selected by
  `IAP_VERIFY_MODE=stub` (real Apple/Google land in LOCAL-598). The same
  `transaction_id` twice → the second is refused (409, enforced by the
  `purchases.transaction_id UNIQUE` and an in-flight catch). A verified L3/L4
  purchase sets the level, resets the pack and sets the anniversary.

The blueprint is self-contained (Flask + psycopg2 only) so the user-api
build context (`./user-tracking`) stays intact; its anniversary/device-state
logic mirrors `subscription_levels.py` exactly.

---

## Deliverable 5 — User migration (`migration/sql/013_migrate_users_to_levels.sql`)

Maps `unlimited, ppu, USER-1073427300 → tester` and `free → l2` into
`device_entitlement`. **No DELETE**, old `plans` rows kept, `users.plan`
unchanged. `ON CONFLICT (user_id) DO NOTHING` so a device that later bought a
pack is never clobbered — safe to re-run.

Row counts on the local `audiotours` DB (reported by the migration's
`RAISE NOTICE`):

```
BEFORE: users by plan: free=35  ppu=35  unlimited=2  other/NULL=0
        device_entitlement rows before: 0
INSERT 0 35   (free   -> l2)
INSERT 0 37   (ppu+unlimited -> tester)
INSERT 0 0    (USER-1073427300 explicit safeguard — already covered)
AFTER:  device_entitlement rows after: 72
        device_entitlement by level: l1=0  l2=35  tester=37  other=0
```

Re-run is idempotent (`INSERT 0 0` on every statement). Old `free/ppu/unlimited`
rows confirmed still present; `users.plan` unchanged (`free=35, ppu=35,
unlimited=2`).

---

## Deliverable 6 — Tests (`tests/test_local595_*.py`) — 48 pass

- **`test_local595_anniversary.py`** (pure, no DB): every anniversary case in
  the doc, renewal inclusivity, and the 3-day warning window.
- **`test_local595_enforcement.py`** (DB-backed): every limit in the table at
  **both edges** — L1 refusal, L2 by-reference + daily cap + stop ceiling, L3
  fresh/edit pack edges and exhaustion, L4 25-stop ceiling and the **combined
  new+edit ops pool** exhausting on a mix, Tester daily/stop/edit edges, and the
  renewal gate (blocks generate, allows listen). Refusals are asserted to carry
  the full LOCAL-580 structure.
- **`test_local595_api.py`** (Flask test client): auth 401, me→L1, app-open,
  `/purchases/verify` L3/L4 grants, **transaction replay → 409**, unknown
  product → 400, empty-transaction rejection.

```
python3 -m pytest tests/test_local595_anniversary.py \
                  tests/test_local595_enforcement.py \
                  tests/test_local595_api.py -q
48 passed
```

**Existing tests (unchanged from base — `git diff b87b93a..HEAD` on these files
is empty):**

| suite | exit |
|---|---|
| `tests/test_local67_entitlement_gate.py` | 1 — pre-existing: the file references a pytest fixture `test_users` that it never defines (collection error, not introduced by this branch) |
| `tests/billing_dry_run/test_entitlements.py` | 0 |
| `test_referral_flow.py` | 5 — no items collected under this invocation (service-dependent) |
| `tests/test_local114_referral_wiring_guard.py` | 0 |

---

## Deliverable 7 — Live check (own containers, no OpenAI spend)

Built **my own** images and ran them on `development_default`, never touching
any `audioura-*` container (verified still running with their original uptimes
afterward):

- `local595-user-api` (from `./user-tracking`) — host `5603` → `5000`.
- `local595-orchestrator` (`Dockerfile.local595-orchestrator` +
  `local595_orchestrator_stub.py`) — host `5602` → `5002`. The stub imports the
  **real** `entitlements.check_operation` / `consume_operation` and reproduces
  the production generate-gate sequence, but **stubs the generator** — $0.00
  OpenAI/Gemini/TTS spend (well under the $0.50 cap).

Dedicated DB `audiotours_local595` (base tables + migration 012). Device
`LIVE595-…`, `IAP_VERIFY_MODE=stub`, `GATEWAY_API_KEY=live595-key`.

```
STEP 1  GET /entitlements/me            → 200  level=l1  renewal_prompt=false
STEP 2  POST /entitlements/app-open     → 200  level=l1
STEP 3  POST /generate-complete-tour    → 429  error_code=level_cannot_generate
          {"allowed":false,"error_code":"level_cannot_generate",
           "message":"The free install level does not include generating new tours.",
           "suggestion":"Buy a $10 pack for 5 new tours, or join the free queue."}
STEP 4  POST /purchases/verify (l3)     → 200  granted_level=l3  fresh_left=5
          anniversary_at=2026-11-06T19:11:48  verified=true
STEP 5  5 × /generate-complete-tour     → 200, 200, 200, 200, 200  (generator stubbed)
STEP 5b GET /entitlements/me            → 200  level=l3  fresh_left=0
STEP 6  6th /generate-complete-tour     → 429  error_code=pack_exhausted  used=5 max=5
          {"allowed":false,"error_code":"pack_exhausted",
           "message":"You've used all 5 new tours in your pack.",
           "suggestion":"Buy another $10 pack for 5 more new tours."}
STEP 7  POST /entitlements/lapse        → 200  level=l1
STEP 7b POST /generate-complete-tour    → 429  error_code=level_cannot_generate
```

Containers were torn down after the walk (`docker run --rm`); the dedicated DB
was left in place. No GCloud touched.

---

## Files

New:
- `migration/sql/012_subscription_levels.sql`
- `migration/sql/013_migrate_users_to_levels.sql`
- `subscription_levels.py`
- `user-tracking/entitlements_api.py`
- `tests/test_local595_anniversary.py`
- `tests/test_local595_enforcement.py`
- `tests/test_local595_api.py`
- `local595_orchestrator_stub.py`, `Dockerfile.local595-orchestrator` (live-check harness)

Changed:
- `entitlements.py` — re-exports `check_operation` / `consume_operation` and the
  level helpers from `subscription_levels` (wallet/PPU paths untouched).
- `tour_orchestrator_service.py` — generate path uses `check_operation` + consume.
- `tour-editing (tour_editing_phase2.py)` — add-stops path uses `check_operation` + consume.
- `user-tracking/app.py` — registers the entitlements blueprint.

Not edited (per process): `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
`WORK_QUEUE.md`, `SUBSCRIPTION_LEVELS.md`, `.continuous_dev/STATUS.md`.


---

# r2 — LOCAL-595B: four defects fixed

**Branch:** `LOCAL-595-subscription-levels` (continued, base `f15b504`)
**Agent:** Mac Mini Kiro
**Why it bounced:** LEAD review 2026-10-06 found r1 solid (schema, arithmetic,
API, 48 tests) but flagged four defects. All four are fixed below. Everything
from r1 is kept.

## Defect 1 — Michael's device was `l2`, not `tester`

**Root cause.** In `013_migrate_users_to_levels.sql` the `free -> l2` INSERT ran
first with `ON CONFLICT (user_id) DO NOTHING`. Michael's `USER-1073427300`
(plan `free`) matched it and got an `l2` row; the later explicit tester INSERT,
also `DO NOTHING`, was then a no-op. L2 generate refuses with
`by_reference_unavailable`, so his phone could not generate any tour. Live DB
confirmed: `USER-1073427300 | l2`.

**Fix (`migration/sql/013`).**
- Exclude his device id from the `free -> l2` and `ppu/unlimited -> tester`
  sweeps (`AND secret_id <> :'michael_user_id'`).
- Assign tester explicitly with an UPSERT that only promotes a
  migration-assigned row, never a real purchase:
  `ON CONFLICT (user_id) DO UPDATE SET level='tester' WHERE device_entitlement.level IN ('l1','l2')`.
- Still additive, no DELETE, idempotent, safe to re-run.

**Live row corrected (an UPDATE, guarded to l1/l2 so a paid pack is never
clobbered — the same semantics as the migration):**

```
BEFORE:  USER-1073427300 | l2
UPDATE device_entitlement SET level='tester', updated_at=NOW()
  WHERE user_id='USER-1073427300' AND level IN ('l1','l2');   -- UPDATE 1
AFTER:   USER-1073427300 | tester
```

Run against `development-postgres-2-1` / db `audiotours` (the dev stack DB, host
port 5433). No `audioura-*` container was touched.

## Defect 2 — a failed tour must not consume the allowance

**Root cause.** `consume_operation` ran at request time in
`generate_complete_tour`, before generation, and `_count_fresh_generations`
counted every orchestrator `tour_requests` row regardless of status. A listener
who hit a factual-integrity / credit / storage failure lost one of their 5
tours, and L2/Tester period counts included in-flight and failed rows.

**Fix — consume on successful delivery only, with a reservation for
concurrency.**
- `subscription_levels._count_fresh_generations` now counts **only
  `status='completed'`** orchestrator rows. In-flight (`started`) and `failed`
  rows never spend an L2/Tester daily or monthly allowance.
- The request-time counter bump is now a **reservation** (`reserve`, with
  `consume` kept as an alias). It is the concurrency guard: two parallel
  requests cannot both pass a limit of 1. A new `release` gives the unit back,
  flooring at 0 (`GREATEST(x-1,0)`), so a double release can never go negative.
- `tour_orchestrator_service.py`:
  - request time → write `tour_requests` row `started` + `reserve_operation`.
  - new helpers `_set_tour_request_status(job_id, status)` (updates the
    orchestrator's own row, keyed `tour_id = job_id`) and
    `_release_generation_reservation(user_id, job_id, reason)`.
  - **completed transition** → mark the row `completed` (fresh keeps the
    reservation — it is the real consumption).
  - **every failure path** → mark `failed` + release: the no-audio-files path,
    the store-failed path, and the top-level exception handler. The old blanket
    `DELETE`-on-exception rollback is replaced by mark-`failed` + release (same
    effect on counting, plus the pack unit is now correctly returned and the
    attempt stays auditable).

## Defect 3 — a cache hit is not a "fresh" tour

**Root cause.** A request served from the cache or fully from the stop pool
costs ~$0, but it still consumed `fresh_used`. The spec prices L3 as "5 *fresh*
tours".

**Fix.** When `store_audio_tour` returns `store_action == "already_exists"`
(cache / stop-pool reuse), the orchestrator **releases** the reserved
`fresh_used` (L3) / `ops_used` (L4) unit, so a cache hit consumes no paid
allowance. The row still reaches `completed`, so a cache hit **still counts
toward the L2/Tester daily & monthly volume caps** (those limit volume, not
cost) — exactly as the defect requires. The D47 wallet "charge on reuse" is a
separate legacy concern and is unchanged; the LOCAL-595 pack allowance is
independent of it. (L4's ops pool is released on a cache hit for the same cost
reason the defect gives for L3; the spec names `fresh_used`, and the L4 ops pool
is the equivalent paid pool — flagged here for the LEAD.)

## Defect 4 — the edit gate failed open

**Root cause.** `tour_editing_phase2._bulk_save_core` only ran the add-stops
gate `if _new_stops > 0 and _edit_user_id:` — when no id was present it skipped
the gate, so any add-stops edit without an id was free and unlimited.

**Fix — fail closed.** The decision now lives in one pure, framework-free helper
`subscription_levels.evaluate_edit_add_stops(data)` (so the service and the
tests share one implementation). An add-stops edit with no `user_id`/`secret_id`
is refused with **HTTP 401 `error_code=user_id_required`**. A text-only edit
(no `action='add'`) is never gated. `_bulk_save_core` calls the helper and, on
an allowed add-stops edit, consumes the L3 `edits_used` / L4 `ops_used`.

**What the app sends today (reported, as asked).** The subscribed app's edit
path is `TourEditingService.updateMultipleStops` →
`POST /tour/<id>/update-multiple-stops` with body `{'stops': [...]}` only, plus
the `X-API-Key` header (`Endpoints.apiHeaders`). **It sends no `user_id` and no
`secret_id`** in the body or headers for the edit path. So with this fix the
current app's add-stops edits are refused with 401 `user_id_required` — the
correct fail-closed behaviour. **LOCAL-598 will add the device id to the edit
request body.** (Text-only re-voice edits are unaffected — they are never
gated.)

## Tests — `tests/test_local595_*.py` = 67 passed

```
python3 -m pytest tests/test_local595_anniversary.py \
                  tests/test_local595_enforcement.py \
                  tests/test_local595_api.py \
                  tests/test_local595_edit_gate.py -q
67 passed
```

New / changed:
- `tests/test_local595_edit_gate.py` (new) — defect 4, drives the shared
  `evaluate_edit_add_stops` helper (no Flask/boto3): add-stops with no id → 401
  `user_id_required`; `secret_id` alias accepted; text-only / no-stops never
  gated; L1 refused `level_cannot_generate`; L3 allowed; over-ceiling →
  `stops_over_plan`.
- `tests/test_local595_enforcement.py` — `_add_tour_requests` now defaults to
  `status='completed'`; added:
  - `TestDefect2CompletedOnlyCounting` — `started`/`failed` rows don't count,
    `completed` rows do; Tester mixed-status.
  - `TestDefect2ReserveRelease` — reserve→release restores `fresh_used`; a
    reservation stands without release; release floors at 0; the reservation is
    the concurrency guard; L4 ops pool reserve/release.
  - `TestDefect3CacheHitNotFresh` — a cache hit releases `fresh_used` yet the
    completed row still trips the L2 daily cap.

**Existing suites re-run (exits):**

| suite | exit | note |
|---|---|---|
| `tests/billing_dry_run/test_entitlements.py` | 1 | 6 passed, 1 failed — `test_get_news_used_period` `UniqueViolation` on a leftover `art-dryrun-N` news row. **Pre-existing**: reproduced identically on the clean base with my changes `git stash`ed. Not introduced by this branch and unrelated to LOCAL-595. |
| `tests/test_local67_entitlement_gate.py` | 1 | pre-existing collection error — references an undefined `test_users` fixture (same as r1). |
| `test_referral_flow.py` | 5 | no items collected under this invocation (service-dependent; same as r1). |
| `tests/test_local114_referral_wiring_guard.py` | 0 | — |

## Live walk (own stub container, `is_test` device, $0.00 spend)

Built **my own** image `local595b-orchestrator`
(`Dockerfile.local595-orchestrator` + the extended
`local595_orchestrator_stub.py`) on `development_default`, against a **dedicated
DB `audiotours_local595b`** (base tables + migration 012). The stub imports the
**real** `subscription_levels` / `entitlements` and reproduces the production
reserve → mark-`completed`/`failed` → release lifecycle for an `outcome` of
`fresh` / `cache_hit` / `fail`. The generator is fully stubbed — **$0.00
OpenAI/Gemini/TTS**, far under the $0.50 cap. **No `audioura-*` container was
touched** (all 13 still up afterward).

Device `LIVE595B-TESTDEV`, granted L3 via the real `grant_pack`:

```
STEP 1  GET /entitlements/me                 → level=l3  fresh_used=0  completed_today=0
STEP 2  POST generate outcome=fail           → allowed=true  delivered=false
STEP 2b GET /entitlements/me                 → fresh_used=0  completed_today=0   (failure consumed nothing — defect 2)
STEP 3  POST generate outcome=cache_hit       → allowed=true  delivered=true
STEP 3b GET /entitlements/me                 → fresh_used=0  completed_today=1   (cache hit kept fresh_used at 0 — defect 3 — but still counts for volume)
STEP 4  POST generate outcome=fresh          → allowed=true  delivered=true
STEP 4b GET /entitlements/me                 → fresh_used=1  completed_today=2   (fresh success consumed exactly one)
```

`tour_requests` for the device: **2 completed + 1 failed**;
`device_entitlement`: `fresh_used=1`. The stub container was torn down after the
walk; the dedicated DB was left in place. Michael's live row re-confirmed
`tester` afterward. No GCloud touched.

## Files (r2)

Changed:
- `migration/sql/013_migrate_users_to_levels.sql` — defect 1 upsert.
- `subscription_levels.py` — completed-only counting; `reserve`/`release`;
  pure `evaluate_edit_add_stops` helper.
- `entitlements.py` — re-exports `reserve_operation`, `release_operation`,
  `evaluate_edit_add_stops`.
- `tour_orchestrator_service.py` — reserve at request time; mark
  completed/failed; release on failure and on cache hit.
- `tour_editing_phase2.py` — gate via the shared helper, fail-closed 401.
- `local595_orchestrator_stub.py` — extended with the reserve/release lifecycle
  and `/entitlements/me` for the walk.
- `tests/test_local595_enforcement.py` — defect 2/3 tests + helper default.

New:
- `tests/test_local595_edit_gate.py` — defect 4.

Not edited (per process): `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
`WORK_QUEUE.md`, `SUBSCRIPTION_LEVELS.md`, `.continuous_dev/STATUS.md`.
