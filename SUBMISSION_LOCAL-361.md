# SUBMISSION_LOCAL-361.md

## LOCAL-361: A stop whose title contains '?' silently vanishes from the tour

### Summary

Fixed two defects that caused punctuated artwork titles (e.g. Gauguin's
"Where Do We Come From? What Are We? Where Are We Going?") to silently
disappear from generated tours:

**(a) F3 guard misfired on legitimate titles** — replaced blunt punctuation
check with a targeted sentence-injection heuristic.

**(b) D2 header stripping deleted F3-modified headers** — fixed D2 to track
actually-rendered headers, and added a hard heading-count invariant.

---

### Per-File Changes

| File | Change |
|------|--------|
| `generate_tour_text.py` (line ~10640) | **F3 guard rewrite.** Replaced `any(c in poi_name for c in '.!?;')` with a three-tier heuristic: (1) >15 words → always CORRUPT; (2) D1v2-verified → always keep; (3) unverified: check for sentence-ending-punct + space + lowercase (`[.!?;]\s+[a-z]`) OR known injection-start patterns (`This|Here|The following|In this|Welcome to`). |
| `generate_tour_text.py` (line ~10595) | Added `_rendered_headers = []` tracking list before the POI loop. |
| `generate_tour_text.py` (line ~10670) | Added `_rendered_headers.append(poi_header)` after F3 processing, capturing the actual header that goes into the tour text. |
| `generate_tour_text.py` (line ~10910) | **D2 fix.** Changed `_real_headers` construction from rebuilding headers off `poi['name']` (which doesn't reflect F3 truncation) to `set(_rendered_headers)` (the actual headers in the text). |
| `generate_tour_text.py` (line ~10930) | **Hard invariant.** After D2 cleanup, counts `Stop N:` lines via regex and asserts count == `len(poi_list)`. Mismatch raises `ValueError` with a diagnostic message — fails loudly at generation time instead of silently delivering a short tour. |
| `tests/test_local361_punctuated_titles.py` | 25 unit tests covering: F3 verdicts for legit titles (9 cases), injection catching (7 cases), D2 header preservation (2 structural checks), invariant existence (2 checks), and the D269 evidence table. |

---

### Design Choices — F3 Heuristic

The ticket suggested several signals. I assessed them and chose:

1. **Word count >15**: Kept as-is — a legitimate title is rarely 16+ words.
   Applies regardless of verification status (even verified titles this long
   would cause TTS and rendering issues).

2. **D1v2-verified exemption**: Implemented as the primary gate. If the corpus
   vouched for the title, no further checking needed. This is both the safest
   and the most efficient path — we already did the hard work of verification.

3. **Sentence-ending punctuation + space + lowercase word** (`[.!?;]\s+[a-z]`):
   This is the actual signal for an injected sentence. Real titles almost
   always capitalize after punctuation (e.g. "What Are We?" — capital W).
   A GPT injection like "a beautiful painting. the artist" has lowercase after
   the period. Applied only to unverified names.

4. **Known injection start patterns**: GPT typically starts injected text with
   "This is…", "Here we…", "The following…", "In this…", "Welcome to…".
   These are not artwork title patterns. Applied only to unverified names.

**Not chosen:**
- Finite-verb/clause-structure detection (too complex, NLP dependency, fragile)
- Simple "contains any punctuation" (the original bug)

---

### Evidence Table (D269)

| Input Title | Old Verdict | New Verdict |
|---|---|---|
| `Where Do We Come From? What Are We? Where Are We Going?` | CORRUPT | keep |
| `Ecce Homo Triptych` | keep | keep |
| `St. Jerome in His Study` | CORRUPT | keep |
| `Whaam!` | CORRUPT | keep |
| `No. 14, 1960` | CORRUPT | keep |
| `This beautiful painting depicts the River Thames. the artist captured light masterfully` (constructed injection) | CORRUPT | CORRUPT |

All verdicts confirmed via `tests/test_local361_punctuated_titles.py::TestEvidenceTable`.

---

### Test Results

```
tests/test_local361_punctuated_titles.py             — 25 passed
tests/test_local345_corpus_in_body.py::TestMuseumScoreBounds — 2 passed (75.0 / 81.2 bounds hold)
tests/test_local357_forced_stops.py::TestMuseumBoundsProperty — 2 passed (75.0 / 81.2 bounds hold)
tests/test_local357_forced_stops.py (full)           — 16 passed
tests/test_local345_corpus_in_body.py (full)         — 8 passed
```

---

### Limitations

1. **15-word limit applies universally** — a verified title with 16+ words
   would still be truncated. No known real artwork title exceeds this, but
   it's theoretically possible for a very long subtitle.

2. **Unverified titles with uppercase-after-punctuation injections** would
   pass the new heuristic (e.g. "A fake name. The artist is great"). This is
   mitigated by the known-injection-start patterns, but a novel injection
   shape starting with a proper noun could slip through. The heading-count
   invariant provides the safety net — a dropped heading always fails loud.

3. **The hard invariant raises ValueError** which must be caught by the
   service layer. The existing `generate_tour_text_service.py` already catches
   exceptions from the generation function and reports them as errors to the
   user — so this is handled, but it's a fail-to-error, not a graceful
   recovery.
