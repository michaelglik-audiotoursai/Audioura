##### READY FOR REVIEW

# SUBMISSION_LOCAL-98.md — Facts Survive Into Prose

**Branch:** `kiro/local98-facts-survive-into-prose`  
**Base:** `storied` @ `d3fc76f`

## Per-file changes

| File | Lines | Description |
|------|-------|-------------|
| `generate_tour_text.py` | +115/−37 | Three changes: (1) relocate binding block from mid-prompt to FINAL position (recency bias); (2) fix `_specificity_short` collision — stops with catalogue metadata never get 120-word "be SHORT" instruction; (3) fix post-gen validator to handle raw years + retry on missing facts + use primary material (not full comma list) |
| `tests/run_local98_evidence.py` | +230 (new) | Evidence runner: 3× N=8 generation + per-stop fact-presence check |
| `local98_evidence.json` | +60 (new) | Structured evidence output from the 3 runs |

## Diagnosis — why the binding instruction was ignored

### The assembled prompt for Stop 3 (La danse cosmique de Ganesh) — BEFORE fix

The user message to GPT-3.5-turbo contained (in order):

```
1. STYLE: [story-type tone instruction]
2. NARRATIVE SPINE CONTEXT (emotional beat, unique angle, callbacks)
3. THEME THREAD CONTEXT (cross-stop connections)
4. VERIFIED FACTS (confirmed_facts from fact_sheet)
5. ──── CATALOGUE RECORD FOR THIS SPECIFIC WORK ────
   DATE/PERIOD: Xe siècle
     → You MUST state this date. Say "Xe siècle" or its English equivalent.
   MATERIAL: chlorite
     → You MUST mention "chlorite" in the description.
   ──── END CATALOGUE RECORD ────
   HARD RULES: 1. The DATE/PERIOD above is the ONLY correct date...
6. DOCUMENTED FACTS FOR THIS WORK (incorporate at least one)
7. STORY ELEMENTS (B6 per-status wiring)
8. CRITICAL CONSTRAINT (venue containment)
9. EXHIBITION VS OBJECT RULE (critical — prevents fabrication)
10. THIN-CORPUS HONESTY RULE (critical — prevents fabrication)
    "Write EXACTLY 120 words (NOT 300). You have very limited verified information..."
    "Be honest and concise: describe only what you can confirm..."
    "Brevity with real content is better than length with filler."
11. BANNED PHRASES list
12. UNEARNED ADJECTIVES list
13. FACTUAL INTEGRITY RULE
14. Format instructions: "Write a flowing, 120-word narrative..."
15. LENGTH CONSTRAINT: "Write EXACTLY 120 words..."
```

### Two simultaneous failures

**Failure 1: Burial.** The binding block (item 5) is followed by 600+ words of competing instructions (items 6–15). GPT-3.5-turbo exhibits well-documented recency bias — instructions near the END of the user message dominate. The binding is 70% through the prompt; the format/length instructions are at 100%.

**Failure 2: Collision with brevity rule.** The THIN-CORPUS HONESTY RULE (item 10) told the model: "Write EXACTLY 120 words... Be honest and concise... do NOT pad." The model interpreted "date and material" as optional padding to be cut when keeping things brief. Result: generic iconography (4 arms, axe, rope) survived because it's general knowledge; "chlorite" and "Xe siècle" were dropped because they feel like catalogue specifics that add length without "honesty."

