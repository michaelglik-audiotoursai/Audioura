# SUBMISSION — LOCAL-644: Structured stops through the STOP-POOL delivery (Strategy A, real path)

**Branch:** `LOCAL-644-structured-pool-path` (from `subscribed` @ `17aa7a4b`)
**Base:** subscribed — `git merge-base --is-ancestor 17aa7a4b HEAD` exits 0.
**Flag:** `STRUCTURED_STOPS=1` (default **OFF** — LEAD flips the default after a
benchmark round with the flag ON beats the flag OFF).
**ZERO PAID CALLS.** No live tour was generated; no OpenAI / Gemini / Serper
request was issued. Everything is proven offline with unit tests, fixtures
exported read-only from the stored `audio_tours` rows, and injected fakes.

---

## Why

LOCAL-643 (merged) renders stops from records only inside
`_generate_tour_text_impl` (the NORMAL path). In the shared stack, fresh tours go
through `stop_pool_orchestrator`:

- gen_text → `parse_delivered_stops` → `assemble_building_tour`, which
  re-renders from parsed TEXT;
- reuse tours assemble pooled units.

So the R14 A/B (`STRUCTURED_STOPS=1`) logged "path = structured" **0 times** — the
flag had no effect on any delivered tour. This ticket carries the generator's
`Stop` records THROUGH the pool so the one renderer runs on every path.

---

## What shipped

### 1. Records bridge — `stop_records.py`

Lossless JSON (de)serialization so a `Stop`/`Opening`/`Closing` survives the two
hops that only move JSON (generator → orchestrator via a per-job `_J` holder, and
into/out of the pool DB):

- `stop_to_dict` / `stop_from_dict`, `_opening_to_dict` / `_opening_from_dict`,
  `_closing_to_dict` / `_closing_from_dict` — every field including the
  `narration` paragraph list and a `_schema` tag; `from_dict` tolerates missing
  keys (older schema).
- `tour_to_record_dicts(text)` — parse a delivered tour (via the existing
  `parse_tour_to_records`, which already `_recover_inline_labels`-un-flattens the
  NG-495 glue) into JSON-safe record dicts keyed by bare title, for the pool
  store's back-compat path.

Round-trip proven exact; render parity after a JSON round-trip holds on the
fixtures.

### 2. Expose the generator's records — `generate_tour_text.py`

- New per-job holder `_LAST_STRUCTURED_RECORDS` registered in the
  `job_scoped_state` `_J` dict (isolated across concurrent jobs).
- Populated (JSON-safe dicts) in the `STRUCTURED_STOPS` render block, right after
  `_LAST_DELIVERY_PATH='structured'`, so a pool caller can retrieve the
  generator's OWN records without re-parsing the delivered text. Empty dict when
  the flag is OFF → the orchestrator falls back to `parse_tour_to_records`
  (back-compat).

### 3. Persist records with each pooled stop — `stop_pool_store.py`

- Additive `stop_record_json TEXT` column (`ALTER TABLE … ADD COLUMN IF NOT
  EXISTS`; never DELETE/DROP).
- `store_delivered_tour(..., records_by_title=…)` writes the generator's carried
  record per stop; when a stop is not covered it DERIVES a record from the parsed
  unit (`_record_from_unit`) so even a legacy/text delivery stores a record.
- `get_pool_stops` returns a narration-aligned `stop_record` on every pooled
  dict: loads `stop_record_json` when present, else back-compat-parses the row
  into a record ONCE. Orientation/directions are kept empty on pooled records —
  they are sequence-dependent (D581.1) and recomputed by the assembler.
- `parse_delivered_stops` now un-glues inline field labels first (reuses
  `stop_records._recover_inline_labels`), so a legacy pooled stop stored with a
  whole block flattened onto one line (NG 495 R9/R12) parses into a CLEAN unit
  and renders correctly on reuse — the ticket's "parse the old units once into
  records and render the same way" rule.

### 4. One renderer for every path — `stop_pool_assembly.py`

- `assemble_building_tour` and `assemble_outdoor_tour` render the body via
  `stop_records.render_tour` when `STRUCTURED_STOPS=1`, else the legacy per-stop
  block loop (byte-for-byte unchanged when OFF).
- Each stop renders from its carried structured record (generator record for a
  new stop, pooled/back-compat record for a reused stop); the authoritative
  guard-cleaned narration, the sequence orientation, and the recomputed
  transition are overlaid in the delivered order.
- The opening section folds into Stop 1 as the `Opening` record's
  `about_paragraphs` (section layout — D640: about → practical facts →
  orientation, before the Orientation line).
