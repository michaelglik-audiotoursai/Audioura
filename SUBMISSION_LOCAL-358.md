##### READY FOR REVIEW

**Task:** LOCAL-358  
**Branch:** `kiro/local358-app-tour-type-transport`  
**Commit:** `fe515bb`  
**Base:** `storied`

---

## Summary

Fixed the app's tour request parser that caused Michael's "biking tour in Norwood MA" to send `tour_type='museum'` to the server, producing museum stops 25 miles away.

Three defects addressed:
1. **Transport modes unrecognized** → added all modes from server's `_TRANSPORT_MODE_KEYWORDS`
2. **Order-dependency** → transport checked FIRST (it's what the tour *is*); place-name nouns checked after
3. **Substring false positives** → word-boundary regex prevents `contains('walk')` matching inside 'boardwalk'
4. **Wrong default** → changed from `'museum'` to `''` (empty string = no signal to server)

---

## Files Changed

| File | Change |
|------|--------|
| `audio_tour_app/lib/utils/tour_request_parser.dart` | Rewrote parser: transport-first ordering, word-boundary regex, empty default, early-return style |
| `audio_tour_app/test/tour_request_parser_test.dart` | 40 tests: LEAD bounce failures, acceptance inputs, substring protection, default behavior |

---

## Verification Evidence

### flutter analyze
```
Analyzing tour_request_parser.dart...
No issues found! (ran in 0.3s)
```

### flutter test (40 parser tests pass)
```
00:00 +40: All tests passed!
```
(56 total including navigation_service_test.dart; 2 pre-existing failures in widget_test.dart from wrong package name)

### Parse results for required inputs
```
  'biking tour in Norwood MA' → tour_type='biking'
  'dog sledding tour in Big Lake AK' → tour_type='dog sledding'
  'walking tour of Vieux Nice' → tour_type='walking'
  'museum tour of the Louvre' → tour_type='museum'
  'camel tour in Abu Dhabi' → tour_type='camel'
```

### LEAD bounce inputs (previously failed, now correct)
```
  'biking tour in Central Park' → tour_type='biking'       (was: park)
  'cycling tour of Hyde Park' → tour_type='biking'         (was: park)
  'horseback tour of the park' → tour_type='horseback'     (was: park)
  'bike tour along the boardwalk' → tour_type='biking'     (was: walking)
```

### Substring protection (word-boundary prevents false positives)
```
  'tour along the boardwalk' → tour_type='(empty)'     (not walking)
  'tour of Walkerville' → tour_type='(empty)'          (not walking)
  'tour of the sidewalk district' → tour_type='(empty)' (not walking)
```

### No-signal default (server decides)
```
  'tour of the Louvre' → tour_type='(empty)'
  'tour of the Uffizi' → tour_type='(empty)'
  'tour of downtown Boston' → tour_type='(empty)'
```

### D242 compliance — tests fail against old parser
Old parser (museum default, no transport modes):
```
  [FAIL] 'biking tour in Norwood MA' → 'museum' (expected 'biking')
  [FAIL] 'dog sledding tour in Big Lake AK' → 'museum' (expected 'dog sledding')
  [FAIL] 'camel tour in Abu Dhabi' → 'museum' (expected 'camel')
  [FAIL] 'biking tour in Central Park' → 'park' (expected 'biking')
  [FAIL] 'cycling tour of Hyde Park' → 'park' (expected 'biking')
  [FAIL] 'horseback tour of the park' → 'park' (expected 'horseback')
  [FAIL] 'bike tour along the boardwalk' → 'walking' (expected 'biking')
```

Round-1 parser (LEAD bounce — transport after park/walk):
```
  [FAIL] 'biking tour in Central Park' → 'park' (expected 'biking')
  [FAIL] 'cycling tour of Hyde Park' → 'park' (expected 'biking')
  [FAIL] 'horseback tour of the park' → 'park' (expected 'horseback')
  [FAIL] 'bike tour along the boardwalk' → 'walking' (expected 'biking')
```

---

## Design Decisions

### Why transport modes first
Transport describes what the tour IS (the mode of travel). 'park', 'museum', 'exhibit' can appear as place names in any tour. "Biking tour in Central Park" is unambiguously a biking tour. Checking transport first ensures mode-of-travel always wins over incidental nouns.

### Why empty string default (not 'walking')
LEAD verified: `'tour of the Louvre' tour_type='walking'` → category `walking` on server. The server's `_classify_tour_category` returns 'walking' when nothing matches — so sending 'walking' is the same as sending nothing. But the `_effective_tour_type` touchpoints (line 3706/3714) pass `tour_type` to `_classify_tour_category` only when `transport_mode == 'on_foot'` and `_pre_category` is not restaurant/specialized. An empty string:
- Does not trigger museum_keywords (`'museum' in ''` → false)
- Does not trigger any other keyword list
- Lets the server's intent analysis (S15 venue_name promotion) handle bare venue requests
- Is explicitly documented as "no signal" at the `_effective_tour_type` touchpoints

### Why 'dog sledding' not 'dog_sledding'
LEAD noted line 7123 builds `"focusing on {tour_type}"`. While this only fires in the museum/exhibit branch (irrelevant for transport tours since `_effective_tour_type` is blanked), using a readable phrase is defensive against future prompt construction that might interpolate tour_type.

### Order-dependency assessment
The remaining order-dependent case: "walking tour of the museum quarter" hits `walking` first. This is CORRECT — the user explicitly said "walking tour"; "museum" in "museum quarter" is a place descriptor, not a tour type. Transport-first + category-second is the right priority.

---

## Limitations

- **On-device behaviour is unverified.** No simulator or device available. `flutter analyze` and `flutter test` are the ceiling.
- **Server integration untested.** Cannot run the pipeline (`OPENAI_API_KEY` not in environment). LEAD must regenerate a Norwood biking tour end-to-end with `DISABLE_TOUR_CACHE=1` and `DATABASE_URL=...` to confirm the fix reaches correct stops.
- **No container rebuilt.** Server code untouched.
- The `tour_generator_screen.dart` pre-existing warnings (unused imports/fields) are not addressed — they are unrelated to this change.

---

## git status
```
$ git status --short
(clean)
```

## git rev-list
```
$ git rev-list --count storied..HEAD
1
```
