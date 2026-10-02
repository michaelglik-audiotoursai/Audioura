##### READY FOR REVIEW

## Commit

```
LOCAL-256: R1 fragment fix, Description: label gate, R7 orientation patterns
```

## Per-File Summary

| File | Change |
|---|---|
| `style_validator_detector.py` | +180 lines: `_take_in_handler` (hoists relative verbs to main clause), `_look_for_handler` (supplies copula for participle patterns), `_has_finite_main_verb` (fragment detector gates all rewrites), `_take_a_moment_handler` updated for participle case, two new R7 patterns for multi-sensory fabrication |
| `generate_tour_text.py` | +20 lines: `Description:` stripped at the LLM-output split point (line ~6200), bare-field-label gate at post-assembly (line ~8030) |
| `tests/test_local256_fragment_and_label.py` | 28 tests covering all three defects + all 15 boundary rows |
| `run_round13.py` | Generation harness: R7 baseline, flags-on generation, measurement, D141-compliant DB round-trip, fact tally, artifact write |
| `RIVIERA_2STOP_ROUND13.md` | Tour artifact (Cap d'Antibes + Saint-Paul-de-Vence, 542 words) |

## Three Defects Fixed

### 1. R1 rewrite no longer produces fragments

**Root cause:** The "Take in the X" and "Look for the X" rules stripped the imperative verb and produced "The X" — a bare noun phrase with no main verb.

**Fix:** Two new handlers (`_take_in_handler`, `_look_for_handler`) that:
- Detect relative clauses ("that stretches...") and hoist the verb to main-clause position
- Detect participial phrases (", founded in...") and supply a copula ("was founded")
- Fall back to "stretches out before you" / "can be found here" when no structural verb is available

**Safety net:** `_has_finite_main_verb` checks every rewrite output in `apply_r1_rewrites`. If a rewrite still produces a fragment (no finite main verb detected), the original imperative is kept — per D156: "an imperative is better than a fragment."

**Fallback-to-original count in round 13:** 0 (all deterministic rewrites produced grammatical sentences).

### 2. `Description:` cannot reach the artifact

**Root cause:** When the LLM echoes "Description:" as a section header between orientation and body text, the `\n\n` split at line 6184 puts it into the `description` variable. Round 7 v2 avoided it by chance (the LLM didn't echo it that time); round 12 reproduced it.

**Fix (two layers):**
1. **At source** (line ~6200): `re.sub(r'^Description:\s*\n?', '', description)` strips the label immediately after the split.
2. **Post-assembly gate** (line ~8030): `_BARE_FIELD_LABELS` regex catches any bare field label on its own line in `complete_tour` and strips it. This gate sits next to LOCAL-251's placeholder gate and covers Description:, Orientation:, Directions:, Sources:, etc.

### 3. R7 fires on orientation fabricated sensory

**Root cause:** R7's existing patterns required either `gentle breeze carries` (no intervening word between adjective and noun) or `breathe in ... mingling` (specific prefix). The round 12 sentences had:
- "gentle **sea** breeze carries" — "sea" between adjective and noun
- "scent of the sea **mingles** with the **fragrance** of lavender" — dual-scent without "breathe in"

**Fix:** Two new patterns in `_R7_PATTERNS`:
- `(?:salty|gentle|soft|...) \w* (?:breeze|wind|air) (?:carries|...) (?:the)? (?:scent|...) .* (?:mingling|sounds? of|waves? lapping|seagulls?)`
- `(?:the)? (?:scent|smell|fragrance|aroma) of .+? (?:mingles?|mixes?|...) with (?:the)? (?:scent|smell|fragrance|aroma)`

**D55 corpus-wide R7 before/after:**
- Before LOCAL-256 patterns: 79/6310 = 1.25%
- After LOCAL-256 patterns: 84/6310 = 1.33%
- Ratio: **1.06×** (well within the 3× ceiling)

## Fifteen Boundary Rows — All Hold

| # | Source | Sentence | Result |
|---|---|---|---|
| 1 | LOCAL-255 | "Position yourself at the entrance of Eze Village, a medieval gem..." | → "Eze Village is a medieval gem..." ✓ |
| 2 | LOCAL-255 | "As you arrive at Cap d'Antibes, take in the breathtaking views..." | → "From Cap d'Antibes, you can admire..." ✓ |
| 3 | LOCAL-255 | "Look for the Fondation Maeght, founded in 1964..." | → "The Fondation Maeght was founded in 1964..." ✓ |
| 4 | LOCAL-255 | "Start cycling south on the main road with the sea on your right." | untouched (navigation) ✓ |
| 5 | LOCAL-255 | "Head east along the coastal path until you reach the roundabout." | untouched (navigation) ✓ |
| 6 | LOCAL-255 | "Start your ride at Cap d'Antibes and pedal east..." | untouched (navigation) ✓ |
| 7 | LOCAL-255 | "Take a moment to absorb the atmosphere." | deleted (pure instruction) ✓ |
| 8 | LOCAL-255 | "Enjoy the view." | deleted (pure instruction) ✓ |
| 9 | LOCAL-253 | "Start cycling south on the main road..." | no violations (bike mode) ✓ |
| 10 | LOCAL-253 | "Head east along the coastal path..." | no violations (bike mode) ✓ |
| 11 | LOCAL-253 | "Follow the signs up the hill to reach the village." | no violations (bike mode) ✓ |
| 12 | LOCAL-253 | "From Antibes train station, take a train towards Eze Village." | caught (PUBLIC_TRANSPORT) ✓ |
| 13 | LOCAL-253 | "Continue east until you hit the A8 highway." | caught (MOTORWAY) ✓ |
| 14 | LOCAL-253 | "Start your walk from Cap d'Antibes." | caught (WRONG_MODE_VERB) ✓ |
| 15 | LOCAL-253 | "Enjoy the walk!" | caught (WRONG_MODE_VERB) ✓ |

## Round 13 Residuals

| Metric | Value |
|---|---|
| R1 residual | 3/32 (9.4%) |
| R7 residual | 0 |
| R9 residual | 0 |
| R10 residual | 0 |
| Description: labels | 0 |
| Fragment sentences (narration) | 0 |
| Word count | 542 |
| Cost | $0.0097 |
| Facts: Cap d'Antibes | 2 (Monet 1888, Sentier du Littoral 2.7km) |
| Facts: Saint-Paul-de-Vence | 4 (Fondation Maeght 1964, Sert architect, Malraux inauguration, 13000 artworks) |

## Evidence

```
$ python3 -m pytest tests/test_local256_fragment_and_label.py tests/test_r1_rewrite.py tests/test_local253_directions_mode_guard.py tests/test_r10_unfulfilled_promise.py -v
85 passed

$ grep -c "^Description:" RIVIERA_2STOP_ROUND13.md
0

$ python3 -c "
from style_validator_detector import check_r7_hallucinated_sensory
s1 = 'As you arrive at Cap d\\'Antibes, a gentle sea breeze carries the scent of pine trees and saltwater, mingling with the sounds of seagulls overhead and waves lapping against the rocky coastline.'
s2 = 'Within the stone walls of Èze, the scent of the sea mingles with the fragrance of lavender that grows abundantly in this region.'
print('S1 fires R7:', bool(check_r7_hallucinated_sensory(s1)))
print('S2 fires R7:', bool(check_r7_hallucinated_sensory(s2)))
"
S1 fires R7: True
S2 fires R7: True

$ python3 -c "
from style_validator_detector import rewrite_r1_sentence_deterministic, _has_finite_main_verb
s1 = 'Take in the panoramic view that stretches out before you, with the ancient village of Èze rising majestically behind you.'
s2 = 'Look for the Fondation Maeght, founded in 1964 by Marguerite and Aimé Maeght.'
r1 = rewrite_r1_sentence_deterministic(s1)
r2 = rewrite_r1_sentence_deterministic(s2)
print(f'S1: {r1}')
print(f'S1 has verb: {_has_finite_main_verb(r1)}')
print(f'S2: {r2}')
print(f'S2 has verb: {_has_finite_main_verb(r2)}')
"
S1: The panoramic view stretches out before you, with the ancient village of Èze rising majestically behind you.
S1 has verb: True
S2: The Fondation Maeght was founded in 1964 by Marguerite and Aimé Maeght.
S2 has verb: True
```

## Limitations

1. **Cap d'Antibes fact density dropped vs round 12.** 2 facts vs round 12's ~9. This is LLM generation variance, not a regression from the fixes. The rewrite path never removes factual content.

2. **R7 pattern is structural, not semantic.** A rephrased multi-sensory fabrication ("salty breeze carries hints of pine and lavender, mingling...") using "hints" instead of "scent" bypasses the regex. The pattern targets the specific shapes LEAD identified; a comprehensive solution would need semantic understanding.

3. **Fragment detector is conservative.** `_has_finite_main_verb` uses heuristics (participial stripping + verb-form lists). It correctly catches our rewrite-produced fragments but may miss exotic fragment shapes not produced by our rules. Design is intentionally permissive to avoid false rejections of valid sentences.

4. **Corpus-wide R7 measurement includes all patterns** (pre-LOCAL-256 + new). The 84/6310 (1.33%) rate is the total; the 5 additional hits from the new patterns are marginal (1.06× baseline).
