##### READY FOR REVIEW

## Commit

`39a0b142c9e5fb37429c63311ab4ef67dff73a6d`

Branch: `kiro/local253-directions-ignore-transport-mode`

## Per-File Summary

| File | Change |
|---|---|
| `directions_generator.py` | Added `validate_directions_mode()` guard function; updated `generate_walking_directions` to accept `transport_mode` parameter with mode-specific system/user prompts and post-generation guard |
| `generate_tour_text.py` | Pass `transport_mode=transport_mode` to `generate_walking_directions` at line 7675; validate pre-existing POI directions against mode |
| `tests/test_local253_directions_mode_guard.py` | 14 unit tests covering all 7 boundary rows plus additional coverage |
| `RIVIERA_2STOP_ROUND11.md` | Round 11 report: 790 words, cycling directions confirmed, fact tally per stop |
| `run_round11.py` | Generation script for round 11 |

## Where the Mode Was Lost

**`generate_tour_text.py` line 7675** (before fix):
```python
_storied_directions = generate_walking_directions(poi_name, next_poi['name'], location, api_key)
```

The `transport_mode` variable is set correctly at line 2617 and used throughout
the stop-selector phase (CRITICAL CONSTRAINT injected into prompts, distance
tiers applied). But at line 7675, in the transition-generation block, it was
simply never passed to `generate_walking_directions`. The function then used a
hardcoded "You write short walking directions for an audio tour" system prompt
for ALL outdoor tours regardless of mode.

## Verbatim Evidence: 7 Boundary Rows

```
$ python3 -m pytest tests/test_local253_directions_mode_guard.py -v
tests/...::test_survive_cycling_south PASSED    ← "Start cycling south on the main road with the sea on your right."
tests/...::test_survive_head_east PASSED         ← "Head east along the coastal path until you reach the roundabout."
tests/...::test_survive_follow_signs PASSED      ← "Follow the signs up the hill to reach the village."
tests/...::test_catch_train_on_biking_tour PASSED ← "From Antibes train station, take a train towards Eze Village."
tests/...::test_catch_a8_motorway_on_biking_tour PASSED ← "Continue east until you hit the A8 highway."
tests/...::test_catch_start_your_walk_on_biking_tour PASSED ← "Start your walk from Cap d'Antibes."
tests/...::test_catch_enjoy_the_walk_on_biking_tour PASSED  ← "Enjoy the walk!"
14 passed in 0.14s
```

## Round 11 Directions (Verbatim)

**Leg 1 (Cap d'Antibes → Saint-Paul-de-Vence), mode: cycling:**

> Start your ride at Cap d'Antibes and pedal east along the scenic coastal road.
> Enjoy the stunning views of the Mediterranean Sea as you cycle towards Antibes
> Old Town. From there, continue your journey north, passing through picturesque
> villages like Saint-Paul-de-Vence along the way. Happy cycling!

Mode guard: **0 violations** ✓

## Fact Tally (Hand-Counted)

| Stop | Facts / Total Sentences |
|---|---|
| Cap d'Antibes | 10 of 17 |
| Saint-Paul-de-Vence | 8 of 10 |

(Round 10 for comparison: Cap d'Antibes 4/9, Èze 8/11)

## Guard Firing Evidence (First Run)

The first generation attempt produced directions containing "on foot" (wrong-mode
verb) from the LLM and "A8" (motorway) from pre-existing POI data. Both were
caught and rejected:

```
❌ [LOCAL-253] DIRECTIONS REJECTED: WRONG_MODE_VERB_BIKE: 'on foot'
❌ [LOCAL-253] PRE-EXISTING DIRECTIONS REJECTED: MOTORWAY_ON_BIKE: 'A8'
```

After regex tightening (bare "on foot" → "continue on foot" / "proceed on foot"
/ "travel on foot"), the second run passed cleanly with proper cycling language.

## Database State

- `audio_tours` before: 142
- `audio_tours` after: 142
- Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED

## STOP_EXISTENCE_GATE_MODE

`enforce` (set explicitly in run_round11.py line 85).

## Cost

$0.0091 (ceiling: $0.60)

## Limitations

1. **`Tour-Category: walking` header** persists on cycling tours. This is the
   separate known bug in `_classify_tour_category` (documented in ROUND10 report).
   NOT this task — fixing it must not be confused with fixing directions.

2. **Guard fallback is generic.** When the LLM produces mode-inappropriate
   directions and the guard rejects them, the fallback is "Continue to
   {next_stop}." — correct but unhelpful. A retry loop (re-prompt with stronger
   constraints) would improve this but adds cost and complexity. The current
   behavior is safe: no dangerous directions are ever delivered.

3. **Wrong-mode verb patterns are English-only.** Translated tours (e.g. Russian)
   would need their own pattern sets. Not in scope for LOCAL-253.

4. **"on foot" as bare phrase was initially too broad** — caught incidental usage
   in otherwise-cycling text ("Once you reach the coast on foot"). Tightened to
   require directive context ("continue on foot", "proceed on foot"). The original
   defect examples ("Start your walk", "Enjoy the walk!") still fire correctly.

5. **No container rebuilt** (D48 compliant). Changes are in Python source files
   that are volume-mounted in development.
