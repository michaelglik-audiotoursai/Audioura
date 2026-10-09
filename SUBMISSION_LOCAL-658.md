# SUBMISSION — LOCAL-658: Boston walking v4 (tour 557)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-658-walking-v4` (from `subscribed` @ `db8b7cd0`)
**Base verified:** `git merge-base --is-ancestor db8b7cd0 HEAD` → exit 0.

Four defects from the Boston walking v4 run
(`Walking tour in Boston dedicated to Massachusetts politics and current affairs, Boston, MA`):
a 4.6 km "walking" leg to a GEO-CHECK replacement, "John F." / "M. Pei" initial
truncation, a museum/art conclusion on a politics walking tour, and a check that
the structured field lines are not spoken. The current-affairs news (LOCAL-655B)
is correct and was left untouched.

---

## Defect 1 — a GEO-CHECK replacement was not distance-checked

**Root cause.** In `generate_tour_text.py`, the walking GEO-CHECK removes a
dispersed stop, asks the model for a replacement, geocodes it, re-orders and
delivers it — but the per-leg / total distance check only ran on the
*pre-replacement* list. "The Boston Globe" was removed as too far; the
replacement "John F. Kennedy Presidential Library and Museum" (Columbia Point)
was added on a **4.6 km leg** and shipped unchecked. The total-route check passed
(5.22 km < 12 km) because only the *per-leg* check (1.75 km) catches a single far
stop, and that check never re-ran.

**Fix.** After the replacement coords are fetched, the replacements are
re-validated against the **same** walking-distance limit as the original stops.
I snapshot the already-validated survivors (`_geo_survivors`) and the added
replacements (`_geo_replacements`), then greedily admit each replacement only if,
placed in the route-ordered set, it introduces no leg over `WALKING_LEG_HARD_KM`
(on_foot) and keeps the total under the mode's hard limit (`_route_leg_ok`). A
replacement that fails is dropped and its name added to `forbidden_norms`. If
that leaves fewer than `total_stops`, the tour is delivered **N−1** and the
existing LOCAL-612 / D616 machinery emits the honest shortfall sentence
(`about_museum_stop.build_shortfall_sentence`, delivered vs requested) — never a
far stop (LOCAL-632). Survivors are never dropped.

Constants (`tour_settings.py`): `WALKING_LEG_HARD_KM = 1.75`,
`WALKING_TOTAL_HARD_KM = 12.0`.

---

## Defect 2 — single-letter initials truncated names and sentences

Three symptoms, two root causes:

**(a) The LOCAL-22 name-corruption guard rejected clean names with initials.**
`_is_name_corrupted` Criterion 2 (`generate_tour_text.py`) rejected any name with
a period mid-string. "John F. Kennedy Presidential Library and Museum" was
rejected (log line 158). Fix: before the mid-string-period test, neutralize
dotted acronyms (`U.S.`) and then single-letter initials (`A-Z` + `.`), so the
test sees no spurious terminator. `John F. Kennedy`, `I. M. Pei`,
`W. E. B. Du Bois`, `J. P. Morgan`, `U.S. Capitol` now pass; real sentence-names
("Located at 5th Ave. This stop…", "Visit the museum. It is great.") are still
rejected.

**(b) The mutating sentence splitter cut names at an initial.**
`style_validator_detector._split_sentences` split on
`(?<=[.!?])\s+(?=[A-Z"'])`, so "architect I. M. Pei" became
`…architect I.` + `M.` + `Pei…`; `unsupported_claim_gate` (which calls this
splitter) then dropped a fragment and rejoined, leaving "architect M. Pei". The
same regex cut "the nearby John F. Kennedy…" into "…John F." + "Kennedy…". Fix:
`_split_sentences` now delegates boundary detection to the shared,
abbreviation-and-initial-safe `sentence_split.split_sentences` (the one
`cross_stop_fact_dedupe` already uses, LOCAL-614), preserving the in-fragment
`?` split the detectors rely on. The directions guard and the Stop header both
read the (now un-truncated) name, so "Continue to John F." / "Stop 5: John F."
no longer occur. (`style_validator_detector.py` is the canonical module;
`tests/style_validator_detector.py` is only a shim that re-exports it, so the fix
is in effect in production.)

