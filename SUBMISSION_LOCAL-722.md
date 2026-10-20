# SUBMISSION — LOCAL-722: Fresh Courtauld tours refused: the same work delivered twice (D3(e))

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-722-duplicate-work`
**Base:** `subscribed` = `800863c9` (`git merge-base --is-ancestor 800863c9 HEAD` → exit 0 ✓)
**code_sha:** `99757736b7cb9af4c67fb0cd53852f7c45f6a585` (the fix commit; this doc is amended into it)

---

## Problem

Fresh 6-stop "Courtauld Gallery, London" museum tours (`DISABLE_TOUR_CACHE=1`,
`DISABLE_STOP_POOL=1`) ended in `error / factual_integrity` ("We couldn't verify
enough facts…") because `D3(e) No duplicate stops (FACTUAL)` fired — the SAME
work was delivered as two stops even though the LOCAL-212 "Selected stops" list
held it only once:

- LOCAL-721's gpt-4.1 run: **"Landscape with the Flight into Egypt"** delivered twice.
- LEAD's Sonnet run: `'A Bar at the Folies-Bergère' = 'A Bar at the Folies-Bergère.'
  (same work)` — the SAME title with a trailing period.

A listener who typed one of the best-documented museums in London saw only
"couldn't verify enough facts" — wrong twice over: the facts were sound, and a
duplicate is a correctable delivery defect, not a reason to discard the tour.

## Root cause

Selection is already unique by normalised title (D1v2 `[A6+]` title-dedup in
`_verify_works_in_collection`). But a second copy of an already-selected work can
still reach the SHIPPED text AFTER selection:

1. the writer narrates the same work twice (LOCAL-721 gpt-4.1); and
2. a replenished / rewritten title can differ from a stop already present by
   only a trailing period, an accent, a hyphen or curly quotes
   (`replenish_to_count` deduped its `seen` set by exact lowercase string, so
   `"A Bar at the Folies-Bergère."` did not match `"a bar at the folies-bergère"`).

When a duplicate reached QA, `D3(e)` counted it as a FACTUAL failure and the
service's generic `FACTUAL_FAIL_COUNT > 0` branch refused the whole tour — with
no corrective, unlike G4 (ungrounded sentences) and LOCAL-639 (lost-newline
headers), which drop/repair and re-check.

## Fix

**One normalisation, shared by prevention and detection** — new module
`stop_title_dedup.py`:
- `normalize_stop_title()` — casefold, strip accents (NFKD), replace every
  non-word/non-space char (punctuation, quotes, italics markers, hyphens) with a
  space, collapse whitespace. Byte-for-byte identical to `story_miner._normalize`
  (asserted by a test), so the guard that prevents a duplicate and the D3(e)
  check that fails on one can never drift.
  `"A Bar at the Folies-Bergère."` → `"a bar at the folies bergere"` ← merges
  the trailing-period pair; `"Self-Portrait"` ≠ `"Self-Portrait with Bandaged Ear"`
  stays distinct.
- `find_duplicate_stop_titles()` — the `(duplicate, first)` pairs D3(e) reports.
- `dedupe_delivered_stops()` — drops any stop BLOCK whose normalised title
  repeats an earlier one (keeps the first), renumbers the surviving `Stop N:`
  headers 1..k. Deterministic and idempotent.

**1. Prevention — unique through delivery.**
- `generate_tour_text._apply_delivery_hours_guard` (the single delivery choke
  point every path returns through — fresh / pool / cache / by_reference /
  overview) now runs `dedupe_delivered_stops` on the finished text BEFORE the
  LOCAL-619 conclusion/header rebuild, so the "That's N stops" count, the
  orientation "first stop" name and the inter-stop Directions are all rebuilt
  against the deduped set.
- `generate_tour_text.replenish_to_count` keeps a normalised-title guard
  (`_seen_norm`) alongside the existing lowercase `seen` set, so a replenishment
  candidate that is the same work as an existing stop (trailing period / accent /
  hyphen / curly quotes) is rejected instead of appended.

**2. Corrective — D3(e) is no longer fatal (same pattern as G4).**
- `content_qa_runner.py`'s D3(e) check uses the shared helper and records the
  duplicate pairs on a job-scoped `DUPLICATE_STOP_TITLES` list (mirrors
  `G4_UNGROUNDED_SENTENCES`).
- `generate_tour_text_service.py`'s QA loop adds a D3(e) corrective branch BEFORE
  the generic refusal: it drops the duplicate block(s), rebuilds the conclusion,
  and re-checks — refusing only if fewer than the minimum (`2`) distinct stops
  remain.

### Files changed
- `stop_title_dedup.py` — **new** shared normalisation + delivered-stop dedup.
- `generate_tour_text.py` — delivery-dedup step in `_apply_delivery_hours_guard`;
  normalised-title guard in `replenish_to_count`.
- `content_qa_runner.py` — D3(e) uses the shared helper; exposes
  `DUPLICATE_STOP_TITLES`.
- `generate_tour_text_service.py` — D3(e) corrective branch in the QA loop.
- `test_local722_duplicate_work.py` — **new** unit tests.
- `.gitignore` — ignore `.local722_live/` (captured live env with secrets; never committed).

## Unit tests — `test_local722_duplicate_work.py`

```
python3 -m pytest test_local722_duplicate_work.py -q
18 passed in 0.87s
```

- **TestNormalisationMergesSameWork** — the two pairs MERGE (trailing period,
  curly quotes, accent, hyphen⇄space); the ticket's negative case
  **"Self-Portrait" vs "Self-Portrait with Bandaged Ear"** stays DISTINCT; two
  other distinct Courtauld works stay distinct.
- **TestNormalisationMatchesStoryMiner** — `normalize_stop_title` == `story_miner._normalize`
  on every sample (no drift between guard and check).
- **TestFindDuplicates** — the trailing-period pair and a verbatim repeat are
  reported; distinct works report nothing; the six real Courtauld works report
  no duplicate.
- **TestDedupeDeliveredStops** — drops the duplicate block, renumbers survivors
  1..3, idempotent, no-op on clean text, and the two distinct Self-Portraits are
  NOT merged.
- **TestQADuplicateCheckExposesPairs** — `run_qa` populates `DUPLICATE_STOP_TITLES`
  on a duplicate tour and leaves it empty on a clean one.
- **TestReplenishRejectsSameWork** — `replenish_to_count` rejects a same-work
  candidate that differs only by a trailing period; exactly one copy ever present.

## Regression suites

```
python3 -m pytest test_local721_cta_link_text.py test_local669c_final_gate.py \
  test_local669b_identity_dedup.py tests/test_d558_replenish_loop.py \
  test_local632_junk_and_shortfall.py test_local639_lost_stop_header.py -q
