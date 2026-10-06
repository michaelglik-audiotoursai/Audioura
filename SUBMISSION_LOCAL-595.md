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
