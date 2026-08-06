##### READY FOR REVIEW

**Task:** LOCAL-324  
**Branch:** kiro/local324-tests-must-call-production  
**Commit:** a9ed192  
**Base:** storied  

---

## Per-file summary

| File | Change |
|------|--------|
| `generate_tour_text.py` | Added module-level `_build_material_period_patch(material_english, period_english)` helper (~line 56). Replaced inline 8-line if/elif/else at ~line 7632 with a 3-line call to the helper. |
| `tests/test_local322_genuine_patch.py` | Added `from generate_tour_text import _build_material_period_patch`. Deleted duplicated patch construction in all three cases; calls helper + separate insertion function. |
| `tests/test_local322_material_language.py` | Added `from generate_tour_text import _build_material_period_patch`. `TestPatchSentence` class now calls the helper directly instead of a local `_build_patch` reimplementation. `TestBugReportReproduction` likewise calls helper. Added `test_neither_returns_empty`. |

---

## Verbatim evidence

### Three sentences produced by the helper

```
Case 1: ✓ MATCH
  expected: 'This work, crafted from schist, dates from the 19th century.'
  actual:   'This work, crafted from schist, dates from the 19th century.'
Case 2: ✓ MATCH
  expected: 'This work was crafted from schist.'
  actual:   'This work was crafted from schist.'
Case 3: ✓ MATCH
  expected: 'This work dates from the 19th century.'
  actual:   'This work dates from the 19th century.'

All three outputs are byte-identical to the known-good strings.
```

### Import lines in both test files

```
tests/test_local322_genuine_patch.py:from generate_tour_text import _build_material_period_patch
tests/test_local322_material_language.py:from generate_tour_text import _build_material_period_patch
```

### Full test suite passes (55 tests)

```
======================== 55 passed, 1 warning in 0.14s =========================
```

### Deliberate break → test goes red

Break applied: `s/crafted from/crafted in/` in helper's material-only branch.

```
tests/test_local322_material_language.py::TestPatchSentence::test_material_only_patch FAILED [100%]

tests/test_local322_material_language.py:176: in test_material_only_patch
    assert patch == "This work was crafted from schist."
E   AssertionError: assert 'This work was crafted in schist.' == 'This work was crafted from schist.'
E     - This work was crafted from schist.
E     ?                       ^^^^
E     + This work was crafted in schist.
E     ?                       ^^
```

```
tests/test_local322_genuine_patch.py:
AssertionError: Patch sentence wrong!
```

Both test files fail when the helper is broken. Restored → 55 passed.

### git status --short (clean)

```
(empty)
```

---

## Limitations

- The `_FR_EN_MATERIAL_MAP` remains duplicated in `test_local322_material_language.py` for the translation-coverage tests (TestMaterialTranslation). Those tests verify the map's completeness, not the patch sentence. Extracting the map was out of scope.
- The `test_local322_genuine_patch.py` file also keeps a local copy of the map for the presence-check simulation logic (deciding *whether* to patch). Only the patch-sentence construction was extracted; the surrounding detection logic was not in scope.
- No containers rebuilt; no database rows modified.
