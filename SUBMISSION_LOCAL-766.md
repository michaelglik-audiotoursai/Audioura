# SUBMISSION — LOCAL-766: the stop pool never rebuilds a paid or community tour for someone else (D713)

**Branch:** `LOCAL-766-pool-respects-paid-community`
**Base:** `subscribed` @ `a3ba699f` (origin/subscribed) — `git merge-base --is-ancestor a3ba699f HEAD` exits 0.
**code_sha (HEAD):** `c48ded6211d543e7eb962df9d4ab13e076441ebf`
**Ruling:** D713 (reuse saves money, but never hand out a paid/community tour); D590 stop pool; D141 (own is_test rows only); D690 (never delete purchase-bearing rows).

## What changed

Whole-tour reuse is already creator-scoped (LOCAL-727). The remaining bypass was the **stop pool** (LOCAL-590): stops are keyed by `(pool_key, title_norm)` with no link to the tour they were made for, so an identical request by another user was served the same stops — a free rebuild of a priced or community tour.

1. **Provenance (additive migration 051).** New table `stop_pool_sources(pool_key, title_norm, audio_tour_id, recorded_at)`, PK `(pool_key, title_norm, audio_tour_id)`, guarded FK to `audio_tours(id) ON DELETE CASCADE`. One row per (pooled stop, source tour). Additive only — no DROP/DELETE/retype. The module `stop_pool_sources.py` self-heals the identical schema (`ensure_table`) so a service converges whether or not 051 ran.

2. **Recording (live path).** `tour_orchestrator_service.store_audio_tour` now calls `_record_pool_provenance` after the `audio_tours` row is INSERTed (both the new-insert and the replacement paths), linking every pooled stop the tour delivered to its id. The stop units and `(pool_key, title_norm)` are reproduced with `stop_pool_store`'s own `parse_delivered_stops` / `_pool_key` / `_title_norm`, so a recorded link targets the row the pool actually holds. Best-effort and strictly non-fatal.

3. **Delivery rule.** `stop_pool_orchestrator.maybe_generate_with_pool` filters `get_pool_stops` through `stop_pool_sources.filter_protected_titles` before K is counted. A pooled stop is **skipped (generated fresh)** when ANY of its source tours is community (`community_id IS NOT NULL`) or priced (`price_tier > 0`), **unless** the requester is that tour's `creator_user_id`. Checked at delivery, so pricing a tour or attaching it to a community **later** protects it from then on. Each skip logs `[LOCAL-766] POOL SKIP protected source tour=<id> reason=community|paid`.

4. **Dual-key correctness (commit c48ded62).** `get_pool_stops` reads a venue under BOTH the `qid:` and `loc:` pool keys (resolver flakiness, D582 class), and the live recorder stores under the `loc:` key while a QID-resolving delivery reads under the `qid:` key. The protection lookup (`_protected_titles_for_keys`, `pool_key = ANY(...)`) now spans both keys keyed by `title_norm`, so a stop recorded under one key is still protected when read under the other. Regression `test_7` fails on single-key, passes on dual-key.

5. **Free, non-community tours keep sharing exactly as today** (unproven rows — no `stop_pool_sources` row — stay shareable). **Organiser-audio tours** (`source_kind='organiser_audio'`) are never generated/pooled; the backfill skips them explicitly.

6. **Dockerfiles.** The only Dockerfile copying sources one-by-one that runs this code is `Dockerfile.orchestrator` — it now `COPY`s `stop_pool_sources.py` and `stop_pool_store.py`. The generator / cloudrun images (which run `maybe_generate_with_pool`) use `COPY *.py`, so they pick the new module up automatically; `tour-worker` builds from `Dockerfile.cloudrun` (confirmed in `docker-compose-beta-local.yml`) and does not run the pool path.

## Files
- `migration/sql/051_stop_pool_provenance.sql` (new, additive, idempotent)
- `stop_pool_sources.py` (new module: record, delivery rule, backfill, self-healing DDL)
- `stop_pool_orchestrator.py` (+provenance filter in `maybe_generate_with_pool`)
- `tour_orchestrator_service.py` (+`_record_pool_provenance`, `_pool_db_url`; `store_audio_tour` takes `tour_type`/`location`, records on both store paths)
- `Dockerfile.orchestrator` (+COPY of the two modules)
- `test_local766_pool_provenance.py` (new, 12 tests)
- `run_local766_live.py` (live-acceptance harness, not imported by any service)

## Red tests first (then green)
Suite is RED on pre-LOCAL-766 behaviour and GREEN with the fix. Proof of red:
- Neutralising `partition_pool_rows` to the pre-766 "allow all" behaviour → **6 failures**: `test_1`, `test_2`, `test_3`, `test_6` (delivery rule) and both `TestOrchestratorEndToEnd` tests.
- Forcing single-key lookup (old behaviour) → `test_7` fails: `AssertionError: 5 != 0 : loc-recorded protection must apply when read under the qid key`.

