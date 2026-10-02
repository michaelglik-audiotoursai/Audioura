# SUBMISSION_LOCAL-363.md

## Summary

**Branch:** `kiro/local363-parser-place-name-guard` (1 commit ahead of `storied`)

LOCAL-363 adds a **place-name guard** to the tour request parser so that
transport keywords embedded inside proper place names no longer hijack the
tour type. The fix preserves LOCAL-358's transport-first ordering.

---

## Per-file changes

### `audio_tour_app/lib/utils/tour_request_parser.dart`

- Transport keyword checks now call `_hasActivityContext(lowerRequest, match)`
  before returning a tour type. The guard requires the mode word to appear
  **before** the first spatial preposition (`of`/`in`/`at`/`around`/`through`/
  `along`/`across`). Words after that boundary are presumed to be part of the
  destination name.
- Fallback rules for requests with no spatial preposition: activity nouns
  (`tour`/`ride`/`trip`) or leading-word position still qualify.
- `by`/`on`/`via` immediately preceding the mode word also qualifies
  (e.g. "tour by bike").
- The same guard is applied to `museum`/`park`/`exhibit` category keywords
  (they too can be place-name nouns: "Safari Park", "Horse Museum").
- `walking`/`walk`/`hike`/`hiking` remain unguarded — they ARE activity words
  regardless of position.
- Vehicle regex consolidated: `car` moved into the main alternation.

### `audio_tour_app/test/tour_request_parser_test.dart`

- Extended with all 15 acceptance-table rows as a dedicated test group.
- Added bare-transport-without-"tour" group (`biking in Norwood MA`).
- 50 total tests, all passing.

---

## Acceptance table (verbatim)

| input | must return |
|---|---|
| `biking tour in Norwood MA` | `biking` |
| `biking tour in Central Park` | `biking` |
| `cycling tour of Hyde Park` | `biking` |
| `bike tour along the boardwalk` | `biking` |
| `dog sledding tour in Big Lake AK` | `dog sledding` |
| `camel tour in Abu Dhabi` | `camel` |
| `walking tour of Camelback Mountain, Phoenix` | `walking` |
| `tour of Horse Guards Parade, London` | `''` |
| `walking tour of the White Horse Tavern` | `walking` |
| `tour of San Diego Safari Park` | `''` |
| `walking tour of Scooter Alley` | `walking` |
| `museum tour of the Horse Museum` | `museum` |
| `walking tour of Carmel-by-the-Sea` | `walking` |
| `tour of the Louvre` | `''` |
| `tour of downtown Boston` | `''` |

---

## D242: Before-run (old parser, LOCAL-363 tests FAILING)

```
00:00 +6 -1: parseTourRequest - LOCAL-363 acceptance table walking tour of Camelback Mountain, Phoenix → walking [E]
  Expected: 'walking'
    Actual: 'camel'

00:00 +6 -2: parseTourRequest - LOCAL-363 acceptance table tour of Horse Guards Parade, London → empty [E]
  Expected: ''
    Actual: 'horseback'

00:00 +6 -3: parseTourRequest - LOCAL-363 acceptance table walking tour of the White Horse Tavern → walking [E]
  Expected: 'walking'
    Actual: 'horseback'

00:00 +6 -4: parseTourRequest - LOCAL-363 acceptance table tour of San Diego Safari Park → empty [E]
  Expected: ''
    Actual: 'safari'

00:00 +6 -5: parseTourRequest - LOCAL-363 acceptance table walking tour of Scooter Alley → walking [E]
  Expected: 'walking'
    Actual: 'driving'

00:00 +6 -6: parseTourRequest - LOCAL-363 acceptance table museum tour of the Horse Museum → museum [E]
  Expected: 'museum'
    Actual: 'horseback'
```

6 of the 15 acceptance rows fail against the merged (storied) parser.

---

## After-run (new parser, all passing)

```
00:00 +0: parseTourRequest - LOCAL-363 acceptance table biking tour in Norwood MA → biking
00:00 +1: parseTourRequest - LOCAL-363 acceptance table biking tour in Central Park → biking
00:00 +2: parseTourRequest - LOCAL-363 acceptance table cycling tour of Hyde Park → biking
00:00 +3: parseTourRequest - LOCAL-363 acceptance table bike tour along the boardwalk → biking
00:00 +4: parseTourRequest - LOCAL-363 acceptance table dog sledding tour in Big Lake AK → dog sledding
00:00 +5: parseTourRequest - LOCAL-363 acceptance table camel tour in Abu Dhabi → camel
00:00 +6: parseTourRequest - LOCAL-363 acceptance table walking tour of Camelback Mountain, Phoenix → walking
00:00 +7: parseTourRequest - LOCAL-363 acceptance table tour of Horse Guards Parade, London → empty
00:00 +8: parseTourRequest - LOCAL-363 acceptance table walking tour of the White Horse Tavern → walking
00:00 +9: parseTourRequest - LOCAL-363 acceptance table tour of San Diego Safari Park → empty
00:00 +10: parseTourRequest - LOCAL-363 acceptance table walking tour of Scooter Alley → walking
00:00 +11: parseTourRequest - LOCAL-363 acceptance table museum tour of the Horse Museum → museum
00:00 +12: parseTourRequest - LOCAL-363 acceptance table walking tour of Carmel-by-the-Sea → walking
00:00 +13: parseTourRequest - LOCAL-363 acceptance table tour of the Louvre → empty
00:00 +14: parseTourRequest - LOCAL-363 acceptance table tour of downtown Boston → empty
...
00:00 +50: All tests passed!
```

---

## Design choice: bare `'biking in Norwood MA'` (no "tour")

**Decision: resolves to `biking`.**

Rationale: "biking" is the leading word before the spatial preposition "in". It
occupies the activity position — there is no ambiguity that it describes travel
mode rather than a place name. Michael's real requests from the app's free-text
field commonly omit "tour" (`biking in Norwood MA` was the original bug report
input). The `_hasActivityContext` rule (a) handles this: matchStart (0) <
spatialPrepMatch.start (8), so it qualifies.

Runs confirming:
```
'biking in Norwood MA'   → biking  (leading word before "in")
'cycling around Paris'   → biking  (leading word before "around")
```

---

## Limitations

1. **Single spatial-prep heuristic.** The guard uses the *first* spatial
   preposition as the activity/place boundary. A request like "in Paris,
   take a horse ride" would place "horse" after "in" and return `''`. This
   pattern is unlikely in the app's free-text field but is a known gap.

2. **Category keywords (museum/park/exhibit) now also guarded.** This means
   "tour of the National Museum" → `''` (server decides). Previously it would
   return `museum`. This is the correct conservative behavior — the server's
   LLM intent analysis handles venue-name detection better than keyword
   matching.

3. **No NER / proper-noun detection.** The parser cannot distinguish "Horse"
   (animal) from "Horse" (place name) semantically. It relies purely on
   position relative to the spatial preposition. This is adequate for the
   app's role as a hint generator — the server is authoritative.
