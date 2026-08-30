# SUBMISSION — LOCAL-471 Carry_Coordinate_Confidence_To_The_App

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-471-geo-confidence-emit`
**Base:** storied = d726c7e (`git merge-base --is-ancestor d726c7e HEAD` → exit 0, verified before work)
**ClickUp:** `wdvrdaxqtf` (second half only — emit + persist the confidence signal; the
place-database first half is untouched)

## Summary

The confidence signal that `geocode_stops.resolve_point`/`resolve_poi` already computes
per stop (`high` when two independent sources agree within 200 m, else `low`) now:

1. **Emits** into each stop's `audio_N.txt` as a `Coordinate-Confidence: <high|low>` line.
2. **Persists** to the DB via an additive `audio_tours.low_confidence_stops` column
   (tour-level count of un-corroborated stops), carried on INSERT in the orchestrator and
   inherited by translations.
3. **Does NOT** touch the mobile rendering half — that is 🟩 Mobile — Kiro's work. The field
   the app should read is **`Coordinate-Confidence`** in each `audio_N.txt`; a per-tour
   summary is in `audio_tours.low_confidence_stops`.

`geocode_stops.py` was **read, called, and left alone** (LOCAL-470 owns it). The prose gates
were not touched (LOCAL-469 owns them). No container was rebuilt or restarted. No
`DELETE FROM audio_tours`. No production rows written (the DB check ran in a rolled-back
transaction).

---

## Part 1 — Emit: format choice and the parser audit

**Chosen shape: a new labelled line `Coordinate-Confidence: <high|low>` inside the stop
block, immediately after the `Coordinates:` line.** Not a JSON side-channel.

**Why this shape.** `audio_N.txt` is already the per-stop artifact every parser reads, and
every existing parser keys off *anchored line prefixes* and ignores lines it does not
recognise. A new labelled line rides the format they already tolerate, stays attached to the
stop through translation, and needs no second file to keep in sync. The task warned that a
format change that breaks the map is worse than no signal — so I read every parser first.

**The parser audit (read before deciding):**

| Parser | File | How it parses | Effect of a new line |
|---|---|---|---|
| Map screen | `audio_tour_app/lib/screens/tour_map_screen.dart` `_parsePoi` | `RegExp('Coordinates:\s*…')`, `Type/Specialty:`, `Address:`; name = `lines[0]` | Ignores unknown lines. Line is placed **after** `Coordinates:`, never line 0, so name is unaffected. **Safe.** |
| Navigation | `audio_tour_app/lib/services/navigation_service.dart` `_getStopCoordinates` | Same coordinate regex; name = `lines[0]` | Same. **Safe.** |
| "Has coords?" badge | `audio_tour_app/lib/screens/my_tours_screen.dart` | `RegExp('Coordinates:\s*…').hasMatch` | Unaffected. **Safe.** |
| Edit tour | `audio_tour_app/lib/screens/edit_tour_screen.dart` | Reads whole file as one opaque editable `text` blob | Line becomes part of the editable text; preserved on save. **Safe.** |
| Edit stop | `audio_tour_app/lib/screens/edit_stop_screen.dart` | Same opaque-blob model | **Safe.** |
| Modernized splitter | `tour_generation_modernized.py` `parse_tour_content_to_modernized`, `_stop_has_coordinates` | Splits on `Stop N:`; coord regex | Unknown line stays in the stop body; coord check still matches. **Safe.** |
| Translation splitter | `translation-service/translation_service.py` `_split_tour_content_into_stops` | Splits on `Stop N:` | Line stays in the stop. **Safe.** |
| Translation metadata restore | same, `_restore_metadata_labels` | Restores English `Coordinates`/`Address` after title, strips translated equivalents | Needed a change (below) so the confidence line is restored in English, not left mangled. |

**Where I emit.** `tour_generation_modernized.py` is the single place `audio_N.txt` is written
(`create_modernized_tour_zip`), and it already calls `geocode_stops.correct_stops()`, which
returns per-stop records carrying `confidence`. I annotate `text_content` there, right after
`correct_stops`, using a new module `geo_confidence_emit.py` (pure, testable, imports nothing
from `geocode_stops`). The emit is robust: `geo_records` is initialised to `[]`, so a geocoder
import failure or `GEOCODE_STOPS=0` (fewer/no records) marks every un-covered stop `low`
rather than crashing or omitting the field.

**Not spoken.** `Coordinate-Confidence:` was added to the TTS strip sets in both
`tour_generation_modernized.py` (`_NAV_LABEL_RE`) and `translation_service.py`
(`_NAV_FIELD_PREFIXES`), so it is never read aloud.

**Translation carry-through.** `Coordinate-Confidence` was added to `_METADATA_LABELS` so the
English line is restored after translation exactly like `Coordinates`/`Address`. To avoid a
duplicate garbled line, the confidence line is stripped from the text sent to the translator
(its English value is restored from the untouched source), so the translated `audio_N.txt`
carries exactly one, in English.

### Files changed for Part 1
- `geo_confidence_emit.py` **(new)** — `annotate_stop_text`, `annotate_text_content`,
  `normalize_confidence`. Idempotent; unknown/missing → `low`.
- `tour_generation_modernized.py` — call the annotator after `correct_stops`; add the label
  to `_NAV_LABEL_RE`.
- `translation-service/translation_service.py` — add label to `_METADATA_LABELS` and
  `_NAV_FIELD_PREFIXES`; strip the confidence line before translating so restore yields one
  English line.

---

## Part 2 — Persist: additive column `audio_tours.low_confidence_stops`

**Declared additive column (no approval needed per the task):**
`ALTER TABLE audio_tours ADD COLUMN low_confidence_stops INTEGER` — nullable.
`NULL` = not measured (legacy rows); `0` = measured, all stops high; `N` = N un-corroborated stops.

The per-stop truth lives in each `audio_N.txt` and rides inside the stored zip; this column is
the **queryable tour-level summary**, the same role `stops_count` plays. It is computed in the
orchestrator by reading the zip's `audio_N.txt` files and counting stops whose
`Coordinate-Confidence` is not `high` (missing line counts as low — the honest default).

Wired the same way `stops_count` is:
- **Self-healing ALTER** in `store_audio_tour` (same pattern as `track`/`stops_count`) so any
  Postgres gains the column on first write.
- **INSERT** in `tour_orchestrator_service.py` carries `low_confidence_stops`.
- **Translation inheritance** in `translation_service.py`: the SELECT fetches the original's
  `low_confidence_stops` and the INSERT copies it (the translated zip carries identical
  confidence lines, so the count is identical).

### Files changed for Part 2
- `tour_orchestrator_service.py` — count low-confidence stops from the zip; self-heal +
  carry the column on INSERT; pass it from the generation caller.
- `translation-service/translation_service.py` — fetch and inherit the column.

---

## Live DB verification (read-only / rolled back — no rows written)

Container `development-postgres-2-1` (up 3 weeks), not restarted.

**Row counts (before):**
```
 total_rows | originals | translations
        164 |       148 |           16
