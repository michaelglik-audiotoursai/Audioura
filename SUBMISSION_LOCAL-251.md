##### READY FOR REVIEW

## LOCAL-251: Naming a person counts as substantiation. It should not.

**Branch:** `kiro/local251-namedrop-is-not-delivery`
**Base:** `storied`

### What was built

Three fixes to `style_validator_detector.py`:

1. **Person name alone is no longer delivery (R10 fix).** `_sentence_has_concrete_payload`
   previously returned True whenever it found a multi-word capitalized sequence that wasn't
   a place name. Now a person name must be paired with an event verb (hosted, painted, wrote,
   visited, built, etc.), a date/decade, a named work (in quotes or with novel/painting/book),
   to count as delivery. A name floating in an abstraction is anchoring, not substantiation —
   same reasoning LOCAL-247 applied to place names.

2. **Poisoned-neighbour mechanism fixed as consequence.** Once the name-drop sentence no
   longer has payload, it can no longer cancel the R10 finding on its neighbour through
   the backward-lookahead path.

3. **R9 extended for contentless metaphorical sentences.** New `_has_contentless_signal()`
   function detects sentences that use metaphorical/abstract language about nothing concrete
   (e.g., "bear the weight of history", "a portal to a world where art and culture
   intertwine", "artistic spirit is palpable, a living testament to the enduring power").
   R9 now fires on these when no proper noun, date, or number is present.

### Commit

```
5468ea1 LOCAL-251: person name alone is not delivery; R9 catches contentless metaphor
```

### Per-file summary

| File | Change |
|------|--------|
| `style_validator_detector.py` | Fix 1: `_sentence_has_concrete_payload` check #4 now requires event verb/date/work alongside person name. Fix 3: new `_has_contentless_signal()` function, `check_r9_generic()` extended to call it. |
| `run_local251_namedrop_not_delivery.py` | Run script: verifies all 3 mechanisms, boundary tests, corpus-wide D55 measurement, generates round 8, expand/delete, residual measurement. |
| `RIVIERA_2STOP_ROUND8.md` | Regenerated tour: 2 stops, 479 words. |

### Verbatim evidence

#### Bug reproduction and fix (all confirmed with real output)
```
  --- Mechanism 1: Name-as-delivery (FIXED) ---
    a has_promise: True
    a has_payload: False
    ✓ R10 FIRES on a — name alone is no longer delivery

  --- Mechanism 2: Poisoned neighbour (FIXED as consequence) ---
    ✓ R10 FIRES on b — a no longer poisons b (a has no payload)

  --- Mechanism 3: Invisible contentless sentence (FIXED via R9) ---
    ✓ R9 FIRES on c — contentless metaphorical language detected
```

#### Boundary rows (10/10 LOCAL-251 + 9/9 LOCAL-249 = 19/19 pass)
```
  === LOCAL-251: MUST FIRE ===
    ✓ [R10] "The legacy of artists like Marc Chagall and Bernard-Henri Levy lingers..."
    ✓ [R10+R9] "The village's artistic spirit is palpable, a living testament..."
    ✓ [R9] "The ancient pathways bear the weight of history on their worn stones."
    ✓ [R9] "Saint-Paul-de-Vence is not merely a destination; it is a portal..."
    ✓ [R9] "Each step taken is a journey through the annals of creativity and culture."

  === LOCAL-251: MUST STAY SILENT ===
    ✓ [SILENT] "In 1888, Monet first experimented with painting in series here..."
    ✓ [SILENT] "The La Colombe d'Or hotel has a storied past, having hosted legendary guests like Jean-Paul Sartre and Pablo Picasso."
    ✓ [SILENT] "In the 1960s, Saint-Paul-de-Vence became a retreat for renowned French actors like Yves Montand, Simone Signoret..."
    ✓ [SILENT] "Start cycling southeast on the main road."
    ✓ [SILENT] "Antibes boasts the largest yachting harbor in Europe."

  === LOCAL-249: MUST FIRE (4/4) ===
    ✓ FIRES: "As you cycle along the coastal path..."
    ✓ FIRES: "The Villa Ephrussi de Rothschild..."
    ✓ FIRES: "These stops reveal different facets of opulence..."
    ✓ FIRES: "The coastline holds stories..."

  === LOCAL-249: MUST STAY SILENT (5/5) ===
    ✓ [SILENT]: "In January 1888, Claude Monet painted..."
    ✓ [SILENT]: "The Hôtel du Cap-Eden-Roc was built in 1870..."
    ✓ [SILENT]: "Start cycling south..."
    ✓ [SILENT]: "The Rue Obscure is a 130-metre fortified street..."
    ✓ [SILENT]: "Èze was first settled near Mount Bastide around 200 BC."

  ALL 19 BOUNDARY ROWS PASS ✓
```

#### Corpus-wide D55 compliance
```
  Total sentences in corpus: 2810
  R9 BEFORE (baseline): 17 (0.60%)
  R9 AFTER:  41 (1.46%)
    - via filler (original): 16
    - via contentless (NEW): 25
  Ratio: 2.41x
  Threshold: 3.0x (max 51 fires)
  ✓ WITHIN 3× THRESHOLD
```

#### Round 8 generation
```
  Total cost: $0.0058 (ceiling $0.60)
  Words: Round 5: 680 | Round 6: 298 | Round 7: 658 | Round 8: 479
  Expanded: 1, Deleted (R10): 4, Deleted (R9): 0
  Residuals: R7=0, R8=0, R9=0, R10=0
  Fact tally (hand-counted):
    Cap d'Antibes: 3/5 sentences carry a fact
    Villefranche-sur-Mer: 2/8 sentences carry a fact
```

#### Post-checks
```
  audio_tours count: 142 (unchanged)
  Nice list unchanged: [1, 12, 14, 17, 24, 29, 152]
  No DB rows created or modified (D141 n/a)
  STOP_EXISTENCE_GATE_MODE: enforce
```

### Limitations

1. **Stop 2 fact density is low (2/8).** The remaining 6 sentences escape both R9 and R10:
   they have proper nouns (Villefranche-sur-Mer) which exempts them from R9, and they don't
   contain R10 subject-matter nouns. They are empty orientation/atmosphere sentences that
   name the place but say nothing about it. A stricter R9 (place-name-only sentences with
   generic predicates) was already partially built in LOCAL-247 but doesn't catch all forms.

2. **"[Description for Cap d'Antibes could not be generated.]"** leaked into the tour text.
   This is a generation-layer failure message, not a style rule issue.

3. **R9 contentless patterns are deterministic.** They catch the specific metaphorical shapes
   seen in rounds 2-7 but cannot catch all possible phrasings. Sentences like "Look out
   towards the deep natural harbor, known for its safe anchorage and historic significance"
   are empty but don't match any pattern because they use a different structure.

4. **The tour is shorter (479 words).** This is expected and stated as correct in the task:
   sentences that said nothing are deleted; expansion recovers some; the rest disappears.
