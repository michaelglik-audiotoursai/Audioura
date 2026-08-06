##### READY FOR REVIEW

## Commit

```
39e8dd4 LOCAL-317: Refine patterns + generation verification
c26ca64 LOCAL-317: R7 extends to culinary/interior sensory register
```

Branch: `kiro/local317-r7-restaurant-register`
Commit count (storied..HEAD): 2

## Per-file summary

| File | Change |
|------|--------|
| `style_validator_detector.py` | 6 new patterns added to `_R7_PATTERNS` list covering culinary/interior sensory register: (1) smell asserted as present with broadened verb set (fills/weaves/wafts/envelops/suffuses/spills) and plural support; (2) adjective-qualified ambient sound (gentle/soft/cheerful/rhythmic/faint/muffled/constant + sound-noun + of); (3) bare sound-noun paired with another sensory marker in same sentence; (4) hum/murmur/chatter of conversation/voices/patrons with optional adjective; (5) sounds from specific interior locations; (6) ambient glow/warmth of interior. Visitor/tourist exclusion on adjective sound pattern. |
| `tests/run_local317_generation.py` | Generation script for 5-stop Old Nice restaurant tour. AUDIOURA_DB_TARGET=production, TOUR_LLM_MODEL=gpt-4o, reports R7 deletions and production real count. |
| `tours/LOCAL317_5stop_old_nice_restaurant.txt` | Generated 5-stop restaurant tour (La Petite Maison → Le Bistro du Port → Olive & Artichaut → Restaurant Acchiardo → Chez Palmyre). 1139 words. |

## Verbatim evidence

### All 4 target sentences + jasmine now detected

```
  HIT: the aroma of garlic, herbs, and simmering sauces fills the air
  HIT: the clinking of cutlery and the cheerful hum of conversation spill onto the cobblestones
  HIT: The sounds from the kitchen and the gentle hum of conversations reflect the rhythm of daily life
  HIT: The scent of garlic and herbs weaves through the cozy space
  HIT: The scent of jasmine fills the courtyard as you approach.
```

### 4 dish-fact controls NOT detected

```
  PASS: The menu features socca and ratatouille.
  PASS: Daube is a beef stew braised in wine.
  PASS: Panisses are crispy chickpea fritters.
  PASS: The restaurant has served Niçoise cuisine since 1927.
```

### Corpus-wide R7 rate (parsed stop bodies, 29 real tours)

```
BEFORE: 88/2090 = 4.21%
AFTER:  93/2090 = 4.45%
D55 ceiling (3× 1.49% baseline): 4.47%
Under ceiling: YES (4.45 < 4.47)
```

Delta: +5 sentences, all true positives:
- Tour29: "the scent of blooming flowers envelop you in a tranquil embrace" (smell pattern)
- Tour17: "the scents of garlic and olive oil dance in the air, and the clinking of glasses mingles with lively chatter" (smell + bare-paired)
- Tour17: "the savory aroma of roasting meats that wafts through the narrow cobblestone streets" (smell pattern)
- Tour17: "soft candlelight, the gentle clinking of glasses, and the hum of animated conversations" (adjective sound pattern)
- Tour17: "The clinking of porcelain teacups and the soft murmur of satisfied patrons create a symphony" (bare-paired + hum-of-patrons)

### Tour regeneration

```
Tour:       restaurants tour in old city of Nice, France (5-stop restaurant)
Stops:      La Petite Maison, Le Bistro du Port, Olive & Artichaut, Restaurant Acchiardo, Chez Palmyre
Words:      1139
Cost:       $0.1262
Time:       81.3s
R7 deletions during generation: 7 (2 from stop bodies, 5 from orientations)
R7 hits in delivered text: 0
```

R7 deletions during generation:
```
[R7_HALLUCINATED_SENSORY] Stop 1 body: 1 sentence deleted
[R7_HALLUCINATED_SENSORY] Stop 5 body: 1 sentence deleted
[R7_HALLUCINATED_SENSORY] Stop 1 orientation: "The aroma of Provençal herbs and freshly cooked dishes wafts through the air, inviting you to discov..."
[R7_HALLUCINATED_SENSORY] Stop 1 orientation: "As you stroll through the charming cobblestone streets of Old Nice, the vibrant buzz of conversation..."
[R7_HALLUCINATED_SENSORY] Stop 3 orientation: "The aroma of fresh herbs and sizzling garlic lingers in the air, a sensory promise of the culinary d..."
[R7_HALLUCINATED_SENSORY] Stop 3 orientation: "Listen for the gentle clinking of cutlery and the low hum of conversation that drifts from the open ..."
[R7_HALLUCINATED_SENSORY] Stop 5 orientation: "Here, the aroma of hearty Provençal dishes mingles with the salty sea breeze."
```

### Production real count

```
Production real count BEFORE: 29
Production real count AFTER:  29
```

### git status

```
$ git status --short
(clean)
```

## Limitations

1. **"aromas of X create an inviting atmosphere" escapes R7.** The verb `creates` was tested but pushed the corpus rate to 4.50% (over ceiling). This sentence survives in Stop 2 of the generated tour. Adding `creates` to the verb list is blocked by the D55 ceiling until the baseline drifts down.

2. **"The sound of clinking glasses and friendly chatter fills the air" escapes.** The structure "sound of [gerund] [noun]" is different from "the clinking of [noun]" — it uses "clinking" as an adjective modifying "glasses", not as a noun in "the clinking of". Catching this variant would require a broader pattern that fires on "sound of [adj] [noun]" which is too wide.

3. **"the enticing aroma of Provençal spices" escapes** in Stop 4 orientation. The smell pattern requires a location/dispersal verb (fills/weaves/wafts), but this sentence uses "aroma" as a bare noun phrase without such a verb. A pattern for "the [adj] aroma/scent of X" without a verb would false-positive on factual descriptions like "the distinctive aroma of socca" in a dish-naming context.

4. **Ceiling constraint is binding.** The corpus rate moved from 4.21% to 4.45% with only 5 net new hits, all TPs. The 0.02% remaining headroom (93.4 sentences) means exactly 0 more patterns can be added without either reducing existing hits or growing the corpus denominator.

5. **Measurement denominator discrepancy.** The task states current rate as "2.77% (556/20048)" but the production database yields 88/2090 on 29 real tours with parsed stop bodies via `parse_tour_stops`. The 20048 denominator is not reproducible from the current database state. Before/after measurements use the same method for consistent comparison.
