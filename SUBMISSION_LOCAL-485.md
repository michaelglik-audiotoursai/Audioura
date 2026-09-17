# SUBMISSION_LOCAL-485.md — A Church Is Not A Museum

**Branch:** `LOCAL-485-venue-class-routing` · **Base:** storied (`407c2c1`)
**Agent:** Mac Mini Kiro

## The report this answers

Michael, build 26, 2026-09-16, requested a 2-stop tour of **"Our Lady Help of
Christians, Catholic Church in Newton MA"** — a real, large, historic parish
church at 573 Washington St. The request was accepted, ran 31 seconds, and was
rejected with *"This venue could not be verified with enough works to generate a
quality tour."*

The trace showed the church routed down the **museum** pipeline. Asked for
*artworks* and having none catalogued, the model answered with the two most
famous religious artworks on earth — the **Sistine Chapel Ceiling** (6,700 km
away) and **The Last Supper** (Milan) — and the museum gate, working exactly as
designed, clean-failed the run `unresolvable` because a parish church has no
Wikidata artwork inventory.

**The museum gate is correct. It was being pointed at the wrong kind of venue.**
This is a routing problem, not a data problem — the proof is that Michael's
approved Cimiez walking tour already includes Cimiez Monastery (a church, in a
walking tour, that worked). The place-based path can see the material; the museum
path cannot.

## Root cause

A church reached `tour_category == 'museum'` through two upstream flips in
`generate_tour_text()`:

- **S15 force-museum**: an inferred `venue_name` + `on_foot` forced museum.
- **CLASSIFY-FIX**: `_VENUE_WORDS_FOR_CLASSIFY` contained `church`, `cathedral`,
  `basilica`, `temple`, `abbey` — so a walking classification was flipped to
  museum on the venue word alone.

Once `tour_category == 'museum'`, the `if tour_category == 'museum' and
_museum_venue_name:` block ran D1v2 in-collection verification, found 0 canonical
titles, and clean-failed at `_d1v2_result.tier == 'unresolvable'` — the
`thin_evidence` evidence dict the report captured.

## Defect 1 — venue class must decide the stop type

A museum's unit is a **catalogued object** (Wikidata-verifiable). A worship/civic
building's unit is a **place with history** — the nave, the bell tower, the war
memorial, the parish hall, the cemetery — verifiable the way a walking tour's
stops are. So: detect the venue class and route accordingly.

### One shared mechanism (AC5)

This is the same family as **D563 / LOCAL-480** (the `facility` category). Rather
than add a second detector, I introduced a single primitive and expressed both
classes through it:

```
_detect_venue_class(location, tour_type) -> 'facility' | 'worship_civic' | None
    _detect_facility_class(...)        = (_detect_venue_class(...) == 'facility')     # LOCAL-480's seam
    _detect_worship_civic_class(...)   = (_detect_venue_class(...) == 'worship_civic') # LOCAL-485
```

`_detect_facility_class` — the exact name LOCAL-480's classifier, FACILITY GUARD,
and tests reference — is now a thin wrapper over the shared detector. When the two
branches merge, they converge on **one function**, not two parallel copies. A
source assertion (`test_shared_mechanism_one_detector`) fails if the wrapper ever
stops delegating.

`facility` takes priority over `worship_civic` (an airport chapel is a facility
errand, not a worship-tour venue).

### Routing (place-based path, not a new category)

The task says to route a church to the **place** path — "the same corpus the
walking tour already uses successfully." So `worship_civic` routes to `'walking'`,
the proven place-based path, rather than inventing a new template with no stop
generator behind it. Three coordinated changes in `generate_tour_text.py`:

1. `_classify_tour_category` returns `'walking'` for a non-facility worship/civic
   venue, above the museum keyword scan.
2. S15 force-museum now excludes worship/civic venues (`and not
   _detect_worship_civic_class(...)`).
3. `church/cathedral/basilica/temple/abbey` **removed** from
   `_VENUE_WORDS_FOR_CLASSIFY`.
4. A **VENUE-CLASS GUARD** runs after category convergence: if anything upstream
   still set `museum` on a worship/civic (non-facility) venue, it is pulled back
   to `walking`. This is the load-bearing hard stop and the seam the
   break-the-routing test flips.

**The museum gate was not touched or weakened.** A church simply never enters it.

## Defect 2 — the honest, venue-named error message

`generate_tour_text_service.py` had `exhibition_closed` and `exhibition_not_found`
messages, then an `else` catch-all telling every other failure it lacked artworks
— including `thin_evidence`, whether or not artworks were ever relevant. Added a
dedicated `thin_evidence` branch that names the venue:

> *We could not find enough verified material about "&lt;venue&gt;" to build a
> tour. Try a broader request — for example a walking tour of the surrounding
> neighbourhood.*

To name the venue, both `thin_evidence` clean-fail sites in `generate_tour_text.py`
now carry `"venue": _museum_venue_name or location` in `_LAST_CLEAN_FAIL_EVIDENCE`.

## Why acceptance criteria hold

1. **Church produces a tour with places at/around it** — it now routes to the
   place-based (walking) path (`test_full_route_walking_even_when_s15_would_fire`),
   the same path the Cimiez tour uses.
2. **No stop outside Newton — Sistine Chapel/Last Supper never appear** — those
   were artifacts of the museum artwork prompt, which the church no longer reaches.
   The scope/route machinery on the place path constrains stops to the venue's
   locale, exactly as it already does for walking tours.
