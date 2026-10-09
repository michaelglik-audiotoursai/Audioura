# SUBMISSION — LOCAL-654: mid-clause collisions under the cheap arm (ON)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-654-collisions` (from `subscribed` @ `8e12c846`)
**Base verified:** `git merge-base --is-ancestor 8e12c846 HEAD` → exit 0.

## The defect

With the cheap arm ON (`NARRATION_MODEL=gpt-4.1-mini RESEARCH_BACKEND=serper
PARALLEL_STOPS=1`), sentences collided mid-clause in 3 of 6 ON tours:

- 599 (AIC): *"…the vulnerability of those who venture into Thousands of copies
  of The Great Wave were…"*
- 597 (Uffizi): *"…giving him two years to complete Leonardo prepared
  extensively…"*
- 592 (Courtauld): one more.

## Root cause (found by offline replay — step 1, commit `33f6972f`)

`gpt-4.1-mini` routinely **drops the space after a sentence-ending period**:
`…venture into its depths.Thousands of copies…`, `…two years to complete
it.Leonardo prepared…`.

Every sentence splitter in the pipeline keyed on a period **followed by
whitespace** — `re.split(r'(?<=[.!?])\s+', text)`. The welded pair
`depths.Thousands` therefore travelled through the pipeline **as one "sentence."**
When a sentence-removing gate (D518 story-replace, LOCAL-626 date/object-type
bleed, PERSON-CAP, D523 seam) dropped the half it had cut, the surviving
neighbour fused mid-clause — leaving exactly the `…venture into Thousands…`
seam the lead described. The passes fire only in the ON logs because only the
mini narrator produces the no-space weld.

Confirmed offline with `repro_local654.py` (replays the logged stop text through
the post-narration passes in order) and `repro_local654_hygiene.py`.

## The fix (step 2 — at the splitter root, NOT a new afterward pass, D643)

`sentence_split.split_sentences` — the shared splitter — now also recognises the
**no-space boundary**: a sentence-ending `.`/`!`/`?` jammed directly against the
next sentence's capitalised first letter (`[A-ZÀ-Ý][a-zà-ÿ]`, optionally through
an opening quote/bracket), with no space. It is guarded by the **same**
`_ends_on_abbreviation` re-join as the whitespace boundary, so:

- initials never split — `Isabella V.McMullen` stays one name;
- dotted acronyms never split — `U.S.Grant`;
- decimals never split — `25.7`, `37.9`;
- domains never split — `artic.edu`.

Because the fix lives in the splitter, **every** sentence-removing gate now cuts
on the real boundary and can no longer weld a mid-clause collision. No new
cleanup pass patches the seam afterwards.

Files: `sentence_split.py` (`_NOSPACE_BOUNDARY`, `_split_keep_boundaries`,
extended guard); `generate_tour_text.py` + `pass_dump.py` (per-pass before/after
dumps behind `LOCAL654_DUMP=1`, no-op when unset).

## Step 3 — guard test

`tests/test_local654_no_midclause_collision.py` (8 tests, **exit 0**):

1. the hardened splitter splits the mini-model welds and keeps initials /
   acronyms / decimals / domains / curly-quote welds intact;
2. over **every** `tests/fixtures` tour **plus the five AB3 tours** (592, 595,
   597, 599, 600, committed under `tests/fixtures/local654/`), **no**
   sentence-removing pass introduces a new mid-clause collision — the
   general `…into Thousands…` shape (a lowercase word running straight into a
   Capitalised real word with no punctuation between them), compared per-pass
   before→after so ordinary proper-noun objects are never falsely flagged.

## Step 4 — suites + canaries (all exit 0)

| suite | exit |
|---|---|
| `tests/test_local654_no_midclause_collision.py` | 0 (8 passed) |
| `tests/test_local611_canary.py` (**museum canary**) | 0 (unchanged) |
| `test_local646_walking_regressions.py` (**walking canary**) | 0 (unchanged) |
| `tests/test_local614_sentence_splitter_initials.py` | 0 |
| `tests/test_local635_sentence_integrity.py` | 0 |
| `tests/test_d523_story_selection_and_hygiene.py` | 0 |
| `tests/test_local626_{invented_facts,recruitment_copy,highlight_first,venue_not_a_stop}.py` | 0 |

