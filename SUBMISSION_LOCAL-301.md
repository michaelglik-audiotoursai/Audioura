##### READY FOR REVIEW

## Commit

`86a1a1a` on branch `kiro/local301-corpus-fixtures`

## File changed

**tests/test_local281_dining_venue_kind.py** — Added `corpus_fixtures` pytest
fixture (module-scoped, autouse). Inserts minimum `venue_corpus` and
`stop_corpus` rows the existence-gate assertions require, removes them on
teardown. No assertions changed.

## What the fixture inserts

- `venue_corpus` row: Musée Matisse (QID Q3329731) with `sparql_works_json`
  (classifies as 'institution') and `canonical_titles_json` containing
  "Odalisque au coffret rouge"
- `venue_corpus` row: French Riviera walking area (QID Q40978) without
  `sparql_works_json` (classifies as 'geographic_area'), with canonical_titles
  containing Eze Village, Cap Ferrat, Villefranche-sur-Mer as geographic POIs
- `stop_corpus` rows: Eze Village, Cap Ferrat, Villefranche-sur-Mer with
  1 passage each and `passage_count = 1` (geographic relaxed path)

All data constructed explicitly in code. No production rows copied.

## Evidence

### Target test file (test database)

```
AUDIOURA_DB_TARGET=test python3 -m pytest tests/test_local281_dining_venue_kind.py -q
14 passed, 1 warning in 13.75s
```

### Target test file (production — no regression)

```
AUDIOURA_DB_TARGET=production python3 -m pytest tests/test_local281_dining_venue_kind.py -q
14 passed, 1 warning in 13.63s
```

### Full suite (test database)

```
AUDIOURA_DB_TARGET=test python3 -m pytest tests/ -q --continue-on-collection-errors
10 failed, 990 passed, 2 skipped, 81 warnings, 50 errors in 227.73s
```

Baseline was: 13 failed, 987 passed, 2 skipped, 50 errors.
Delta: −3 failed, +3 passed. Exactly the 3 existence-gate tests fixed.

### Corpus tables empty after run

```
SELECT count(*) FROM venue_corpus;  → 0
SELECT count(*) FROM stop_corpus;   → 0
```

### Production real count unchanged

```
SELECT count(*) FROM audio_tours WHERE is_test = false OR is_test IS NULL;  → 29
```

### git status

```
git status --short  → (empty — clean)
```

## Constraints honoured

- No assertion changed
- No row copied from production
- `init_test_db.sh` not modified (schema-only preserved)
- No container rebuilt
- `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*` not touched
- Production `audiotours` read-only (only SELECTs via test runs)

## Limitations

- The fixture uses `ON CONFLICT DO NOTHING`, so if a prior crashed run left
  rows behind, the fixture would silently skip insertion. The conftest session
  cleanup (TRUNCATE audio_tours, stop_metrics) does not cover these tables.
  In practice, the fixture's own teardown handles cleanup, and re-running
  is idempotent.
