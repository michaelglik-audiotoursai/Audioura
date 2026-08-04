##### READY FOR REVIEW

# SUBMISSION LOCAL-219: Subject-Match Fragility Fix (R2)

**Branch:** `kiro/local219-subject-match-fragility`
**Base:** `storied`
**Commit:** `524719b`
**Date:** 2026-08-04

---

## What R1 Got Right

The symmetry fix works. Both phrasings of the same fact get the same verdict:

```
"The museum opened in 1890 in Nice, France."  → CONTRADICTED
"The museum opened in 1890."                  → CONTRADICTED   (was UNSUPPORTED)
"MAMAC was inaugurated in 1975 by the mayor." → CONTRADICTED   (was: no claims)
"The museum opened on 21 June 1990."          → SUPPORTED_PARAPHRASE
"The chapel was built in 1432."               → UNSUPPORTED
```

## What R1 Got Wrong

The corpus-wide CONTRADICTED rate was not measured against stored tours. LEAD
ran 107 paragraphs from stored tours against their venue corpora and found 3
false alarms (was 0 after LOCAL-218). The subject matcher was accepting
passages that shared a proper noun (like a city name) or a generic subject
token, without verifying that the passage was asserting a **competing value
for the same event**.

## The R2 Fix: Predicate Proximity Requirement

Three changes to `_check_contradiction`:

### 1. Subject extraction returns empty on verb-less sentences

When `_extract_subject_nouns` cannot find a main verb, the subject phrase is
indeterminate. R1 returned the entire sentence as "subject nouns" — dozens of
tokens that created spurious matches (e.g., "also" appearing in both). R2
returns an empty list, preventing subject-noun path matches for these
sentences.

### 2. Proper noun and subject noun filtering

Added `_proper_noun_generics` — common place-name prefixes ("Saint", "Port",
"Cap", "Fort", "Mont", "Bay") that appear in many different place names and
cannot identify a specific entity. "Saint-Tropez" sharing "Saint" with
"Saint-Jean-Cap-Ferrat" is not a same-subject match.

Added place-name prefixes and spatial words to `_GENERIC_SUBJECT_NOUNS`:
"saint", "mont", "cap", "shores", "nestled", "commune", "town", "promenade".

### 3. Predicate proximity check (the core fix)

After subject match is established and a competing number is found, R2 adds a
final gate: the passage's competing number must appear **within 120 characters
of at least one predicate context token** from the claim sentence.

Predicate context tokens are the meaningful words from the claim sentence that
indicate what the number is *about* — e.g., "opened", "inaugurated",
"lighthouse", "beacon", "donated". Excluded from this set:
- Subject nouns and proper nouns (already matched on those)
- Common stopwords and prepositions
- Generic place names (Nice, France, Paris, Antibes...)
- Generic time words ("years", "century", "period")
- Generic building types ("museum", "palace", "gallery")
- Generic verbs ("made", "work", "became")

This ensures the passage is asserting a date/value for the **same predicate**,
not just having any random number somewhere while mentioning the same place.

Example:
- "Cap Ferrat Lighthouse... since 1827" vs passage saying "Cap Ferrat...
  population of 72,999 in 2023" → "Cap Ferrat" is the same subject, but the
  passage's number (2023/72,999) does NOT appear near "lighthouse", "beacon",
  or "sailors" → no contradiction. Verdict: UNSUPPORTED. ✓

---

## Corpus-Wide CONTRADICTED Rate

**Methodology:** For each stored tour with content (79 tours), match it to a
venue corpus by name. Extract all paragraphs (skipping metadata). For each
paragraph, run `check_paragraph` against all stop_corpus + venue_corpus
passages for that venue. Collect all CONTRADICTED verdicts.

Tour-to-venue matching is explicit (manual map) to avoid fuzzy match errors.
36 tours matched to 16 venues.

```
Paragraphs checked:     758
Total claims extracted:  188

Per-verdict counts:
  SUPPORTED_PARAPHRASE:   91
  SUPPORTED_ELSEWHERE:     0
  UNSUPPORTED:            97
  CONTRADICTED:            0
```

**Corpus-wide CONTRADICTED: 0 of 188 claims.**

No CONTRADICTED verdicts fire across any stored tour. Every false alarm that
LEAD found in R1 is eliminated.

---

## Paraphrase Symmetry: 7/7 Passing

```
$ python3 tests/test_local219_paraphrase_symmetry.py
  ✓ PASS: Museum opening date: incidental location removed
  ✓ PASS: MAMAC inauguration: incidental agent removed
  ✓ PASS: Villa construction date: incidental attribution removed
  ✓ PASS: Matisse residency start: incidental clause removed
  ✓ PASS: Correct date: location detail removed
  ✓ PASS: Correct date: agent detail removed
  ✓ PASS: Different subject (chapel vs museum): location removed
  Passed: 7/7
  ✓ All paraphrase pairs symmetric and correct
```

---

## Labelled Sets: Both Unchanged

### LOCAL-195/210 (29 claims, MAMAC)

| Metric | Before | After |
|--------|--------|-------|
| Agreement rate | 82.8% (24/29) | **82.8% (24/29)** |
| False SUPPORTED | **0** | **0** |
| False UNSUPPORTED | 5 | 5 |

### LOCAL-215 Holdout (20 claims, Chagall)

