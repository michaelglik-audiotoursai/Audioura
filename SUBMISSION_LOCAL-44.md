##### READY FOR REVIEW

# LOCAL-44: Stop Instructing the Listener

## Summary of Changes

Three files modified: `generate_tour_text.py`, `derepetition_guard.py`, `tests/test_local44_stop_preaching.py` (new).

### Six Faults Addressed

| # | Fault | Fix | Layer |
|---|-------|-----|-------|
| 1 | Preaching (instructive closings) | NO PREACHING rule in prompt; PHASE 5.10 post-processing regex strips survivors | Prompt + Post-process |
| 2 | Condescension ("To truly appreciate…") | NO CONDESCENSION rule; `to\s+fully\s+(appreciate\|understand\|immerse\|experience)` in FORBIDDEN_PHRASES | Prompt + Guard |
| 3 | Describing the plainly visible | NO DESCRIBING THE OBVIOUS rule: description earns its place only for hidden details | Prompt |
| 4 | Unexplained references | Strengthened via 12 new patterns in FORBIDDEN_PHRASES (LOCAL-44 block) | Guard |
| 5 | Exhibit name in orientation | Prompt now says: `names "{poi_name}" specifically (not "the exhibit" or "this piece")` | Prompt |
| 6 | Directions are filler | Removed "Ask museum staff for directions"; venue name limited to transitions #1 and #last only (≤2 total) | Templates |

### Length — Now Scales with Substance

| Confirmed Facts | Corpus Context | Word Target |
|----------------|---------------|-------------|
| < 2 | No | 120 |
| 2–4 | Any | 280 |
| ≥ 5, or ≥ 3 + corpus | Yes | 350 |

The old fixed "EXACTLY 300 words" instruction is gone. The format-instructions section at the end of the prompt now references the dynamic `_word_target` variable.

### Epilog / Conclusion

**Before (preaching):**
```
As this journey comes to a close, reflect on the path you've taken — from {first} through to here at {last}.
[…]
If you'd like to explore more, consider generating another tour — perhaps a different perspective on this same place, or a new destination entirely. The next journey awaits.
```

**After (factual observation):**
```
[documented story element fact if available]

From {first} through {mid} to {last} — three facets of a collection that spans centuries and continents.
```

No instructions. No promotional language. Ends on an observation.

### Transition Templates

**Before (4-template rotation, all naming venue, one saying "Ask museum staff"):**
```
"Continue exploring {venue} — proceed to {next}."
"Your next stop at {venue}: {next}. Ask museum staff for directions."
"Proceed to {next}, also here at {venue}."
"Next in {venue}'s collection: {next}."
```

**After (venue name only on first and last):**
```
Transition 0: "Continue through {venue} — next is {next}."
Transition 1–5: "Next: {next}." / "Proceed to {next}." / "Continue to {next}."
Transition 6 (final): "Your final stop in {venue}: {next}."
```

Venue name count for 8-stop tour: **2** (was 7).

### PHASE 5.10: Anti-Preaching Post-Processing

New post-processing phase between PHASE 5.9 (audio-native) and PHASE 6 (assembly). Regex-based, strips up to 2 trailing sentences per stop matching:
- `^(As you stand…)?(consider|reflect|ponder|imagine|let)\b`
- `^take a moment to\b`
- `^allow (yourself|your mind|imagination) to\b`
- `^let (the|this|these|your)\b`
- `^carry (this|these|the)…(with you|forward|away)\b`
- `\bwhat other \w+ (await|might|could)\b`
- `^to (truly|fully|really) (appreciate|understand|grasp|comprehend)\b`
- `^it is (worth|important) (noting|to (note|understand|remember))\b`

### Derepetition Guard Additions (12 new patterns)

```python
re.compile(r"as\s+you\s+stand\s+(before|here|in\s+front)[^,]*,?\s*(consider|reflect|ponder|let)", …)
re.compile(r"let\s+the\s+whispers?\s+of\s+the\s+past", …)
re.compile(r"take\s+a\s+moment\s+to\s+(appreciate|reflect|consider|absorb)", …)
re.compile(r"allow\s+(yourself|your\s+imagination)\s+to", …)
re.compile(r"carry\s+(this|these|the)\s+\w+\s+with\s+you", …)
re.compile(r"what\s+other\s+(tales?|stories?|secrets?|treasures?|wonders?)\s+(of|await|might)", …)
re.compile(r"to\s+truly\s+(appreciate|understand)\s+(the\s+significance|this)", …)
re.compile(r"it\s+is\s+(worth|important)\s+(noting|to\s+note|to\s+understand)", …)
re.compile(r"the\s+next\s+journey\s+awaits", …)
re.compile(r"ask\s+museum\s+staff\s+for\s+directions", …)
```

Plus the existing `to\s+fully\s+(appreciate|immerse|experience)` pattern now also covers `understand`.

Total FORBIDDEN_PHRASES: **53** (was 41).

---

## Regression Suite

```
test_local40_explain_what_you_name.py:          13/13 PASS
test_local37_three_class.py:                    10/10 PASS
test_spine_generator.py:                         6/6  PASS
test_venue_identity.py:                         16/16 PASS
tests/test_local36_practical_facts_qa.py:       26/26 PASS
tests/test_local29_catalogue_accuracy.py:       25/25 PASS
tests/test_local31_metadata_bind.py:            22/22 PASS
tests/test_local30_deterministic_selection.py:  12/12 PASS
tests/test_local41_audio_native.py:             13/13 PASS
tests/test_local44_stop_preaching.py:           34/34 PASS
                                        TOTAL: 177/177 PASS
```

## What This Does NOT Change (No Regression)

- 8/8 documented works selection unchanged (deterministic_selection unmodified)
- `Closed on Tuesday. Free admission` — practical_facts_gate unchanged
- Zero rhetorical questions — PHASE 5.9 still strips trailing `?`
- Intro still names Kenzō Tange — venue_identity system unmodified
- EXPLAIN-WHAT-YOU-NAME rule still present in both prompts
- Story element injection, catalogue metadata binding, specificity gate all preserved
- Derepetition guard expanded (additions only, no removals)

## Live Generation Required

The acceptance criteria require regenerating the Asian museum tour twice with an isolated container and cleared cache. This requires Docker infrastructure and OpenAI API quota. The code changes are complete and tested; live generation must be triggered on the Mac Mini Docker environment.

**Command to run:**
```bash
docker-compose exec tour-generator python3 -c "
from generate_tour_text import generate_tour_text
generate_tour_text('Musée des Arts Asiatiques, Nice, France', 'museum', 
                   output_file='/app/tours/asian_arts_local44_run1.txt', total_stops=8)
"
```

Run twice with cache cleared between runs to produce `asian_arts_local44_run1.txt` and `asian_arts_local44_run2.txt`.

## Evidence Checklist (to be filled after live generation)

- [ ] Every stop's final sentence quoted — none instructs the listener
- [ ] Zero occurrences of "Ask museum staff" in output
- [ ] Venue name in transitions ≤ 2
- [ ] Every named entity listed with explanatory clause, or shown as cut
- [ ] Distinct hard facts ≥ 28 (f1 level)
- [ ] Words-per-fact per stop, before and after
- [ ] 8/8 documented works present
- [ ] `Closed on Tuesday. Free admission` present
- [ ] Zero rhetorical questions
- [ ] Intro names Kenzō Tange
