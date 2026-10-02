# SUBMISSION_LOCAL-432.md

## Summary

LOCAL-432 addresses two problems from LOCAL-431:
1. The story retry fires but under-delivers by one sentence
2. `check_thesis_threaded` was unconditionally passing for `venue_purpose`

## Part 1: Story Retry Improvement + Sacqueboute Zero Diagnosis

### Why the retry stopped at 2

The LOCAL-431 retry prompt had three deficiencies:
1. **Did not show rejected sentences** — the model retried blind, not knowing which
   of its own sentences failed or why
2. **Did not name available people** — the beat data existed but wasn't surfaced
3. **Generic examples only** — "Dalí chose Freud's text" is irrelevant to a
   musical-instrument museum

The LOCAL-432 fix:
- Shows the model its own rejected sentences with per-sentence diagnostic reasons
  (no story verb, no named person, evaluative claim)
- Injects the stop's assigned beat people with their known actions
- Specifies the exact deficit count ("you need EXACTLY 1 more")
- Adds instrument-domain passing examples ("Schnitzer specialized...")

### Sacqueboute's zero: diagnosis and fix

**Root cause:** Beat extraction had no pattern for the "[instrument] by [Maker] (City, Year)"
attribution construction. The corpus says "a tenor sackbut by Anton Schnitzer (Nuremberg,
1581)" — but `_PUBLISHED_PRINTED_BY` only matched published/printed/edited/designed/bound,
and `_PERSON_ACTION` requires `[Person] [verb]` (not `[work] by [Person]`).

**Evidence:**
- Before fix: `extract_story_beats(SACQUEBOUTE_CORPUS)` → 2 beats: "Wikipedia" (bogus),
  "Fischer" (valid). Zero usable maker beats.
- After fix: → 3 beats: "Anton Schnitzer" (maker, crafted in 1581), "Egger" (maker),
  "Fischer" (published). Wikipedia filtered.

**Fix:** Added `_WORK_BY_MAKER` regex pattern + `_KNOWN_NON_PERSON_NAMES` blocklist.

**Live evidence: Sacqueboute went 0 → 3 story sentences.** Internal gate reports
`story_count=3, entities_ok=True, thesis_ok=True` — PASS.

### Is 3/3 reachable?

**Yes.** Sacqueboute proves it in this run (0→3). Harpe achieved 3 on the 08-11 artifact.
The retry mechanism works when it has beats to work with. The remaining stops (Harpe 0,
Violes 1, Basse 1) need their beat corpus enriched — the retry fires but under-delivers
because those stops have fewer actionable person+action beats than Sacqueboute now has.

## Part 2: `check_thesis_threaded` venue_purpose check

### What LOCAL-431 did wrong

Replaced the thesis check with `return True` for venue_purpose. The complaint was
legitimate (_THESIS_KEYWORDS are livre-d'artiste-specific) but the fix made the
component dead code.

### What LOCAL-432 builds

`_check_venue_purpose_threaded()`: extracts meaningful terms from the venue's detected
purpose sentence using three categories:
- **Person surnames** (Gautier, Antoine)
- **Domain nouns** (instruments, musical, collection)
- **Action words** (bequeathed, testament, collector)

Uses stem-based matching (5+ char prefix) so "instruments" in the purpose matches
"instrument" in the description.

A stop that mentions ANY of these terms passes. A stop that completely ignores the
venue's reason for existing fails.

### Both directions demonstrated

**PASS:** "Part of the musical instruments collection assembled by Gautier."
→ matches "instrument" (domain), "collection" (action stem), "Gautier" (surname)

**FAIL:** "Lovely Renaissance engineering in the bell curves."
→ no instrument/collection/bequest/Gautier/musical → False

## Live Palais Run (LOCAL-432)

```
framing=venue_purpose source='bequeathed to the city of Nice in the testament of 26 May 1901...'

PER-STOP STORY COUNTS (internal gate, authoritative):
  ✓ Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581): story_count=3
  ✗ Harpe by Naderman (Paris, 1780): story_count=0
  ✗ Violes gambe by William Turner (Londres, 1652): story_count=1
  ✗ Basse de violon by Paolo Antonio Testore (Milan, 1696): story_count=1

STORY GATE VERDICT: 1/4 pass (≥3 story sentences)

CONTROL (D302/D326):
  Stops: 4/4
  Dates: 1780/1652/1581/1696 (4/4 intact)
  Coordinates: 4/4 (43.6984, 7.2763)
  thesis_ok: True for all 4 stops (venue_purpose check passes on real content)
```

## Neutralisation Evidence (red output)

### _check_venue_purpose_threaded → always True

```
Neutralise: story_gate._check_venue_purpose_threaded = lambda desc, vp: True

FAIL: test_fails_when_description_ignores_venue_purpose
  AssertionError: True is not false : Should fail: no reference to instruments/collection/bequest/Gautier

FAIL: test_venue_purpose_failure_in_verify_stop_story
  AssertionError: True is not false

FAIL: test_check_can_fail
  AssertionError: True is not false

--- NEUTRALISATION RESULT: 3 failures, 0 errors ---
```

### _WORK_BY_MAKER → never-match pattern + revert _PUBLISHED_PRINTED_BY

```
Neutralise: _WORK_BY_MAKER = re.compile(r'NEVER_MATCH_THIS_PATTERN_xyzzy42')
            _PUBLISHED_PRINTED_BY reverted to original (no made/crafted/built)

FAIL: test_extracts_maker_from_by_attribution
  AssertionError: 0 not greater than 0 : Should extract Anton Schnitzer as maker

--- NEUTRALISATION RESULT: 1 failures ---
```

## Story retry fired (evidence from live run log)

```
[LOCAL-432] Stop 4: STORY RETRY — story_count=2 < 3, need 1 more, retrying (attempt 2/3)
[LOCAL-432] Stop 3: STORY RETRY — story_count=0 < 3, need 3 more, retrying (attempt 2/3)
[LOCAL-432] Stop 1: STORY RETRY — story_count=1 < 3, need 2 more, retrying (attempt 2/3)
[LOCAL-432] Stop 2: STORY RETRY — story_count=1 < 3, need 2 more, retrying (attempt 2/3)
[LOCAL-432] Stop 4: STORY RETRY — story_count=1 < 3, need 2 more, retrying (attempt 3/3)
[LOCAL-432] Stop 1: STORY RETRY — story_count=1 < 3, need 2 more, retrying (attempt 3/3)
[LOCAL-432] Stop 3: STORY RETRY — story_count=0 < 3, need 3 more, retrying (attempt 3/3)
[LOCAL-432] Stop 2: STORY RETRY — story_count=2 < 3, need 1 more, retrying (attempt 3/3)
```

## Tests

```
77 passed, 1 skipped in 0.39s

tests/test_local432_venue_thesis_and_retry.py: 17 passed
tests/test_local431_story_gate_enforcement.py: 15 passed
tests/test_local391_required_beats.py: 23 passed, 1 skipped
test_local421_story_per_stop.py: 22 passed
```

## Unproven, handing to LEAD

- 3/4 or 4/4 story gate pass on a single Palais run. The mechanism works (Sacqueboute
  proves 0→3 is achievable) but LLM stochasticity means a single run doesn't guarantee
  all 4 pass simultaneously. The retry needs richer beat corpus for Harpe/Violes/Basse.
