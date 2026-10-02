# SUBMISSION_LOCAL-420.md

## Branch
`kiro/local420-never-ship-an-empty-stop` off `storied` (5ee28d0)

## Summary

LOCAL-417's positive assertion gate correctly detects stops that lack concrete
facts, but its failure path emitted a stub telling the listener the system
failed. This is strictly worse than the prose it replaced. Fixed by:

1. **Never ship the stub when a valid earlier attempt exists** — both the
   LOCAL-415 refusal path and the LOCAL-417 gate path now fall back to
   `_best_description` (the longest valid attempt from earlier retries).

2. **Save gate-rejected text as `_best_description` before retrying** — the
   gate rejects text for lacking a concrete fact, but that text IS real prose.
   Previously it was discarded on `continue` (never reaching the tracking below),
   so `_best_description` was always `None` on final failure. Now it's saved.

3. **The stub can never become `_best_description`** — added `_is_stub_text()`
   guard to the tracking condition.

4. **Material fallback when nothing else exists** — `_build_material_fallback()`
   builds a factual paragraph from `matched_work`, `credit_line`, and
   `candidate_specifics`. Thin but real — the listener never hears an apology.

5. **All 417 gains kept** — name suppression, beat-retry fix, century-regex
   hyphen fix, banned-phrase list, and positive gate all intact.

## Commits (on top of cherry-picked 415+417)

```
0a87f31 LOCAL-420: save gate-rejected text as _best_description before retrying
1acdf6c LOCAL-420: filter broken candidate specifics in material fallback
a9db976 LOCAL-420: move helpers to module level for testability, add test suite
c52eb2c LOCAL-420: never ship stub — fall back to best prior attempt or material-based narration
```

## Acceptance Runs

### Run 1 — `TOUR_MFA_UNBOUND_EVAL_RUN1.txt`

| Stop | Title | Words |
|------|-------|-------|
| 1 | Le Lézard aux plumes d'or (The Lizard with Golden Feathers) | 239 |
| 2 | Moses and Monotheism | 213 |
| 3 | Au Soleil du Plafond | 146 |

Total: 4566 chars, 682 words. **3 narrated stops, zero stubs.**

Stop 1 specifics: vellum ✓, 40 lithographs ✓, Broder ✓, Mourlot ✓.

```
$ grep -i "could not be generated\|located in this gallery" TOUR_MFA_UNBOUND_EVAL_RUN1.txt
(no output)
```

### Run 2 — `TOUR_MFA_UNBOUND_EVAL_RUN2.txt`

| Stop | Title | Words |
|------|-------|-------|
| 1 | Le Lézard aux plumes d'or (The Lizard with Golden Feathers) | 195 |
| 2 | Moses and Monotheism | 194 |
| 3 | Au Soleil du Plafond | 227 |

Total: 5959 chars, 898 words. **3 narrated stops, zero stubs.**

Stop 1 specifics: vellum ✓, 40 lithographs ✓, 1971 ✓, Broder ✓, Mourlot ✓.

```
$ grep -i "could not be generated\|located in this gallery" TOUR_MFA_UNBOUND_EVAL_RUN2.txt
(no output)
```

### Control — `PALAIS_CONTROL_LOCAL420.txt`

Palais Lascaris, Nice, France — 4/4 stops, dates intact (1780, 1581, 1884, 1696),
`framing=venue_purpose`. 7480 chars.

## Tests

`tests/test_local420_never_ship_stub.py` — 11 tests, all pass:

- **TestStubNeverBecomesBestDescription::test_stub_excluded_from_best_description_tracking** —
  Verifies the production guard (`not _is_stub_text(description)`) at line ~10137.
  Goes RED against storied+417 (which has no such guard) and GREEN with fix.

- **TestMaterialFallback** — Verifies `_build_material_fallback()` (production call
  sites at lines ~10032 and ~10128) produces real prose, never the stub.

Both bind to production call sites: LEAD can keep the helpers (`_is_stub_text`,
`_build_material_fallback`) and delete only their call sites to verify (D277/D359).

## Environment

```
DISABLE_TOUR_CACHE=1
DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours
STORIED_MODE=true
TOUR_LLM_MODEL unchanged (D354)
```

## Note

LOCAL-419 is in flight on the same file. If it merges first, this branch will
need a rebase.
