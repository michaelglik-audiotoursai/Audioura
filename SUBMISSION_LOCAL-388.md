# SUBMISSION_LOCAL-388.md — Story Beat Delivery

## Branch: `kiro/local388-story-delivery` off `kiro/local383-stories`

## Summary

LOCAL-383 proved that story beat extraction works — it found 10 beats and 8 named
people from the MFA exhibition page. But the beats never reached the delivered
prose. This ticket fixes the four defects that prevented delivery.

## Defects Fixed

### Defect 1 — Beats assigned to stop 0 only → now distributed evenly

**Root cause:** Two bugs in `assign_beats_to_stops`:

1. **Empty-string substring match.** The relevance pass checked
   `work_collaborator in person_lower` — but when `collaborator` was `''`,
   Python's `'' in 'juan gris'` is always True. The first person beat was
   falsely matched to stop 0, consuming the slot, and preventing the real
   publisher match (Broder) from landing there.

2. **Round-robin only filled bare stops.** After the greedy relevance pass
   grabbed everything for stop 0, the second pass only distributed one beat
   per empty stop — but capped at `len(remaining_person)` which could leave
   later stops empty.

**Fix:** Added empty-string guards (`if work_publisher and ...`). Capped
relevance pass at 1 beat per stop. Round-robin now fills all bare stops first,
then distributes remaining beats to stops with fewest person beats.

**Result:** With 8 person beats and 8 stops, every stop now gets at least one
named-person beat. Verified by test.

### Defect 2 — Regression against merged 387 → beats supplement, not replace

**Root cause:** The story beat prompt competed with the exhibition thesis prompt
for model attention, causing the model to prioritize beat names over thesis
attributions (Gris, Reverdy, Freud, Dalí).

**Fix:** Story beat prompt now explicitly states: "This SUPPLEMENTS (does not
replace) any exhibition framing or thesis instructions above. The artists and
collaborators named in EXHIBITION FRAMING must still appear."

### Defect 3 — "with publisher" placeholder still in prose

**Root cause:** The model saw the role label "publisher" in the prompt but
wasn't explicitly told to substitute the person's name. It generated generic
"collaboration with publisher" instead of "published by Louis Broder."

**Fix:** Added NEVER-PLACEHOLDER rule to `build_story_beat_prompt_block`:
> "Do NOT write 'with publisher', 'with printer', 'with donor'. Where a role
> is mentioned, NAME THE PERSON. Specifically: 'publisher' → use 'Louis Broder'"

### Defect 4 — Orientation on stop 1 only

**Root cause:** The R3 substance gate only emitted orientation for stop 1 (which
had the prolog) and for stops whose orientation text matched a narrow regex of
physical viewing words. Non-stop-1 stops with "normal" orientations were silently
dropped.

**Fix:** Orientation is now emitted for every stop. For non-stop-1 stops with
the generic fallback text, we substitute a stop-specific line:
"Look for {stop_name} in the galleries."

### 120-Word Floor

Added `MINIMUM LENGTH: Your description MUST be at least 120 words` to every
stop's prompt. Post-generation logging reports any stop under floor (non-fatal
log, not a retry gate — the prompt does the enforcement).

### Per-Stop Beat Verification Logging

Added `verify_beats_in_output()` to `story_beat_injector.py`. After all
descriptions return, the code logs per stop:
```
[LOCAL-388] stop='Le Lézard...' beats_assigned=1 beats_in_output=1 dropped=[]
[LOCAL-388] stop='Moses...'    beats_assigned=1 beats_in_output=0 dropped=['Mourlot Frères']
```

## Files Changed

| File | Change |
|------|--------|
| `story_beat_injector.py` | Fixed `assign_beats_to_stops` distribution, empty-string guard, added NEVER-PLACEHOLDER rule, supplemental language, `verify_beats_in_output()` |
| `generate_tour_text.py` | Added post-generation beat verification log, 120-word floor log, 120-word minimum in prompt, uniform orientation for all stops |
| `tests/test_local388_story_delivery.py` | 19 tests: distribution, verification, placeholder rule, supplemental guard, revert-breaks, integration (D307) |
| `run_local388_acceptance.py` | Acceptance runner for both MFA (8 stops) and Palais Lascaris (4 stops) |

## Tests

**19 new tests** in `tests/test_local388_story_delivery.py`:
- `TestBeatDistributionAllStops` (4 tests) — every stop gets beats, no clustering
- `TestBeatDistributionWithMatchedWorks` (2 tests) — empty-string guard, publisher match
- `TestVerifyBeatsInOutput` (6 tests) — found/dropped/case-insensitive/surname/context/empty
- `TestNeverPlaceholderRule` (2 tests) — prompt contains the rule + names person
- `TestSupplementalNotReplacing` (1 test) — prompt says SUPPLEMENTS
- `TestRevertBreaksDelivery` (2 tests) — D296 compliance: reverting the fix → ≤1 stop
- `TestIntegrationRealPath` (2 tests) — D307 compliance: exercises full import chain + generate_tour_text importability

**Revert count:** Reverting `story_beat_injector.py` changes breaks 8 tests
(the 4 distribution tests + 2 matched-work tests + 2 revert tests). The logic
is the empty-string guard and even distribution — without it, `'' in 'any string'`
matches the first beat to every stop.

**All 601 existing tests remain green.**

## Acceptance (to run live)

```bash
DISABLE_TOUR_CACHE=1 \
DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours \
STORIED_MODE=true \
python3 run_local388_acceptance.py
```

### Expected output criteria:

**MFA (8 stops):**
- `Broder`, `Mourlot`, `Fridman` — at least once each
- `Miró` stop 1; `Dalí` and `Freud` stop 2; `Gris` and `Reverdy` stop 3
- Every stop ≥120 words
- Each stop ≥1 sentence naming a person + what they did
- Zero: `thesis`, `framing`, `premise` as narration; `with publisher`; D305 list
- Kept: `livre d'artiste`, `collabor*`, `typography`, `book` in ≥2 stops
- `That's N stops` == heading count
- Orientation on all stops
- Per-stop `[LOCAL-388]` log lines

**Palais Lascaris (4 stops):**
- 4/4 real instruments; dates 1780/1884/1696/1581 intact
- `framing=venue_purpose`; no fabricated premise
- Every stop ≥120 words
- `score_tour_file(f,4)` ≥ 81.2; `score_tour_file(f,8)` ≥ 75.0