- Field suppression (contained museum/facility suppress Type/Specialty, Specific
  Examples, Operational Details) and the LOCAL-623 address validation mirror the
  legacy block exactly. Proven **byte-identical** legacy == structured on
  well-formed input (plain and with an opening section).

### 5. Wire the orchestrator — `stop_pool_orchestrator.py`

- `_structured_records_by_title()` reads `_LAST_STRUCTURED_RECORDS`.
- `_pooled_unit_from_row` carries the pooled row's `stop_record` onto the unit so
  reuse renders from it; `_new_unit_from_parsed(stop, records_by_title)` attaches
  the generator record to a new stop.
- First-tour (K==0) and N>K paths capture `_gen_records`, pass them to the new
  units, and pass `records_by_title` to `store_delivered_tour`; the N>K store
  preserves the pooled stops' existing records.

### 6. Parity tests + fixtures — `test_local644_pool_structured.py`, `tests/fixtures/tour_{553,554,555,556}_r2.txt`

Fully offline (no DB/network/LLM in the test; fixtures exported read-only from
`audio_tours`). For stored tours **485, 488, 495, 531, 553–556**:

- **fresh-via-pool** and **reuse-via-pool** rendered through
  `assemble_building_tour` with `STRUCTURED_STOPS=1`.
- The detectors.py structural checks are ported and run on the rendered text;
  the renderer-structural subset is **0 failures** for all 8 tours on both fresh
  and reuse.
- Clean tours (485, 488, 555, 556) render **byte-identical** legacy == structured;
  495/531/553/554 differ only because the structured path RECOVERS the stored
  flatten/whitespace defect (strictly better, never worse).
- D640: each stop keeps its OWN orientation (none migrates).

Cross-check with the LIVE `~/Audioura/.continuous_dev/bench/detectors.py` on the
STORED (legacy) rows: 485/495/531/553/554/555 = 0; 488 = 2 and 556 = 1 — those
are inherited **content** defects of the stored source narration
(`admission_twice`/`recruitment_copy`, `one_word_sentence`), present identically
in the legacy text, which a renderer neither creates nor removes. The renderer's
contract — structure — is clean on every tour.

---

## Tests (exit codes)

Full required battery, both flag states. Each command's exit code is `0`.

```
# flag OFF
test_local60*/61*/62*                                     296 passed            EXIT 0
test_local63*/64*/590_* (root)                            246 passed, 1 skip    EXIT 0
tests/test_local60*/61*/62*/63*                           394 passed            EXIT 0
tests/test_lead_*                                           8 passed            EXIT 0
python3 test_sq4_merge.py                                 ALL TESTS PASSED      EXIT 0
consolidated (all pytest groups above)                    944 passed, 1 skip    EXIT 0

# flag ON (STRUCTURED_STOPS=1)
test_local60*/61*/62*                                     296 passed            EXIT 0
test_local63*/64*/590_* (root)                            246 passed, 1 skip    EXIT 0
tests/test_local60*/61*/62*/63*                           394 passed            EXIT 0
tests/test_lead_*                                           8 passed            EXIT 0
python3 test_sq4_merge.py                                 ALL TESTS PASSED      EXIT 0
consolidated (all pytest groups above)                    944 passed, 1 skip    EXIT 0

# LOCAL-644 parity harness (both flag states)
test_local644_pool_structured.py                            5 passed            EXIT 0
```

The 1 skip is a fixture-gated test (`test_local643_parity` 523 edge), unrelated to
this change.

---

## Safety / scope

- Default OFF: with `STRUCTURED_STOPS` unset, every path is byte-for-byte the
  legacy behaviour (proven: 944 passed OFF, and the clean-tour byte-identical
  assertions).
- Additive only: the new DB column uses `ADD COLUMN IF NOT EXISTS`; nothing
  DELETEs or DROPs; a pre-LOCAL-644 row (NULL `stop_record_json`) is parsed once
  into a record on read.
- ZERO paid calls: no live generation; fixtures and the local Postgres row store
  only.
- Did NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
  .continuous_dev/STATUS.md.

## Commits

```
cd2cc8ba step 1 — Stop/Opening/Closing <-> JSON serialization helpers
58b1831f step 2 — expose generator records via _J holder
af626ce9 step 3 — persist per-stop structured record in stop_pool (additive)
7b3f4637 step 4 — assemble_building/outdoor render via stop_records.render_tour
7239d284 step 5 — wire orchestrator to carry records through the pool
6e24ff91 step 6 — offline parity tests + fixtures 553-556 + flatten recovery
(this commit) step 7/8 — full battery exit codes + SUBMISSION_LOCAL-644.md
```
