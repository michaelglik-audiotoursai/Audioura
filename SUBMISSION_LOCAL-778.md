# SUBMISSION — LOCAL-778: Free (L2) generation = reuse-first hybrid

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-778-l2-reuse-first`
**Base:** `subscribed` @ `f35db377` (Merge LOCAL-784). `git merge-base --is-ancestor f35db377 HEAD` exits 0.

---

## What this does (D719 amended)

Michael, 2026-10-26: *"Free users may research new places forever. If we have the
places to substitute for the ones in the tour, then do it."*

Before this change a Free (L2) request either ran fully **by-reference**
(LOCAL-597: reuse only, refuse if short, never tops up) when
`plans.l2.by_reference_only=TRUE`, or — with `by_reference_only=FALSE` (D719) —
ran the **normal fresh** path, which only reused the stop pool for an *identical*
request (LOCAL-590).

LOCAL-778 adds a third L2 mode, **`reuse_first`**: reuse whatever matching
material already exists and research **only the stops that are missing**.

```
N requested, K reusable stops found
  N <= K   → assemble from reused stops only, zero grounding / zero SERP (by_reference-style)
  N >  K   → keep the K reused, research exactly N-K new stops (K titles excluded so
             no duplicates), re-stitch route/order, every gate runs on the new stops
  K == 0   → identical to the fresh path (return None → caller researches the whole tour)
