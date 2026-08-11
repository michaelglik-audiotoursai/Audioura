# SUBMISSION_LOCAL-418.md

## Summary

The exhibition extractor was treating the running-dates string
`Wednesday, September 16–Wednesday, October 7, 2026` as an artwork:
title = "Wednesday, September 16–Wednesday", artist = "October 7", date = "2026".

**Root cause:** `_WORK_LINE_PATTERNS[0]` (`^(.+?),\s+([A-Z][\w\s\-]+),\s*(\d{4})`)
matched the date line. The real credit line (349 chars, containing Le Lézard aux
plumes d'or) was excluded by the `len(line) > 300` filter and never reached any
regex. With 1 fake work extracted, the pipeline took the `partial`/`highlights_only`
path and never fell through to `prose_llm_extract_works`, which handles this page
correctly.

## What was fixed

### 1. `extract_works_from_exhibition_page` rejects dates at the source

Added `_is_date_like(title)` and `_is_date_like(artist)` checks in the validation
block. A title or artist made entirely of weekdays, months, and numbers is rejected
before it enters the works list.

### 2. `plausibility_gate` rejects date-range titles

Added `_is_date_like` checks to `_work_entry_is_implausible`. With 1 date-work,
the 100% implausible ratio exceeds the 50% threshold and discards all works,
forcing fallthrough to prose_llm.

### 3. Artist must never be a date

The `_is_date_like` check applies to the artist field too, rejecting "October 7" as
an artist at the source in `extract_works_from_exhibition_page`.

## Test output (red against `storied`)

Against the `storied` branch (no fix):

```
plausibility_gate on storied: 1 works kept
  BUG CONFIRMED: gate did NOT reject: {'title': 'Wednesday, September 16–Wednesday', 'artist': 'October 7', 'date': '2026'}
```

Against the fix (all 33 tests pass):

```
======================== 33 passed, 1 warning in 0.14s =========================
```

## Live extraction call and output

```python
from exhibition_checklist import _fetch_page, extract_works_from_exhibition_page, plausibility_gate, prose_llm_extract_works

text, links = _fetch_page('http://www.mfa.org/exhibition/picasso-miro-dali-unbound')
works = extract_works_from_exhibition_page(text, links)
# → 0 works (date line rejected)

works = prose_llm_extract_works(text, 'Picasso, Miró, Dalí: Unbound')
# → 3 works:
#   Le Lézard aux plumes d'or (The Lizard with Golden Feathers) by Joan Miró (1971)
#   Moses and Monotheism by Salvador Dalí (1974)
#   Au Soleil du Plafond by Juan Gris (1955)
```

## Full live tour — `run_mfa_unbound_eval.py`

File: `TOUR_MFA_UNBOUND_EVAL.txt`

```
Stop 1: Le Lézard aux plumes d'or (The Lizard with Golden Feathers)
Stop 2: Moses and Monotheism
Stop 3: Au Soleil du Plafond
```

All 3 works are real. No date appears as a title or artist anywhere in delivered
text. Pipeline log confirms:

```
[LOCAL-368] ✓ PROSE LLM PATH: 3 works extracted from prose
  Source: http://www.mfa.org/exhibition/picasso-miro-dali-unbound
  - Le Lézard aux plumes d'or (The Lizard with Golden Feathers) by Joan Miró (1971)
  - Moses and Monotheism by Salvador Dalí (1974)
  - Au Soleil du Plafond by Juan Gris (1955)
```

## Control (D302/D326): Palais Lascaris 4/4

File: `TOUR_PALAIS_CONTROL.txt`

```
Stop 1: Harpe by Naderman (Paris, 1780)
Stop 2: Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581)
Stop 3: Guitar by Antonio de Torres (Almeria, 1884)
Stop 4: Basse de violon by Paolo Antonio Testore (Milan, 1696)
```

`framing=venue_purpose` confirmed:
```
[LOCAL-382] framing=venue_purpose source='bequeathed to the city of Nice in the testament of 26 May 1901 and by a codicil '
```

Dates are intact (instrument dates preserved), no regressions.

## What produced the three-work 10:15 version

`TOUR_MFA_STORIED_CURRENT.txt` was committed at 10:16 on 2026-08-11 in D344
(`48f3763`). `exhibition_checklist.py` last changed at 2026-08-10 14:30 (LOCAL-373).
The same extractor code was running at 10:15.

**The structured extractor would have produced the same 1-work date result at 10:15**
(the code is identical, the page content is identical). Without the `_is_date_like`
fix, the pipeline takes the `highlights_only` path with 1 date-work and never
reaches prose_llm. It cannot produce 3 real works.

**Conclusion:** The three-work 10:15 version was NOT produced by live extraction
through the committed `exhibition_checklist.py`. Consistent with D357's hypothesis,
the most likely explanation is a runner or interactive test that pre-populated works
(the D345 pattern), where works were supplied directly to the generation pipeline
without going through `extract_works_from_exhibition_page`. No evidence of a
different code state exists in the git history.

## Zero-check

- No date appears as a title or artist in delivered text ✓
- No impossible relations ✓
- `DISABLE_TOUR_CACHE=1` confirmed
- `STORIED_MODE=true` confirmed
- `TOUR_LLM_MODEL` unchanged

## Files produced by this run

- `TOUR_MFA_UNBOUND_EVAL.txt` — 3-stop exhibition tour (live extraction)
- `TOUR_PALAIS_CONTROL.txt` — 4-stop Palais control
- `tests/test_local418_date_as_work_rejection.py` — 33 tests
