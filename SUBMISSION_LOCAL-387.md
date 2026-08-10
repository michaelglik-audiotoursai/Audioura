# SUBMISSION_LOCAL-387.md — Framing variable ordering fix

## Summary

LOCAL-382 introduced exhibition thesis/venue purpose framing for museum tours.
The framing detection (`detect_framing_case`) was placed at line ~10735 in the
tour assembly section — but `_generate_description` (a nested closure that reads
`_framing_case`) was called via `ThreadPoolExecutor` at line ~9585. Python binds
closure variables at call time; since the assignment hadn't executed yet, every
museum tour crashed with:

```
NameError: free variable '_framing_case' referenced before assignment in enclosing scope
```

## Fix

Moved the entire framing detection block (default assignments + `detect_framing_case()`
call) from the post-assembly section to the Phase 5 preamble — before
`_generate_description` is defined at line 8248. The closure now captures an
already-bound variable.

The original location is replaced with a comment pointing to the new location.
No logic changes; purely a reordering fix.

### Files changed

| File | Change |
|---|---|
| `generate_tour_text.py` | Moved `[LOCAL-382]` framing detection block from line ~10735 to line ~8171 (Phase 5 preamble, before `_generate_description` def) |
| `tests/test_local387_framing_ordering.py` | New: 9 tests covering ordering, integration, and framing engagement |

## Tests

**9 tests**, all passing:

| # | Test | What it verifies |
|---|---|---|
| 1 | `test_framing_case_assigned_before_generate_description` | AST ordering: assignment < def |
| 2 | `test_framing_source_phrase_assigned_before_generate_description` | AST ordering for second variable |
| 3 | `test_framing_page_text_assigned_before_generate_description` | AST ordering for third variable |
| 4 | `test_phase5_museum_path_no_nameerror` | Integration: real source path, no NameError |
| 5 | `test_stop_block_injection_with_framing` | Stop block produces content for exhibition case |
| 6 | `test_framing_none_produces_no_stop_block` | No injection for framing=none |
| 7 | `test_exhibition_scoped_produces_exhibition_framing` | Detection returns 'exhibition' for MFA |
| 8 | `test_unscoped_museum_produces_none` | Encyclopedic museum → framing=none |
| 9 | `test_palais_lascaris_no_fabricated_framing` | No fabricated thesis for instrument museum |

**Expected red-on-revert count: 4** — reverting the fix (moving assignment back
after `_generate_description` def) breaks:
- `test_framing_case_assigned_before_generate_description` (ordering)
- `test_framing_source_phrase_assigned_before_generate_description` (ordering)
- `test_framing_page_text_assigned_before_generate_description` (ordering)
- `test_phase5_museum_path_no_nameerror` (source scan confirms wrong order)

Revert breaks logic (wrong execution order → unbound variable), not the symbol
(D296). Tests import successfully on both branches.

No `inspect.getsource`, no mirrors (D277). Tests exercise the real
`exhibition_thesis` module and verify source structure via AST (structural guard,
not logic duplication).

## Acceptance status

**IMPLEMENTATION COMPLETE — awaiting live acceptance with API key.**

The fix eliminates the NameError. Live acceptance (per D284) requires:
- MFA exhibition tour generation (verifies framing engages per-stop)
- Palais Lascaris at 4 stops (verifies no crash + no fabricated premise)
- Large encyclopedic museum (verifies framing=none, no invented language)
- Score bounds: `score_tour_file(f,4)` ≥ 81.2, `score_tour_file(f,8)` ≥ 75.0

LOCAL-382 acceptance targets (book in ≥2 stops, collaboration mentions,
artist/publisher/printer details per stop, framing log line) can only be verified
on live generation — all previously blocked by this crash.