105 passed

python3 -m pytest tests/test_local616_hours_guard_every_path.py \
  test_local585_about_museum_stop.py test_local592_about_in_stop1.py \
  test_local642_paren_title_flatten.py tests/test_local593_actionable_factual_failure.py -q
91 passed, 1 failed
```

The one failure —
`test_local592_about_in_stop1.py::TestPartialPointerOnlyForMissing::test_admission_known_hours_missing_points_to_hours_only`
("12 dollars" vs "8 dollars" in `about_museum_stop.build_opening_section`) — is
**PRE-EXISTING on the base `800863c9`** (verified by `git stash` + re-run: fails
identically with my changes stashed) and is unrelated to LOCAL-722 (About-stop
admission-price formatting).

## Live test — own container, no phones

- Built `local722-gen` from `Dockerfile.generator` (`COPY *.py` bakes the
  working-tree fix in; verified inside the image: `stop_title_dedup` importable,
  `normalize_stop_title` merges the trailing-period pair and keeps the two
  Self-Portraits distinct, the D3(e) corrective and the delivery dedup are both
  present in the image's source).
- `docker run --rm --name local722-gen -p 5097:5000 --network development_default`,
  env copied from `audioura-tour-generator-1` + `DISABLE_TOUR_CACHE=1
  DISABLE_STOP_POOL=1`, meter mounts. **No `docker compose -p audioura`; the
  `audioura-*` containers were never touched or renamed** —
  `audioura-tour-generator-1` stayed `Up … (healthy)` on 5000 throughout.
  Container + image removed after the run. `/health` code_sha = `800863c9`
  (the image's build `GIT_SHA`; the working tree carries the uncommitted
  LOCAL-722 fix, baked in by `COPY *.py`).
- `POST /generate {"location":"Courtauld Gallery, London","tour_type":"museum",
  "total_stops":6}`, twice.

**Run 1 — job `82ab3ddc` — COMPLETED, D3(e) PASSED, 6 distinct works:**

1. Self-Portrait with Bandaged Ear
2. Ambroise Vollard
3. Christ and the Woman Taken in Adultery
4. Footed Bowl with the Crucifixion
5. A Bar at the Folies-Bergère
6. Landscape with the Flight into Egypt

**Run 2 — job `1ca09075` — COMPLETED, D3(e) PASSED, 6 distinct works:**

1. Ambroise Vollard
2. Self-Portrait with Bandaged Ear
3. Christ and the Woman Taken in Adultery
4. Footed Bowl with the Crucifixion
5. A Bar at the Folies-Bergère
6. Landscape with the Flight into Egypt

Both tours delivered the same six distinct works (order differs). The two works
that duplicated in the LEAD's failing runs — **A Bar at the Folies-Bergère** and
**Landscape with the Flight into Egypt** — each appear **exactly once**. QA
passed round 1 on both; `D3(e) No duplicate stops (FACTUAL)` PASSED on both.

**Overpass:** every `[OSM-VENUE] Overpass ConnectionError` fired in my isolated
container (the same symptom LOCAL-721 saw). It did **not** change the result —
Overpass only supplies supplementary coordinate/venue facts; both tours
completed with six distinct works regardless.

**`audio_tours` row count:** **498 before / 498 after** — `/generate` writes no
`audio_tours` rows, as expected.

**Meter cost:** run 1 `$0.719032` + run 2 `$0.961252` = **$1.680284** total
(`[COST_METER] FRESH | tour_generate`), under the $2 budget.

**Daily-cap note (not a D3(e) refusal):** the shared account's
`DAILY_PAID_LIMIT_USD=$8` was already exhausted earlier today. Run 1's core
generation squeaked through before the cap blocked everything (its optional
enrichment — SERP, prolog LLM, I-CON advisory, Part-4 recap — fell back
gracefully) and COMPLETED. Run 2's first attempt (job `58c6eedf`) errored with a
`'artist'` KeyError because EVERY paid call was refused by the cap — **not** a
D3(e) refusal and unrelated to this fix. I re-ran run 2 with a container-local
`DAILY_PAID_LIMIT_USD=9` override (my container only; `audioura-*` untouched) and
it COMPLETED as reported above. Total metered spend stayed under the $2 budget.

## Process compliance

- Branched from HEAD (`subscribed` = `800863c9`); `git merge-base --is-ancestor
  800863c9 HEAD` → 0. Did not branch from `origin/*`.
- Did NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, or `.continuous_dev/`.
- No phones; no `audioura-*` containers touched or renamed. Captured live env
  kept in gitignored `.local722_live/` (never committed).
