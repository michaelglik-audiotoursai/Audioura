# SUBMISSION — LOCAL-577: a museum tour must deliver the stops it was asked for

**Agent:** Mac Mini Kiro **Branch:** `LOCAL-577-museum-refill` **Base:** `storied` (08ee199)
`git merge-base --is-ancestor 08ee199 HEAD` → exit 0 (verified before every commit).

## The defect
GCloud_Storied, Preview v4, 2026-10-04 (ClickUp wdvrdayrdp). Palais Lascaris,
Nice, museum, **4 stops → 3 delivered** (job b5982123, tour 431). The log:

```
[EXISTENCE-GATE] LOG_ONLY - 4/4 stops verified (100%), 0 would be dropped
[R4] Replenishment round 1/3: need 3 more, asking for 8
[D1v2] DROPPED 'The Adoration of the Magi' - no canonical title match
```

Four real works existed and passed the existence gate. D1v2 then dropped one on
a **canonical-title** mismatch — not non-existence, not a wrong venue, just a
title our Wikidata/site corpus could not line up. R4 ran, but its freshly
generated candidates also failed the canonical match, so the count was never
restored. D592: *a thin stop is acceptable; a missing one is not.*

## Root cause (file:line, `generate_tour_text.py`)
- **D1v2 title-mismatch drop:** `_verify_works_v2`, line 4575
  (`[D1v2] DROPPED '…' — no canonical title match`), records
  `evidence_log[name] = {"status": "DROPPED", "reason": "no canonical match"}`.
  The real POI survives only in `_pre_d1v2_candidates`.
- **R4 replenishment loop:** the `while` at ~8648, round log at ~8657; R4's own
  generated candidates that fail `match_candidate_to_canonical` go to
  `_r4_all_dropped_pois`.
- **The fills (UNIFIED-FILL ~8787, POST-R4-FILL ~8820) mark every fill
  `verified=False`.**
- **LOCAL-16 GATE (~8900):** for museum tours it strips every `verified=False`
  stop, with the single exemption `user_explicit` (LOCAL-547). So the real,
  existence-passed stop D1v2 dropped on a title technicality is deleted here, and
  the tour ends at 3.

The one thing missing was a path to re-admit a *title-mismatch* drop in a form
that survives the gate — the stop was real, it just lacked a canonical-title
match.

## The fix
Narrow, hedged, last-resort — and it reuses the exact mechanism unverified
exhibits already use (verified=False narration hedge, D592) and the exemption a
listener-named stop already uses (LOCAL-547).

New **module-level** helpers (so the real logic is unit-tested directly, D277):

- `_title_mismatch_refill_pool(evidence_log, pre_d1v2_candidates, current_poi_list, venue_name)`
  — line 1152. Returns ONLY the candidates D1v2 dropped for `"no canonical
  match"`. Each copy is `verified=False` + `_title_mismatch_refill=True`.
  **Never** re-admits: REJECTED (wrong venue), theme/book-word or cycle-name
  drops (prolog material, not stops), non-existence, a stop already present, a
  VERIFIED stop, or a LOCAL-24 `excluded` classifier kind.
- `_local16_gate_survivors(poi_list, evidence_log)` — line 1210. The museum
  verified-only choke-point as a pure function: exempts `user_explicit` AND the
  new `_title_mismatch_refill`, strips any other `verified=False`, dedups
  verified stops by canonical title. Returns `(survivors, removed)`.
- `_is_title_mismatch_drop` / `_norm_name_for_refill` — supporting predicates.

Wiring in `_verify_works_v2`’s caller:
1. **R4 now logs WHY it stopped** when short (line ~8771): round cap /
   candidate ceiling / no further verifiable works / scope-suppressed, plus how
   many R4 candidates failed the canonical match. R4 already re-runs until the
   count is met or the pool is exhausted; now the stop reason is never silent.
2. **New LOCAL-577 refill step** after R4/UNIFIED-FILL/POST-R4-FILL and before
   the gate (line ~8880, museum + still short): re-admits the title-mismatch
   drops, hedged, up to `total_stops`, logging each re-admission.
3. **The inline LOCAL-16 GATE now calls `_local16_gate_survivors`** — same
   behaviour as before plus the `_title_mismatch_refill` exemption.

Never invents a stop (only existence-passed D1v2 candidates re-enter). Never
drops a verified one (verified stops are untouched; the gate dedup is unchanged).

## Tests
Step-1 reproduction, exercising the REAL module helpers (no mirrors):
`tests/test_local577_museum_refill.py`.
- **RED on storied:** both helpers absent → `AttributeError`, 9/9 ERROR.
- **GREEN after the fix:** `Ran 9 tests … OK`.