| Metric | Before | After |
|--------|--------|-------|
| Agreement rate | 90.0% (18/20) | **90.0% (18/20)** |
| False SUPPORTED | **0** | **0** |
| False UNSUPPORTED | 2 | 2 |

---

## Zero False SUPPORTED

```
LOCAL-195/210: False SUPPORTED = 0
LOCAL-215:     False SUPPORTED = 0
Corpus-wide:   Zero CONTRADICTED → cannot have false SUPPORTED via that path
```

---

## MAMAC Extraction: Fixed

Same as R1. The venue-name filter compared full claim text (including
parenthetical context annotation) against the venue name, causing year claims
to be silently dropped when "MAMAC" appeared in the context string. Fixed by
comparing against core claim text only.

```
>>> check_paragraph('MAMAC was inaugurated in 1975 by the mayor.',
...                 'History', 'MAMAC',
...                 ['MAMAC was inaugurated on 21 June 1990 by Jacques Médecin.'])
claims: [{'text': '1975 (in context: "MAMAC was inaugurated...")',
          'verdict': 'CONTRADICTED'}]
```

---

## Database

```
audio_tours: 130
Nice list: [1, 12, 14, 17, 21, 24, 27, 28, 29, 152] — unchanged
```

---

## Per-File Summary

| File | Change |
|------|--------|
| `claim_check.py` | Rewrote `_extract_subject_nouns` to return empty on verbless sentences; added `_proper_noun_generics` filter; added predicate proximity requirement in `_check_contradiction`; expanded `_GENERIC_SUBJECT_NOUNS` with place prefixes; fixed venue-name filter |
| `tests/test_local219_paraphrase_symmetry.py` | 7 paraphrase pairs (unchanged from R1) |
| `tests/test_local219_corpus_wide.py` | New: corpus-wide CONTRADICTED measurement (758 paragraphs, 188 claims, explicit venue matching) |

---

## Verbatim Evidence

### Bug reproduced (R1's corpus-wide false alarms, now fixed):
```
>>> # 1820/beggars vs Antibes passage (was CONTRADICTED in R1)
>>> check_paragraph('In 1820, faced with an influx of beggars...', 'Promenade', 'Riviera',
...   ['Antibes is a seaside resort city... population of 72,999'])
verdict: UNSUPPORTED  ✓

>>> # 1827/lighthouse vs Cap Ferrat passage (was CONTRADICTED in R1)
>>> check_paragraph('...beacon of hope and safety for sailors since 1827.',
...   'Cap Ferrat Lighthouse', 'Riviera',
...   ['Saint-Jean-Cap-Ferrat... In 2012, Cap Ferrat was named...'])
verdict: UNSUPPORTED  ✓
```

### Symmetry (both directions):
```
>>> check_paragraph('The museum opened in 1890 in Nice, France.', 'History', 'MAMAC',
...   ['The museum opened on 21 June 1990 in Nice, France.'])
verdict: CONTRADICTED

>>> check_paragraph('The museum opened in 1890.', 'History', 'MAMAC',
...   ['The museum opened on 21 June 1990 in Nice, France.'])
verdict: CONTRADICTED  ← symmetric ✓
```

### Different subject:
```
>>> check_paragraph('The chapel was built in 1432.', 'Donations', 'MAMAC',
...   ['The museum opened on 21 June 1990 in Nice, France.'])
verdict: UNSUPPORTED  ✓
```

### Corpus-wide:
```
$ python3 tests/test_local219_corpus_wide.py
  Paragraphs checked: 758
  Total claims: 188
  CONTRADICTED: 0  ✓
```

### Labelled sets:
```
LOCAL-195/210: 24/29 (82.8%), False SUPPORTED: 0
LOCAL-215:     18/20 (90.0%), False SUPPORTED: 0
```

---

## Limitations

1. **Under-claiming is by design.** The predicate proximity requirement means
   some genuine contradictions where the passage uses very different phrasing
   will be missed (verdict: UNSUPPORTED instead of CONTRADICTED). This is the
   correct direction of error per D95 — under-claiming a contradiction is far
   safer than crying wolf.

2. **The generic exclusion lists are corpus-specific.** Words like "nice",
   "france", "museum", "palace" are excluded because they appear incidentally
   in the Nice/Riviera corpus. A corpus about, say, London museums would need
   "london", "thames", etc. The lists could be generalized further but the
   current set covers the actual deployment corpus.

3. **Verb-less sentences cannot fire CONTRADICTED.** If the claim sentence has
   no recognizable main verb from the curated list, subject extraction returns
   empty and the contradiction check bails out. This handles cases like "In
   1820, faced with..." (participle, not finite verb) safely — they get
   UNSUPPORTED rather than false CONTRADICTED.

4. **The corpus-wide measurement covers 36 of 79 tours.** The other 43 have no
   matching venue corpus (Abu Dhabi camels, Philadelphia, regression tests,
   etc.). The 36 matched tours include all the Nice museum, Riviera cycling,
   and walking tours — the production-relevant subset.

5. **Decade claims (1960s) are extracted as the number "1960".** A passage
   mentioning any year in the 1960s (e.g., 1965) would be "contradicting"
   1960, even though 1965 is within the 1960s. This is an existing claim
   extraction limitation, not new to R2. In practice it does not fire because
   the predicate proximity check prevents spurious matches.

---

## Spend

$0.00 — no LLM calls, no API calls. Pure Python logic changes.

Ceiling: $0.25. Actual: $0.00.
