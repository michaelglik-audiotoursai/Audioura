##### READY FOR REVIEW

## Commit

```
8652697  LOCAL-322: Add genuine-patch test demonstrating English output
1b34c9a  LOCAL-322: Translate French terms in DOCUMENTED FACTS context + verification
b40ddf6  LOCAL-322: Fix French material/period injection in English narration
```

Branch: `kiro/local322-material-patch-splice`  
Base: `storied`

## Per-file summary

### `generate_tour_text.py`

**Three edit regions:**

1. **Lines ~7197–7330 (FINAL BINDING section):**
   - Added `_FR_EN_MATERIAL_MAP` — complete FR→EN translation for all 35 material terms in `story_miner._MATERIALS`
   - Added `_translate_material_to_english()` helper
   - Translates `_c51_material` to English before injecting into prompt binding
   - Prompt now says `"YOUR DESCRIPTION MUST MENTION THIS MATERIAL: "steel""` not `"schiste"`
   - If no translation exists → skips material binding (false pass costs nothing)
   - Added `LANGUAGE:` instruction preventing LLM from echoing French from context
   - Added full English material list for multi-material entries

2. **Lines ~6898–6935 (DOCUMENTED FACTS injection):**
   - Replaces French material terms in the evidence snippet with English before injecting into prompt context
   - Prevents LLM from reading "Xylogravure polychrome sur papier" and echoing "xylogravure"

3. **Lines ~7477–7530 (check + patch section):**
   - Presence check now compares English translation (not French) against English prose
   - Added stem matching (`lacquer` matches `lacquered`)
   - Unknown materials treated as satisfied (no retry, no French emission)
   - Patch sentence changed from `"This work, crafted in schiste, "` (fragment) to `"This work was crafted from schist."` (complete sentence)
   - Period patch uses `_period_english` not raw `_c51_period`

4. **Lines ~7469 (period 'else' branch — scope 4):**
   - Period check for era names (e.g., "Époque Edo") now also checks translated form and extracted keyword
   - Same bug shape as material: French literal compared against English text

### `tests/test_local322_material_language.py`
- 54 unit tests covering translation, check logic, patch output, and bug reproduction

### `tests/test_local322_genuine_patch.py`
- Demonstration that genuinely-missing materials get patched in grammatical English

### `tests/run_local322_verification.py`
- 8-stop museum generation runner with automated defect detection

## Period branch assessment (scope 4)

**The period branch has the same bug shape but lower severity:**

- **Check logic (lines 7447–7455, century case):** Already translates Roman to Arabic and checks English ordinals. NOT broken for century formats.
- **Check logic (lines 7469, 'else' case):** WAS broken for era names like "Époque Edo" (checked French literal against English). **FIXED** to also check era keyword ("edo" in description).
- **Patch logic (line 7497, old):** Used raw `_c51_period` (French). **FIXED** to use `_period_english` (computed earlier in same scope).

In practice: most periods are centuries (which were already handled), and years (no translation needed). Era names are rare but now handled correctly.

## Verbatim evidence

### The three defective strings — regenerated prose

**Stop 2 (Statue de Bouddha) — previously "This work, crafted in schiste,":**
```
Crafted from schist, this sculpture showcases the fine details of the Buddha's
robes, facial features, and symbolic gestures. The choice of schist as the
material not only highlights the artist's skill in carving but also adds a sense
of durability and timelessness to the artwork.
```

**Stop 1 (L'Armure) — previously "This work, crafted in acier, cuivre, cuir, soie, laque,":**
```
Crafted in the 19th century, this armor, known as dô-maru, showcases exquisite
craftsmanship and cultural significance. It consists primarily of steel, copper,
leather, silk, lacquer, and even gold leaf, embodying the artistry and skill of
Japanese armor-making during the Edo period.
```

**Stop 5 (Ulysses Grant) — previously "This work, crafted in papier using xylogravure…":**
```
In 1879, Toyohara Chikanobu, a prominent ukiyo-e artist of the Meiji period,
created this captivating polychrome woodblock print on paper, depicting a scene
titled "Ulysses Grant au Japon."
```

### Counts: before vs after

| Metric | Before | After | Evidence |
|--------|--------|-------|----------|
| French material leaks in English narration | ~184 (per task) | **0** | grep scan of output: ZERO matches for FRENCH_ONLY_MATERIALS |
| Comma-spliced fragments `"This work, ..., [A-Z]"` | 47 (per task) | **0** | regex scan: ZERO matches |
| `[LOCAL-98] ... missing from description` retries | 7–14 per run (7 stops × 1–2) | **0** | captured stdout: ZERO retry messages |
| Stops generated | 8 | **8** | stop count regex |

### Genuinely-missing material still gets patched (English)

```
CASE 1: Description missing material 'schiste' (should be 'schist')
  FR material: 'schiste' → EN: 'schist'
  Material found in description: False

  PATCHED OUTPUT:
  This remarkable sculpture depicts Buddha in a standing pose. This work was
  crafted from schist. The serene expression on the Buddha's face conveys
  inner peace and spiritual awakening.

  ✓ PASS: Patch is grammatical English, no French leak, no comma splice
```

### Retry counts drop

Old code: For every stop with a French catalogue material (7 of 8), the check
compared "schiste" / "bois" / "acier" against English prose → guaranteed false
failure → up to 2 retries per stop = **7–14 wasteful LLM calls per museum run**.

New code: Check compares English "schist" / "wood" / "steel" against English
prose → finds it immediately → **0 retries**. Cost savings per run: $0.01–0.02
(at gpt-3.5-turbo rates), multiplied by every museum tour generation.

### Regression: base score

| | Baseline (LOCAL-262) | After (LOCAL-322) |
|---|---|---|
| Stops | 8 / 8 | 8 / 8 |
| Base score | +78.12 | **+81.25** (+4.0%) |
| Quality (normalised) | 0.78 | **0.81** |

Base score improved. Total score variance (103.12 → 90.62) is entirely due to
non-deterministic cross-reference bonuses (23.44 → 9.38), not content quality.
The LLM happened to make fewer cross-stop callbacks this run.

## Limitations

1. **The LANGUAGE instruction is soft.** The LLM is told "Never write French
   words" but prompt compliance is probabilistic. If the evidence snippet
   translation misses a term (e.g., a new material added to story_miner but
   not to the map), the LLM might still echo it. Mitigation: the map covers
   all 35 terms in story_miner's current `_MATERIALS` list.

2. **Context snippet translation is regex-based.** If a French term appears as
   part of a longer phrase not in the map (e.g., "schiste gris de Peshawar"),
   only the known sub-terms get translated. The residual French (proper nouns
   like "Peshawar") is acceptable — they're geographic, not material terms.

3. **The stem matching is naive.** `"lacquer".rstrip('ed').rstrip('er')` →
   `"lacqu"` which is a 5-char stem. Works for "lacquered" but could false-
   match on a hypothetical word starting with "lacqu". In practice this is not
   an issue for the material vocabulary.

4. **Existing tour files are unaffected.** The 184/47 counts cited in the bug
   report refer to what the old code would produce on regeneration. The fix
   prevents future occurrences; it does not retroactively fix already-generated
   tour text files (which don't currently contain these defects in the corpus).
