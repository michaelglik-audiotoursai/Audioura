# SUBMISSION — LOCAL-743: a stop written as "Stop 1 is the X." loses its audio

**Branch:** `LOCAL-743-stop-header-split`
**Base (subscribed):** `b6427bba89b9e7c88770b99c50035a14267cf3ae`
**Agent:** Mac Mini Kiro
**Ancestry verified:** `git merge-base --is-ancestor b6427bba HEAD` → exit 0.

---

## The defect (tour 716, job ad5f966f, "the episode 1 of season 1 biking tour, Salem, MA", 5 requested)

The model wrote Stop 1's header as a **sentence** —

    Stop 1 is the Salem Maritime National Historic Site.

— while stops 2–5 used the house `Stop N: <name>` form. The live splitter
(`tour_generation_modernized.parse_tour_content_to_modernized`) and the stop
counter (`tour_conclusion.count_delivered_stops`) both key on `Stop N:` (colon).
The sentence form was therefore never a header: the split folded it into the
pre-stop title part and dropped it, so only 4 stops reached TTS and **Stop 1 lost
its audio** (ZIP had audio_1..4; orchestrator logged `STOP COUNT MISMATCH:
requested 5, delivered 4`; DB stops_count=4). The generator meanwhile logged
`[LOCAL-394] Stop count invariant: OK (5 selected == 5 delivered)` because that
invariant counts in-memory `poi_list` OBJECTS, not rendered `Stop N:` headers.

A second live defect: Stop 1's `Directions:` line swallowed the next stop's
`Type/Specialty:` / `Specific Examples:` fields onto one physical line, so those
structural labels could reach the spoken text.

## Root cause

No code emits the `Stop 1 is the X.` shape — the model wrote it. The splitter and
counter are strict `Stop N:` matchers. The gap was: nothing normalised a
sentence-form heading back to the house form before the split/count, and the
`LOCAL-394` invariant counted objects, not what the splitter would see.

## The fix (deterministic, offline — no new model calls)

1. **`tour_conclusion.normalize_heading_variants(text)`** — rewrites a line-start
   sentence heading to the colon header:
   `Stop N is the X.` / `Stop N is X` / `Stop N - X` / `Stop N – X` / `Stop N — X`
   → `Stop N: X`. One trailing sentence terminator on the name is dropped
   (`…Site.` → `…Site`); interior punctuation (`No. 14`, `Whaam!`) is preserved;
   a header already in colon form is untouched (idempotent).
2. **`normalise_stop_headers`** calls it FIRST (step 0), so both
   `count_delivered_stops` and the generator's every-path final-text guard see
   the colon header. Because that guard writes `final` to the delivered `.txt`,
   this is the **source-level guarantee**: the shipped file always has `Stop N:`
   headers regardless of what the model wrote.
3. **`tour_generation_modernized.parse_tour_content_to_modernized`** normalises
   the same variants before its `re.split` (belt-and-braces, fail-soft), so the
   live packer and the counter agree.
4. **`generate_tour_text._apply_delivery_hours_guard`** (every-path delivery
   guard) now cross-checks, after `normalise_stop_headers(final)`, that the
   rendered-header count equals the modernized splitter's block count, and warns
   if a field label leaked into the spoken text — a mismatch is now caught in the
   generator, not only later in the orchestrator.
5. **Field-label leak:** `enforce_header_field_line_invariant` now also re-breaks
   `Type/Specialty:` and `Specific Examples:` onto their own lines, and
   `find_leaked_field_labels(text)` asserts spoken text carries no mid-line
   `Coordinates:` / `Type/Specialty:` / `Specific Examples:`.

### Files changed (only these three code files)

```
 generate_tour_text.py         | 40 ++++++++++++++++++
 tour_conclusion.py            | 98 +++++++++++++++++++++++++++++++++++++++++--
 tour_generation_modernized.py | 16 +++++++
```
New: `fixtures/tour716_stop1_sentence_header.txt`,
`test_local743_stop_header_split.py`, `run_local743_live.sh`,
`run_local743_container.py`.

## Red → green test

`test_local743_stop_header_split.py` (24 tests). The fixture
`fixtures/tour716_stop1_sentence_header.txt` reconstructs tour 716: Stop 1 is the
sentence form, plus the Directions label leak.

* **Red proof:** the raw fixture has 4 line-start `Stop N:` headers (Stops 2–5);
  `re.findall(r'^Stop \d+:', ...)` == 4.
