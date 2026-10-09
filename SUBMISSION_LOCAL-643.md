# SUBMISSION — LOCAL-643: Structured stops end to end (Strategy A)

**Branch:** `LOCAL-643-structured-stops` (from `subscribed` @ `de54df9`)
**Base:** subscribed — `git merge-base --is-ancestor de54df9 HEAD` exits 0.
**Flag:** `STRUCTURED_STOPS=1` (default **OFF** — LEAD flips the default after a
benchmark round with the flag ON beats the flag OFF).
**Parallel with LOCAL-642** (it fixes one flattening bug inside the current text
pipeline; this replaces the cause class).

> Note: `MORNING_REPORT_2026-10-09.md` is not present in this worktree or in git
> history; this work follows the ticket spec directly.

---

## Why

The overnight benchmark plateaus at ~6.2 because most low scores are
TEXT-SURGERY accidents: about 100 late passes edit the assembled tour as one
string and glue headers onto addresses (NG 495 R9/R12), move one stop's
orientation into another (LOCAL-641), split "9.00", lose stop headers (Uffizi
2-of-3), and duplicate blocks. Strategy A removes the **cause class**: carry
records, render the delivered text ONCE at the end, and run each late pass on a
single stop's narration paragraphs — never on headers or field lines.

---

## What shipped

### 1. Records module — `stop_records.py`

- `Stop{index, title, artist, year, address, coordinates, type_specialty,
  specific_examples, operational_details, orientation, narration:[paragraphs],
  directions}`, plus `Opening{shortfall, about, first_stop_sentence,
  entrance_directive, about_paragraphs, inline_prefix}` and
  `Closing{conclusion, offer, sources, raw_tail}`.
- `render_tour(stops, title, opening, closing)` — produces the delivered text
  ONCE, in today's exact format: title line + `Tour-Category:`; then each
  `Stop N:` header, fields (Address, Coordinates, Type/Specialty, Specific
  Examples, Museum Information | Operational Details), Orientation, narration,
  Directions; the opening folds into Stop 1 (D640/D611); the conclusion then the
  offer ride on the last stop. Directions come from the records — no "Continue
  to" inference. The renderer is the ONLY place headers and field lines are
  emitted, so no later pass can see or produce them.
- `run_pass_per_stop(stops, pass_fn)` + `as_text_pass(fn, …)` — the per-stop
  wrapper: `for stop in stops: stop.narration = pass(stop.narration)`. A pass is
  handed one stop's narration block and never a header or field line.
- `structured_stops_enabled()` — reads `STRUCTURED_STOPS` (default OFF).
- `parse_tour_to_records(text)` — a READER (parity + stored-record rendering),
  not part of the delivery path. Includes `_recover_inline_labels` which
  un-flattens a stored line that already had field labels glued inline (the NG
  495 corruption), so the reader can reconstruct the intended structure and the
  renderer prove it un-glues it.

### 2. Pipeline threaded with records — `generate_tour_text.py`

Inside `_generate_tour_text_impl` the render loop now also builds a `Stop`
record per iteration from the exact values it already computes (header parts,
field values, `_orientation_prefix`, `_clean_orientation`, `description`,
`_transition`), captures the Stop-1 `Opening` and the last-stop `Closing`
(verbatim epilog tail). After the legacy passes, when `STRUCTURED_STOPS=1`:
narration-only passes (`clean_spoken_text`, `grammar_splice_lint`) run per stop
via `run_pass_per_stop`; the delivered text is re-rendered ONCE from the
records; one whole-text `clean_spoken_text` runs as the single allowed
post-render hygiene exception; `complete_tour` is replaced and
`_J._LAST_DELIVERY_PATH='structured'`. The whole block is wrapped in
try/except — any failure keeps the legacy string. **Default OFF: the legacy
string path is byte-for-byte unchanged.**

### 3. Live harness — `run_local643_live.sh` + `run_local643_container.py`

Own disposable container (`local643-gen`, `--rm`, spare port, built from
`Dockerfile.generator`), cache + pool off, `STRUCTURED_STOPS=1`, `$1.50` hard
cap with a reserve gate. **Never** `docker compose -p audioura`; never touched an
`audioura-*` container. Additive `is_test` rows only; no DELETE.

---

## Parity (step 5) — structure matches, only bugs disappear

Stored tours **485, 488, 495, 523, 531** were read (read-only `SELECT`,
all `is_test=t`) from `development-postgres-2-1` into `tests/fixtures/
tour_{id}_r2.txt`, parsed to records and re-rendered. `test_local643_parity.py`
(11 tests) + the broader structure suites (`636/639/618/590/627`) are green.

