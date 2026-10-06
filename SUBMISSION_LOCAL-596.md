# SUBMISSION — LOCAL-596: L2 seats, FIFO queue, claim offers, 7-day eviction, referral seats

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-596-l2-seats` (from `subscribed` @ `04eee1d`)
**Base:** subscribed — `git merge-base --is-ancestor 04eee1d HEAD` exits 0.
**Design of record:** `SUBSCRIPTION_LEVELS.md`, "L2 seats and queue" (D613).

Builds directly on LOCAL-595 (`subscription_levels.py`, `user-tracking/entitlements_api.py`,
`referral_engine.py`, migrations 012–014) — it extends them, it does not duplicate them.

## No constants in code
Every number is read at runtime:
- **seat cap (100)** and **inactivity days (7)** → `plans.l2` columns (migration 012).
- **auto-grant threshold (50)**, **offer expiry (72 h)**, and **max offer misses (2)** →
  the singleton `l2_settings` row (migration 015).

"Seats in use" is **counted**, never stored: a device holds a seat iff
`device_entitlement.level = 'l2'`. There is no denormalised counter to drift, and referral
seats count automatically because a referral grant sets `level='l2'` like any other seat.

---

## What shipped, by deliverable

### 1. Schema — migration 015 (`migration/sql/015_l2_seats_queue.sql`)
Additive and idempotent (every `CREATE … IF NOT EXISTS`, settings `INSERT … ON CONFLICT DO
NOTHING`; no `DELETE`, no `DROP`). Verified: applies clean, and a second run skips everything
(`INSERT 0 0`).
- `l2_queue` — `user_id` **UNIQUE** (PK), `joined_at`, `status`
  (`waiting`/`offered`/`claimed`/`expired`/`left`), `offer_misses`.
- `l2_offers` — `user_id`, `code` (UNIQUE), `offered_at`, `expires_at`, `claimed_at`, `status`.
- `l2_settings` — singleton (`id BOOLEAN PK CHECK(id=TRUE)`): `auto_grant_threshold=50`,
  `offer_expiry_hours=72`, `max_offer_misses=2`.

### 2. Install auto-grant (`l2_seats.grant_on_install`, wired into `subscription_levels.ensure_device`)
A new device is granted **L2 only if** `seats_in_use < auto_grant_threshold` **AND** the queue
has no `waiting` entry; otherwise **L1**. The count-and-insert is serialized by a
transaction-scoped Postgres advisory lock (`pg_advisory_xact_lock`, fixed key), so **two
parallel installs at 49 seats cannot both pass** — proven by a threaded test. `ensure_device`
with no explicit level now returns the resulting level and fails closed to L1 if seat state is
unreadable (never auto-grants a scarce seat on error). An explicit `level=` keeps the old
unconditional insert for migrations/tests.

### 3. Queue API (`user-tracking/entitlements_api.py`)
- `POST /l2/queue/join` — L1 only (409 `already_l2` if the device holds a seat); idempotent
  (re-join returns the same position).
- `POST /l2/queue/leave` — idempotent; also expires any live offer so the seat frees next cycle.
- `GET /entitlements/me` — now returns `queue_position` (1-based FIFO place) and
  `pending_offer {code, expires_at}`.
- `POST /l2/claim {code}` → L2 when the code is valid, unexpired, belongs to this device, and a
  seat is free under the 100 cap (claim serialized by the same seat lock). Structured refusals
  (LOCAL-580 contract): `claim_invalid_code` 400, `claim_wrong_device` 403, `claim_expired` 409,
  `claim_seats_full` 409.

### 4. Offers job (`l2_seat_job.py`) — idempotent, concurrency-safe
One cycle (`l2_seats.run_seat_cycle`), in order:
1. **evict** L2 devices idle ≥ `inactivity_days` → L1, seat freed (any app-open/listen/download/
   article resets `last_activity_at` via the existing `record_activity`);
2. **expire** offers past 72 h → back to the queue **tail** (`waiting`, fresh `joined_at`),
   or **dropped** (`expired`) after `max_offer_misses` misses;
3. **offer** each free seat (under the cap, minus live offers) to the head of the FIFO.
Running it twice back-to-back makes no second offer (the first run flipped rows to `offered`),
and seat decisions hold the advisory lock. A failed cycle rolls back and changes nothing.

`l2_seat_job.py` is both a **standalone CLI** (`python3 l2_seat_job.py [--daemon] [--quiet]`)
and an **importable runner** (`run_once(conn=…)`, `run_forever(stop_event=…)`).

**Scheduling decision (the task asked us to say which and why).**
The task offered two homes: a line in launchd's `autonomy_tick.sh`, *or* an orchestrator
background thread "if that is the existing pattern." **There is no `autonomy_tick.sh` in this
worktree** — the launchd tick is a *task-file dispatcher* (it claims unclaimed
`new_kiro_session_is_required_*.md` files), not a general-purpose cron. The orchestrator, by
contrast, already runs background work as **daemon threads** (`GENERATION_MODE=thread`,
`_ACTIVE_GENERATION_THREADS`). So the hourly schedule is wired as a **guarded orchestrator daemon
thread** in `tour_orchestrator_service.py` `__main__`: it is **OFF by default** and starts only
when `L2_SEAT_JOB_ENABLED=true` (interval `L2_SEAT_JOB_INTERVAL_SECONDS`, default 3600), so
existing deployments are unaffected until explicitly opted in. The standalone CLI remains for
manual use or a future launchd/cron entry — **one authority, two ways to invoke.**
`Dockerfile.orchestrator` now ships `l2_seats.py` + `l2_seat_job.py`.

### 5. Referral seats (`referral_engine.redeem_referral_for_seat`, wired into `referral_endpoints`)
A redeemed referral grants the **redeemer** an L2 seat, **counted against the 100 cap** and
**refused with a structured error when full** (Michael accepts referrals can starve the queue).
In one transaction it validates the code, blocks self-referral, gates on the **referrer's**
allowance read from `plans` (**L3 3 lifetime, L4 5/month, Tester 3** — no constants), blocks
duplicates (UNIQUE backstop), then grants the seat under the seat lock. The allowance is checked
*before* the redemption is recorded, so a refusal costs no slot; the seat grant and redemption
row commit together. `POST /referral/redeem` returns `granted_level: "l2"` on success, else
`referral_duplicate` 409 / `referral_self` 403 / `referral_unknown_code` 404 /
`referral_allowance_spent` 409 / `referral_seats_full` 409.

### Shared core (`l2_seats.py`)
All of the above delegates to one **framework-free** module (no Flask/boto3) so the install
path, the user-api, and the job share a single source of truth. It is mirrored into
`user-tracking/l2_seats.py` because that container's build context is `./user-tracking` (same
constraint and pattern as `entitlements_api.py` in LOCAL-595).

---

## 6. Tests (`tests/test_local596_*.py`) — 32 pass

```
python3 -m pytest tests/test_local596_seats.py tests/test_local596_api.py tests/test_local596_referral.py -q
................................                                         [100%]
32 passed
```

Coverage:
- **threshold edges** — below → L2, at threshold → L1, waiting queue blocks auto-grant;
- **concurrency** — two parallel installs at one free seat → exactly one L2 (advisory lock);
- **cap edges** — one free seat → claim granted; full → `claim_seats_full`;
- **eviction** — evicted at exactly 7 days; **not** evicted at 6 d 23 h;
- **offer expiry** — expired offer requeues (miss 1) then drops to `expired` (miss 2);
- **claim validation** — bad code, other device's code, expired offer;
- **referral** — L3=3 / L4=5 / Tester=3 counting, self + duplicate + unknown + **full-cap**
  refusals, endpoint grants `l2` / returns `referral_seats_full` 409;
- **idempotency** — `run_seat_cycle` twice makes no second offer.

**LOCAL-595 suites rerun — green, no regressions:**

```
tests/test_local595_api.py          -> exit 0 (10 passed)
tests/test_local595_edit_gate.py    -> exit 0 (8 passed)
tests/test_local595_enforcement.py  -> exit 0 (31 passed)
tests/test_local595_anniversary.py  -> exit 0 (18 passed)
```

---

## 7. Live walkthrough (`run_local596_live.py`) — $0 spend

Ran against a **stub** `local596-user-api` container on `development_default` (HTTP calls to the
stub only — **no `audioura-*` container was touched, rebuilt, or renamed**) and `audiotours_test`.
Synthetic device ids all prefixed `LOCAL596-`.

```
[0] Michael's PRODUCTION row BEFORE: USER-1073427300|admin
[1] Baseline: seats_in_use=0, threshold=50, cap=100
[2] Filling to 99 seats (99 synthetic L2 devices)...  seats_in_use now = 99
[3] Install LOCAL596-LIVE-NEWBIE-… -> level=l1 (seats>=threshold)
[4] Join via stub API -> queue_position=1
[5] Aged seat LOCAL596-LIVE-FILL000-… to 8 days idle
[6] Job ran. evicted=True, offered_to_newbie=True   offer code = L2OF-…
[7] Claim via stub API -> level=l2
[8] Final seats_in_use=99 (99 - 1 evicted + 1 claimed)
[9] Cleanup: removed exactly 100 LOCAL596- ids; seats back to baseline 0;
    residual LOCAL596- rows: device_entitlement=0, l2_queue=0, l2_offers=0
