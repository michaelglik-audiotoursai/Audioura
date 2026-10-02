##### READY FOR REVIEW

**Commit:** `93eca32`  
**Branch:** `kiro/local350-person-detector-appositive-gap`  
**Base:** `storied` (128aa1c)

---

## Diagnosis

**Losing stage for `Madalin Acchiardo`:** Check 2 (active verb), line ~611.
`_PROPER_PHRASE_RE` extracts `Madalin Acchiardo` at position [37-54]. It passes
`_NOT_A_PERSON_RE`, passes the preposition guard. `_PERSON_CONTEXT_RE` does NOT
match because "opened" is not in the vocabulary list. The appositive check
(Check 1) does NOT match because the post-text is `, who opened...` — "who" is
not a determiner (a/an/the/one). The active verb check (Check 2) finds "opened"
in the verb window, but the subject-change guard `\b(?:who)\b` in the
`_before_verb` text fires on ", who " — treating the relative pronoun as
indicating a DIFFERENT subject. The name falls through all checks undetected.

**Losing stage for `Giuseppe`:** Never extracted. `_PROPER_PHRASE_RE` requires 2+
capitalised words — "Giuseppe" is a single word. It does not match any deity
pattern (Track 2) or role-adjacent pattern (Track 3) because "husband" is not in
those vocabularies. Falls through all detection tracks.

## Fix (structural, per LOCAL-333 principle)

| File | Change |
|------|--------|
| `tour_rubric_scorer.py` | **Check 1b**: Non-restrictive relative clause detection. `, who <verb>` after a name identifies the antecedent as the person. Guard: stative verbs (is/was/has/had/been/being/becomes/became) do not fire. **Track 4**: Familial/identity role nouns (`husband`, `wife`, `widow`, `son`, `daughter`, etc.) immediately preceding a capitalised name identify a person. **Track 4b**: `named X` with guard against copula prefix (`was/is/been named` = stative naming, not person identification). |
| `tests/test_local350_person_appositive_gap.py` | 19 tests: 6 relative clause (incl. 2 stative guards), 6 familial role noun (incl. copula guard), 6 existing-guard regression (filler, place-appositive, D247 Grant/Andô, Chez Palmyre, La Merenda), 1 fact-count band. |

## Verbatim Evidence

### Target sentence — before and after

```
BEFORE (unfixed, storied base):
  named_people=[]
  distinct_fact_count=1

AFTER (fixed):
  named_people=['Giuseppe', 'Madalin Acchiardo']
  distinct_fact_count=3
```

### Filler and place-appositive guards

```
FILLER ("a mix of laughter and clinking glasses creating a symphony of conviviality"):
  named_people=[], distinct_fact_count=0

PLACE-APPOSITIVE ("Nice, a coastal city, offers…"):
  named_people=[]
```

### D247 cases intact

```
D247 'Ulysses Grant' (inside title "Ulysses Grant au Japon"):
  named_people=['Ulysses Grant']

D247 'Andô Naoyuki' (inside title "L'Armure d'Andô Naoyuki"):
  named_people=['Andô Naoyuki']

'Chez Palmyre' (IS the whole title):
  named_people=[]

'La Merenda' (IS the whole title):
  named_people=[]
```

### Museum bounds (D258)

```
Museum 8-stop (Arts Asiatiques): 82.56 ≥ 75.0 ✓
Museum 4-stop (Palais Lascaris): 81.25 ≥ 81.2 ✓
```

No museum stop gained a person that wasn't already there — the museum tours don't
use relative clause or familial noun patterns in their body text.

### D258 Distribution (453 stops from 99 DB tours)

```
              BEFORE (storied)     AFTER (LOCAL-350)
  n=0:       109 (24.1%)          109 (24.1%)
  n=1:        95 (21.0%)           94 (20.8%)
  n>=2:      249 (55.0%)          250 (55.2%)
  n<=1:      204 (45.0%)          203 (44.8%)
```

1 stop moved from n=1 to n≥2. Newly detected real people in DB tours (all correct):
- Pablo Picasso (via ", who ..." relative clause)
- Scott Fitzgerald (via relative clause)
- Claude Monet (via relative clause)
- Marie Clews (via relative clause)
- Isabel (via "wife Isabel" familial noun)

### Test results

```
tests/test_local350_person_appositive_gap.py     19 passed
tests/test_local333_fact_detector_nonmuseum.py   34 passed
tests/test_local339_corpus_and_person.py         13 passed, 2 skipped
tests/test_local344_fact_claim_alignment.py      12 passed
tests/test_local345_corpus_in_body.py             8 passed
tests/test_local346_bridge_vs_thin_row.py        10 passed
```

### D242 verification (tests fail on unfixed code)

```
Unfixed (storied base 128aa1c):
  named_people=[], distinct_fact_count=1
  → test_madalin_acchiardo_who_opened WOULD FAIL
  → test_husband_giuseppe WOULD FAIL
```

## Limitations

- The relative clause pattern only fires on multi-word names (captured by
  `_PROPER_PHRASE_RE`). A sentence like "Giuseppe, who opened..." would NOT
  be caught by Check 1b because "Giuseppe" is single-word and not extracted.
  It would need an independent single-word relative clause track (out of scope).

- Track 4 only matches the familial noun immediately adjacent to the name.
  "her late husband the great Giuseppe" (with intervening words between the role
  noun and the capitalised name) would not fire. Real prose rarely uses this
  construction.

- `OPENAI_API_KEY` is NOT in environment — cannot regenerate or re-score tours
  that require the pipeline. Distribution measured from existing DB content only.