Fixtures added: `John F. Kennedy`, `I. M. Pei`, `W. E. B. Du Bois`,
`J. P. Morgan` (name guard + splitter).

---

## Defect 3 — a museum/art conclusion on a walking tour

**Root cause.** `tour_conclusion.py`'s deterministic fallback
(`_derive_common_elements`, LOCAL-652/619) mines `_SUBJECT_WORDS` — a purely
**art** vocabulary (`"modern" → "modern art"`, `"figure" → "the human figure"`,
Impressionism, the Baroque, …) — and a century label, with **no awareness of the
tour category**. On the Boston politics walking tour, incidental words ("modern
Boston", "modern governance", "figure") produced the thread *"modern art in the
eighteenth to twentieth centuries"* and the meaning *"Seen together, the works
show how differently that subject could be imagined."* LOCAL-652's foreign-entity
guard only blocks naming a foreign *work/artist* — it does not stop art
*vocabulary* on a non-art tour.

**Fix.** `build_conclusion` now determines the category from the tour text
(`_parse_tour_category`) and whether the art vocabulary is appropriate
(`_tour_is_art`: museum/art/gallery, OR stops that carry `artist` grounding —
walking/restaurant/specialized = not art). For a non-art tour it parses the
request's theme from the title (`_request_theme_from_title`:
"…dedicated to X" → "Massachusetts politics and current affairs", location tail
stripped). `_derive_common_elements` takes `is_art_tour` + `request_theme`:

* **non-art** → skip `_SUBJECT_WORDS` entirely; thread = the request theme
  (meaning "…how that story is written into the places themselves"), else the
  shared period as plain history ("the history of the 18th century"), else a
  places thread ("the places that shape {venue}" / "the places on this route").
  The meaning never says "works" or "art".
* **art (museum)** → unchanged: subject/period thread and "the works show …".

**Verified both directions (offline):**
* Boston walking → thread "Massachusetts politics and current affairs";
  `modern art` / `the works show` absent.
* Van Gogh museum canary → still "the human figure in the nineteenth century" and
  "the works show …". The LOCAL-652 phantom-thread suite (the museum canary) still
  passes unchanged.

---

## Defect 4 — the structured field lines are kept in text but not spoken

**Confirmed already correct — no code change.**
`tour_generation_modernized._strip_nav_fields_for_tts` strips `Type/Specialty:`,
`Specific Examples:`, `Address:`, `Coordinates:`, `Museum Information:`,
`Operational Details:` (via `_NAV_LABEL_RE`) from the text sent to Polly, while
the `.txt` text view (written from the original) keeps every field for the app.
Added a test asserting the field labels are absent from the TTS-stripped text and
present in the text view, and that the stop name + narration survive.

---

## Tests (offline) — exit codes

New: `tests/test_local658_walking_v4.py` — **22 passed** (all four defects:
name-guard + splitter initials, GEO-CHECK replacement distance geometry +
guard-wired-in, non-art vs museum-canary conclusion, TTS field-line strip).

Relevant suite + museum canary (one pytest invocation):
`test_local658`, `test_local652_phantom_thread` (museum canary),
`test_local614_sentence_splitter_initials`, `test_local619_real_conclusion`,
`test_local263_unsupported_claim_gate`, `test_local600_order_and_shortfall`,
`test_local612_shortfall_everywhere`, `test_local309_verified_unavailable`,
`test_lead_double_conclusion`, `test_lead_header_sanitizer`,
`test_local653_site_candidates`, `test_local650_walking_route`,
`test_local646_walking_regressions` → **262 passed, 3 skipped (DB), EXIT=0**.
Style/directions suites → **26 passed, EXIT=0**.