```

One delivered tour counts **once** against the L2 caps regardless of the mix; the
cost record carries `reused_stops=K` / `researched_stops=N-K`.

---

## Build — where it lives

### 1. Mode selection — `subscription_levels.py`
`_check_generate` returns an allow result whose `mode` is:
- `by_reference` when the L2 plan has `by_reference_only=TRUE` (unchanged, LOCAL-597);
- **`reuse_first`** when the L2 plan has `by_reference_only=FALSE` (D719 amended);
- `None` for paid levels (L3/L4/Tester/admin) — **unchanged**.

The daily/monthly caps are identical for both L2 modes (one delivered tour counts
once). Paid levels never reach the L2 block, so reuse-first stays strictly L2-only.

### 2. Candidate gathering + D713 + assembly — `stop_pool_orchestrator.py`
`maybe_generate_with_pool(..., reuse_first=True)`:
- gathers candidates with the **LOCAL-597 material finder** — the stop pool **plus**
  `parse_delivered_stops` of **non-test, non-translation** tours of the same venue
  identity (`_reuse_first_existing_tour_rows`), deduped by normalised title;
- **D713 ownership filter**: a stop from a **priced** (`price_tier > 0`) or
  **community** (`community_id IS NOT NULL`) source tour is dropped unless the
  requester is that tour's `creator_user_id` — applied to **both** sources (pool
  via `stop_pool_sources.filter_protected_titles`, mined tours inline);
- `N <= K` → assemble exactly like by-reference (zero grounding/SERP);
- `N > K` → run the normal fresh pipeline for the remaining `N-K`, passing the K
  reused titles as `exclude_titles` so selection never re-picks them; the assembler
  re-sequences outdoor routes and the D611 opening covers all N for buildings;
- reused stops keep their stored text (and therefore their audio — the audio reuse
  identity is unchanged).

### 3. Metering — `generate_tour_text.py`
The `mode == "reuse_first"` branch (ahead of the by-reference branch) routes
through the same hybrid assembly and records on the tour's cost record
(`_LAST_GENERATION_COST`): `reused_stops`, `researched_stops`, `new_stops`,
`rewritten_transitions`, `research_cost_reused`, and a provider `breakdown`.
`_LAST_DELIVERY_PATH='reuse_first'`. With nothing reusable it **falls through** to
the fresh pipeline (never refuses on its own).

### 4. Partial-success + refusal fallback
If the fresh part returns no text but `K >= 1`, the orchestrator delivers the K
reused stops with an honest shortfall opening ("We could only cover K of N")
instead of refusing or re-running the whole pipeline. `K == 0` falls through to the
fresh path, whose own structured refusal (LOCAL-774 dialog) reaches the app.

### 5. Concurrency guard for L2 (LEAD, from the LOCAL-777 review)
`subscription_levels._count_active_generations` now counts, for the cap
**decision** only, this user's `status='completed'` rows **plus** `status='started'`
rows **younger than 30 minutes**. Older `started` rows stay ignored (stale). The
user-facing "tours used" **display** still counts only completed tours
(`_count_fresh_generations`, unchanged). Red test: two parallel requests at a cap
of 1 → the second is refused `plan_limit_daily`.

### Forwarding — `tour_orchestrator_service.py`
`generate_complete_tour` forwards `quota['mode']` (`by_reference` **or**
`reuse_first`, else `None`) unchanged into the generation request.

---

## Paid levels — would reuse-first suit them? (LEAD decides)

**Recommendation: do not enable it for paid levels as-is.** Paid levels (L3/L4)
sell a *fresh* research allowance; silently substituting reused stops would change
what the buyer paid for and could surprise them (they may want a genuinely new
take on a venue they already toured). The pool fast-path (LOCAL-590, identical
request) already saves cost for paid levels without changing the product promise.
If LEAD wants paid reuse-first later, it should be **opt-in per request** (a "reuse
what you can" toggle) with the reuse/research split shown before delivery — not a
silent default. This submission leaves paid levels byte-for-byte unchanged.

---

## Tests (red-first) — `tests/test_local778_reuse_first.py` (11, all green)

| Ticket red item | Test | Result |
|---|---|---|
| (i) N fully covered → zero grounding | `test_full_coverage_researches_nothing` | reused=5, new=0, new_cost=0, generator raises if called | PASS |
| (ii) K of N covered → only N−K researched, no dup titles | `test_partial_coverage_researches_only_the_rest` | fresh call asked for 2, exclude_titles == the 3 reused | PASS |
| (iii) paid/community source stop never reused for another user (D713) | `test_priced_source_stop_not_reused_for_another_user` / `..._reused_for_its_creator` | protected for others, reusable for creator | PASS |
| (iv) nothing covered → identical to fresh | `test_no_coverage_falls_through_to_fresh` | returns None (caller researches) | PASS |
| (v) paid levels unchanged | `test_paid_level_unchanged` | l3 carries no mode | PASS |
| gate: L2 → `reuse_first` | `test_l2_reuse_first_mode` | mode == reuse_first | PASS |
| concurrency guard | `test_recent_started_row_blocks_second_parallel_request` | 2nd refused plan_limit_daily | PASS |
| stale started ignored | `test_stale_started_row_is_ignored` | 45-min started not counted | PASS |
| mining existing tours | `test_existing_tour_stops_are_reused` | 3 mined stops cover N=3 | PASS |

All DB-touching tests run inside a private throwaway schema
(`tests/_isolated_db.IsolatedSchema`); public proof counts are asserted unchanged
(zero production/shared writes, LOCAL-601). No `DELETE` anywhere.

### Companion suites — green (base vs branch)
Run against my **own** `local778-postgres-2-1` (host port 55433), conftest routed
to `audiotours_test`:
- `test_local778_reuse_first.py` — **11 passed**
- `test_local595_enforcement.py` + `test_local597_by_reference.py` +
  `test_local597_guard.py` + `test_sq4_merge.py` — **54 passed**
- `test_palais_fix_lead_fixture.py` (standalone script) — **23/23 assertions**
- Stop-pool regression suites that exercise `maybe_generate_with_pool`
  (588, 600, 612, 615×2, 616×2, 641, 572×2) — **all passed**
- `test_local599b_opening_section.py` — 9 passed, **3 pre-existing failures**.
  Verified identical on a clean worktree at base `f35db377` (same `3 failed, 9
  passed`, same assertion errors). They exercise `_source_practical_facts` /
  `_build_opening_section` (MassArt live-fixture hours/admission drift), which
  LOCAL-778 did not touch. **Zero regressions introduced.**

---

## Live test — own containers only (`-p local778`, spare ports)

Stack: `docker-compose.local778-proof.yml` (project `local778`), orchestrator
`:55002`, generator `:55000`, postgres `:55433`, DB `audiotours`,
`plans.l2.by_reference_only=FALSE`. Generator + orchestrator images **rebuilt from
this branch**; baked `/app` files verified byte-identical to the worktree. Never
touched `audioura-*` or `development-postgres-2-1`.

L2 plan on this stack: `max_stops=5`, `tours_per_day=1`. A request over 5 stops is
refused `stops_over_plan` (existing LOCAL-595 behaviour), and each device is capped
at 1 tour/day — so each run below used a fresh L2 test device.

| # | Request | pooled (K) | reused | researched | rewritten transitions | new_cost | research_reused | stop titles |
|---|---|---|---|---|---|---|---|---|
| 1 full-reuse | Peabody Essex Museum, Salem, MA — museum, 4 | 5 | **4** | **0** | 0 | **$0.0000** | $0.4000 | The Examination of a Witch · The Yin Yu Tang House · The Maritime Gallery · The Asian Export Art Wing |
| 2 hybrid | Gyms near me, West Roxbury, MA — walking, 4 | 2 | **2** | **2** | 2 | **$0.0995** | $0.2295 | *reused:* Planet Fitness · Fitness Together — *researched (no dup):* CrossFit West Roxbury · YMCA of Greater Boston – West Roxbury |
| 3 fresh | Isabella Stewart Gardner Museum, Boston, MA — museum, 3 | 0 | **0** | **3** | — | **$0.3935** | $0.0000 | The Concert · The Rape of Europa · The Story of Lucretia |

Generator log evidence (verbatim):
```
[LOCAL-590] pool: venue=qid:Q3373790 ... requested=4 pooled=5 reuse_first=True
[LOCAL-778] REUSE-FIRST DELIVERY: reused=4 researched=0 ... research_reused=$0.4000 new_cost=$0.0000
[LOCAL-590] pool: venue=loc:gyms near me west roxbury ma ... requested=4 pooled=2 reuse_first=True
[LOCAL-590] generating 2 NEW stop(s) (excluding 2 pooled); reusing 2 pooled narration(s)
[LOCAL-778] REUSE-FIRST DELIVERY: reused=2 researched=2 rewritten_transitions=2 research_reused=$0.2295 new_cost=$0.0995
[LOCAL-590] pool: venue=qid:Q49135 ... requested=3 pooled=0 reuse_first=True
[LOCAL-778] reuse-first: no reusable material; researching the whole tour fresh (identical to the fresh path)
```

**Cost:** total API spend for the live runs = **$0.4938** (fresh Gardner $0.3935 +
hybrid Gyms research $0.1003). Reuse-only deliveries cost **$0.00** in research —
the whole point of the feature. **Well under the $2.00 budget.**

**audio_tours row counts:** grew `6 → 12` originals over the session (first clean
batch of 3 + Peabody + Gardner + hybrid Gyms). `is_test` rows = **0**. Zero writes
to the shared/dev DB.

---

## Process notes
- Branch was found at `6733f580` (behind `subscribed`). Reset to `f35db377`,
  reapplied WIP cleanly (3-way auto-merge, no conflicts), re-verified the base
  ancestor check. Both the base's LOCAL-784/785 changes and this ticket's
  reuse-first changes coexist; all modified files compile.
- Committed only the LOCAL-778 files (never `git add -A`). No `DELETE` of any kind.
  Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md.
- One heavy build at a time (generator + orchestrator rebuilt once, together).