* **Green:** `tour_conclusion.count_delivered_stops(fixture)` == 5 and
  `parse_tour_content_to_modernized(fixture)` yields 5 `text_content` blocks.
* Per-variant unit tests (`is the` / `is` / `-` / `–` / `—` / multi-digit /
  colon-form untouched / overview em-dash title untouched / interior punctuation
  / idempotent / mid-sentence reference untouched).
* Label-leak tests: raw fixture leaks `Type/Specialty:` + `Specific Examples:`;
  after `normalise_stop_headers` the leak is gone and the labels start their own
  lines; `find_leaked_field_labels` detects each.

### Suites vs baseline (not "zero failures")

Relevant header/conclusion/split suites, run on this branch and on a stash of the
three code files at base `b6427bba`:

* **Baseline (b6427bba):** 137 passed (new LOCAL-743 file excluded — it needs the
  fix).
* **This branch:** 161 passed — the same 137 still pass + 24 new LOCAL-743 tests.
  No regressions.

Suites: `test_local743_stop_header_split.py`, `test_local639_lost_stop_header.py`,
`test_local642_paren_title_flatten.py`, `test_local636_text_bleed.py`,
`test_local632_junk_and_shortfall.py`,
`test_local638_directions_between_stops.py`,
`test_local618_orientation_pretell.py`, `tests/test_local619_real_conclusion.py`,
`tests/test_local280_closing_recap.py`, `tests/test_lead_header_sanitizer.py`,
`tests/test_lead_double_conclusion.py`, `tests/test_local675_bilingual_header.py`,
`tests/test_local616_no_spoken_sourcing_sentence.py`. Python 3.9.6.

## Live run (own containers only)

Disposable container `local743-gen` (`docker run --rm`, spare published port
**5143**, network `development_default`, cache OFF + pool OFF), built from
`Dockerfile.generator` on this branch. The 14 `audioura-*` service containers
were never touched; `local743-gen` and its image were removed at the end.

Request: **"the episode 1 of season 1 biking tour, Salem, MA", 5 stops, biking.**

Result (`RESULT SALEMBIKE: id=717 outcome=DELIVERED delivered_stops=5
splitter_blocks=5`):

* `count_delivered_stops` = **5**
* modernized splitter blocks = **5** (== the number of `audio_N` files the live
  packer writes)
* sentence-form stop headers remaining = **NONE**
* field-label leaks in text = **NONE**
* TTS-spoken contains `Coordinates:` / `Type/Specialty:` / `Specific Examples:` =
  **False / False / False**
* Stored `audio_tours` id **717**, **stops_count=5**, `is_test=true`.

Rendered headers delivered:

```
Stop 1: Salem Common
Stop 2: Salem Maritime National Historic Site
Stop 3: The House of the Seven Gables
Stop 4: Salem Willows Park
Stop 5: Salem Witch Trials Memorial
```

### Row counts (no `DELETE FROM audio_tours`, D141)

| | total | is_test |
|---|---|---|
| BEFORE | 499 | 423 |
| AFTER  | 500 | 424 |

Exactly one additive `is_test` row (id 717). No delete.

### Cost — HONEST DISCLOSURE: $0.029 OVER the cap

Metered across all providers by `tests/live_run_meter.py` (cap set to $0.60):

```
openai            $0.2959
gemini_grounding  $0.3180  (requests=6, queries=11)
gemini_tokens     $0.0142
serper            $0.0010
TOTAL             $0.6291
```

**This is $0.029 over the $0.60 budget.** The hard cap did not pre-empt the run
because the Gemini grounding spend accrued before the terminal reserve/cap check;
the tour completed and delivered 5 stops. `paid_api_calls` for the host recorded
$0.591348. Recorded in `cost_ledger` row
`d218e526-8868-4afd-aa8d-b6f493624d8d`. Reporting the overage transparently
rather than hiding it; the measured pipeline cost for this 5-stop fresh biking
tour is ~$0.63, slightly above the $0.60 target for this location.

## Note found while running live

My first cut of the generator cross-check referenced
`_requested_stop_count_original`, a local of the main generate function that is
NOT in scope inside the `_apply_delivery_hours_guard` delivery guard, so it
logged `[LOCAL-743] cross-check skipped: name ... is not defined`. I rewrote the
cross-check to compare `count_delivered_stops(final)` against the modernized
splitter's block count — both computable from `final` in that scope — which is a
stronger check anyway (it compares exactly what the packer will do). The
functional fix was never affected (the live splitter produced 5 blocks); tests
re-run green (34 passed).
