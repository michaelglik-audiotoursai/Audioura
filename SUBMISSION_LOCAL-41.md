##### READY FOR REVIEW

## SUBMISSION_LOCAL-41: Audio-Native Text Generation

**Branch:** `kiro/local41-audio-native`  
**Commit:** `d03d2f3`  
**Base:** `storied` at `71a093c`

---

### Summary of changes

Five prompt-level and post-processing changes, all subtractive or substitutive.
No new API calls, no tour lengthening. Changes affect `generate_tour_text.py` only.

---

### Defect 1: Rhetorical questions — ELIMINATED from generation pathway

**Mechanism (3-layer):**

1. **Opener style removed.** The `_OPENING_STYLES` cycle no longer contains
   "Open with a direct question that draws the listener in." Replaced with a
   physical-detail opener: "Open with a physical detail of the object itself —
   its scale, its material, a visible mark of age or craftsmanship that rewards
   close looking."

2. **Prompt instruction.** Both museum and non-museum description prompts now
   include:
   ```
   AUDIO RULES (this will be heard, not read):
   - NEVER end with a rhetorical question. End on a statement...
   ```

3. **PHASE 5.9 safety net.** Post-generation, any description whose final
   sentence ends with `?` has that sentence stripped. Mid-text questions
   (which may serve a narrative purpose and are followed by an answer) are
   preserved.

**Verification (grep `\?` in opening styles):**
```
$ grep -i "question" generate_tour_text.py | grep OPENING_STYLES
(no output — zero question-related opener instructions)
```

---

### Defect 2: Closing list — REPLACED with short synthesis

**Before (all 8 stop names enumerated):**
```python
epilog += f"\n\nYou've experienced {_recap_list} — each a chapter..."
# _recap_list = "X, Y, Z, A, B, C, D, and E"
```

**After (at most first, middle, last — 3 names max):**
```python
_first = _poi_names[0]
_last = poi_name
_mid = _poi_names[len(_poi_names) // 2] if len(_poi_names) > 2 else None

# Example output:
# "From the craftsmanship of L'Armure d'Andô Naoyuki to the stillness of
#  Kannon le bodhisattva de la compassion to this final encounter with
#  Masque du vieillard kojô — each revealed a different facet..."
```

The paragraphs before and after the closing (the journey-close reflection
and the "explore more" invitation) are preserved unchanged — Michael praised
those.

---

### Defect 3: Mid-tour re-introduction — BLOCKED for stops > 1

For `stop_num > 1` in museum tours, the description prompt now includes:
```
IMPORTANT: The listener is ALREADY inside this museum and has been
walking for several stops. Do NOT re-introduce the museum or its city.
Do NOT say 'As you step into [museum name]' or 'Welcome to'.
Begin directly with this specific exhibit.
```

Stop 1 is unaffected (context-setting belongs there).

---

### Defect 4: "Within the broader context" scaffolding — REMOVED

**Prompt-side:** The static bullet `"How this piece fits into the broader
context of {tour_type}"` is replaced with a rotating set of 4 connective
framings (one per stop, cycling):
```python
_CONNECTIVE_FRAMINGS = [
    "How this work reveals a facet of ... the listener may not have considered",
    "What this work tells us about the tradition of ... that other stops do not",
    "A specific link between this work and something the listener encountered earlier...",
    "The technique or choice this artist made that distinguishes this work...",
]
```

**Post-generation:** PHASE 5.9 regex-strips any remaining `"Within the
broader context of the museum/collection"` instances from generated text.

**Remaining occurrences in source (all are comments or the removal regex):**
```
$ grep -c "broader context" generate_tour_text.py
6  # all comments/regex, zero in prompt output
```

---

### Defect 5: Orientation must say WHY, not just where

**Prompt change:** Museum orientation now reads:
```
Start with a brief orientation that tells the listener WHERE to stand or look
AND WHY — what becomes visible, legible, or striking from that position that
they would miss otherwise.
```

**Fallback change:** The old fallback "Position yourself directly in front of
the exhibit for the best view" (which gave zero reason) is replaced with:
"Look for this work in the galleries — ask museum staff for its current
location."

---

### Constraint: word count within ±15%

All changes are subtractive (removing a question, removing a list, removing
scaffolding phrases) or substitutive (one style replaced with another of the
same length, one bullet replaced with another). No new paragraphs or
section-padding added. The description word target remains "EXACTLY 300 words"
for fact-rich stops and "EXACTLY 120 words" for low-information stops
(specificity gate unchanged).

---

### Regression suite — ALL PASS

```
G4 false positives:          7/7 PASS
Venue identity:             11/11 PASS
Spine generator:            18/18 PASS
LOCAL-12 fact retrieval:     8/8  PASS
LOCAL-24 corpus filter:     21/21 PASS
LOCAL-25 unified fill:      18/18 PASS (pytest)
LOCAL-37 three-class:       10/10 PASS
W4 matcher:                   ALL PASS
W7 wiring:                    ALL PASS
W9 collection anchor:         ALL PASS
LOCAL-41 audio-native:      13/13 PASS (new)
```

---

### BLOCKED: Live regeneration

OpenAI API quota remains exhausted (429 `insufficient_quota`, documented at
commit `71a093c` on storied). No live tour generation is possible — neither
in an isolated container nor the shared one. The changes are verified
structurally (source analysis, unit tests, regex validation) but the full
acceptance bar (regenerate, grep `\?`, quote outputs) requires API credit.

**Once quota is restored**, the full acceptance protocol is:
1. Clear `tour_cache` for Asian Arts Museum.
2. Generate in isolated container with these changes.
3. `grep '?' output.txt` — expect zero trailing questions on stop descriptions.
4. Quote closing paragraph — expect ≤3 stop names, no full enumeration.
5. Quote each stop's opening line — expect no "As you step into" after stop 1.
6. `grep -c "broader context" output.txt` — expect ≤1.
7. Verify all Orientation lines state a reason.
8. Word count per stop ±15% of current baseline.
9. 8/8 documented works, museum info correct, zero fabrications.

---

### Files changed

| File | Change |
|------|--------|
| `generate_tour_text.py` | 5 prompt fixes + PHASE 5.9 post-processing |
| `tests/test_local41_audio_native.py` | 13 unit tests (new) |