3. **Genuine museum still routes to museum; Cimiez unchanged** —
   `test_real_museums_route_to_museum`, `test_museum_full_route_stays_museum`,
   `test_cimiez_walking_tour_unchanged` (detector returns `None`, category stays
   `walking`).
4. **A venue with genuinely no material still fails, with the venue-named
   thin_evidence message** — `test_thin_evidence_branch_exists_and_is_not_the_catchall`,
   `test_evidence_dict_carries_venue_name`.
5. **Shared detector, not a second copy** — `test_shared_mechanism_one_detector`.
6. **Break the routing, show a test go red** — `TestBreakTheRoutingGoesRed`, plus
   the live demonstration below.

## Tests — real output (D242)

`python3 -m unittest test_local485_venue_class_routing -v`

```
test_break_routing_regresses_to_museum (...TestBreakTheRoutingGoesRed) ... ok
test_classify_returns_walking (...TestChurchRoutesToPlaceNotMuseum) ... ok
test_full_route_walking_even_when_s15_would_fire (...TestChurchRoutesToPlaceNotMuseum) ... ok
test_full_route_walking_when_intent_failed (...TestChurchRoutesToPlaceNotMuseum) ... ok
test_venue_class_guard_catches_a_forced_museum (...TestChurchRoutesToPlaceNotMuseum) ... ok
test_cimiez_walking_tour_unchanged (...TestMuseumRegression) ... ok
test_museum_full_route_stays_museum (...TestMuseumRegression) ... ok
test_real_museums_route_to_museum (...TestMuseumRegression) ... ok
test_evidence_dict_carries_venue_name (...TestServiceMessageNamesVenue) ... ok
test_thin_evidence_branch_exists_and_is_not_the_catchall (...TestServiceMessageNamesVenue) ... ok
test_shared_mechanism_one_detector (...TestSharedMechanism) ... ok
test_cathedral_basilica_synagogue_mosque_temple_courthouse_townhall (...TestVenueClassDetector) ... ok
test_church_is_worship_civic (...TestVenueClassDetector) ... ok
test_cimiez_is_not_a_venue_class (...TestVenueClassDetector) ... ok
test_facility_takes_priority_over_worship (...TestVenueClassDetector) ... ok
test_no_false_match_inside_larger_words (...TestVenueClassDetector) ... ok
test_plain_museum_is_not_worship_civic (...TestVenueClassDetector) ... ok
test_classifier_routes_worship_civic_to_place (...TestWiringSourceAssertions) ... ok
test_s15_excludes_worship_civic (...TestWiringSourceAssertions) ... ok
test_venue_class_guard_present (...TestWiringSourceAssertions) ... ok
test_worship_civic_words_removed_from_museum_flip (...TestWiringSourceAssertions) ... ok

----------------------------------------------------------------------
Ran 21 tests in 0.007s

OK
```

### AC6 — the routing broken, tests go RED

Neutering `_detect_worship_civic_class` (simulating a revert of the routing) and
re-running the church-routing assertions:

```
test_full_route_walking_even_when_s15_would_fire ... FAIL
test_classify_returns_walking ... ok
test_venue_class_guard_catches_a_forced_museum ... FAIL

AssertionError: 'museum' != 'walking'
 : church must route to the place-based path, not the museum pipeline

Ran 3 tests in 0.001s
FAILED (failures=2)
```

The church regresses straight back to `'museum'` — the exact build-26 defect —
proving the routing is load-bearing. (`test_classify_returns_walking` stays green
because the classifier's museum keyword scan never matched "church"; the church
defect lived in S15/CLASSIFY-FIX, which the VENUE-CLASS GUARD now catches.)

### Detector behaviour (direct)

```
worship_civic | cat=walking    | tour of Our Lady Help of Christians Catholic Church located in Newton MA
worship_civic | cat=walking    | St. Patrick's Cathedral, New York
worship_civic | cat=walking    | Temple Emanu-El, Manhattan
worship_civic | cat=walking    | Middlesex County Courthouse, Cambridge MA
None          | cat=walking    | Walking tour around Cimiez District, Nice, France
None          | cat=museum     | Museum of Fine Arts, Boston
None          | cat=museum     | Louvre Museum
facility      | (LOCAL-480)    | Logan Airport
None          | cat=restaurant | restaurant tour in Nice
```

## Files changed

- `generate_tour_text.py` — shared `_detect_venue_class` + wrappers; worship/civic
  routing in `_classify_tour_category`; S15 worship/civic exclusion; worship/civic
  words removed from `_VENUE_WORDS_FOR_CLASSIFY`; VENUE-CLASS GUARD; `"venue"` key
  on both `thin_evidence` clean-fail dicts.
- `generate_tour_text_service.py` — dedicated `thin_evidence` message naming the
  venue.
- `test_local485_venue_class_routing.py` — 21 tests, six ACs + LOCAL-465-style
  source assertions so a revert of the wiring goes red.

## Process notes

- Base verified: `git merge-base --is-ancestor 407c2c1 HEAD` → exit 0.
- **No container rebuilt or restarted; nothing deployed.** Michael is field-testing
  build 26. Offline verification only.
- No prose gate or story-engine change. The museum gate's bar was not lowered.
- LOCAL-480 (`facility`) lives on the sibling branch `LOCAL-480-facility-category`,
  unmerged into `storied`. This change is written so the two converge on the single
  `_detect_venue_class` at merge time rather than duplicating detectors.