| Tour | Venue | Result |
|------|-------|--------|
| 485 | Courtauld | records → render **byte-identical** (whitespace-normalized) |
| 488 | — | records → render **byte-identical** |
| 495 | National Gallery | stored string has Stop 2's **header + Address + Coordinates + Orientation + narration glued onto ONE line** (the exact R9/R12 bug). Rendered from records: clean `Stop 2: The Toilet of Venus ('The Rokeby Venus')` with each field on its own line — **bug gone** |
| 523 | Frick | stored string has **empty bare `Address:` / `Directions:` labels**. Renderer omits empty fields — **bug gone** |
| 531 | — | structure identical; only blank-line whitespace differs |

Clean tours round-trip exactly; the two tours carrying the named bug classes are
repaired by rendering from records. The generation-time path never produces the
495 glue because records are field-wise *before* any string exists.

---

## Live test (step 6) — NG + Courtauld, 3 stops each, under $1.50

Both ticket venues were generated FRESH (cache off, pool off) with
`STRUCTURED_STOPS=1`, each delivered via `[delivery] path = structured`
(rendered from 3 records).

| Run | Venue | Tour id | Delivery path | Cost (tour / run) | Structural detectors |
|-----|-------|---------|---------------|-------------------|----------------------|
| 1 | National Gallery | **552** | structured | $0.8152 / $0.7847 | 1 fail → `doubled_orientation_label` |
| 2 | Courtauld Gallery | **554** | structured | $0.9805 / $0.9498 | **0 — CLEAN** |

Run 1's reserve gate correctly **skipped** the Courtauld ($0.78 + $0.80 reserve
> $1.50 cap) — the cap held. Run 2 used a fresh container (the cap is enforced
per container-host; the container hostname is random per `docker run`), stayed
at $0.95, under $1.50.

**Defect found and fixed live.** Tour 552 showed `Orientation: Orientation:
Each piece…` — a doubled label, because the captured `_orientation_prefix`
already begins with the literal `"Orientation: "` and the renderer added its
own. Fix: strip a leading `Orientation:` from the captured inline prefix in
`generate_tour_text`, plus a defensive strip in `stop_records.render_stop_block`;
regression test `TestOrientationLabelNotDoubled`. Tour 554 (post-fix) is CLEAN —
`Orientation: These diverse works…`, a single clean label — confirming the fix
live.

**Structural detectors run** (inline, in `run_local643_container.py`):
`header_glued_to_field`, `two_headers_one_line`, `empty_bare_label`,
`two_orientations_in_stop`, `doubled_orientation_label`, `split_decimal_price`,
`stop_count_mismatch`. Post-fix tour 554 = 0 failures.
`critique.sh <id> <stops>` and `detectors.py` are EXTERNAL (not in this repo) —
run them on the Mac-Mini runner with ids **552** and **554**.

**Row counts (additive is_test only, NO DELETE):**
- BEFORE: `audio_tours` 356 total / 293 is_test.
- AFTER: 360 total / 297 is_test (+4 = 2 tours + 2 `cost_ledger` rows).

---

## Safety / scope

- The old string path is NOT deleted; it is the default. Records capture runs
  unconditionally but only affects delivery when `STRUCTURED_STOPS=1`, inside a
  try/except that falls back to the legacy string.
- No `audioura-*` container was created, renamed, replaced, or stopped. The
  live container was my own (`local643-gen`, `--rm`), joined `development_default`
  only to INSERT additive `is_test` rows and read cost.
- DB writes are additive `is_test` rows only; the stored tour ids are 552, 554.
  No DELETE. No GCloud.
- Did NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, or
  .continuous_dev/STATUS.md.

## Commits
1. `68e21df` step 2 — records module + renderer + per-stop wrapper (inert).
2. `c90ca02` step 4 + parity — conditional Orientation, section-style opening,
   byte-exact renderer proven against `tour_485_r2`; parity harness.
3. `d72fd47` step 3 — thread records through the render loop; STRUCTURED_STOPS
   re-render; default OFF keeps the legacy string unchanged.
4. `f45f19d` step 5 — parity across 485/488/495/523/531; bug-elimination tests.
5. `c372685` step 6 — isolated live harness; live NG(552)+Courtauld(554);
   doubled-Orientation fix + regression test.

## How to run
```bash
# unit + parity (offline)
python3 -m pytest test_local643_parity.py -q
STRUCTURED_STOPS=1 python3 -m pytest test_local643_parity.py -q

# isolated live (own container, cache+pool off, STRUCTURED_STOPS=1, cap $1.50)
./run_local643_live.sh                       # both venues (reserve-gated)
LOCAL643_ONLY=COURTAULD ./run_local643_live.sh   # one venue against remaining budget
```