Green (dev Postgres on host port 5433, every DB test inside a throwaway schema via `tests/_isolated_db.py`; `public` row counts asserted identical before/after; routes to `audiotours_test` under pytest):
```
test_local766_pool_provenance.py ............  12 passed in 50.38s
```
Covers: priced tour blocks another user / creator keeps reuse; community tour blocks another user; priced AFTER pooling → protected from then on; free tour → reused as today; unproven rows → shared; mixed (one protected source protects the shared stop); dual-key regression; orchestrator E2E (non-creator gets fresh for the protected stop only, creator reuses all); backfill proves matching tour + idempotent; organiser-audio not attributed.

Regression — **LOCAL-590 suites green** (no change expected elsewhere; no Flutter change):
```
test_local590_orchestrator.py test_local590_pool_store.py test_local590_assembly.py
..........................................  42 passed
test_local607_pooled_coherence.py test_local644_pool_structured.py
..........................  26 passed
```

## Backfill counts (authoritative run against the local766 copy DB)
```
[LOCAL-766] backfill: tours_scanned=420 links_written=0 pool_rows_total=731
            pool_rows_proven=14 pool_rows_unproven=717
```
- `pool_rows_total=731`, `pool_rows_proven=14` (provenance proven from existing tour content), `pool_rows_unproven=717` — **the 717 unproven rows stay shareable** (ticket rule). `links_written=0` on this run because the backfill is idempotent and had already been run with identical logic; proven/unproven are stable across re-runs (`test_backfill_is_idempotent`).

## Live test (own containers, $0 paid API — no generation spend)
Done against **our own `local766-pg` container** (port 5466), a COPY of the shared data (`stop_pool=731`, `audio_tours=523`); the shared `stop_pool` rows were never modified. The delivery rule and the recording path were proven on **real pooled rows** with the real code — no paid API call was needed, so **total spend $0.00** (well under the $1.00 cap). Meter mount was available at `/Users/micha/Audioura/meterlogs`; the last `paid_api_calls.jsonl` entry predates this session's activity (`ts=2026-10-25T21:03:09Z`) and nothing was appended.

**Delivery proof — real community tour (id=716, `community_id=10`, creator `USER-41659366`, 4 pooled stops linked):**
```
--- Requester = ANOTHER USER (USER-OTHER-766) ---
  [LOCAL-766] POOL SKIP protected source tour=716 reason=community
  [LOCAL-766] POOL SKIP protected source tour=716 reason=community
  [LOCAL-766] POOL SKIP protected source tour=716 reason=community
  [LOCAL-766] POOL SKIP protected source tour=716 reason=community
  → allowed(reuse)=0  skipped(fresh)=4
--- Requester = CREATOR (USER-41659366) ---
  → allowed(reuse)=4  skipped(fresh)=0
[LOCAL-766 LIVE] RESULT: PASS — non-creator skipped 4 (community); creator skipped 0
```

**Recording proof — real `tour_orchestrator_service._record_pool_provenance` on a venue with 10 pooled stops:**
```
  [LOCAL-766] provenance: linked 10 pooled stop(s) to tour 751 (type='museum', is_test=True)
[proof] after cleanup, provenance rows for 751: 0 (FK cascade)
```
The recording proof inserted our **own is_test priced tour** (`is_test=TRUE`, lat/lng NULL), then deleted ONLY that row (`DELETE ... WHERE id=751 AND is_test=TRUE`; provenance rows removed by the FK cascade) — D141-compliant, no purchase-bearing row touched (D690).

### Row counts before/after (local766 copy DB, port 5466)
| table | before | after |
|---|---|---|
| stop_pool | 731 | 731 |
| audio_tours | 523 | 523 |
| stop_pool_sources | 31 | 31 |

Both live proofs net-zero (the recording proof's own is_test row was cleaned up). **Shared DB (port 5433) untouched:** `stop_pool=731`, `audio_tours=523` unchanged.

### Note on shared-DB hygiene (not mine)
The shared `audiotours.public` schema contains **38 `stop_pool_sources` rows recorded 2026-10-25 19:42–20:06 UTC** — before this session (~20:48 UTC) — by a prior worker that ran the backfill against the shared DB and then died (LEAD's resume note mentions two workers died silently). I did **not** write them: my pytest runs route to `audiotours_test` and use throwaway schemas (dropped on teardown; no `t766_*` schema or `public.stop_pool_sources` remains in `audiotours_test`), and my backfill/live proofs ran only against the `local766-pg` copy. Per D713/D141 I did not modify or delete these shared rows (they are not is_test-identifiable and are not mine); flagging them for the LEAD to clean up.

## Process
- Branched from the correct base: the WIP (`920199b7`) had been saved on `110ac991` (one commit before the stated base); I rebased it onto `a3ba699f` so `git merge-base --is-ancestor a3ba699f HEAD` passes. No `git add -A` was used; only named files were staged.
- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, or `legal/`.
- Commits: `91f69950` (rebased WIP), `c48ded62` (dual-key fix + regression test), plus this submission.