[10] Michael's PRODUCTION row AFTER: USER-1073427300|admin
WALKTHROUGH COMPLETE — all assertions passed, $0 spend
```

- **Michael's device (`USER-1073427300`, level `admin`) is unaffected** — `admin` before and
  after, read from the production `audiotours` DB.
- Cleanup used an **exact captured id list** (100 ids); no other `DELETE`. Residual `LOCAL596-`
  rows = 0 across all three tables.
- The stub container was removed afterward; the 13 `audioura-*` containers remained running and
  untouched. **No GCloud.**

---

## Files
- `migration/sql/015_l2_seats_queue.sql` (new) — schema + settings.
- `l2_seats.py` (new) + `user-tracking/l2_seats.py` (mirror) — shared seat core.
- `l2_seat_job.py` (new) — hourly job (CLI + runner).
- `subscription_levels.py` — seat-aware `ensure_device`.
- `user-tracking/entitlements_api.py` — queue/claim endpoints + `/me` additions.
- `referral_engine.py`, `referral_endpoints.py` — referral → L2 seat grant.
- `tour_orchestrator_service.py`, `Dockerfile.orchestrator` — guarded background-thread wiring.
- `tests/test_local596_seats.py`, `tests/test_local596_api.py`, `tests/test_local596_referral.py`.
- `run_local596_live.py` — live walkthrough harness.

## Process
Committed and pushed after each step; `git rev-list --count origin/subscribed..HEAD` ≥ 1
throughout (final value reported at push). Not edited: `DECISIONS.md`, `CLAUDE.md`,
`BACKLOG.md`, `WORK_QUEUE.md`, `SUBSCRIPTION_LEVELS.md`, `.continuous_dev/STATUS.md`.
