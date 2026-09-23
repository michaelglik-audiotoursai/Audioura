# SUBMISSION_LOCAL-3485.md — A Church Is Not A Museum

**Branch:** `LOCAL-3485-venue-class-routing` · **Base:** storied (`e1341e6`)
**Agent:** Mac Mini Kiro

## The verdict this answers

Michael, build 26, 2026-09-16, requested a 2-stop tour of *"Our Lady Help of
Christians, Catholic Church in Newton MA"* — a real, large, historic parish
church at 573 Washington St. The request ran 31 s and was rejected:

> "This venue could not be verified with enough works to generate a quality tour."

The reproduced trace shows the church was **routed down the MUSEUM pipeline**. It
was asked for *artworks*; having none catalogued, the model answered with the two
most famous religious artworks on earth — the **Sistine Chapel Ceiling
(6,700 km away)** and **The Last Supper (Milan)** — and the museum gate (working
exactly as designed) clean-failed the run `unresolvable`, because a parish church
has no Wikidata artwork inventory. The gate is correct; it was pointed at the
wrong kind of venue.

## What this task is

This is a re-run of the LOCAL-485 work whose **deliverable file was lost** when a
prior worktree was pruned before committing. The code fix itself is present in the
base tree (commits `fd5aa5c` … and the merged `LOCAL-485-venue-class-routing`,
all ancestors of `e1341e6`). My work here: **re-verify every acceptance criterion
against the committed code with real test output, demonstrate the routing going
red on breakage, and commit the surviving deliverable** so it is not lost again.

Base is correct and verified:

```
$ git log --oneline -1
e1341e6 Cap one person to two stops; never empty a stop doing it
$ git merge-base --is-ancestor e1341e6 HEAD ; echo $?
0   (BASE OK)
```

## The two defects, and where each is fixed

### 1. Venue class decides the stop type — a church's stops are places, not works

`generate_tour_text.py` routes the knowledge-fetch focus by category:

```python
_kf_focus = 'object' if tour_category == 'museum' else 'place'   # line 11691
```

A museum's unit is a **catalogued object** (Wikidata-verifiable); a church's unit
is a **place with history** — nave, bell tower, war memorial, parish hall,
cemetery — verifiable the way a walking tour's stops are. The fix detects the
**venue class** and routes a worship/civic building to the place-based (`walking`)
path, so `_kf_focus` becomes `'place'` and the artwork prompt is never issued.
That is why the Sistine Chapel / Last Supper fabrication can no longer occur: it
was a product of the object/artwork prompt the museum path runs (AC2).

**One shared detector (AC5).** `_detect_venue_class(location, tour_type)` returns
`'facility'` (LOCAL-480), `'worship_civic'` (this task), or `None`.
`_detect_facility_class` is a thin wrapper delegating to it — not a second copy:

```python
def _detect_facility_class(location, tour_type=""):
    return _detect_venue_class(location, tour_type) == 'facility'
```

The worship/civic class is word-boundary anchored
(`church|cathedral|basilica|chapel|abbey|minster|priory|monastery|convent|…|
synagogue|mosque|temple|…|courthouse|town hall|city hall|…`), so it fires only
when the request **names** such a venue — never on a walking tour that merely
passes a church, and never inside a larger word (`Churchill`, `temperature`).
`facility` takes priority (an airport chapel is a facility errand).

Routing points fixed in `generate_tour_text.py`:
- **S15 force-museum** excludes worship/civic (`and not _detect_worship_civic_class(...)`).
- **`_classify_tour_category`** routes a worship/civic request to `walking`, above the museum keyword scan.
- **VENUE-CLASS GUARD** pulls a `museum` verdict back to `walking` for a worship/civic, non-facility venue.
- **CLASSIFY-FIX** — worship words (`church`, `cathedral`, `basilica`, `temple`, `abbey`) were removed from `_VENUE_WORDS_FOR_CLASSIFY`, the set that flips `walking → museum`.

Direct verification of the reported request and the regressions:

```
$ python3 - (against the committed module)
detect_venue_class:          worship_civic
classify_tour_category:      walking          <- place path, NOT museum
detect_facility_class:       False
detect_worship_civic_class:  True
MFA classify:                museum           <- real museum regression intact
Cimiez classify:             walking          <- approved tour unchanged
Cimiez venue_class:          None             <- names no venue class
```

### 2. The catch-all error message was lying about the cause

`generate_tour_text_service.py` gave every unclassified failure the museum
"not enough works" string (the `else` branch). Michael spent a day believing a
quota had blocked him. Now `thin_evidence` has its **own** branch (line ~198),
and the catch-all `else` no longer borrows the museum wording. Both **name the
venue** and point at a request shape that can succeed:

> "We could not find enough verified material about "\<venue\>" to build a tour.
> Try a broader request — for example a walking tour of the surrounding
> neighbourhood."

Both `thin_evidence` clean-fail sites in `generate_tour_text.py` carry the venue:

```
7726:  "error_type": "thin_evidence",
7735:  "venue": _museum_venue_name or location,
7785:  "error_type": "thin_evidence",
7793:  "venue": _museum_venue_name or location,
```

## Break the routing and show a test go red (AC6)

I neutered the worship/civic branch of `_detect_venue_class` (forced it never to
match) and re-ran the suite. The church regressed to the **build-26 defect**
(`'museum' != 'walking'`) and **5 tests went red**:

```
def test_break_routing_regresses_to_museum(self):
>       self.assertEqual(route_category(self.LOC, ...), 'walking')
E       AssertionError: 'museum' != 'walking'

FAILED ... TestVenueClassDetector::test_cathedral_..._townhall
FAILED ... TestVenueClassDetector::test_church_is_worship_civic
FAILED ... TestChurchRoutesToPlaceNotMuseum::test_full_route_walking_even_when_s15_would_fire
FAILED ... TestChurchRoutesToPlaceNotMuseum::test_venue_class_guard_catches_a_forced_museum
FAILED ... TestBreakTheRoutingGoesRed::test_break_routing_regresses_to_museum
5 failed, 16 passed
```

The file was restored immediately afterward; `git diff --stat` is empty and the
suite is green again (below). The routing is load-bearing: with it, the church is
`walking`; without it, `museum` — the Sistine Chapel path.

## Test output (D242 — real output, not exit=0)

`python3 -m pytest test_local485_venue_class_routing.py -v`

```
TestVenueClassDetector::test_cathedral_basilica_synagogue_mosque_temple_courthouse_townhall PASSED
TestVenueClassDetector::test_church_is_worship_civic                       PASSED
TestVenueClassDetector::test_cimiez_is_not_a_venue_class                   PASSED
TestVenueClassDetector::test_facility_takes_priority_over_worship          PASSED
TestVenueClassDetector::test_no_false_match_inside_larger_words            PASSED
TestVenueClassDetector::test_plain_museum_is_not_worship_civic             PASSED
TestSharedMechanism::test_shared_mechanism_one_detector                    PASSED
TestChurchRoutesToPlaceNotMuseum::test_classify_returns_walking            PASSED
TestChurchRoutesToPlaceNotMuseum::test_full_route_walking_even_when_s15_would_fire PASSED
TestChurchRoutesToPlaceNotMuseum::test_full_route_walking_when_intent_failed PASSED
TestChurchRoutesToPlaceNotMuseum::test_venue_class_guard_catches_a_forced_museum PASSED
TestMuseumRegression::test_cimiez_walking_tour_unchanged                   PASSED
TestMuseumRegression::test_museum_full_route_stays_museum                  PASSED
TestMuseumRegression::test_real_museums_route_to_museum                    PASSED
TestWiringSourceAssertions::test_classifier_routes_worship_civic_to_place  PASSED
TestWiringSourceAssertions::test_s15_excludes_worship_civic                PASSED
TestWiringSourceAssertions::test_venue_class_guard_present                 PASSED
TestWiringSourceAssertions::test_worship_civic_words_removed_from_museum_flip PASSED
TestBreakTheRoutingGoesRed::test_break_routing_regresses_to_museum         PASSED
TestServiceMessageNamesVenue::test_evidence_dict_carries_venue_name        PASSED
TestServiceMessageNamesVenue::test_thin_evidence_branch_exists_and_is_not_the_catchall PASSED
======================== 21 passed, 1 warning in 0.25s =========================
```

Regressions (AC3, AC5):

```
$ python3 -m pytest tests/test_local474_empty_tour_type.py -q   →  13 passed
$ python3 -m pytest test_local480_facility_category.py -q       →  20 passed
```

LOCAL-474 keeps `_classify_tour_category('Walking tour around Cimiez District,
Nice, France', '')` returning `walking`; LOCAL-480 confirms the shared detector
still classifies airports/terminals/hospitals as `facility` — the church change
did not disturb it.

## Acceptance criteria

| # | criterion | evidence |
|---|---|---|
| 1 | Church request produces a place-based tour, not a museum clean-fail | `classify_tour_category → walking`; `TestChurchRoutesToPlaceNotMuseum` (4 tests) |
| 2 | No stop outside Newton; Sistine Chapel / Last Supper never appear | `_kf_focus='place'` on the walking path — the artwork/object prompt is never issued; church no longer enters the museum pipeline |
| 3 | A genuine museum still routes to museum; Cimiez stop list unchanged | `MFA/Louvre/Met → museum`; `test_cimiez_walking_tour_unchanged`; LOCAL-474 13/13 |
| 4 | A materially-empty venue fails with the `thin_evidence` message naming the venue | `thin_evidence` branch + venue-named message; both clean-fail dicts carry `"venue"` |
| 5 | Venue-class detector shared with LOCAL-480, not a second copy | `_detect_facility_class` delegates to `_detect_venue_class`; `test_shared_mechanism_one_detector`; LOCAL-480 20/20 |
| 6 | Break the routing → a test goes red | broke the detector → 5 red incl. church→`museum`; restored → 21 green |

## Notes

- **The museum gate was not weakened.** The fix routes *around* it (worship/civic
  → place path); the gate's Wikidata/SPARQL bar is untouched. That bar is what
  stopped the Sistine Chapel reaching a listener in Newton.
- Michael is field-testing build 26: **no container was rebuilt or restarted, and
  nothing was deployed.** All verification is offline.
- Protected files (`DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
  `.continuous_dev/STATUS.md`, `BUILD_NUMBERS.md`, `PENDING_REMINDERS.md`) were
  not touched.

## Files

- `generate_tour_text.py` — `_detect_venue_class` (shared), `_detect_worship_civic_class`, classifier routing, S15 exclusion, VENUE-CLASS GUARD, CLASSIFY-FIX word removal, `"venue"` on both `thin_evidence` clean-fails. (present in base `e1341e6`)
- `generate_tour_text_service.py` — `thin_evidence` branch + venue-named catch-all. (present in base `e1341e6`)
- `test_local485_venue_class_routing.py` — 21 tests, six ACs. (present in base `e1341e6`)
- `SUBMISSION_LOCAL-3485.md` — this file (the lost deliverable, re-created and committed).
