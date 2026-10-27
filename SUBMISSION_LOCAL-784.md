# SUBMISSION — LOCAL-784: Escalation ladder before "nothing found" + escalation log + learned routing (D722)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-784-escalation-ladder`
**Base:** `subscribed` @ `208ceac6` — `git merge-base --is-ancestor 208ceac6 HEAD` = 0 (HEAD is 208ceac6 + this branch; LOCAL-783 and LOCAL-785 are merged into it).

## Why — Michael, 2026-10-26 (D722)
LOCAL-779B refused "Middle Eastern restaurants near me, West Roxbury" because the
free OSM tool found nothing, while Google lists three (Al Wadi, Stardust, Bread
Thyme). Michael's rule: **if the cheap tools find nothing, try a dearer one before
refusing. If it really is nothing we spent little; if it was our mistake we avoided
an embarrassment. Record each case and learn from it.**

## What was built

### `escalating_lookup.py` (new) — the ladder, the log, the learned routing
`escalating_lookup(kind, query, scope, needed, *, tier_a, tier_b, verify, …)`
runs tiers until the **first** one yields ≥ `needed` verified results:

- **tier (a)** — the current cheap path (free Nominatim). `D722_FORCE_CHEAP_MISS=1`
  forces it empty (test / live-proof only).
- **tier (b)** — Serper Places with `ll` (LOCAL-783), metered $0.002/query.
- **tier (c)** — Gemini with Google-Search grounding: a structured JSON list of
  real places `{name, address}`, **each re-verified on Places/geocode inside the
  scope before use** — an unverifiable Gemini name is **dropped**. Skipped when a
  grounding guard is active (an L2 by-reference build forbids grounding/SERP).

A **per-request $0.10 escalation budget** (`D722_ESCALATION_BUDGET_USD`) caps the
dearer tiers: before tier b/c the ladder checks the meter's `check_daily_limit()`
**and** the running escalation spend; a tier that would breach the budget is not
attempted.

**Learned routing** (`lookup_routing`): `region_key` = a dependency-free geohash-5
of the scope centre (~5 km cell; West Roxbury → `drt2s`). Every cheap-tier miss
increments `misses_7d` for `(category, region_key)`; once it is **≥ 3 in 7 days**
the ladder **starts at the tier that worked**, skipping the known-empty cheap call,
and logs a `[D722] route hit` line. Every routing row is **reversible** — deleting
it restores start-at-tier-a with no code change (a LEAD lever, never a code path).

### `migration/sql/055_lookup_escalations.sql` (new, additive — no DROP/DELETE)
- `lookup_escalations` — id, ts, user_id, request, kind, category, scope,
  scope_lat, scope_lng, tier_found (a/b/c/none check), `results_by_tier` JSONB
  (`{a:[names], b:[names], c:[names]}`), cost_usd. Written whenever a dearer tier
  (b/c) found what a cheaper tier missed, **and** whenever all tiers found nothing
  (`tier_found='none'`, so real absences are visible). A tier-a hit — the cheap
  path already sufficed — writes **no** row.
- `lookup_routing` — (category, region_key, start_tier, misses_7d, updated_at),
  composite PK, start_tier check (a/b/c).
- `CREATE … IF NOT EXISTS` + guarded CHECKs, one transaction, idempotent. The
  module self-heals the same DDL, so a DB that never ran the file converges to the
  identical schema.

### `stop_existence_gate.py` (+~200) — the wiring shim
`replenish_with_escalation(kind, poi_type, scope, needed, …)` is a drop-in for
`dining_replenish_candidates` / `business_replenish_candidates` that feeds the
ladder three tiers built from the **existing** functions, so each tier's behaviour
is byte-for-byte the LOCAL-779/779B/783 behaviour — the ladder only adds the
"try the next tier before refusing" step, the log and the routing:
- `tier a` = the replenish fn with Serper **off** (free Nominatim — today's miss),
- `tier b` = the replenish fn with Serper **on** (Serper Places — the rescue),
- `verify` = `_verified_candidate`, which re-verifies one tier-c name via
  `verify_listing_in_scope` (+ `verify_listing_cuisine` for dining) with Serper on
  and recovers its coordinates through `places_search`, returning a candidate in
  the same shape the caller already consumes (or `None` to drop it).

`_run_with_serper(enabled, fn)` flips `SERP_PROVIDER` per tier and restores it —
the only switch `places_search.serper_places_enabled()` reads. If the ladder module
is unavailable it falls straight through to today's plain replenish (never blocks a
tour).

### Call sites wired (the four the ticket lists)
1. **business/restaurant search + refill** — `generate_tour_text.py` PHASE 3C
   maps-first top-up now calls `replenish_with_escalation`.
2. **existence-gate "no evidence" for business POIs** — the same file's maps-first
   refill fires exactly when the gate empties the list; it now escalates.
3. **`no_matching_places_in_area` refusal** — both refusal sites are now preceded
   by the ladder; the refusal stands only after tiers a→b→c all come up empty.
4. **by-reference "no material"** — `l2_by_reference.py` records the attempt
   through the ladder with `tier_b=None, verify=None, allow_grounding=False`
   (the L2 build is zero-grounding, zero-SERP), so a named-place no-material case
   is a logged `tier_found='none'` row with zero spend.

Found results are appended to `poi_list` exactly as the LOCAL-779B maps-first stops
are, so they go into the **LOCAL-783 24 h places cache** and a repeat is served
cheaply.