The nine assertions cover: the recorded 3-of-4 shortfall; the Adoration drop is
offered back; refills are `verified=False` + tagged; REJECTED is never refilled;
theme/cycle drops are never refilled; an already-present stop is never
duplicated; the refill survives the gate while a plain unverified pad is still
stripped; and end-to-end 4/4.

Named regressions — all green on this branch (pasted exits):
```
test_local394_never_drop_a_stop.py ....... Ran 6 tests OK            EXIT 0
test_palais_fix_lead_fixture.py .......... 23/23 assertions hold     EXIT 0
test_sq4_merge.py ........................ ALL TESTS PASSED          EXIT 0
tests/test_local576_named_anchors.py ..... OK                        EXIT 0
```
Related museum/replenish/gate suites also exit 0: `tests/test_d558_replenish_loop.py`,
`tests/test_local357_forced_stops.py`, `tests/test_local3481_a_stop_must_be_a_place.py`,
`tests/test_local370_exhibition_listing_false_match.py`, `tests/test_local372_book_word_drop.py`.

## Live runs — Palais Lascaris, Nice, museum, 4 stops, ×2
GCloud config: `TOUR_LLM_MODEL=gpt-4o`, `COST_HARD_LIMIT_USD=2.00`,
`DISABLE_TOUR_CACHE=1` (D262), `DATABASE_URL` set so the existence gate runs
(D261), `STORIED_MODE=true`. Runner: `run_local577_palais_live.py`.

| Run | Requested | Delivered | Chars | Wall | OpenAI cost | D1v2 | R4 | LOCAL-16 GATE | Existence gate |
|-----|-----------|-----------|-------|------|-------------|------|----|---------------|----------------|
| 1 | 4 | **4** ("That's 4 stops") | 8458 | 527.7s | **$0.4905** | Cache HIT, 8/8 verified, tier=exhibit_museum | Target reached 8/4 | All 8 cleared ✓ | LOG_ONLY 8/8 (100%) |
| 2 | 4 | **4** ("That's 4 stops") | 7824 | 589.1s | **$0.6161** | Cache HIT, 8/8 verified, tier=exhibit_museum | Target reached 8/4 | All 8 cleared ✓ | LOG_ONLY 8/8 (100%) |

Both runs stayed well under the $2.00 hard cap and delivered the full 4/4.
Artifacts: `LOCAL577_RUN1.log` / `LOCAL577_PALAIS_RUN1.txt`,
`LOCAL577_RUN2.log` / `LOCAL577_PALAIS_RUN2.txt`.

**Honest note on what the live runs did and did not exercise.** On both runs the
D1v2 **venue cache** resolved all works (8/8 verified, `tier=exhibit_museum`), so
no title-mismatch drop occurred organically and the new refill step did not need
to fire — the venue corpus has since filled in. The live runs therefore prove
the fix **delivers 4/4 and does no harm** at the exact config GCloud uses, under
cap. The specific **drop → refill → gate** path is driven directly through the
real module helpers in `tests/test_local577_museum_refill.py` (9/9), which is why
that test exercises the live code, not a mirror.

## audio_tours row counts (never DELETE)
- **Before:** `count = 200`, `max(id) = 389`.
- **After:** `count = 201`, `max(id) = 390`.
- `generate_tour_text()` returns text only — it does **not** write `audio_tours`
  (grep confirms no `INSERT INTO audio_tours` in the module; neither run log
  contains such an insert). **My two Palais runs added ZERO rows.**
- The single new row **id=390** is
  `"LOCAL49 Тест регрессии 1790219302 - Пешеходная экскурсия"` (`stops_count=3`,
  created 18:17) — a **LOCAL-49 regression walking tour from a separate
  concurrent process**, not a Palais Lascaris museum tour. Documented, not
  deleted. **Nothing was DELETEd.**

## Process / guardrails
- Base verified at 08ee199 before branching (the worktree started at the parent
  `fcdcdc1`; the branch was reset to `storied` so
  `git merge-base --is-ancestor 08ee199 HEAD` exits 0).
- Commit + push after each step; `git rev-list --count storied..HEAD` = 2 (≥ 1).
  Branch pushed `-u origin LOCAL-577-museum-refill`.
- No GCloud. Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, or
  .continuous_dev/STATUS.md.

## Files changed
```
generate_tour_text.py                | 258 +++++++++++++++++------------
tests/test_local577_museum_refill.py | 193 ++++++++++++++++++  (new)
run_local577_palais_live.py          |  (new, live-run harness)
SUBMISSION_LOCAL-577.md              |  (new, this file)
+ live artifacts: LOCAL577_RUN{1,2}.log, LOCAL577_PALAIS_RUN{1,2}.txt
```

## Reproduce
```
# red on storied (helpers absent → AttributeError), green here:
python3 tests/test_local577_museum_refill.py

# live, GCloud config, $2.00 cap, existence gate on, cache off:
python3 run_local577_palais_live.py 1
python3 run_local577_palais_live.py 2
```