**Failure 3 (Grant's "1879" → "late 19th century"): Validator gap.** The post-generation validator only handled century-format periods (via Roman numeral regex). Raw years like "1879" were never checked — `_century_match` returned None, so `_period_ok` stayed True. The model wrote "late 19th century" and the validator shrugged.

### The fix (three changes)

1. **Relocate binding to FINAL position.** The catalogue date/material requirements are now appended as the LAST instruction in the prompt, after all format/length/style rules. Header: "━━━ FINAL REQUIREMENT (non-negotiable — your description will be REJECTED if these are missing) ━━━". Explicit English target strings are provided (e.g., "second half of the 10th century" for "2nde moitié du Xe siècle").

2. **Fix the `_specificity_short` collision.** Previously, a stop could have catalogue metadata (period + material) but still receive the 120-word "be SHORT and FACTUAL" instruction if `fact_sheet.confirmed_facts < 2`. Now: `_specificity_short = (count < 2 and not _had_corpus and not _has_catalogue_metadata)`. Stops with structured catalogue data always get the normal 280-word target.

3. **Fix the post-generation validator.** (a) Handle raw years — `_year_match` path triggers retry if "1879" is absent. (b) Retry on ANY missing fact, not just wrong-century cross-contamination. (c) Use primary material (first in comma list) for both binding and validation — prevents asking the model to write "bois, bois laqué, laqué" verbatim.

## Three N=8 runs — evidence

All runs after fix applied to container (Docker cp + restart).

### Per-stop results

| Stop | Material expected | Period expected | Run 1 | Run 2 | Run 3 |
|------|-------------------|-----------------|-------|-------|-------|
| 1 L'Armure d'Andô Naoyuki | — | — | exempt | exempt | exempt |
| 2 Statue de Bouddha | schiste | — | ✓ mat | ✓ mat | ✓ mat |
| 3 La danse cosmique de Ganesh | chlorite | Xe siècle | ✓ both | ✓ both | ✓ both |
| 4 Kannon, bodhisattva compassion | — | XIIe siècle | ✓ date | ✓ date | ✓ date |
| 5 Ulysses Grant au Japon | — | 1879 | ✓ date | ✓ date | ✓ date |
| 6 Robe de prêtre taoïste | soie | XVIIIe siècle | ✓ both | ✓ both | ✓ both |
| 7 Kannon à mille bras | — | — | exempt | exempt | exempt |
| 8 Masque du vieillard kojô | bois | XVIe siècle | ✓ both | ✓ both | ✓ both |

### Summary

| Run | Passes (of 6 testable stops) | Distinct facts | Baseline comparison |
|-----|------------------------------|----------------|---------------------|
| 1 | **6/6** | 38 | was 3/8 |
| 2 | **6/6** | 38 | was 3/8 |
| 3 | **6/6** | 38 | was 4/8 |

Target ≥6: **MET** (all three runs at 6/6).

### Verbatim evidence — Stop 3 description (Run 3, representative)

> In the 10th century, the sculptor crafted "La danse cosmique de Ganesh" from chlorite, a choice that adds a unique luster to the piece. Ganesh, often associated with wisdom and intellect despite his appearance, is depicted here in a vibrant dance, embodying the essence of creation and renewal. His four arms each hold a significant object: an axe symbolizing detachment, a rope to guide devotees from illusion, a broken tusk for writing, and a sweetmeat as a reward for a disciplined life.

Both "10th century" (= Xe siècle) and "chlorite" appear in the opening sentence. Contrast with pre-fix where 2 of 3 runs had NEITHER.

### Verbatim evidence — Stop 5 description (Run 3, representative)

> In the year 1879, Chikanobu masterfully crafted a xylogravure on papier, employing a polychrome technique that brings vibrant colors to life. The print vividly depicts the reception at the imperial palace of the President of the United States, Ulysses Grant, and his wife during their visit to Japan.

"1879" appears explicitly. Pre-fix: the binding block said "You MUST state 1879" but the model wrote "late 19th century."

### Distinct facts

38 distinct facts across all 3 runs (stdev = 0). LOCAL-96 baseline was not measured with this exact counter, but THIN stops (which dominated) carried ≤2 verifiable facts each. 38 facts across 8 stops = ~4.75 per stop average, consistent with ADEQUATE-to-RICH classification.

## Constraints verified

- ⛔ No `DELETE FROM audio_tours` — row count 60 before and after all runs
- ✓ `tours-near/43.7009358/7.2683912?radius=50` returns `[1,12,14,17,21,24,27,28,29]`
- ✓ No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md
- ✓ Each run completes in ~30s, cost ~$0.065 (under $1.30 ceiling)
- ✓ `practical_facts_gate` and fabrication guards untouched
- ✓ Stop 7 remains exempt — genuinely no catalogue data

## Limitations

1. **Orchestrator wipes coordinates on regeneration.** The tour generator returns `coordinates: [None, None]` for museum tours (all stops share one address), so `store_audio_tour` UPDATEs tour 21 with NULL lat/lng. This is a pre-existing behavior unrelated to this fix. Coordinates were manually restored after evidence runs. A proper fix would be: don't overwrite lat/lng with NULL when coordinates are missing from the generator response.

2. **Stop 1 is exempt because its catalogue metadata (acier, cuivre, cuir, soie, laque) arrives via a different path.** The evidence_log entry's method is `canonical_title_match` (not `catalogue_work`), so `_c51_material` is empty and no binding fires. The stop nonetheless includes rich material mentions from the STORY ELEMENTS (B6) path. Not a regression — same as pre-fix behavior.

3. **Post-gen patch still fires occasionally.** When the model's first attempt omits the fact despite the final binding, the retry catches it. In Docker logs, Stop 2 (schiste) occasionally needs a patch rather than organic inclusion. The fact still reaches the prose — just via patch instead of the model's own compliance.

4. **Distinct facts counter is approximate.** It counts materials, dates, people, and techniques via regex — not a perfect measure of "verifiable claims." The number 38 should be compared against future runs using the same counter, not against LOCAL-96's manual classification.

5. **"Vibrant colors" persists in some descriptions** (Stop 5 uses it despite the banned-phrases rule). This is a pre-existing GPT-3.5-turbo compliance issue with the banned-phrases list, not introduced by this fix.
