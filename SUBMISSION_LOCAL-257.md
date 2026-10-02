##### READY FOR REVIEW

## Commit

```
LOCAL-257: Fragment checker quoted-span masking, determiner restoration, Chagall trace
```

## Per-File Summary

| File | Change |
|---|---|
| `style_validator_detector.py` | +85 lines: `_QUOTED_SPAN` regex masks titles/quotes before verb search; `_restore_determiner` restores "The" when R1 strips it; `_has_finite_main_verb` rewritten with field-label stripping, imperative detection, broader verb recognition, possessive/adjective exclusion from -s heuristic; `_FINITE_VERB_FORMS` expanded with irregular past tenses and present-tense verbs |
| `tests/test_local257_fragment_checker.py` | 59 tests: quoted-span masking (4 must-fragment, 6 must-pass), determiner restoration (5 must-fix, 5 must-not-change), all 34 prior boundary rows (8 LOCAL-255, 7 LOCAL-253, 10 LOCAL-251, 9 LOCAL-249), round 13 fragment recount |
| `run_round14.py` | Generation harness: flags-pop, D141-compliant DB round-trip, fragment/determiner/fact measurement, artifact write |
| `RIVIERA_2STOP_ROUND14.md` | Tour artifact (Cap d'Antibes + Eze Village, 555 words, 9 facts) |

## Three Defects Addressed

### 1. `_has_finite_main_verb` matches verbs inside quoted titles (FIXED)

**Root cause:** The function searched for finite verb patterns in the entire sentence without masking quoted spans. `"Tender is the Night"` — "is" matched, so the function returned True even though the sentence has no main-clause verb.

**Fix:** `_QUOTED_SPAN` regex masks `"…"`, `"…"`, `'…'`, `«…»`, and `*…*` spans before any verb search. Additionally:
- Field-label prefixes (`Orientation:`, `Directions:`) stripped before analysis
- Imperative mood recognized as finite (sentence-initial verbs)
- "Once/When/As you…" subordinate clauses recognized
- `_FINITE_VERB_FORMS` expanded with irregular past tenses (`held`, `drew`, `found`, `built`, `wrote`, `came`, `became`, etc.)
- Possessives (`'s`) excluded from 3rd-person-s heuristic
- Adjectives ending in -ous/-less excluded from 3rd-person-s heuristic
- The naive "> 8 words passes" heuristic replaced with actual verb-pattern searches

**Round 13 true fragment count (with fixed checker):**
- 1 narration fragment: `Scott Fitzgerald's "Tender is the Night," a vivid portrayal...`
- 4 metadata lines (headers/addresses, not narration)
- The old checker reported 0 narration fragments (fooled by "is" inside the title)

### 2. Determiner restored where the rewrite strips it (FIXED)

**Root cause:** When R1 strips an imperative like "Explore the charming village…", the article "the" goes with the verb. The remainder "Charming village of X is…" is grammatical but missing "The".

**Fix:** `_restore_determiner()` detects sentences starting with `adjective + common noun + preposition` or `bare common noun + preposition` and prepends "The" with correct capitalization. Applied after both deterministic and LLM rewrites in `apply_r1_rewrites`.

### 3. Chagall misplacement traced to source (REPORTED)

**Investigation results:**
- Cap d'Antibes `stop_corpus` (ids 227, 236): **0 mentions of Chagall** across 9 passages
- Saint-Paul-de-Vence `stop_corpus` (id 230): Chagall mentioned in Fondation Maeght passage
- "clandestine atelier" appears in **0 corpus passages** across all 88 rows — entirely fabricated
- The same tour correctly places Chagall at Saint-Paul-de-Vence (stop 2)

**Cause:** LLM cross-stop contamination. Both stops' corpus passages are in the generation prompt, and the model placed a Saint-Paul-de-Vence fact at Cap d'Antibes with fabricated detail ("clandestine atelier"). The existence gate validates stop-level passage presence, not per-sentence fact provenance. Fixing this class requires per-fact attribution checking (not cheap — the gate would need to trace each generated claim back to a specific passage).

## All Prior Boundary Sets Hold (144 tests green)

| Source | Rows | Status |
|---|---|---|
| LOCAL-255 (R1 rewrite) | 8 | ✓ all pass |
| LOCAL-253 (directions mode) | 7 | ✓ all pass |
| LOCAL-251 (R10 unfulfilled promise) | 10 | ✓ all pass |
| LOCAL-249 (R9 generic) | 9 | ✓ all pass |
| LOCAL-256 (fragment/label/R7) | 28 | ✓ all pass |

## Round 14 Metrics

| Metric | Value |
|---|---|
| Stops | Cap d'Antibes, Eze Village |
| Word count | 555 |
| Generation cost | $0.0098 |
| R1 rewritten | 2 |
| R1 residual | 3 |
| R7 residual | 0 |
| Fragment sentences (narration) | 1 ("Happy cycling!" — exclamation) |
| Missing determiners | 0 |
| Facts: Cap d'Antibes | 2 (population 77,637 in 2023, second-most populous in Alpes-Maritimes) |
| Facts: Eze Village | 7 (200 BC settlement, Antonine Itinerary, 1388 House of Savoy, 1543 French/Ottoman siege, 1706 Louis XIV destruction, Chapelle de la Sainte Croix 1306, 1860 vote to join France) |

## Evidence

```
$ python3 -m pytest tests/test_local257_fragment_checker.py tests/test_local256_fragment_and_label.py tests/test_r1_rewrite.py tests/test_local253_directions_mode_guard.py tests/test_r10_unfulfilled_promise.py -v
144 passed

$ python3 -c "
from style_validator_detector import _has_finite_main_verb
# Must be flagged as fragment
s1 = 'Scott Fitzgerald\'s \"Tender is the Night,\" a vivid portrayal of the Roaring Twenties set against the backdrop of this opulent paradise.'
print(f'Fitzgerald (should be False): {_has_finite_main_verb(s1)}')
# Must NOT be flagged
s2 = 'Eze Village is a medieval gem perched high above the French Riviera.'
print(f'Eze (should be True): {_has_finite_main_verb(s2)}')
s3 = 'The Fondation Maeght was founded in 1964 by Marguerite and Aimé Maeght.'
print(f'Maeght was (should be True): {_has_finite_main_verb(s3)}')
s4 = 'The Fondation Maeght, founded in 1964 by Marguerite and Aimé Maeght.'
print(f'Maeght no verb (should be False): {_has_finite_main_verb(s4)}')
s5 = 'Start cycling south on the main road with the sea on your right.'
print(f'Imperative (should be True): {_has_finite_main_verb(s5)}')
s6 = 'In 1888, Monet first experimented with painting in series here.'
print(f'In year (should be True): {_has_finite_main_verb(s6)}')
"
Fitzgerald (should be False): False
Eze (should be True): True
Maeght was (should be True): True
Maeght no verb (should be False): False
Imperative (should be True): True
In year (should be True): True

$ python3 -c "
from style_validator_detector import _restore_determiner
s = 'Charming village of Saint-Paul-de-Vence is a medieval gem nestled in the Alpes-Maritimes department of the French Riviera.'
print(_restore_determiner(s))
"
The charming village of Saint-Paul-de-Vence is a medieval gem nestled in the Alpes-Maritimes department of the French Riviera.

$ python3 -c "
import sys; sys.path.insert(0, 'tests')
from db_connection import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute(\"SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id\")
print([r[0] for r in cur.fetchall()])
cur.execute(\"SELECT COUNT(*) FROM audio_tours\")
print(f'Total rows: {cur.fetchone()[0]}')
conn.close()
"
[1, 12, 14, 17, 24, 29, 152]
Total rows: 142
```

## Limitations

1. **Stop selection is LLM-stochastic.** The task requested Cap d'Antibes + Saint-Paul-de-Vence; the generator consistently picks Eze Village over Saint-Paul-de-Vence for the second stop. Both are in the corpus, but Eze has higher passage count (28 vs 7) and higher existence-gate pass rate, making it more likely to be selected. The code fixes are stop-independent.

2. **"Happy cycling!" detected as fragment.** This is technically correct — it's a noun phrase used as an exclamation, not a sentence with a finite verb. It's in the Directions section, not narration body text. The fragment checker is conservative by design.

3. **Chagall fix is a report, not a code change.** Per-fact attribution checking (tracing each generated claim back to a corpus passage) would prevent this class of fabrication but is not cheap. The existence gate operates at stop level, not sentence level.

4. **The broader verb list is still incomplete.** English has thousands of verb forms. The heuristic approach means some rare verb forms will slip through. The design errs on the side of catching known fragment patterns (our rewrite output) rather than attempting perfect verb classification, which would require a parser.

5. **Cap d'Antibes fact density lower than Eze.** 2 facts vs Eze's 7. This is corpus depth: Cap d'Antibes has 9 passages vs Eze's 28. The generator has less material to work with.
