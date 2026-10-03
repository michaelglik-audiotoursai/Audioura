# SUBMISSION — LOCAL-569: Story retry, keep the best draft and stop when a rewrite stops helping

**Keep the best story-retry draft instead of shipping the last; stop rewriting once a rewrite
stops helping. Flag-gated, both default off, measured.**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-569-keep-best-retry`
- **Base:** `subscribed` (`3350bc9`)
- **Merge-base check:** `git merge-base --is-ancestor 3350bc9 HEAD` → exit 0 ✓

---

## The defect (LOCAL-568 / D597)

The LOCAL-432 story retry (`generate_tour_text.py`, `_max_retries = 4`, trigger when
`story_count < 3`) re-writes the **whole stop** at rising temperature and **ships the LAST
attempt**. `_best_description` keeps the longest draft only on fallback paths — never the draft
with the most *story* sentences. LOCAL-568 found that in **12 of 42** logged episodes the shipped
stop had FEWER story sentences than a draft already produced; 25 of 42 never reached 3. The real
trajectory LOCAL-568 pinned was **1 → 0 → 2 → 1**: four attempts, the richest (2) produced third,
and the loop shipped the last (1). (LEAD correction to 568: "attempt 5 never pays" was a logging
artefact — the final attempt's `story_count` was never printed, so it was *unknown*, not zero.)

---

## What shipped (all default OFF — behaviour byte-for-byte unchanged unless opted in)

Three changes, each committed separately, plus one regression fix found during verification.

### 1. Instrument (always on, logging only) — `805f3b7`
Every attempt that produces parseable prose now logs, **including the last**:

```
[LOCAL-569] Stop N attempt K/5 story_count=C words=W
```

Emitted before any gate/`continue`, wrapped so instrumentation can never raise or alter control
flow (`generate_tour_text.py:14365`). This directly answers the "unknown, not zero" gap: the final
attempt's `story_count` is now printed for every stop.

### 2. `STORY_RETRY_KEEP_BEST=1` (default off) — `0a39f72`
Among the drafts the story retry produced, ship the one with the **most story sentences**, ties
broken by **most words**, instead of whichever happened to be last. A draft becomes a keep-best
candidate only *after* it has already passed the placeholder / refusal / LOCAL-417 positive gate /
word-floor / beat gates (those gates `continue` earlier and never reach the candidate call), so a
**gate-failing draft can never win over a passing one**. The decision lives in one importable
helper, `_l569_select_best_story` (`:5684`), so it is unit-tested against the real trajectory
rather than a copy. Ship points: the in-loop keep-best point (`:15108`) and the post-loop point
(`:15239`).

### 3. `STORY_RETRY_EARLY_STOP=1` (default off, **requires** keep-best) — `a6241c4`
Stop the story retry once an attempt **fails to beat the running-best `story_count`** (a tie also
stops), with a **hard cap of 3** story attempts (`_L569_STORY_ATTEMPT_CAP = 3`, `:5702`; decision
in `_l569_should_early_stop`, `:5705`). The running best is captured from **prior** attempts only,
so "fails to beat" compares this attempt against earlier ones, not itself. It changes **only** the
LOCAL-432 story branch — LOCAL-417/393/391/98 retries keep their full budget. On early stop the
loop breaks and ships the keep-best draft (`:14699`, `:15239`).

### 4. Regression fix — `5b60062` (found during verification, not in the original plan)
The step-2 keep-best insertion had accidentally deleted the `else:` and the
`_DESC_TRANSIENT_CODES = {429, 500, 502, 503, 504}` definition for the **non-200** response path.
That left the LOCAL-292 transient / 429 / credit-exhausted retry logic as **dead code after a
`return`** inside the `status == 200` branch, and referenced an **undefined** `_DESC_TRANSIENT_CODES`.
Any non-200 response would have fallen through the `try` with no backoff and no Retry-After
handling. Restored the else-branch verbatim from base. **The diff vs `subscribed` is now purely
additive** (`git diff subscribed -- generate_tour_text.py | grep '^-'` → empty).

### Unit test — `tests/test_local569_keep_best_story.py` (committed in `0a39f72`)
18 tests, all passing. It builds the **1 → 0 → 2 → 1** trajectory from real sentences, asserts the
counts against the real `story_gate.extract_story_sentences` (so the fixture can't drift from the
classifier), then shows:

- flag **off** / today == ship-last == **story_count 1**
- `STORY_RETRY_KEEP_BEST` **on** == keep-best == **story_count 2**

plus tie-breaks (word_count), story_count dominates word_count, early-stop semantics
(improvement keeps going, tie stops, no-improvement stops, hard cap stops even on improvement,
cap == 3), and a loop simulation (keep-best-only uses all attempts and ships 2; early-stop halts
after 2 writer calls and ships the best-seen 1; cap bounds a never-reaches-3 trajectory).

```
18 passed in 0.72s
```

---

## Measurement (step 4)

Harness: `run_local569_measure.py`. **D261 host env** (`DISABLE_TOUR_CACHE=1`, `STORIED_MODE=true`,
`DATABASE_URL → localhost:5433`). **Gemini off** as in LOCAL-566 (`GEMINI_API_KEY`/`GOOGLE_API_KEY`
set empty *before* `.env` is read, because `story_leads.py` re-`setdefault`s a popped key — an
empty-but-present value is falsy for the guard and blocks the refill). **3 stops** per tour so the
9-cell matrix fits the $6 OpenAI cap; the stop count is identical across arms so the A/B/C
comparison is unaffected. One run per cell, as specified.

**Three museums:**
- **Palais Lascaris, Nice** — story-poor (LOCAL-566: 39 writer calls / 4 stops, most stops stuck
  at story_count 1–2 through 5/5). The venue the retry hurts most.
- **Museum of Fine Arts, Boston** — the standing storied reference venue.
- **The Metropolitan Museum of Art, New York** — the **non-story-poor control** (my choice).
  *Why:* the Met resolves offline from a dense Wikidata/Wikipedia corpus even with Gemini off, and
  its signature works carry rich named-person provenance (artists, donors, acquisitions), so stops
  reach story_count ≥ 3 readily. Here the flags should barely change the outcome and early-stop
  should ship as soon as ≥ 3 is hit — the guard that the flags **don't harm** a storied museum.
  (Isabella Stewart Gardner was tried first but is unresolvable offline with Gemini off — 0 corpus
  pages — so it produced an empty tour and could not exercise the retry; discarded.)

**Arms:** A = both flags off (today). B = keep-best. C = keep-best + early-stop.

### Results per cell

| Cell | writer calls | attempts logged | story retries | writer $ | stops delivered | shipped story_count by stop* | early stops | keep-best ships | `score_tour` defects |
|---|---|---|---|---|---|---|---|---|---|
| **Palais A** | 81 | 18 | 12 | 0.5164 | 3/3 | {1:3, 2:0, 3:3} | — | — | none (clean) |
| **Palais B** | 84 | 22 | 16 | 0.6111 | 3/3 | {1:0, 2:3, 3:3} | — | 1,2,3 | none (clean) |
| **Palais C** | 89 | 12 | 6 | **0.3456** | 3/3 | {1:1, 2:2, 3:3} | **1,2,3** | 1,2,3 | none (clean) |
| **MFA A** | 96 | 19 | 12 | 0.5450 | 3/3 | {1:2, 2:4, 3:2} | — | — | none (clean) |
| **MFA B** | 103 | 15 | 9 | 0.4399 | 3/3 | {1:3, 2:1, 3:3} | — | 1,2,3 | none (clean) |
| **MFA C** | 96 | 12 | 6 | **0.3657** | 3/3 | {1:2, 2:3, 3:5} | **1** | 1,2,3 | unsourced_person_event |
| **Met A** | 86 | 7 | 1 | 0.2343 | 2/3 | {1:4, 2:3, 3:4} | — | — | thin, offsite_entity, unsourced_person_event |
| **Met B** | 90 | 6 | 0 | 0.2138 | 2/3 | {1:3, 2:4, 3:3} | — | 1,2,3 | thin |
| **Met C** | 100 | 7 | 1 | 0.2395 | 2/3 | {1:6, 2:3, 3:4} | — | 1,2,3 | thin, dangling_reference, offsite_entity, unsourced_person_event |

Costs are `cost_rates.llm_cost` as recorded by `_LAST_GENERATION_COST`. OpenAI auto-caching is on
in all arms (D596: ~66.8% of writer input is auto-cached), so these are the **cache-discounted**
figures; the harness captured no separate non-discounted total, so the pre-cache number is not
reported rather than estimated. **Cumulative OpenAI tour cost across all 9 cells: $3.5114 of the
$6 cap.** Per-attempt `[LOCAL-569] Stop N attempt K/5 …` lines are in each cell's `.log`; full tour
texts in each `.txt`; `score_tour` detail and attempt arrays in `summary.json`.

\* **Important measurement caveat.** `shipped_story_count_by_stop` in the table is parsed from the
*last logged attempt line* for each stop — a ship-last proxy. With keep-best ON it **understates**
what actually ships, because keep-best ships an *earlier, richer* draft. The `[LOCAL-569] KEEP-BEST
ship` log lines carry the truth. Example from `Palais_C.log`:

```
[LOCAL-569] Stop 2 attempt 1/5 story_count=2 words=286
[LOCAL-432] Stop 2: STORY RETRY — story_count=2 < 3, need 1 more, retrying
[LOCAL-569] Stop 2 attempt 2/5 story_count=1 words=222
[LOCAL-569] Stop 2: EARLY STOP story retry — story_count=1, prev_best=2, story_attempts=1 (no improvement over prior best)
[LOCAL-569] Stop 2: KEEP-BEST ship (post-loop) — story_count=2 words=286
```

Today (arm A) would have shipped the last draft, **story_count 1**. Keep-best shipped the earlier
**story_count 2** — exactly the LOCAL-568 defect, fixed and observed live. The same pattern repeats
on Palais_C stop 1 (last 1 → shipped 2). So Palais_C's *real* shipped counts are {1:2, 2:2, 3:3},
not the proxy {1:1, 2:2, 3:3}.

### What the arms show

1. **Keep-best never ships worse than ship-last, by construction, and demonstrably ships better.**
   The candidate set is every gate-passing story-retry draft; the chosen draft maximises
   `(story_count, word_count)`. The `KEEP-BEST ship` lines fired on **all 3 stops in every B and C
   cell**. The Palais_C log shows two stops where keep-best rescued a richer earlier draft the
   ship-last loop would have discarded.

2. **Early-stop cuts writer cost on story-poor venues without losing story content.** On the two
   story-poor venues, arm C roughly **a third cheaper** than arm A — Palais **$0.5164 → $0.3456
   (−33%)**, MFA **$0.5450 → $0.3657 (−33%)** — because `story_retries` halved (Palais 12 → 6,
   MFA 12 → 6) and attempts-logged dropped (Palais 18 → 12, MFA 19 → 12). Early stops fired on all
   three Palais_C stops and one MFA_C stop. The hard cap of 3 was never even reached — the
   no-improvement rule stopped each stop after a single unhelpful rewrite.

3. **On the non-story-poor control (Met) the flags barely move anything.** Met already resolves
   story_count ≥ 3 on the first or second attempt (story_retries 1 / 0 / 1 across A/B/C), so there
   is little retry to prune: cost is flat (0.2343 / 0.2138 / 0.2395) and story content is unchanged
   or richer (Met_C stop 1 shipped 6). This is the intended guard — the change targets the retry
   waste on story-poor venues and is a no-op where the writer already succeeds. (Met delivered 2/3
   stops in **all** arms, including today's A — a resolution property of this run with Gemini off,
   independent of the flags.)

### Comparison against the LOCAL-563 noise floor

Per D596/D597 the LOCAL-563 noise floor is **qualitative**: stop selection and per-stop story_count
are **stochastic run-to-run** (D570: "Stop selection is stochastic"), so a change that alters output
"ships only after a blind comparison inside the LOCAL-563 noise floor." There is no committed
numeric noise-floor table in this worktree to difference against, so I characterise the floor from
the arms themselves and frame the result as a blind comparison rather than a point estimate:

- The A-arm (today, unchanged code) already swings widely between stops and venues: Palais stop 2
  shipped **0** story sentences; MFA stop 3 shipped **2**; Met stops **3–4**. Across arms B and C
  (same code at the retry entry, same stops) the per-stop counts reshuffle in the same band
  (Palais stop 1: 3 / 0 / 1; stop 2: 0 / 3 / 2) — this run-to-run reshuffle **is** the noise floor,
  and it is as large as or larger than the arm-to-arm differences in the raw proxy.
- Therefore the raw per-stop proxy counts **cannot** by themselves prove the change helps — they
  sit inside the noise. What is **outside** the noise and attributable to the code, because it is
  logged per decision rather than inferred from a single sample, is: (a) keep-best shipping a
  strictly richer earlier draft on the stops where ship-last would have regressed (the Palais_C
  evidence above), and (b) early-stop's **−33% writer cost** on story-poor venues with no loss of
  shipped story content. Both are mechanism-level facts, not single-sample outcomes.
- The product question "does arm C *read* better than arm A?" is left to Michael's ear via the
  blind pack below — exactly the D596 "blind comparison" gate. No flag flips on without his verdict.

---

## Blind pack for Michael

`~/Desktop/Audioura_story_blind/` (outside the repo):

```
MFA_P.txt     MFA_Q.txt
Met_P.txt     Met_Q.txt
Palais_P.txt  Palais_Q.txt
KEY.md
```

For each museum the arm-A and arm-C tour texts are written as `_P.txt` / `_Q.txt`, with **P/Q
flipped independently per museum** (so the assignment is not uniform and carries no cross-museum
tell). The texts contain **no arm markers** (verified: no `LOCAL-569`, `KEEP-BEST`, `arm`,
`STORY_RETRY` strings in any P/Q file). `KEY.md` opens with a "do not read" title, then **exactly
60 blank lines**, then the mapping. Judge first, then scroll.

---

## DB declaration — no writes, nothing hidden, never a DELETE

`audio_tours` row counts (via `tests/db_connection`, same DB the harness used):

| | total | non-test |
|---|---|---|
| **before** | 198 | 56 |
| **after** | 198 | 56 |

Equal. Independently confirmed **0 rows created in the last 4 hours** (the whole measurement
window). The in-process `generate_tour_text()` path the harness calls makes **no**
`store_audio_tour` call, so no tours were inserted. Consequently there was **nothing to hide** — no
lat/lng nulling was needed — and **no DELETE** was ever issued. No GCloud. Both snapshots are also
recorded in `LOCAL569_measure/summary.json` (`audio_tours_before` / `audio_tours_after`).

---

## Files

- `generate_tour_text.py` — instrumentation, keep-best, early-stop, helpers `_l569_story_count`
  (`:5670`), `_l569_select_best_story` (`:5684`), `_l569_should_early_stop` (`:5705`),
  `_L569_STORY_ATTEMPT_CAP` (`:5702`); regression fix to the non-200 else-branch.
- `tests/test_local569_keep_best_story.py` — 18 tests, the 1→0→2→1 replay.
- `run_local569_measure.py` — the measurement harness (resumable, cost-capped, log-parsing).
- `LOCAL569_measure/` — per-cell `.txt` / `.log` / `*_evidence.json` / `*_story_elements.json` /
  `*_threads.json`, and `summary.json` (full matrix, costs, attempts, scores, DB snapshots).
- `~/Desktop/Audioura_story_blind/` — the blind pack (not in the repo).

## Commits (base `subscribed` `3350bc9`)

```
fd58086  LOCAL-569 step 4: complete A/B/C measurement matrix (3 museums x 3 arms)
5b60062  LOCAL-569 fix: restore non-200 else-branch dropped during step 2
a6241c4  LOCAL-569 step 3: STORY_RETRY_EARLY_STOP (default off, requires keep-best)
0a39f72  LOCAL-569 step 2: STORY_RETRY_KEEP_BEST (default off) + early-stop scaffolding
805f3b7  LOCAL-569 step 1: always-on per-attempt story instrumentation
```

`git rev-list --count subscribed..HEAD` ≥ 1 ✓ (6 after this submission).
`DECISIONS.md` / `CLAUDE.md` / `BACKLOG.md` / `WORK_QUEUE.md` / `.continuous_dev/STATUS.md` — left
untouched.

## Recommendation

Keep both flags **off** by default (as shipped). The mechanism is correct and tested; early-stop
buys a real ~33% writer-cost cut on story-poor venues with no measured loss of shipped story
content, and keep-best is a strict no-regression over ship-last. But the per-stop story_count
differences in a single run sit inside the LOCAL-563 noise floor, so the flip to on is a **product
decision gated on Michael's blind verdict** (D596), not something these three runs can decide alone.
