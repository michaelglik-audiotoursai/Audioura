##### READY FOR REVIEW

## LOCAL-216: R9_GENERIC — a sentence that fits any stop belongs to no stop

**Commit:** `26735d1`
**Branch:** `kiro/local216-r9-generic-sentence`
**Base:** `storied`
**Commits ahead of base:** 1

---

## Per-file summary

| File | Change |
|------|--------|
| `style_validator_detector.py` | Added R9_GENERIC rule: detection (`check_r9_generic`), deletion logic (`apply_r9_deletions`, `apply_r9_to_description`), filler/proper-noun/date/number heuristics, dangling-connective cleanup |
| `generate_tour_text.py` | Wired R9 deletion as PHASE 5.15, behind `DISABLE_R9_DELETION=1`. No LLM call, $0.00 cost |
| `tests/style_validator_detector.py` | Added R9 exports to shim (check_r9_generic, apply_r9_deletions, apply_r9_to_description, check_r8_prompt_leakage) |
| `tests/test_r9_generic_deletion.py` | Labelled set test: 39/39 pass (both directions) |
| `tests/run_r9_riviera_and_corpus.py` | Per-sentence Riviera analysis + corpus-wide deletion rate |

---

## Labelled set (from Michael's evaluation, both directions)

### MUST FIRE (0/5 — "should be removed"):
```
"As you continue your journey through this charming town, consider how these
 hidden paths have shaped the stories of this place, leading you to uncover
 more of its intriguing history."                                        → R9 FIRES ✓

"From Cap d'Antibes to Villefranche-sur-Mer — a collection that spans more
 ground than these stops alone."                                         → R9 FIRES ✓
```

### MUST NOT FIRE (1–5 — keep or rewrite): 23/23 pass

Navigation (5/5): `Start biking southeast...` → SILENT ✓
Sourced facts (5/5): `The town's strategic location east of Nice...` → SILENT ✓
Content with specifics (3/5): `In January 1888, Claude Monet...` → SILENT ✓
Style failures (1–2/5): `Look for the Rue Obscure...` → SILENT ✓
Prompt leakage (3A): `One concrete sensory detail...` → SILENT ✓ (handled by R8, not R9)

---

## Per-sentence table: R9 verdict vs Michael's score

```
Para  Group   Score  R9_fires  Match
1A            5      no        ✓  Start biking southeast on the main road...
              5      no        ✓  Take the second exit onto the coastal path...
1B            1      no        ✓  As you arrive at Cap d'Antibes...listen to...
              1      no        ✓  Look out for the Villa Eilenroc...
2 prolog      3      no        ✓  You are about to embark on a journey...
              3      no        ✓  Each stop along this tour serves as a chapter...
              3      no        ✓  From the opulent Villa Eilenroc...Rue Obscure...
              3      no        ✓  Join us as we delve into the timeless elegance...
3A            3      no        ✓  The Cap d'Antibes, a peninsula located south...
              3      no        ✓  In January 1888, the renowned artist Claude Monet...
              3      no        ✓  Inspired by the beauty of Cap d'Antibes, Monet...
              3      no        ✓  One concrete sensory detail that envelops you...
              3      no        ✓  The Tire-Poil coastal trail allows you to explore...
              3      no        ✓  Along this 2.7 km route, you'll traverse rocky...
3B            2      no        ✓  As you stand at the highest point of Cap d'Antibes...
              2      no        ✓  The nearby Abri de l'Olivette...
              2      no        ✓  Pedal along the coastline, envisioning...
4A            1      no        ✓  As you arrive at Villefranche-sur-Mer...
4B            1      no        ✓  Look for the Rue Obscure, a mysterious 13th-century...
5A            5      no        ✓  Villefranche-sur-Mer, known as "Free City on Sea"...
              5      no        ✓  The town's strategic location east of Nice...
              5      no        ✓  The deep bay of Villefranche...320 feet...
5B            1      no        ✓  Walking through the narrow streets...
              1      no        ✓  The Rue Obscure, with its shadowy passageways...
              1      no        ✓  This historical gem adds depth...Villefranche-sur-Mer...
5C            0      YES       ✓  As you continue your journey through this charming town...
6             0      YES       ✓  From Cap d'Antibes to Villefranche-sur-Mer — a collection...
```

**Disagreements: 0** — R9 perfectly matches Michael's 0/5 vs 1–5 boundary.

---

## Corpus-wide deletion rate

```
Tours scanned:          79
Total sentences:        4,623
Sentences R9 deletes:   59
Paragraphs emptied:     44
Tours affected:         48
Deletion rate:          1.3%
```

Well within the 15% ceiling. At 1.3%, R9 is identifying filler, not rewriting the product.

---

## Navigation and 5/5 groups — verifiably unaffected

- Navigation (5/5): "Start biking southeast on the main road, continue straight until you reach the roundabout" → **R9 silent** (navigation exemption via `_is_style_navigation_sentence`)
- Sourced generalities (5/5): "The town's strategic location east of Nice and southwest of Monaco has been pivotal in its history" → **R9 silent** (has proper nouns: Nice, Monaco)
- All 3 navigation test sentences: exempt ✓
- Both 5/5 sentence groups (¶1A, ¶5A): all 5 sentences silent ✓

---

## R1–R4, R7, R8 regression sets

```
R1: ✓  R2: ✓  R3: ✓  R4: ✓  R7: ✓  R8: ✓  NAV: ✓
ALL REGRESSION SETS: ✓ PASS
```

---

## Deletion wired into assembly

- **PHASE 5.15** in `generate_tour_text.py`, between style retry (5.1) and post-validation (5.5)
- Behind `DISABLE_R9_DELETION=1` env var
- Empty-paragraph removal: tested ✓
- Dangling-connective cleanup: tested ✓ (strips "However," etc. after deletion)
- $0.00 cost — deterministic, no LLM call

---

## Database invariants

```
audio_tours row count:  130 (unchanged — read-only operation)
Nice list (filtered):   [1, 12, 14, 17, 21, 24, 27, 28, 29, 152] ✓
No INSERT/UPDATE/DELETE executed.
```

---

## git status

```
$ git status --short
(clean)
$ git rev-list --count storied..HEAD
1
```

No container rebuilt. No modification to `claim_check.py`, `corpus_coverage.py`,
anchor detector, `DECISIONS.md`, `CLAUDE.md`, or `.continuous_dev/*`.

---

## Limitations

1. **R9 is sentence-level, not group-level.** Michael scored *groups* of 1–3 sentences. A sentence within a 3/5 group could theoretically be generic by itself, but R9 is conservative enough (requires 2+ filler signals or 1 strong signal) that it did not fire on any sentence within a group Michael scored 3+.

2. **The "From X to Y — filler" detection is pattern-based.** If a sentence uses a different frame to wrap proper nouns around a generic predicate (e.g., "Between X and Y, one finds..."), R9 may not catch it. The 1.3% rate suggests this is rare.

3. **No online measurement yet.** R9 was validated against Michael's offline evaluation and the stored corpus. The actual deletion in production runs happens in PHASE 5.15 and has not been A/B tested against listener retention. The `DISABLE_R9_DELETION=1` flag enables this.

4. **Dangling connective list is finite.** If a sentence after a deletion starts with a connective not in the list (e.g., "Henceforth,"), it won't be stripped. The list covers the common English connectives.
