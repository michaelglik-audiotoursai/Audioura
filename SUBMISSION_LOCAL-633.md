# LOCAL-633 — Practical facts: ONE short spoken sentence pair, composed from structured data

**Branch:** `LOCAL-633-practical-facts-composer`  **Base:** `subscribed` @ `f543b2f`
**Agent:** Mac Mini Kiro

## Problem (Bench R1)

Three of six tours spoke the raw preflight dump inside the first stop — the full
ticket-office / discount / price-table paragraph:

- **Uffizi 488:** "The museum is open Tuesday to Sunday, 8:15 AM to 6:30 PM (the
  ticket office closes at 5:30 PM, and halls begin closing at 6:00 PM / 6:30 PM);
  closed on Mondays, January 1, and December 25. Free admission: Visitors under
  18, … (Discounts exist …)."
- **Reina Sofía 505 (Stop 2):** "admission is General Admission: €12; Combined
  Ticket …: €18; Two-visit pass …: €18; Free Admission: …"
- **Met 507:** "admission is General admission is $30 for adults, $22 for seniors
  (65+), $22 for visitors with disabilities, $17 for students, …"

## What was delivered

### 1. `compose_practical_facts(preflight) -> str` (`practical_facts_gate.py`)
Turns the **structured** preflight (`hours` / `admission` strings, optional
`name`) into at most two short spoken sentences (~30 words), per D633:

- day **ranges**, not day lists (an open-day list such as the Met's six weekdays
  is reduced to "daily except Wednesday"; a non-contiguous list → "daily except X
  and Y");
- **one** adult price plus **at most one** free group (never the price table);
- **no** parentheses, discount schemes or ticket-office details;
- currency spoken as a **word** ("euros", "dollars"), never a symbol;
- only facts present in the preflight — nothing invented.

Pure/deterministic. Hardening (all covered by tests): a single simplified time
span is kept ("from 8:15 to 6:30" — the task example keeps it, and one short span
cannot trip `long_practical_sentence`); weekday abbreviations ("Tue–Sun", "closed
Mon") and noon/midnight word-times are understood; a free group is named only when
the source explicitly ties that group to free entry (never a priced concession).

### 2. One placement, every injection point routed through the composer
The composer output is spoken **once**, in the Stop-1 opening section (right after
the About sentences), with the existing once-guard (`tour_speaks_hours_in_prose`).
Every former verbatim-paste injection point now goes through the composer:

- `about_museum_stop._compose_visiting_sentences` (the designated opening-section
  location) — delegates to the composer instead of keeping page segments verbatim.
- `venue_preflight.plan_b_opening_practicals.speak` — composed, not pasted.
- `practical_facts_gate.ensure_spoken_hours_line` (LOCAL-629) — composes, and
  places the sentence in a Stop-1 opening-section **prose** paragraph (or, when no
  opening prose exists yet, as its own paragraph right after the first stop
  header). **Never** inside an Orientation, and never on a title / `Tour-Category:`
  / field line.

### 3. TTS speaks only the composed sentence
The `Museum Information:` field line keeps the full detail for the **text view**,
but is now dropped **whole** (label + value) from TTS — previously only the label
was stripped, so the long value was still read aloud (D-LEAD 7f320a0). Fixed in
both strip paths: `tour_generation_modernized._strip_nav_fields_for_tts` and the
`translation-service` equivalent. The `.txt` text view is unchanged.

## Tests

New `tests/test_local633_practical_facts_composer.py` (12 tests): the composer on
the exact 488/505/507 dumps (all pass the five bench detectors), the once-guard,
no practical facts in any Orientation, and the TTS drop of the Museum Information
line.

Sibling tests that asserted the pre-LOCAL-633 verbatim dump were updated to the
composed contract (one adult price, currency as a word, day range, simplified
span, no spoken citation tail, no practical facts in an Orientation):
`test_local603_preflight`, `test_local615_preflight_hours_fresh`,
`test_local616_hours_guard_every_path`, `test_local628_stop_editor`,
`test_local630_venue_truth`, `test_local592_about_in_stop1`,
`test_local592_r4_dayrange_spoken`, `test_local629_selection_diversity`.

### Required suites (all exit 0)
```
test_local60*/61*/62*  (root+tests)   656 passed
test_local6[23]*       (root+tests)   272 passed
test_local590_*                        42 passed
python3 test_sq4_merge.py             ALL TESTS PASSED
```
Pre-existing, unrelated: `test_local585_r2_about_hygiene::test_properly_cased_locality_present`
(About narration locality casing) fails identically with these changes stashed —
not caused by LOCAL-633, left untouched.

## Live verification

Own disposable container `local633-gen` (`docker run --rm`, spare port 5098,
network `development_default`, **cache + pool OFF**, hard cap **$1.30** with a
reserve gate). Built from `Dockerfile.generator` on the branch HEAD. Never
`docker compose -p audioura`; no `audioura-*` container touched.

Two fresh 3-stop museum tours (each run in its own fresh container; combined spend
well under cap — Uffizi $0.60, Met $0.45):

| id | venue | spoken practical-facts sentence |
|----|-------|---------------------------------|
| 511 | Uffizi Gallery | "The museum is open Tuesday to Sunday from 8:15 to 6:30, and closed on Mondays. Admission is 25 euros for adults; under-18s go free." |
| 512 | Metropolitan Museum of Art | "The museum is open Sunday to Tuesday from 10:00 to 5:00, and closed on Wednesdays. Admission is 30 dollars for adults; under-18s go free." |

Each is a single standalone paragraph in the Stop-1 opening section — not a field
line, not an Orientation.

**Detectors** (`detectors.py <id> 3`): all five required — `price_list_dump`,
`label_echo`, `long_practical_sentence`, `hours_said_twice`, `admission_twice` —
**PASS** on both. Tour 512 = 0 total failures; tour 511's only flag is the
unrelated `title_line_rewritten` (title formatting, out of scope).

**critique.sh** (`<id> 3`): both PASS criterion 3 (hours/admission spoken):
- 511 Uffizi — score 7/10, "hours and admission are spoken aloud (criterion 3 ✓)".
- 512 Met — score 5.5/10, "speaks hours and admission … (criterion 3 ✓)". Its
  remaining defects (where the works actually hang; the Met's $30 being suggested
  for non-NY residents; the thematic frame) are selection / factual-grounding
  concerns outside LOCAL-633.

**Rows:** additive `is_test` only. `audio_tours` 314 → 318 (`is_test` 251 → 255):
+4 rows (509, 510 first run; 511, 512 final run), all `is_test = true`. **No DELETE.**
(509/510 came from the first run, where the sentence landed on a header line that
critique.sh strips; placement was fixed and re-verified as 511/512.)

## Commits
- `9f561d6` compose_practical_facts()
- `479c4cf` route every injection point through the composer
- `e321d0b` TTS drops the whole Museum Information line
- `c75717a` tests + superseded-assertion updates
- `90e3a71` opening-section placement fix + live harness
