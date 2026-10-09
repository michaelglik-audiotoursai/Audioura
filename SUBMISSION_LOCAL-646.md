# SUBMISSION — LOCAL-646: WALKING-tour regressions from the museum work

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-646-walking-regressions`
**Base:** `subscribed` @ `2d162ba5` (verified: `git merge-base --is-ancestor 2d162ba5 HEAD` → exit 0)

## Summary

Tour `audio_tours.id=557` (the Oct-6 baseline request, re-run today) regressed on two
counts versus the Oct-6 baseline (commit `3d2eb84c`, Kiro 7 → 6.5). Both regressions
were introduced by the museum work (LOCAL-628 / LOCAL-638) and are fixed **at the
source**. A third issue — surfaced by the first fix on the museum canary — is also
fixed. Regression 3 (CURRENT events) was investigated and found **not** to be caused
by a guard; it is documented, not "fixed", per the ticket.

| # | Regression | Root cause | Fix |
|---|-----------|-----------|-----|
| 1 | Stop 4 layout collapsed: `Type/Specialty: … Specific Examples: …` on one line, and the ENTIRE narration glued onto the `Orientation:` line | `stop_editor._split_stop_block`'s `_STRUCT_LABELS` set did not know `Type/Specialty:` / `Specific Examples:` (nor `Operational Details:` / `Museum Information:`). A stop carrying those fields had the field lines — and everything after them, incl. the `Orientation:` block and the narration — mis-classified as rewritable *body*, which the LLM editor reflowed into one run-on line. | `stop_editor.py`: add the four field labels to `_STRUCT_LABELS` so each field line is preserved verbatim and only the true narration paragraph(s) reach the editor. |
| 2 | Duplicate transition: a bare `Continue to The Old State House.` added right after an existing `Directions: … until you reach the iconic Old State House`. | `directions_guarantee._DIRECTIONS_LABEL_RE` lacked `re.MULTILINE`. `_block_has_transition` joins the last ~4 spoken lines with `\n` and searches; the `Directions:` line was the LAST of the joined lines, so `^` (without MULTILINE) never matched → the stop was treated as missing a hand-off and a duplicate `Continue to …` was appended. | `directions_guarantee.py`: compile `_DIRECTIONS_LABEL_RE` with `re.MULTILINE` so an existing walking `Directions:` line anywhere in the tail is recognised and nothing is added. |
| 3 (canary) | Museum canary (Courtauld, tour 559): `hours_said_twice` / `admission_twice` detector failures. | Pre-existing LEAD `97f1784a` field-sync in `place_practical_facts_in_opening`: the composed hours/admission were placed as the Stop-1 spoken opening paragraph AND copied into the `Museum Information:` field line. The TTS extractor strips the whole `Museum Information:` line, so the **audio** spoke the facts once — but the bench `detectors.py` greps the whole `tour_content` and counts the field-line value too. The stop-editor fix (reg 1) made the field line survive cleanly, exposing the double-count. | `practical_facts_gate.py`: clear the `Museum Information:` field line instead of mirroring the composed facts into it. The facts remain in the spoken opening paragraph (and the text view); hours/admission now appear exactly once in the delivered text. |

## Regression 3 — investigated, NOT a guard

The baseline told recent dated events (2023 City Hall slide, Walsh-era Boston Calling
trial, Romney's 2006 Faneuil Hall signing); 557 has "nothing after 2011" in those
spots. I checked whether a guard drops dated recent sentences:

- There is **no** recency/year-threshold filter anywhere in the pipeline.
- `date_consistency_guard` drops a sentence only when its date **conflicts** with the
  stop's kept date (intra-stop coherence); the date-span logic only drops *unverifiable
  computed spans*. Neither keys on how recent a date is.
- 557's content actually includes recent dated stories — Chuck Turner (2010), the
  "Soiling of Old Glory" (1976), the Sacred Cod heist (1933), DiMasi (2011). It simply
  chose a **different, valid** set of stories than the baseline's.

Conclusion: the difference is LLM generation variance in *which* dated events the model
selected, **not** a guard removing recent sentences. Per the ticket ("Fix it only if a
guard is the cause"), no code change was made.

## Pre-existing items (documented, NOT fixed — present on Oct 6 too)

- Stop 5 is the topic itself ("Massachusetts politics and current affairs", Address N/A).
- Stop 4's directions lead back to Stop 1.
- Walking tours speak no hours/admission (the critic flags it; it is a walking tour of
  public civic sites, and this was true in the baseline).

These remain visible in the 558 critique (6.5/10) and are out of scope for this ticket.

## Tests

New: `test_local646_walking_regressions.py` — 13 tests on the REAL tour-557 Stop 3 / Stop 4
blocks (verbatim), plus a DB-backed live-557 check that skips when the DB is unreachable:

- Reg 1: `_STRUCT_LABELS` contains the four labels; the splitter keeps fields + Orientation
  out of the editor body; the (flattening) editor does not collapse the fields; the exact
  557 run-on first line never reappears.
- Reg 2: `_DIRECTIONS_LABEL_RE` is MULTILINE; the real 557 Stop 3 (pre-guarantee) counts as
  having a transition; the guarantee adds 0 and no duplicate `Continue to`; and it STILL
  adds a transition for a stop that genuinely lacks one (no over-correction).
- Canary: `place_practical_facts_in_opening` clears the `Museum Information:` line, hours/admission
  are spoken once, the bench-detector shape passes, and the pass is idempotent.

```
$ python3 -m pytest test_local646_walking_regressions.py -q
13 passed
```

### Museum suites re-run — every one exit 0

Root-level (44 files): `test_local605,607,617,618×4,620,623,624,625,627×8,628,629,630,631,632,
634×2,636×3,637,638×4,639×3,642,643,644,646` + `test_local590_assembly,590_orchestrator,590_pool_store`
→ **44 pass / 0 fail**.

`tests/` (50 files): `test_local600,602×12,603×2,604,606,609,60_cost,611,612,613,614×5,615×5,
616×5,619,622,626×4,633,635,640,641,645,64_cost` + `tests/test_lead_double_conclusion,
lead_header_sanitizer,lead_pf_placement` → **50 pass / 0 fail**.

`python3 test_sq4_merge.py` → exit **0**, `ALL TESTS PASSED`.

(The "9 pre-existing failures" noted on the LEAD base commit are elsewhere in the full
suite, not in any museum suite listed by the ticket.)

## Live acceptance — own disposable container, cap respected

Harness: `run_local646_live.sh` + `run_local646_container.py`. Builds `Dockerfile.generator`
from this branch tree into image `local646-gen-img`, runs `docker run --rm --name local646-gen
-p 5114:5000 --network development_default` against `development-postgres-2-1`. Cache OFF, pool
OFF (fresh). **Never** `docker compose -p audioura`; **never** renamed/replaced an `audioura-*`
container. Image + container removed on exit.

**Cost: `$1.1043` combined < `$1.20` cap** (authoritative `LIVE_RUN_METER`: openai `$0.8156`,
gemini_grounding `$0.2100`, gemini_tokens `$0.0357`, serper `$0.0430`, preflight `$0.0724`),
enforced by `tests/live_run_meter.py` with a reserve gate.

**Rows: additive `is_test` only.** `audio_tours` total **363 → 366** (+3); `is_test` **300 → 303**
(+3). The three new rows:

| id | tour | note |
|----|------|------|
| 558 | Boston walking, 5 stops | as generated by the fixed pipeline |
| 559 | The Courtauld Gallery, 3 stops | as generated (shows the pre-existing canary double-count) |
| 560 | The Courtauld Gallery, 3 stops | 559 content with the deterministic `place_practical_facts_in_opening` fix applied (no LLM, no cost) |

No DELETE. No GCloud.

### Detectors + critique

| id | tour | detectors | critique |
|----|------|-----------|----------|
| 558 | Boston walking | **0 failures** — `reg1_collapse=False`, `reg2_dup=False`, `missing_directions=0` | **6.5/10** |
| 560 | Courtauld (fixed) | **0 failures** | **7.5/10** |

- **558 walking:** Stop 4 has each field on its own line, `Orientation:` as its own
  paragraph, narration as separate paragraphs. Stop 3 ends with its `Directions:` line and
  there is NO duplicate `Continue to The Old State House.` The critic confirms "Stop count
  matches the 5 requested" and "Stops 1–4 each lead strongly with place + human stakes".
  Its remaining items are the pre-existing/document-only ones above.
- **560 canary:** hours and admission spoken exactly once; 0 detector failures.

(The 559 as-generated row carries the pre-existing canary double-count so the before/after is
visible; 560 is the delivered shape with the fix.)

## Files changed

- `stop_editor.py` — reg 1 (`_STRUCT_LABELS`).
- `directions_guarantee.py` — reg 2 (`_DIRECTIONS_LABEL_RE` MULTILINE).
- `practical_facts_gate.py` — canary (clear `Museum Information:` field line).
- `test_local646_walking_regressions.py` — new, 13 tests.
- `run_local646_container.py`, `run_local646_live.sh` — own-container live harness.

Commits (each step committed): `5ecd3100` (reg 1 + reg 2 + tests), `a26fd30c` (canary fix +
tests + harness).
