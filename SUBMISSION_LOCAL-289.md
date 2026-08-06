##### READY FOR REVIEW

## LOCAL-289: Degrade path removes whole governed construction

**Commit:** `6f61b1f`  
**Branch:** `kiro/local289-degrade-path-stubs`  
**Base:** `storied`

---

### Per-file summary

| File | Change |
|------|--------|
| `unglossed_reference_gate.py` | Rewrote `_degrade_reference_in_text` to excise the whole governed construction (possessives, prep phrases, appositives, hyphenated prefixes). Added 6 mechanical guards + `validate_and_repair_full_text()` as full-text safety net. |
| `tests/test_local289_degrade_path.py` | 40 new tests: possessive handling (4), stacked preps (4), dangling articles (3), empty appositives (2), sentence-drop fallback (2), degrade guards (6), full-text validation (5), validate+repair (2), bug report examples (5), prose-read regressions (6). |
| `run_local289_generation.py` | Generation script: 3 tours (2-stop Riviera, 8-stop Riviera, 5-stop museum), D141 cleanup, full degrade guard reporting. |

---

### Degradation report

**2-stop Riviera** (1 degradation):
- `Cap Ferrat` → DEGRADED (name dropped)
  - Before: "The Cap d'Antibes, along with the nearby [Cap Ferrat] forms one of the major landforms..."
  - After: Sentence dropped by guard (orphan adjective: "the nearby forms")

**8-stop Riviera** (3 degradations):
- `Remarkable Gardens` → DEGRADED
  - Before: "the gardens are designated as Remarkable Gardens of France, featuring fountains"
  - After: Sentence dropped by guard (stacked prep: "as of")
- `Via Julia Augusta` → DEGRADED
  - Before: "Built on Via Julia Augusta, it marks the triumph..."
  - After: Sentence dropped by guard (stacked prep: "on it marks")
- `Antonine Itinerary` → DEGRADED
  - Before: sentence contained reference
  - After: excised cleanly, sentence passed all guards

**5-stop Museum** (3 degradations):
- `Musée des Arts Asiatiques` → DEGRADED (excised cleanly)
- `Yves Trémois` (×2) → DEGRADED
  - Before: "Pierre-Yves Trémois envisioned these landscapes..."
  - After: Sentence dropped by guard (orphan hyphen: "Pierre- ")

**Total sentences dropped by guard:** 5 across 3 tours  
**Total degrade violations in delivered text:** 0

---

### Five guards — explicit check over full tour text

| Guard | riviera_2stop | riviera_8stop | museum_5stop |
|-------|:---:|:---:|:---:|
| Bare possessive (`\s's\b`) | ✓ CLEAN | ✓ CLEAN | ✓ CLEAN |
| Stacked prepositions | ✓ CLEAN | ✓ CLEAN | ✓ CLEAN |
| Sentence ending in func word | ✓ CLEAN | ✓ CLEAN | ✓ CLEAN |
| Empty appositive (`, ,` / `, .`) | ✓ CLEAN | ✓ CLEAN | ✓ CLEAN |
| Double space | ✓ CLEAN | ✓ CLEAN | ✓ CLEAN |
| Orphan hyphen | ✓ CLEAN | ✓ CLEAN | ✓ CLEAN |

---

### Composition path untouched

Verified by running all 28 existing LOCAL-287 tests (`test_local287_gloss_composition.py`) — all pass. Functions `compose_glosses()` and `_host_sentence_already_explains()` have zero diff.

---

### Test results

```
96 passed in 0.13s
```

- `test_local289_degrade_path.py`: 40 passed
- `test_local287_gloss_composition.py`: 28 passed  
- `test_local269_unglossed_reference_gate.py`: 28 passed

---

### Tours delivered

```
/Users/micha/Audioura/tours/LOCAL289_riviera_2stop_round35.txt   (623 words → 603 after repair)
/Users/micha/Audioura/tours/LOCAL289_riviera_8stop_round35.txt   (2477 words → 2431 after repair)
/Users/micha/Audioura/tours/LOCAL289_museum_5stop_round35.txt    (1282 words → 1237 after repair)
```

---

### Database state

```
[PRE]  Nice list: [1, 12, 14, 17, 24, 29, 152] ✓
[POST] Nice list: [1, 12, 14, 17, 24, 29, 152] ✓
```

No container rebuilt. Total generation cost: ~$0.46.

---

### Limitations

1. **Detection scope:** The entity detector (`_PERSON_PATTERN`) finds "Yves Trémois" not "Pierre-Yves Trémois" because the regex doesn't handle hyphens in first names. The fix handles this at degrade time (extends backward past hyphen), but ideally the detector should capture the full name.

2. **Gloss composition redundancy:** Some glosses from `compose_glosses()` repeat information already present in the sentence (e.g., Eze Village stop has "House of Savoy, who fortified the town strategically, recognized Èze's strategic importance, fortifying it as a stronghold"). This is a composition issue from the untouched path — the gloss source fact is the same content the sentence already uses. Not addressed here per scope constraints.

3. **Guard coverage:** The guards are pattern-based, not grammatical. A sentence could have a semantic gap (missing subject, orphan clause) that isn't one of the 6 patterns. The sentence-drop fallback catches the known patterns; novel patterns require new guards.

4. **Orphan adjective guard** is narrow: only catches "the nearby [verb]". Other adjective-without-noun patterns (e.g., "the famous features...") would need a broader rule.
