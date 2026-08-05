##### READY FOR REVIEW

## LOCAL-259: Four-Part Prolog Structure

**Commit:** `8e83471`
**Branch:** kiro/local259-prolog-four-part

---

### Summary of Changes

| File | Change |
|---|---|
| `generate_tour_text.py` | Replaced prolog prompt (lines ~7148-7284) with four-part structure per Michael's specification from `Review_on_RIVIERA_2STOP_ROUND2.txt`. Computes distance from coordinates, extracts sourced facts from `_stop_corpus_data`, names specific stop content for Part 4. |
| `run_round16.py` | Run script: generates 2-stop French Riviera cycling tour with all gates on, produces RIVIERA_2STOP_ROUND16.md with labelled prolog |
| `RIVIERA_2STOP_ROUND16.md` | Round 16 artifact with four-part prolog labelled, fact tallies, and full tour content |

---

### What Was Done

Michael specified the tour opening must have four parts in sequence:
1. Tour name + transport mode
2. Route physicality (endpoints, distance, terrain)
3. Purpose/intrigue (sourced facts, causal or thematic)
4. Forward connection (names specific stop content, not vague promises)

This was written in `Review_on_RIVIERA_2STOP_ROUND2.txt` and noted as unimplemented in LOCAL-244.

**Implementation:** The prolog LLM prompt was rewritten to:
- Compute straight-line distance between stops from their coordinates (`_haversine_km`)
- Use `transport_mode` (already in scope from LOCAL-253)
- Extract factual sentences from `_stop_corpus_data` (dates, proper nouns + verbs)
- Pull `_story_elements` for additional grounding
- Feed stop arc previews from the spine for Part 4

The prolog still passes through LOCAL-244's PHASE 5.9 gates (R9, R10, subject routine) — no bypass added.

---

### Evidence

#### Prolog text (from RIVIERA_2STOP_ROUND16.md)

> You are about to embark on a cycling journey through the French Riviera. This route will take you from the opulent Cap d'Antibes to the ancient Eze Village, spanning approximately 28 kilometers of coastal terrain. The path winds through a landscape where artists like Monet found inspiration and where historical events shaped the region's identity. Claude Monet's artistic exploration in Antibes and Eze Village's strategic significance under the House of Savoy are testaments to the intertwined legacies of art and power in the French Riviera. In the stops ahead, you will encounter Monet's 1888 paintings at Cap d'Antibes and the 1706 destruction of Eze Village's fortifications during the War of the Spanish Succession.

Word count: 113

#### Four-part checklist

| Part | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Tour name + transport | ✓ | "cycling journey through the French Riviera" |
| 2 | Endpoints, distance, terrain | ✓ | "from...Cap d'Antibes to...Eze Village, spanning approximately 28 kilometers of coastal terrain" |
| 3 | Sourced facts, causal/thematic | ✓ | "Claude Monet's artistic exploration in Antibes and Eze Village's strategic significance under the House of Savoy" — both from stop_corpus |
| 4 | Names specific stop content | ✓ | "Monet's 1888 paintings at Cap d'Antibes and the 1706 destruction of Eze Village's fortifications during the War of the Spanish Succession" |

#### Fact sourcing for prolog claims

| Claim in prolog | Source |
|---|---|
| "28 kilometers" | Computed: haversine((43.5411, 7.1356), (43.7296, 7.3616)) = 27.5 km ≈ 28 km |
| "cycling" | `transport_mode = 'bike'` detected from "cycling tour" in location string |
| "Monet's 1888 paintings" | stop_corpus for Cap d'Antibes: "In January 1888, Claude Monet painted..." |
| "House of Savoy" | stop_corpus for Eze Village: "By 1388, Èze came under the control of the House of Savoy" |
| "1706 destruction...War of the Spanish Succession" | stop_corpus for Eze Village: "in 1706, Louis XIV ordered the destruction of the castle and walls during the War of the Spanish Succession" |

#### Part 4 discharge verification

Part 4 promises: "Monet's 1888 paintings at Cap d'Antibes" and "the 1706 destruction of Eze Village's fortifications."

- Stop 1 (Cap d'Antibes) delivers: "In 1888, Claude Monet first experimented with painting in series in this very region, producing masterpieces like 'Morning at Antibes.'" ✓
- Stop 2 (Eze Village) delivers: "later ravaged by Louis XIV during the War of the Spanish Succession in 1706" ✓

Both promises discharged by the tour itself.

#### Gates applied to prolog (LOCAL-244 PHASE 5.9)

From generation log:
- R9 generic-sentence deletion: applied (0 deletions in final run)
- R10 unfulfilled-promise deletion: applied (1 deletion in first run — removed "Explore these sites to uncover tales...")
- Subject routine: applied (enabled, 0 expanded/deleted in final run)

No bypass added. Prolog runs through identical gates as stop descriptions.

#### Fact tally per stop

- **Cap d'Antibes**: 5 facts (round 15 had 2)
- **Eze Village**: 6 facts (round 15 had 7)

#### Row counts

- audio_tours before: 142
- audio_tours after: 142 (delta: 0)
- Nice list: `[1, 12, 14, 17, 24, 29, 152]` — UNCHANGED

#### Cost

- Total: $0.0096 (under $0.60 ceiling)

---

### Constraints Observed

- ⚠️ No container rebuilds (D48) ✓
- ⚠️ No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, .continuous_dev/* ✓
- ⚠️ No edits to style_validator_detector.py (LOCAL-257 in progress) ✓
- ⚠️ Ceiling $0.60 — actual cost $0.0096 ✓
- ⚠️ No hardcoded credentials — uses `os.environ` ✓
- ⚠️ Test tour: `is_test=true`, cleanup by captured id confirmed ✓
- ⚠️ `git status --short` clean after commit ✓

---

### Limitations

1. **Part 3 quality is model-dependent.** When the corpus supports a causal chain (e.g., sheltered shoreline → luxury hotel → Fitzgerald novel → Monet painting), the LLM may or may not build it. The prompt instructs it to, but the fallback ("write the plainest true version — two sourced facts without manufacturing a connection") fires more often than the causal chain does. This is by design: a false causal claim is worse than a plain one.

2. **"Opulent" and "ancient" in Part 2 are unsourced adjectives.** These are evaluative rather than factual (they don't claim a specific date or event), so they don't violate the grounding constraint, but they lean toward the filler language Michael has flagged in other contexts. A future tightening could add "no evaluative adjectives" to the constraints.

3. **Stop selection is non-deterministic.** Multiple runs may produce different stop pairs (the first run gave Mont Boron instead of Eze Village). The prolog adapts correctly to whatever stops are selected — computing distance and extracting corpus facts for the actual stops in the tour.

4. **113 words (inside 100-180 range but not the full 190).** The LLM tends toward concision with the strong constraint set. Not a defect — Michael's examples were 60-80 words total across all four parts.