```
`low_confidence_stops` column did **not** exist yet (will be added by the self-healing ALTER
on the next real tour write, which I did not trigger).

**Schema + INSERT proof, inside a transaction that was ROLLED BACK:**
```
ALTER TABLE  -- track (self-healed; live DB lacked it too)
ALTER TABLE  -- low_confidence_stops  → data_type integer, is_nullable YES
-- orchestrator INSERT column list:
 id  | tour_name                | stops_count | low_confidence_stops | is_test
 343 | LOCAL-471 rollback probe |           3 |                    2 | t
-- translation inheritance INSERT column list:
 id  | content_language | stops_count | low_confidence_stops
 344 | fr               |           3 |                    2
ROLLBACK
```
**Row counts (after, rolled back — unchanged):**
```
 audio_tours_rows
              164
```
Both INSERT column lists succeed against the live schema; nothing persisted.

---

## Tests (run, real output pasted)

### `tests/test_local471_confidence_emit.py` — 17 tests
```
17 passed, 1 warning in 0.25s
```
Covers: `normalize_confidence` fails safe to `low`; line lands after `Coordinates:`;
idempotent (exactly one line on re-annotation); missing-`Coordinates:` still gets the field;
records align by index; **short/empty records default low, never skip (AC4)**; the ported
app coordinate/type/address regexes still match a file carrying the line; name is still
line 0; a guard that fails if Mobile-Kiro changes the .dart regex; the modernized splitter +
coord check still read it; the TTS strip removes it.

**AC5 acceptance stops** (`TestAcceptanceStops::test_matisse_high_leopolda_and_sport_low`)
— stubbed geocoder, end to end through `correct_stops` → `annotate_text_content`:
Musée Matisse → `Coordinate-Confidence: high` (coord corrected in place);
Villa Leopolda → `low`; Musée National du Sport → `low`. **PASSED.**

**AC4** (`test_geocode_disabled_marks_every_stop_low_and_does_not_crash`) — `GEOCODE_ENABLED=False`:
every stop carries exactly one `Coordinate-Confidence: low`, no crash. **PASSED.**

### `tests/test_local471_translation_carries_confidence.py` — 4 tests
```
4 passed in 0.15s
```
Runs the **real** `_split_tour_content_into_stops`, `_restore_metadata_labels`,
`_strip_nav_fields_for_tts` (cloud SDKs stubbed; no AWS): splitter keeps the line; restore
re-inserts the **English** line even when the translator mangles it; the pre-translation
strip yields exactly one English line (no duplicate); TTS strip removes it.

### `tests/dart/local471_map_parser_check.dart` — real Dart runtime
```
PASS: parser returns a POI for a file with the confidence line
PASS: name is still line 0 (not the confidence line)
PASS: latitude parsed correctly
PASS: longitude parsed correctly
PASS: Type/Specialty still parsed
PASS: Address still parsed
PASS: a low-confidence stop still parses and plots
PASS: legacy file with no confidence line still parses
ALL PARSER CHECKS PASSED   (exit 0)
```
Reifies `tour_map_screen.dart::_parsePoi` verbatim (no Flutter import, so it runs under plain
`dart run` without `flutter pub get` — network avoided while tours are being generated). The
Python suite asserts these regex literals are still the ones in the .dart source, so the copy
cannot silently drift.

### The suite can fail (D242)
Broke `normalize_confidence` to always return `high` (the exact bug the field guards against):
```
FAILED ... test_matisse_high_leopolda_and_sport_low
  AssertionError: 'Coordinate-Confidence: low' not found in
  'Villa Leopolda\n…Coordinate-Confidence: high\n…' : Villa Leopolda should be low
