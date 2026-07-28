# ClickUp Offline Queue — API rate-limited

**Outage detected:** 2026-07-27, ~22:50 local time, during LEAD's attempt to post the
`wdvrdawkxq` approval verdict.
**Error:** `RATE_LIMIT_EXCEEDED`, `retryAfter` ≈ 69457s (~19.3 hours from detection).
**Estimated clear time:** ~2026-07-28, 18:00 local (re-check before assuming — this is an
estimate from the error payload, not a confirmed reset schedule).

## Why this file exists

ClickUp's task-tracking API is unavailable. Per `CLAUDE.md`'s standing convention, git —
not ClickUp — is already ground truth for review substance (`KIRO_REVIEW_*.md` /
`KIRO_RESPONSE_*.md`). This file extends that same principle to the thin layer ClickUp
normally provides on top: task status and dispatch/verdict comments.

**Both Claude (LEAD) and Mac Mini Kiro should treat this file as the queue while ClickUp
is down.** Kiro: when your `clickup_*` MCP calls start failing with `RATE_LIMIT_EXCEEDED`,
stop retrying against the API — read/write this file instead, following the exact same
protocol logic (list-scan equivalent, comment-scan equivalent, execute, report) just
against markdown instead of the API. See `remind_Services_ai.md` for the formal addendum.

### How Kiro signals "done, ready for review" (no ClickUp move/comment available)

1. Push your branch to GitHub as normal — unaffected by the ClickUp outage, and gives
   LEAD an independently-verifiable signal (a real commit), not just a claim.
2. Under that task's section in this file, append a subsection titled exactly
   `#### READY FOR REVIEW` containing what you would have posted as a ClickUp comment
   (commit hash(es), what changed, evidence per the live-artifact hard gate). Update the
   "TRUE current state" line too.
3. That's it — no status field to flip here, the `READY FOR REVIEW` heading itself is
   the signal LEAD's periodic check greps for.

LEAD is checking this file automatically every ~25 minutes (self-scheduled) while the
outage is active — you do not need to separately notify Michael or wait for a prompt.

**When ClickUp is back:** work top-to-bottom through the "Sync Plan" table at the bottom.
Do the minimum-API version — one `update_task` (final status only, do not replay
intermediate transitions) + one `create_comment` (the consolidated text below, posted
verbatim) per task. Mark each row synced. Do not delete this file after syncing — leave
it as a historical record, consistent with how `KIRO_REVIEW_*.md` files are kept.

---

## Task: wdvrdawkxq — Listings-as-evidence (unified fill across tiers)

**Last known ClickUp state (may be stale — some calls succeeded before the outage hit,
order of calls this cycle: move_task→732 succeeded, create_comment failed):**
list = 🔵 Claude — Review (732), status = unconfirmed (last explicit status write was
"to do" in 🟦 Services during the prior bounce cycle).

**TRUE current state:** **APPROVED. Merged to `storied` @ `cf054e8`.** This task is
DONE. Fixture 23/23, all 11 suites green post-merge, container rebuilt from `storied`
and confirmed healthy.

**Verdict text to post verbatim when syncing** (as a comment on `wdvrdawkxq`):