Wider sweep of all 29 test files importing the touched modules →
**615 passed, 7 failed**. All 7 failures are **pre-existing on base `db8b7cd0`**
(verified by checking out the base versions of the three edited source files:
`test_local256` R7 and `test_local271` R1 fail identically on base;
`test_local142` single-pass translation (5) touches unrelated modules). **No
regression introduced by this branch.**

---

## Live (own container, ONE paid tour)

Isolated disposable container only: `docker run --rm --name local658-gen -p
5119:5000` on `development_default`, own image `local658-gen-img` built from this
branch tree. **No `docker compose -p audioura`; no `audioura-*` container
renamed, replaced or touched** (all 13 audioura service containers still up after
the run). Container + image removed on exit. Harness:
`run_local658_live.sh` + `run_local658_container.py`. Cache + stop-pool OFF
(fresh), model `gpt-4o`. The museum canary is **offline (fixtures) only** — no
paid museum tour was started.

**Request:** `Walking tour in Boston dedicated to Massachusetts politics and
current affairs, Boston, MA`, 5 stops, walking.
**Delivered:** `audio_tours` id **628** (`is_test = true`), 5 stops, wall 375.8 s.

**Stop list + leg distances (D1):**

| # | Stop | Leg from prev |
|---|------|---------------|
| 1 | Massachusetts State House | — |
| 2 | Boston City Hall | 0.42 km |
| 3 | Faneuil Hall | 0.39 km |
| 4 | The Old State House | 0.17 km |
| 5 | The Boston Athenaeum | 0.62 km |

Max leg 0.62 km, total straight-line 1.61 km (limits: 1.75 km per-leg,
12.0 km total). Generator log: `GEO-CHECK: all 5 stops within walking distance`.
No far replacement was delivered. This run selected a compact downtown set, so
the replacement path was not exercised live; the distance re-validation guard is
proven by the unit tests and present in the shipped source.

**D2:** stop headers truncated at an initial = **NONE**; no truncated directions
targets.

**D3:** conclusion was LLM-written this run (SQ had story elements, so the
deterministic mosaic fallback was not hit) and is category-correct:
*"…the dynamic interplay of governance, social change, and the ongoing struggle
for justice within Massachusetts politics."* `modern art` = False,
`the works show` = False. The mosaic-fallback fix (the exact v4 defect path) is
proven by the offline unit tests.

**D4:** text view has `Type/Specialty:` and `Specific Examples:`; the
TTS-stripped spoken text has **neither** label.

**Kiro critique** (`.continuous_dev/calib/critique.sh 628 5`): **6.5 / 10.** It
did **not** flag any LOCAL-658 defect — it read the tour as a politics walking
tour with a proper conclusion and 5 stops as requested. Its flagged items belong
to other tickets: an orphaned "this episode" wrap-up paragraph at Stop 2 (a
dropped story), hours/admission not spoken, news attribution/ordering
(LOCAL-655 — kept as-is per this ticket), and one factual red flag at Stop 5.
None are D1–D4.

**Spend:** `live_run_meter` TOTAL **$0.5356** (openai $0.3009, gemini_grounding
$0.2170, gemini_tokens $0.0166, serper $0.0010); `paid_api_calls` for the
container host = **$0.4689**. Under the **$1.20** task cap. **ONE** paid tour.

**Rows:** `audio_tours` 425 → 426 in the isolated run (+1 additive `is_test` row,
id 628). **No DELETE.** No GCloud.

---

## Files changed

* `generate_tour_text.py` — defect 1 (GEO-CHECK replacement distance re-validation)
  and defect 2a (LOCAL-22 name guard initials).
* `style_validator_detector.py` — defect 2b (initial-safe shared splitter).
* `tour_conclusion.py` — defect 3 (category-aware conclusion fallback).
* `tests/test_local658_walking_v4.py` — fixtures/tests for all four defects.
* `run_local658_container.py`, `run_local658_live.sh` — isolated live harness.

Defect 4 required no code change (confirmed correct; covered by a new test).

Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
`.continuous_dev/STATUS.md`.