FAILED ... test_geocode_disabled_marks_every_stop_low_and_does_not_crash
FAILED ... test_short_or_missing_records_default_low_not_skip
FAILED ... test_everything_else_fails_to_low
4 failed, 13 deselected
```
Restored immediately; full suite green again (36 passed across the two Python files + D559).
The Dart check was also shown to exit 1 when the line is mis-placed as line 0.

Pre-existing `tests/test_d559_geocode_shared.py` still passes (I did not alter `geocode_stops.py`).

---

## Acceptance criteria

1. **Per-stop artifacts carry the value** — ✅ `Coordinate-Confidence:` line in every
   `audio_N.txt`.
2. **Every existing parser still reads the file** — ✅ audit above; proven with the real Dart
   map parser and the real Python translation/modernized parsers.
3. **Survives into the DB and into translations** — ✅ `low_confidence_stops` column
   (verified against the live schema, rolled back) + translation inheritance.
4. **`GEOCODE_STOPS=0` still works end to end, every stop `low`** — ✅ test
   `test_geocode_disabled_marks_every_stop_low_and_does_not_crash`.
5. **Villa Leopolda & Musée National du Sport `low`; Musée Matisse `high`** — ✅ test
   `test_matisse_high_leopolda_and_sport_low`.

## What the app team needs to read
- Per stop: the `Coordinate-Confidence:` line in `audio_N.txt` (`high` or `low`; treat missing
  as `low`). Sits right after `Coordinates:`.
- Per tour (optional summary): `audio_tours.low_confidence_stops` (INTEGER, nullable).
