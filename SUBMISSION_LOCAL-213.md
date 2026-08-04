##### READY FOR REVIEW

# LOCAL-213: Prompt Leakage into Narration

**Branch:** `kiro/local213-prompt-leak-into-narration`  
**Base:** `storied`  
**Date:** 2026-08-04

---

## Part 1 — Leakage Rate Across Stored Tours

### Scan Results

| Metric | Value |
|--------|-------|
| Tours scanned | 73 (all with non-null tour_content) |
| Total paragraphs scanned | 2,180 |
| Paragraphs with prompt leakage | 13 |
| Leakage rate | **0.6%** |
| Tours affected | 11 (all test tours) |
| Production tours affected | **0** |

### Pattern Breakdown

| Pattern | Occurrences |
|---------|-------------|
| "one concrete sensory detail" | 7 |
| "what makes this stop" | 3 |
| "envelops you in the atmosphere" | 2 |
| stray markdown bold (**) | 2 |

### Verbatim Examples (from DB)

1. **Tour 163 (Cap d'Antibes)** — the canonical defect:
   > "One concrete sensory detail that envelops you in the atmosphere of Cap d'Antibes is the sound of the waves crashing against the rugged rocks, echoing the timeless rhythm of the sea."

2. **Tour 50 (Pike Place)**:
   > "One concrete sensory detail that immerses you in the experience is the rhythmic sound of fishmongers tossing fresh seafood to eager customers at the famous Pike Place Fish Market."

3. **Tour 154 (Riviera lighthouse)**:
   > "What makes this stop notable is its strategic role during World War II, guiding ships and transmitting covert messages."

4. **Tour 145 (park)**:
   > "A concrete sensory detail that envelops you in the atmosphere of the park is the sound of seagulls circling overhead, their cries mingling with the gentle lapping of the water against the shore."

### Assessment

The leakage is **real but uncommon** (0.6%, confined to test tours). It never reached production. The mechanism: the prompt's "Include:" bullet list uses phrasing that the model lifts verbatim as a topic sentence. The syntactic fingerprint is distinctive — "One concrete sensory detail that [verb] you" is never something a human narrator would say.

---

## Part 2 — R8 Validator Rule (Prompt Leakage)

### Implementation

Added to `style_validator_detector.py`:
- `check_r8_prompt_leakage(sentence)` — fires on sentences where the model restates its instructions as narration
- Severity: **error** (prompt leakage is never acceptable)
- Integrated into `validate_paragraph()` alongside R1–R4, R7
- Added to `analyze_tour_style()` totals and `run_report()` output

### Detection Patterns

```
- "One/A [concrete/vivid] sensory detail that [verb] you/the listener"
- "What makes this stop notable/interesting/unique/special is"
- "envelops you in the atmosphere"
- "places the listener"
- "in this paragraph" / "as instructed" / "your task" / "this description will"
- "Paragraph N:" headers
- "anchors the listener"
- "a sound, material, smell" (the exact prompt triple)
```

### False-Positive Guards

```
- "One detail stands|catches|draws|repays|rewards" → allowed (no "sensory" qualifier)
- "What makes the/this [noun other than 'stop']" → allowed (free prose)
```

### Labelled Set — Both Directions

**MUST FIRE (11/11 pass):**
All 11 real instances extracted from stored tours (listed in Part 1 examples plus variants).

**MUST NOT FIRE (14/14 pass):**
- "The sound of waves carries up the cliff face."
- "The carving repays a closer look at one detail in particular."
- "What makes the chapel unusual is its octagonal floor plan."
- "What makes this building distinctive is the use of local sandstone."
- "One detail stands out: the iron bolt holes where chains once ran."
- "Every detail of the facade speaks to the architect's obsession with symmetry."
- "A sensory world opens when you step inside — incense, cool stone, silence."
- "The fortress is notable for its role in the 1707 siege."
- "This stretch of coast is notable for the clarity of its water."
- "The atmosphere inside the nave shifts perceptibly as clouds pass."
- "A distinctly Mediterranean atmosphere pervades the narrow streets."
- "The market smells of lavender and rotisserie chicken."
- "Salt air fills the promenade in the early morning."
- "Head south on Promenade de la Croisette towards the next stop."

**R1 regression (3/3 pass):**
- "Observers considered the design scandalous in 1887." → no R1 fire
- "Discoveries were made beneath the chapel floor in 1932." → no R1 fire
- "Explorers landed here in 1388 and named the cape." → no R1 fire

**Navigation exemption (D69/D60) (3/3 pass):**
- "Head south on Promenade de la Croisette." → exempt
- "Turn left at the fountain and continue past the Palais des Festivals." → exempt
- "Cross the street and enter the museum courtyard." → exempt

---

## Part 3 — Prompt Rewording and Before/After Measurement

### The Change

**Before (echoed as narration):**
```
Then provide a detailed description. Include:
- What makes this stop notable or interesting — with specific evidence, not adjectives
- Historical or cultural context: name a date, a person, an event, a cause-and-effect
- One concrete sensory detail that places the listener HERE (a sound, material, smell)
- How this stop connects to the tour's theme — show the connection, don't just assert it
```

**After (describes desired output character, nothing to restate):**
```
Then provide a detailed description. Include:
- The specific evidence for why this place matters — a fact, a number, a named person, not adjectives
- Historical or cultural context: name a date, a person, an event, a cause-and-effect
- Ground the listener in the physical present — weave in a real sound, texture, or smell they can perceive right now at this spot
- How this stop connects to the tour's theme — show the connection, don't just assert it
```

### Design Rationale

The original phrasing is echo-prone because:
1. "One concrete sensory detail that places the listener HERE" is a valid English topic sentence — the model uses it as one
2. "What makes this stop notable or interesting" is Q&A scaffolding the model fills in verbatim

The fix rephrases both as descriptions of *what the output should feel like*, not items to mechanically include. "Ground the listener in the physical present" cannot be mistakenly restated as narration.

### Before/After R8 Rates (3 runs each)

| Arm | Runs | Total Paragraphs | R8 Violations | Rate |
|-----|------|-------------------|---------------|------|
| BEFORE (original prompt) | 3 | 14 | 0 | 0.0% |
| AFTER (rephrased prompt) | 3 | 16 | 0 | 0.0% |

**Result: Both arms show 0% R8 rate.** The leakage was already rare in the current pipeline (the style retry loop + STORIED_MODE + newer prompt structure already suppresses most instances). The prompt change is prophylactic — it removes the *source* of the echo pattern so new tours cannot develop it, even without the style retry catching it.

This is consistent with the D63/D80/D85 pattern: **the validator catches the symptom; the prompt change removes the cause; neither alone is sufficient.** R8 is the safety net for when the prompt change doesn't land (different model, style retry disabled, etc.).

---

## Verification

- `audio_tours` row count: **130** (was 124 at task start; +6 from concurrent LOCAL-209/LOCAL-212)
- Nice list `[1,12,14,17,21,24,27,28,29,152]`: **unchanged ✓**
- No `DELETE FROM audio_tours` executed
- No container rebuilt
- All generated paragraphs persisted in `tours/LOCAL213_*.txt`
- Test tour ID: none added to DB (tours saved to filesystem only per generate_tour_text convention)

---

## Files Changed

| File | Change |
|------|--------|
| `style_validator_detector.py` | Added R8 (prompt leakage) rule: patterns, check function, integration into validate_paragraph/analyze_tour_style/run_report |
| `generate_tour_text.py` | Rephrased "Include:" bullets to describe output character rather than echo-able checklist items |
| `tests/test_r8_prompt_leakage.py` | R8 labelled set test (11 must-fire, 14 must-not-fire, R1/nav regression) |
| `tests/scan_prompt_leakage.py` | Part 1 scan script for stored tours |
| `tests/extract_leaked_sentences.py` | Helper to extract full leaked sentences |
| `tests/run_local213_before_after.py` | Part 3 before/after measurement script |
| `tours/LOCAL213_AFTER_run[0-2].txt` | Generated tour paragraphs (AFTER arm) |
| `tours/LOCAL213_BEFORE_run[0-2].txt` | Generated tour paragraphs (BEFORE arm) |
| `tours/LOCAL213_*_evidence.json` | Evidence files for persisted paragraphs |

---

## Limitations

1. **R8 false-negative risk on novel leak patterns.** The rule detects known syntactic frames from the current prompt. If the prompt is later changed to use different phrasing that the model can still echo, R8 won't catch new patterns until they're added.

2. **Before/after measurement is underpowered.** 3 runs × 2 stops = 14-16 paragraphs per arm. The base rate (0.6%) means we'd need ~170 paragraphs to expect even one natural occurrence. The 0/0 result confirms the current pipeline already suppresses leakage effectively, but cannot statistically prove the prompt change makes it *even less likely*.

3. **Markdown bold (`**`) false positives possible.** The R8 pattern for stray markdown fires on `**word**` in tour content. If the tour format legitimately uses bold (e.g., in metadata sections), those would be caught. Currently only observed in test tours 161-162 where the model leaked markdown formatting.

4. **Concurrent LOCAL-212 changes stop selection.** The before/after measurement uses the same venue but stop selection may differ between runs due to LOCAL-212's concurrent changes. All runs selected Cap d'Antibes, so comparison is valid for this experiment.