### `escalation_report.py` (new, read-only) — LEAD's hourly tick
`python3 escalation_report.py --since 24h` (also 48h/7d/90m, `--kind`, `--tier`,
`--examples`, `--json`). Strictly `SELECT`-only (sets `TRANSACTION READ ONLY`),
groups `lookup_escalations` by (kind, category, tier_found) with counts, total/avg
cost and newest examples (showing each tier's names), and prints the `lookup_routing`
table with a note that each row is reversible.

## Tests — red-first, recorded fixtures only (offline, no DB, no web)
- **`tests/test_local784_escalation_ladder.py`** (15 tests) — a `FakeStore`
  in-memory DB fake proves: a tier-a hit writes **no** row; a cheap miss → tier b
  **logged** with `results_by_tier`; tier c **re-verifies and drops** an
  unverifiable Gemini name ("Ghost Cafe"); all tiers empty → honest refusal **plus
  a 'none' row**; the **budget cap stops** escalation before the Gemini call;
  **routing kicks in after 3 misses** (the 4th lookup starts at tier b and skips
  tier a); `D722_FORCE_CHEAP_MISS` empties tier a; geohash-5 WRox = `drt2s`;
  tier-c JSON parsing (plain / fenced / prose / unparseable); the grounding guard
  skips tier c.
- **`tests/test_local784_replenish_escalation.py`** (4 tests) — the **real**
  `replenish_with_escalation` through the recorded LOCAL-783 Serper capture: a
  cheap miss escalates to Serper and returns the real West Roxbury places with
  coordinates + `verified`; a **repeat is served from the LOCAL-783 cache** (no new
  Serper call); force-cheap-miss still reaches Serper.

**LOCAL-779 / 779B / 783 + L2-guard suites stay green** (regression):
`test_local783_serper_places.py` + `test_local779b_restaurant_places.py` = 71;
`test_local779_business_poi.py` + `test_local597_guard.py` +
`test_local603_meter_and_l2.py` = 54; `test_local785_recorder.py` +
`test_pricing.py` = 41. With this ticket's 19 tests, the combined run is **139
passed** across the LOCAL-784/783/779/779B/597 suites.

## Live test — isolated container `local784-tg` (never `-p audioura`; `--rm`)
Network `development_default`, image `audioura-tour-generator`, DB via the
`postgres-2` alias, this worktree mounted over `/app`, `STORIED_MODE=true`,
`SERP_PROVIDER=serper`, `D722_FORCE_CHEAP_MISS=1`. Migration 055 applied to the dev
DB first (BEGIN … COMMIT, all OK). The ladder was exercised through the real
`replenish_with_escalation` path (not a ~$0.5 full generation — both cheaper and a
direct proof of the new code).

- **BEFORE:** `lookup_escalations`=0, `lookup_routing`=0, `audio_tours`=538.
- **CASE 1** — "middle eastern restaurants near me, west Roxbury, MA", cheap tier
  forced to miss → **tier b delivered** **Al Wadi** (42.27725, −71.17266) and
  **Bread Thyme** (42.285767, −71.15497), the real West Roxbury Middle-Eastern
  places. Escalation **row id=1, tier_found=b, cost $0.004**,
  `results_by_tier={a:[], b:[Al Wadi, Bread Thyme]}`. One new `/places` call.
- **CASE 1b** — the SAME request repeated → delivered 2, **0 new `/places` calls**
  (served from the LOCAL-783 24 h cache). Row id=2 (a second escalation *event*,
  places from cache).
- **CASE 2** — "yak-wool cafes in West Roxbury, MA" (nonsense) → **0 delivered,
  honest refusal**, **row id=3, tier_found=none, cost $0.064**,
  `results_by_tier={a:[], b:[], c:[]}` (tier c Gemini grounding ran **live** and
  found nothing verifiable — the real-absence record).
- **ROW COUNTS:** `lookup_escalations` 0 → 3; `lookup_routing` 0 → 1
  (`middle eastern | drt2s | start_tier=a | misses_7d=2` — below the threshold of 3,
  so correctly **not yet promoted**); `audio_tours` 538 → 538 (**no new rows, no
  DELETE**).
- **`escalation_report.py --since 24h`** ran live in the container and correctly
  grouped the 3 events (tier b rescued 2, 1 genuine absence), showed examples with
  a/b/c names, and printed the reversible routing table.

### Budget — HONEST
Ledger, this run (last 5 min): **1 grounded Gemini call $0.053** (the yak-wool tier
c), **2 Serper `/places` calls $0.002**. Total live spend ≈ **$0.055** — well under
the **$1.00** hard cap. No leftover containers (`--rm`); the 14 `audioura-*`
containers were left running and untouched.

## Process
- Branched from HEAD (`208ceac6`); `git merge-base --is-ancestor 208ceac6 HEAD` = 0.
- Committed only the source/test/migration/runner files (no `git add -A`). Did not
  touch DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md.
- No `DELETE` of any kind; the migration is additive and idempotent. One heavy
  container at a time; `--rm`; never `-p audioura`, never replaced/renamed
  `audioura-*`.

### Files
- `escalating_lookup.py` (new) — the ladder, budget, log, learned routing.
- `migration/sql/055_lookup_escalations.sql` (new) — `lookup_escalations` +
  `lookup_routing` (additive).
- `escalation_report.py` (new) — read-only LEAD report.
- `stop_existence_gate.py` — `replenish_with_escalation` + tier helpers.
- `generate_tour_text.py` — both maps-first call sites now escalate.
- `l2_by_reference.py` — by-reference no-material records a 'none' escalation.
- `run_local784_container.py` (new) — the live acceptance runner.
- `tests/test_local784_escalation_ladder.py`,
  `tests/test_local784_replenish_escalation.py` (new).
