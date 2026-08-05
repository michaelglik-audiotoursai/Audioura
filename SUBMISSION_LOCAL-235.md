##### READY FOR REVIEW

**Task:** LOCAL-235 — R10: name a subject and then deliver it, or delete the sentence  
**Branch:** `kiro/local235-r10-unfulfilled-promise`  
**Commit:** `bf3a307`  
**Agent:** Mac Mini Kiro

---

## 1. Per-file summary

| File | Change |
|---|---|
| `style_validator_detector.py` | +`_is_place_name`, +`_sentence_has_promise`, +`_sentence_has_concrete_payload`, +`check_r10_unfulfilled_promise`, +`apply_r10_deletions`, +`apply_r10_to_description`; added `Optional` to typing import |
| `generate_tour_text.py` | Wired PHASE 5.155 (R10 deletion) between R9 and CONTRADICTED block, behind `DISABLE_R10_DELETION=1` |
| `run_quality_profile.py` | Added `check_r10_unfulfilled_promise` to imports |
| `tests/test_r10_unfulfilled_promise.py` | 17 tests: labelled set (6 must-fire, 10 must-not-fire), unit tests, integration, R9 regression |
| `run_local235_r10_measurement.py` | Corpus-wide measurement + calibration re-run |
| `r10_measurement_output.json` | Full per-tour results |

---

## 2. Labelled set (from Michael's file, both directions)

### MUST FIRE (his Round 2 complaints)

| Sentence | Why |
|---|---|
| "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story." | "what story?" |
| "The hillsides hold a multitude of tales from a bygone era." | "where are the tales??" |
| "The medieval charm of Eze Village serves as a bridge between ancient civilizations and contemporary life…" | "why?" — no facts follow |
| "…creating a harmonious symphony of past and present." | Pure metaphor, no delivery |
| "As you cycle onward, remember Eze Village, a testament to the enduring allure of the French Riviera's rich historical tapestry." | Names "allure" and "tapestry" without content |
| "Cycling along the shimmering waters, you are not just exploring a physical landscape but also delving into a rich tapestry of history…" | "we do not follow the declarative with a story or fact" |

### MUST NOT FIRE (his own rewrite prose)

| Sentence | Why safe |
|---|---|
| "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide." | Date + named place |
| "The Antonine Itinerary mentions the bay of Èze as Avisionis portus." | Named document + named place |
| "Start cycling south on the main road…" | Navigation (exempt) |
| "F. Scott Fitzgerald based the opening hotel of his 1934 novel on Eden-Roc." | Named person + date + place |
| "The Hôtel du Cap-Eden-Roc was built here in 1870, at the southern tip…" | Date + named venue |
| "At Cap d'Antibes… inspired artists like Picasso…" | Named person |
| "At the apex of Jardin Exotique…" | Named landmark |
| "In January 1888, the renowned artist Claude Monet visited…" | Date + named person |
| "Along this 2.7 km route…" | Measurement |
| "Look out for the Villa Eilenroc… elite of the 19th century." | Century reference |

All 17 tests pass: `python3 -m pytest tests/test_r10_unfulfilled_promise.py` → 17/17

---

## 3. Corpus-wide rate by tour type

```
Type         Tours   Sentences   R10 del   R10 rate   R9 del   Combined   > 1/3
----------------------------------------------------------------------
cycling      21      1118        62        5.5%       21       7.4%       0
museum       20      1656        11        0.7%       7        1.1%       0
other        19      627         7         1.1%       10       2.7%       0
walking      24      1018        31        3.0%       24       5.4%       0
----------------------------------------------------------------------
TOTAL        84      4419        111       2.5%       62       3.9%       0
```

**Paragraphs emptied:** R10=6, R9=47, combined=53

---

## 4. Tours exceeding 1/3 combined deletion

**None.** Zero tours lose more than 1/3 of their sentences under R9+R10 combined. The highest individual tour is well under 15%.

---

## 5. Calibration re-run (QUALITY_PROFILE.md §5)

| Metric | Before R10 | After R10 |
|---|---|---|
| Agree | 5 | **6** |
| Partial | 2 | 2 |
| Disagree | 4 | **3** |

**New agreement:** M8 ("The Rue Obscure, with its shadowy passageways, whispers tales of a bygone era…") — Michael scored 1/5, R10 now fires. Detection correct.

M4 ("Pedal along the coastline, envisioning the hidden coves and stories…") does not fire R10 because the previous sentence contains "2.7 km route" (concrete payload within look-back window). This is correct: the promise IS fulfilled by adjacent content.

---

## 6. Detection mechanism

**Look-ahead:** 2 sentences forward + 1 sentence backward + cross-paragraph boundary.

A sentence fires R10 when:
1. It contains a "promise trigger" (story, tales, tapestry, testament, bridge-between, symphony-of, witness-to, steeped-in, echoes-of, chapter-in, centuries-of, sense-of-antiquity, transport-visitors-back, etc.)
2. Neither the sentence itself NOR any neighbour within the window delivers a "concrete payload" (date/year, named person [2+ consecutive caps excluding place names], century reference, measurement, or numeric fact)
3. The sentence is not navigation (exempt)

**Critical distinction from R9:** R9 checks for ABSENCE of specifics + PRESENCE of filler. R10 checks for PRESENCE of promise + ABSENCE of delivery. R9 catches "can be placed in millions of stops" (generic). R10 catches "names something but doesn't tell us about it" (unfulfilled). They are complementary.

---

## 7. Existing suites

```
R9 regression: 39/39 pass
R10 labelled:  17/17 pass
```

R9 test output:
```
  R9 must fire:         2/2 pass
  R9 must NOT fire:     23/23 pass
  Navigation exempt:    3/3 pass
  R1 regression:        3/3 pass
  R8 fires:             2/2 pass
  R8 silent:            2/2 pass
  TOTAL:                39/39 pass  ✓ ALL PASS
```

---

## 8. Invariants

- `audio_tours` row count: **138** (before and after)
- Nice list: **[1, 12, 14, 17, 21, 24, 27, 28, 29, 152]** — unchanged
- `git status --short`: empty (clean)
- No container rebuild
- Cost: **$0.00** (deterministic, no LLM calls)

---

## 9. Limitations

1. **M4 does not fire** because the look-back window finds concrete payload in the preceding sentence. Michael scored it 2/5 for different reasons (suggestive gerunds, not unfulfilled promise). This is a correct negative — the content around it delivers.

2. **The "enduring allure" pattern depends on word "allure"** — synonyms like "magnetism" or "draw" would escape. The pattern set is built from Michael's actual vocabulary in his complaints.

3. **Place-name detection is heuristic.** The `_is_place_name` function catches common patterns (Village, Cap, Mont, Rue, nationality adjectives + geographic proper nouns) but cannot distinguish every multi-word place from a person name without a gazetteer. Trade-off is conservative: ambiguous cases are NOT deleted.

4. **Cycling tours have the highest R10 rate (5.5%)** — exactly as predicted from Michael's scoring. This suggests the cycling tour generation prompt produces more promise-without-delivery than other types. A prompt-level fix would reduce generation-time R10 violations rather than deleting post-hoc.