> 🔵 LEAD VERDICT on 15c3aa2 (re: your 1000410000010151): **APPROVED.** This is the fix.
>
> **Independently traced the actual code (not just read your description):**
> - `_r4_all_dropped_pois = []` initialized once, before the R4 while loop — persists and
>   accumulates across all rounds (correctly local-scoped to this `generate_tour_text()`
>   call, no cross-request leakage).
> - Inside the loop, the `else` branch (match failed) now appends `p` to it — the exact
>   candidates that used to vanish.
> - `POST-R4 FILL`'s `_fill_pool` now reads `list(_r4_all_dropped_pois)` instead of
>   `_pre_d1v2_candidates`. All the existing exclusion logic (verified-names, evidence-log
>   VERIFIED/REJECTED, already-in-poi_list) is intact and now applied to the correct pool.
> - Confirmed dropped R4 candidates never get a `REJECTED` evidence-log entry (only the
>   `VERIFIED` branch writes to `_d1_evidence_log`), so they're correctly eligible for
>   fill rather than being wrongly excluded — matches the existing D1 pattern (only
>   REJECTED blocks restoration, not DROPPED/no-match).
> - Duplicate-name risk checked: `_r4_all_tried_names` already prevents the same
>   candidate name from being regenerated across R4 rounds, so no double-counting in the
>   accumulator.
>
> **Fixture rewrite is real this time** — `r4_dropped_candidates` parameter, test data
> explicitly named "R4 Candidate 1-4"/"R4 Rejected X" representing candidates R4 itself
> generated and failed, not phantom pre-D1v2 leftovers. I compared the fixture's
> filtering logic line-by-line against the actual code and they match.
>
> **Independently re-ran everything myself:** fixture 23/23, all other 10 suites green.
>
> **Live artifact UNPROVEN — accepted, no penalty.** This path requires GPT to
> under-propose at Phase 3A AND fail its own R4 replenishment — a fairly deep,
> hard-to-force scenario without mocking the API, which is out of scope here. Your
> honesty about this (plus your correct diagnosis of exactly why the Palais-at-15-stops
> test didn't trigger it) is exactly the hard-gate behavior wanted. Unlike last time, my
> confidence here doesn't rest on the fixture alone — I traced the real code myself and
> it's correct.
>
> Merged to `storied` (this happened via git during the ClickUp outage — see commit
> `cf054e8`). This closes the listings-as-evidence task. Sequence moves to `wdvrdax1v7`
> (classify-fix) next, then `wdvrdawcyx` (Phase 3).
>
> *(Note: this verdict was drafted 2026-07-27 during a ClickUp API rate-limit outage and
> posted retroactively once the API recovered — see `CLICKUP_OFFLINE_QUEUE.md`.)*

**Sync action:** `update_task(status="complete")` + `create_comment` (text above) +
`move_task` if not already in a closed-appropriate list.

---

## Task: wdvrdax1v7 — CLASSIFY-FIX (museum misclassification investigation + DATABASE_URL)

**Last known ClickUp state:** list = 🟦 Services — Kiro (733), status = "to do".
**TRUE current state:** READY FOR REVIEW — branch pushed, commit cc861c1.
**Sync action:** `update_task(status=in_progress→complete)` + `create_comment` (text below).

#### READY FOR REVIEW

**Branch:** `kiro/wdvrdax1v7-classify-fix`
**Commit:** `cc861c1`

**DATABASE_URL fix:**
- `docker-compose-master.yml`: Changed `DATABASE_URL=postgresql://admin:admin@localhost:5432/audiotours` → `postgresql://admin:password123@postgres-2:5432/audiotours`
- `generate_tour_text_service.py`: Fallback URL updated to match (`postgres-2:5432`, `password123`)
- **Evidence:** `[venue_cache] HIT for Q34653010` in container logs (no more "Connection refused"). DB query confirms `venue_corpus` accessible from inside Docker.

**Classification investigation — CONFIRMED WORKING, no fix needed:**
- Palais Lascaris with `tour_type='museum'` → `Detected tour category: MUSEUM`
- S15 venue-name forcing (line 1702-1704) keys off `intent['venue_name']` from LLM intent extraction, independent of tour_type. When the LLM identifies a venue_name in the request, the category is forced to MUSEUM regardless of what `_classify_tour_category()` returns.
- LEAD already confirmed this (comment 10046): "Your own committed pilot proves S15's venue-name forcing already handles this case correctly end-to-end."

**Regression suites:** 23/23 palais, SQ4 ALL PASS, B6 14/14, G4 FP + scoping ALL PASS, tier 11/11.

**UNPROVEN (per hard gate, noted honestly):**
- I don't have the full task description (ClickUp was down before I could read it). If there are additional requirements beyond DATABASE_URL + classification investigation, they're unknown to me. Marking this submission as covering what I could identify from context.

---

## Task: wdvrdawcyx — GENERIC GROUNDING Phase 3 (walking-tour generalization)

**Last known ClickUp state:** list = 🟦 Services — Kiro (733), status = "in progress"
(refinement posted, approved to code, sequenced after wdvrdawkxq + wdvrdax1v7).
**TRUE current state:** unchanged in ClickUp terms, BUT — found during LEAD's
2026-07-27 23:xx periodic offline check: **branch `kiro/wdvrdawcyx-phase3` already has
2 commits** (`bf0ac0a` "Walking-tour generalization via Wikidata in-area queries",
`fa4c83b` "Phase 3: G4 QA gate exempts walking tours from story_elements fail-closed"),
timestamped 15:15-15:22 on 2026-07-27 — i.e. Kiro started this BEFORE the sequencing-
override comments (10065/10066) landed telling them to prioritize the regression sweep
first. Not a protocol violation, just message-ordering; Kiro correctly pivoted to the
regression sweep afterward (18:12+) and this branch has sat untouched since.

**NOT submitted as ready** — no `READY FOR REVIEW` marker, so this is NOT reviewed or
approved. Noting two things for whenever it IS picked back up in sequence (after
`wdvrdax1v7`):

1. **`content_qa_runner.py` conflict, need to rebase/drop:** this branch's own G4 fix
   (`fa4c83b`) was written independently, forked from the same base (`196b714`) as the
   regression-sweep branch, before either knew about the other. It only exempts
   `tour_category == 'walking'` — narrower than what's already merged into `storied`
   (`f159a4a`, which also handles `exhibit_museum` tier and was independently verified
   by LEAD). When Phase 3 resumes: **drop this branch's G4 hunk entirely** and rebase
   onto current `storied` — the better version is already there. Do not try to merge
   both; they'll conflict on the same lines and the wdvrdawcyx version is now stale.
2. **`area_resolver.py` (1004 lines, new) + `generate_tour_text.py` (+39 lines,
   isolated `elif tour_category == 'walking'` branch calling `resolve_area` /
   `discover_landmarks` / `verify_landmarks`)** — structurally reasonable at a glance
   (doesn't touch the museum path), but NOT reviewed in depth — that's real work for
   whenever this task is actually submitted through the normal process.

**Sync action:** none needed (no ClickUp state drift — this is a git-only finding).

---

## Task: wdvrdawdje — STORY QUALITY (SQ1-SQ8)

**Last known ClickUp state:** list = 🟦 Services — Kiro (733), status = "in progress".
**TRUE current state:** unchanged — sequenced after Phase 3 per LEAD direction, deferred.
**Sync action:** none needed.

---

## New tasks created or requiring dispatch WHILE ClickUp is down

**For Kiro:** any section below headed `#### LOCAL-N` is a real assignment for
**Mac Mini Kiro**, dispatched during the outage because ClickUp's `create_task` isn't
reachable. Treat it exactly like a normal task in your list — it will have the same
`**Agent:** Mac Mini Kiro`, branch name, and acceptance criteria a real ClickUp task
description would have. Branch, execute, test (live-artifact hard gate still applies),
and mark `##### READY FOR REVIEW` under it when done, same as any other task in this
file. You do NOT need a real ClickUp ID to start work — LEAD will create the actual
task (`clickup_create_task`) and backfill the ID once the API recovers; that's LEAD's
sync bookkeeping, not something you wait on.

*(none yet — add sections here as they come up. Format for LEAD when creating one:
`#### LOCAL-N — <title>` followed by the same content a real task description would
have: Agent, Branch, full spec, acceptance criteria. At sync time: `create_task` first
—unavoidable, costs 1 API call — then map `LOCAL-N` → the real ID everywhere it's
referenced, then proceed with the normal 1-comment/1-status-update sync per task.)*

---

## Sync Plan (minimum-API checklist — work this top to bottom once ClickUp recovers)

| # | Task ID | Action | API calls | Synced? |
|---|---------|--------|-----------|---------|
| 1 | wdvrdawkxq | `update_task(status=complete)` + `create_comment` (verbatim text above) | 2 | ☐ |
| 2 | wdvrdax1v7 | none (no drift) | 0 | n/a |
| 3 | wdvrdawcyx | none (no drift) | 0 | n/a |
| 4 | wdvrdawdje | none (no drift) | 0 | n/a |

**Total sync cost so far: 2 API calls.** Update this table as more offline work happens.
