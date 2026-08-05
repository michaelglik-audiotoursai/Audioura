##### READY FOR REVIEW

**Task:** LOCAL-235 R10 — Unfulfilled Promise (resubmission after LEAD bounce)
**Branch:** `kiro/local235-r10-unfulfilled-promise`
**Commit:** `bb5b167`
**Date:** 2026-08-05

---

## What changed

The LEAD bounce identified one failure: **delivery was not topic-aware.** A date
about Mount Bastide settlers was accepted as delivery for "stone walls holding a
story" — because the code only checked "is there ANY concrete payload nearby?"
without verifying it concerned the same subject.

### Fix: `_delivery_matches_promise(promise_sent, delivery_sent)`

Extracts content words from both sentences (stripping stopwords and abstract
fillers like "history", "tales", "legacy", "heritage") and requires at least one
shared content word. A stemming fallback checks shared 4-char prefixes for
morphological variants (wall/walls, village/villages).

**Before (v1):** `_sentence_has_concrete_payload(next_sent)` → if True, delivery accepted regardless of topic.

**After (v2):** `_sentence_has_concrete_payload(next_sent) AND _delivery_matches_promise(stripped, next_sent)` → delivery accepted only if on-topic.

---

## Per-file summary

| File | Change |
|---|---|
| `style_validator_detector.py` | Added `_R10_STOPWORDS`, `_R10_ABSTRACT_FILLERS`, `_extract_content_words()`, `_delivery_matches_promise()`. Modified `check_r10_unfulfilled_promise()` to require topic overlap for delivery. |
| `tests/test_r10_unfulfilled_promise.py` | Rebuilt from scratch with real paragraphs (tour 180). Added falsification tests. Removed synthetic context. |
| `r10_measurement_output.json` | Updated corpus-wide measurement results. |

---

## Labelled set — real paragraphs, both directions

### MUST FIRE (Michael's complaints, tested IN their real paragraph from tour 180):

| Sentence (in Eze paragraph 5) | Fires? |
|---|---|
| "each crack and crevice holding a story" | ✓ |
| "The hillsides hold a multitude of tales from a bygone era." | ✓ |
| "serves as a bridge between ancient civilizations and contemporary life" | ✓ |
| "a harmonious symphony of past and present" | ✓ |
| "a testament to the enduring allure of the French Riviera's rich historical tapestry" | ✓ |

In Cap d'Antibes paragraph 3:

| Sentence | Fires? |
|---|---|
| "delving into a rich tapestry of history and culture" | ✓ |

### MUST NOT FIRE (his rewrite prose — what good looks like):

| Sentence | Fires? |
|---|---|
| "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide." | ✗ (concrete, no promise) |
| "The Antonine Itinerary mentions the bay of Èze as Avisionis portus." | ✗ (concrete, no promise) |
| "Start cycling south on the main road…" | ✗ (navigation exempt) |
| "F. Scott Fitzgerald based the opening hotel of his 1934 novel on Eden-Roc." | ✗ (concrete, no promise) |
| "the Hôtel du Cap-Eden-Roc, was built here in 1870, at the southern tip" | ✗ (concrete, no promise) |
| "At Cap d'Antibes…inspired artists like Picasso…" | ✗ (concrete, named person) |
| "At the apex of Jardin Exotique…panoramic vista" | ✗ (concrete, named place) |

---

## Falsification cases (proves delivery check works)

Each case: R10 fires on a sentence → append a genuine on-topic delivery → R10 stops firing.

1. **"walls holding a story"** → add "These fortification walls were erected in 1388 by the House of Savoy after Saracen raids" → R10 silent. (Shared: "walls")
2. **"hillsides hold tales"** → add "These hillsides were terraced in the 14th century for olive cultivation by Benedictine monks" → R10 silent. (Shared: "hillsides")
3. **"bridge between ancient civilizations"** → add "The village was founded as a Ligurian settlement in 600 BC, conquered by Romans in 154 BC" → R10 silent. (Shared: "village")

---

## Corpus-wide rate by tour type

```
Type         Tours   Sentences   R10 del   R10 rate   R9 del   Combined   > 1/3
----------------------------------------------------------------------
cycling      21      1118        77        6.9%       21       8.8%       1
museum       20      1656        16        1.0%       7        1.4%       0
other        19      627         12        1.9%       10       3.5%       0
walking      24      1018        45        4.4%       24       6.8%       0
----------------------------------------------------------------------
TOTAL        84      4419        150       3.4%       62       4.8%       1
```

**Paragraphs emptied:** R10=6, R9=47, combined=53.

**Tours exceeding 1/3 deletion:** 1 — Tour 180 (cycling), 11/29 sentences = 38%.
This is Michael's reviewed tour. He scored 5 of 5 paragraphs at 1-3/5, largely
for this rule. The high deletion rate confirms the corpus cannot support this
tour without substantial rewriting. **Product decision for Michael per D123.**

---

## Calibration re-run (QUALITY_PROFILE.md §5)

| Before R10 | After R10 |
|---|---|
| 5 agree, 2 partial, 4 disagree | **6 agree**, 2 partial, **3 disagree** |

R10 catches M8 ("whispers tales of a bygone era") which was previously a blind
spot. M4 ("envisioning the hidden coves") does NOT fire R10 — it's a
suggestive/prescribed-feeling issue (R3/R4 gap), not an unfulfilled promise.

---

## All suites green

```
R10 test suite:  27/27 pass
R9  test suite:  39/39 pass
LOCAL-40 tests:  13/13 pass
```

---

## Invariants

- `audio_tours`: **138** (unchanged)
- Nice list: `[1, 12, 14, 17, 21, 24, 27, 28, 29, 152]` (unchanged)
- No container rebuilt
- `DISABLE_R10_DELETION=1` flag wired and tested
- `git status --short`: clean

---

## R9/R10 distinction (kept verbatim from v1)

- **R9** checks absence of specifics plus presence of filler ("can be placed in millions of stops")
- **R10** checks presence of promise plus absence of on-topic delivery ("names something then doesn't follow up")

These are complementary: R9 catches generic sentences that never name anything
worth substantiating; R10 catches sentences that DO name something but fail to
deliver on it.

---

## Limitations

1. **Topic matching is lexical, not semantic.** "The ancient fortification"
   does not share a word with "walls holding a story" even though they're about
   the same thing. Synonyms are not resolved. This is an inherent limitation of
   a deterministic, $0-cost rule. An honest partial rule beats one that passes
   on synthetic context.

2. **The 4-char prefix stemming is crude.** It handles "wall"/"walls" and
   "village"/"villages" but would incorrectly match "carpet"/"carpe" if such
   cases arose. In practice the tour corpus doesn't produce such false matches.

3. **Tour 180 exceeds 1/3 deletion.** This is flagged, not suppressed. The
   emptied-paragraph guard is in place but the decision on whether to delete
   that many sentences is Michael's.

4. **R10 is more aggressive on cycling tours (6.9%) than museum tours (1.0%).**
   Museum tours tend to name specific artworks and artists (self-delivering).
   Cycling tours tend to describe landscapes abstractly.
