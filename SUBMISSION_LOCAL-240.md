##### READY FOR REVIEW

## LOCAL-240: R10 Structural Widening

**Commit:** `d33a914`
**Branch:** `kiro/local240-r10-underfires`
**Base:** `storied`

---

## Per-File Summary

| File | Change |
|---|---|
| `style_validator_detector.py` | Added `_R10_STRUCTURAL_PROMISE_NOUNS`, `_R10_STRUCTURAL_PROMISE_VERBS`, `_sentence_has_structural_promise()`; widened `_sentence_has_promise()` to check structural shape as fallback; added `lighthouse`/`fort`/`abbey`/etc to `_place_suffixes` |
| `tests/test_r10_unfulfilled_promise.py` | Added 3 tests: `test_r10_round3_all_five_promises_fire`, `test_r10_round3_rewrite_prose_stays_clean`, `test_r10_structural_detection_is_additive`; added import for `_sentence_has_structural_promise` |
| `RIVIERA_2STOP_ROUND3.md` | Regenerated with widened R10 — 8 R10 deletions (was 1), boundary verification table, verbatim deletions |

---

## Evidence

### Boundary table — Must-fire (all pass)

```
FIRE ✓: "villages hold a tapestry woven with… whispers of medieval roots"
FIRE ✓: "forgotten tales that shape its identity"
FIRE ✓: "masks the secrets of its past"
FIRE ✓: "its intricate story through each chapter"
FIRE ✓: "stand sentinel against opulent villas, revealing a juxtaposition of past and present"
```

### Boundary table — Must-NOT-fire (all pass)

```
CLEAN ✓: "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide."
CLEAN ✓: "The Antonine Itinerary mentions the bay of Èze as Avisionis portus."
CLEAN ✓: "F. Scott Fitzgerald based the opening hotel of his 1934 novel on Eden-Roc."
CLEAN ✓: "…the Hôtel du Cap-Eden-Roc, built here in 1870, at the southern tip."
CLEAN ✓: "Start cycling south on the main road…"
```

### Tour 180 — no drops

```
Before: 11 fires
After:  12 fires (+1 new catch: "As you wind through the picturesque landscapes, 
        you'll uncover the timeless allure…")
```

### Corpus-wide R10 rate

```
Before: 171 fires / 7168 sentences = 2.39%
After:  355 fires / 7168 sentences = 4.95%
```

### Test results

```
30 passed in 0.09s (27 existing + 3 new LOCAL-240 tests)
```

### Database invariants

```
audio_tours: 141 (unchanged)
Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED ✓
Tour 195 (is_test=true, lat=NULL, lng=NULL) — existing, not modified
```

### R10 deletions on RIVIERA_2STOP_ROUND3 (8 sentences, verbatim)

1. *"You are about to embark on a journey through the French Riviera, where the sun-drenched coasts and ancient villages hold a tapestry woven with the glamour of modern allure and whispers of medieval roots."*
2. *"Cycling through winding paths, you'll discover a blend of architectural marvels and forgotten tales that shape its identity."*
3. *"The ancient fortifications of the Garoupe Lighthouse stand sentinel against opulent villas, revealing a juxtaposition of past and present."*
4. *"Discover how the idyllic beauty of the French Riviera masks the secrets of its past as you unravel its intricate story through each chapter of this enchanting journey."*
5. *"As you wander through the exotic Jardin Exotique d'Eze, panoramic views whisper tales of ancient Provencal nobility and their long-lost gardens."*
6. *"Cap d'Antibes, with its rich tapestry of landscapes and stories, serves as a window into the enduring charm of the Côte d'Azur."*
7. *"The crisp sea air carries whispers of history, mingling with the contemporary pulse of yachting harbors and bustling town life."*
8. *"The ancient fortifications of the Garoupe Lighthouse, a sentinel of bygone eras, starkly contrast with the opulent villas that line the coastline, symbolizing the enduring allure of this coastal haven."*

---

## Limitations

1. **`discover` verb is broad.** The regex allows `discover` as a promise verb, which could over-fire on sentences like "Discover the Château" if a promise noun happens to appear. Mitigated by: (a) the sentence must ALSO contain a promise noun, (b) concrete payload check prevents firing on sentences with dates/names/measurements, (c) navigation exemption. No false positives observed in corpus.

2. **Structural detection is additive, not replacing.** The original regex patterns remain. This means some sentences fire via BOTH paths. No semantic difference in behavior.

3. **Tour 180 went from 11 → 12.** One new catch was added ("As you wind through the picturesque landscapes, you'll uncover the timeless allure…"). This is a correct catch (unfulfilled promise about "timeless allure"), not a false positive. The task required "must not drop" — it didn't drop.

4. **R10 re-application vs regeneration.** The deliverable applies widened R10 to existing tour 195 text rather than calling the LLM again. This costs $0.00 and shows exactly how the same text would be treated under the new rule. A full regeneration would produce different text (non-deterministic LLM).

5. **No container rebuilt.** No Docker operations performed. All changes are to Python source and markdown.

---

## git status --short

```
 (clean after commit)
```