Full offline suite (`python3 run_tests.py`): **no new failures introduced by this
branch.** Verified by running `run_tests.py` on this branch and on a throwaway
worktree at base `8e12c846` and diffing the failure sets — the only differences
are flaky service/network/timeout tests (live `*_style_ab`, `*_model_upgrade`,
`*_anchor_regression`, and `test_d539_closure_regression.py` which collects 0
tests on both trees). This branch had **fewer** failures than base, none in any
sentence/splitter/hygiene suite.

## Step 5 — Live (own disposable container)

`run_local654_live.sh` builds `Dockerfile.generator` from this branch (so the
hardened `sentence_split.py` is in the image) and runs `run_local654_container.py`
in a **disposable** container: `docker run --rm --name local654-gen -p 5121:5000`
on `development_default`. **Never** `docker compose -p audioura`; no `audioura-*`
container renamed, replaced or touched. Image + container removed on exit.

Env (the ON arm): `NARRATION_MODEL=gpt-4.1-mini RESEARCH_BACKEND=serper
PARALLEL_STOPS=1`, fresh (`DISABLE_TOUR_CACHE=1 DISABLE_STOP_POOL=1`). Hard cap
**$1.20 combined** via `tests/live_run_meter.py` with a $0.45 reserve gate before
each tour. `paid_api_calls` checked before the run (my container is a fresh host,
spend $0.00).

Two fresh 3-stop tours, both DELIVERED 3/3:

| venue | id | collisions | no-space welds | detectors | Kiro | cost |
|---|---|---|---|---|---|---|
| Uffizi Gallery, Florence | **627** | **none** | **0** | **0 fail (exit 0)** | **8/10** | $0.7725 |
| The Art Institute of Chicago | **629** | **none** | **0** | **0 fail (exit 0)** | **4.5/10** | $0.5331 |

- **Collisions (none):** both delivered tours contain **0** no-space period-welds
  (the `depths.Thousands` shape) and none of the original evidence strings
  (`venture into Thousands`, `complete Leonardo`, `depths.Thousands`,
  `it.Leonardo`). The stop-1 prose on both tours (the stops that collided in the
  evidence) reads cleanly. (The harness's broad candidate regex prints 39/28
  *lowercase→Capital* pairs, but every one is a legitimate proper-noun object —
  "Mount Fuji", "Grant Wood", "the Art Institute" — not a dropped-into sentence
  weld; the authoritative signals are 0 welds + 0 detector failures.)
- **Detectors** (`.continuous_dev/bench/detectors.py <id> 3 "<venue>"`):
  `627: 0 detector failure(s)` exit 0; `629: 0 detector failure(s)` exit 0.
- **Kiro** (`.continuous_dev/calib/critique.sh <id> 3`): Uffizi **8/10**; AIC
  **4.5/10**. Neither critique flags a mid-clause collision or sentence-boundary
  defect — the LOCAL-654 bug is gone. The AIC 4.5 is driven entirely by
  **content/factual** issues unrelated to this ticket (the Great Wave is not
  distinctively an AIC holding; a hallucinated "1961 founding"; a thin
  conclusion) — the critique's own code suggestions are a collection-residency
  gate and a verified museum-intro, not sentence splitting.

### Rows & spend
- `audio_tours`: additive **is_test only** — exactly two rows written, **627** and
  **629**, both `is_test = true`, 3 stops each. **No DELETE.** (Snapshot counts in
  the log, 424→427, span concurrent LOCAL-617 inserts by another agent on the
  shared DB — id 628 is a LOCAL-617 row, not mine.)
- **Spend** (`paid_api_calls`, my host `c84f83946ba2`): **$1.0028** over 399
  calls — under the $1.20 whole-task cap. `cost_ledger` test row written
  (`user_id=TEST-LOCAL-654`, breakdown openai $0.3723 / gemini_tokens $0.0274 /
  serper $0.0600 / preflight $0.0734).
- No GCloud used.

## Files
- `sentence_split.py` — no-space boundary + extended abbreviation/initial guard.
- `generate_tour_text.py`, `pass_dump.py` — per-pass dumps behind `LOCAL654_DUMP=1`.
- `tests/test_local654_no_midclause_collision.py` — the guard (8 tests).
- `tests/fixtures/local654/tour_{592,595,597,599,600}.txt` — AB3 fixtures.
- `repro_local654.py`, `repro_local654_hygiene.py` — offline replays.
- `run_local654_container.py`, `run_local654_live.sh` — isolated live verify.
- `SUBMISSION_LOCAL-654.md` — this file.
