# SUBMISSION — LOCAL-805: "<business> near <landmark>, <city>" routed to WALKING and lost the businesses

**Base:** subscribed @ `db3e8051` — `git merge-base --is-ancestor db3e8051 HEAD` exits 0 (verified before commit).
**Branch:** `LOCAL-805-near-landmark`

## The regression (since 788B/790/791)
"Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City" (3) was
delivered on the cloud on Oct 27 (wave 2) as 3 real spas (tour 465). After
788B/790/791 the same phrasing was routed to the WALKING path and scope-memory
rejected the nearby spas (LOCAL-800 submission note; P1 at 7e2db321 delivered 2/3
then 1/3).

Two independent causes, both reproduced deterministically before the fix:

1. **Routing.** `_classify_tour_category` scanned the generic walking keywords
   (`city`, `district`, `street`, `center`, …) BEFORE the LOCAL-791 business
   check. "…, District 1, Ho Chi Minh City" contains "district"/"city", so the
   request matched the walking default and returned `'walking'` — the places path
   (places_search / MAPS-FIRST) never ran.
   ```
   _classify_tour_category("Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City", "")
       → 'walking'     (before)   →   'restaurant'  (after)
   ```

2. **Containment scope.** Even once routed to places, the LLM intent returned
   `geographic_scope="Ben Thanh Market, District 1, Ho Chi Minh City"`,
   `scope_precision=DISTRICT`, so the PHASE 5.6 / D558 containment check treated
   the landmark as a BUILDING and dropped every real spa as "near Ben Thanh Market
   but not INSIDE the market" — CiCi International Spa, Saigon Heritage Spa, Temple
   Leaf Spa Land, Golden Lotus, Miu Miu Spa all rejected by scope-memory. This is
   the "scope-memory rejects the nearby spas" the LOCAL-800 note flagged.

## The fix

A request whose **SUBJECT** is a business/activity provider (massage, spa,
restaurant(s), café(s), coffee, bar(s), shop(s), school(s), gym(s), …) goes to the
PLACES path whatever follows it ("near X", "around X", "close to X", "in X"). The
landmark X is the **SEARCH CENTRE** (geocoded, ~1.5 km walkable radius, LOCAL-802
×2 widen once), **never a stop**, and **never a containment boundary**.

### `generate_tour_text.py`
- **`_business_subject_of_request(location)`** (new) — keys on the SUBJECT only:
  the text up to the first locative connector (`near`, `around`, `close to`,
  `next to`, `in`, `of`, `at`, …). The landmark after the connector is the search
  centre, so a business word trapped inside the landmark name ("Market" in "walk
  near Ben Thanh Market") cannot flip the request, and an explicit walking verb
  subject ("walk", "stroll", "hike") stays walking. True for a 'business' OR
  'dining' subject (both ride the maps-first/places path).
- **`_classify_tour_category`** — the business-subject check now runs right after
  the food-keyword scan and BEFORE the museum / specialized / generic-walking
  scans. This fixes the "District"/"City" mis-route AND the broader case where the
  LANDMARK name carries a keyword that belongs to another scan ("park" in "bars
  near Fenway Park", "garden" in "cafés near the Botanic Garden", "gallery" in
  "coffee near the National Gallery"). A genuine museum/specialized SUBJECT ("MFA",
  "botanical garden") still classes as landmark here and falls through to its own
  scan. The old LOCAL-791 whole-string business check (below the walking scan) is
  rebased onto the same subject helper so it, too, no longer misreads a landmark
  name.
- **`_scope_from_request`** (deterministic fallback) — for a business-near-landmark
  request it returns the LANDMARK as the search centre ("Massage and spa near Ben
  Thanh Market, District 1, HCMC" → "Ben Thanh Market, District 1, Ho Chi Minh
  City"; "coffee near Boston Common" → "Boston Common"), dropping the business
  words and connector. A walking subject is untouched.
- **`_near_landmark_enclosing_area(location)`** (new) + **`_resolve_scope_for_check`**
  — the stop-by-stop CONTAINMENT scope for a business-near-landmark request is the
  ENCLOSING AREA (the admin tail after the landmark — "District 1, Ho Chi Minh
  City"), never the landmark point. When there is no enclosing area ("coffee near
  Boston Common") the containment check is skipped entirely and the ~1.5 km radius
  bounds the result. The ONE-SCOPE-PER-TOUR invariant (LOCAL-591) is rebound to the
  enclosing area so it accepts the correction instead of clearing it. This is the
  fix for "scope-memory rejects the nearby spas".

### `places_search.py`
- **`LANDMARK` scope precision** (new) — a scope whose head is a point-landmark
  class word (market, square, common, park, cathedral, pagoda, temple, …) gets a
  tighter **~1.5 km** radius (`_LANDMARK_RADIUS_KM`), the walkable distance the
  ticket asks for. A known neighbourhood / region marker still wins first, so
  "Hyde Park" / "West Roxbury" stay NEIGHBOURHOOD. LOCAL-802's ×2 widening grows
  the landmark radius to ~3 km once before delivering fewer than requested.

### The landmark is never a stop
"near"/"around" is not a named-stop clause (`extract_named_places_from_clause`
only reads "including / featuring / with / such as …"), so the landmark is never
captured as a named-place or a named-anchor. Verified by unit test and by the live
run (Ben Thanh Market does not appear as a stop).

## Unit tests — `tests/test_local805_near_landmark.py` (38 tests, all pass)
```
python3 -m pytest tests/test_local805_near_landmark.py -q      # 38 passed
```
The exact ticket strings are covered:
- "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City" → places
- "coffee near Boston Common" → places
- "seafood restaurants around Mui Ne fishing village" → places
- "gyms near me, West Roxbury" → places (near-me unchanged)
- "walk near Ben Thanh Market" → **stays walking**

Plus: landmark-name keyword does not mislead (Fenway Park / Louvre / Grand Palace
/ Union Square); museum & specialized subjects unchanged; the landmark is the scope
centre; the landmark is NOT a stop; LANDMARK precision ⇒ 1.5 km, ×2 ⇒ 3 km, and a
known neighbourhood ending in a landmark word ("Hyde Park") is not misread; the
containment scope is the enclosing AREA (District 1, HCMC), and a point landmark
("Boston Common") has no containment boundary (radius only).

### Regression (only NEW failures count)
The affected modules' test files — LOCAL-485, 591, 802, 330, 285, 662, 788B, 779,
779B, 783, 790, 791, 800, 576, 3481, 751, d557, d558:
**482 passed, 2 skipped, 0 failures.**
Pre-existing failures on the baseline `db3e8051` (identical with the branch
stashed, NOT introduced here): `tests/test_local351_us_address_parsing.py`
(2 parenthetical-parse cases) and `tests/test_local359_scope_check_address.py`
(4 scope-memory state-pollution cases) — both fail the same way on the clean base.

## Live — OWN isolated container, `RESEARCH_BACKEND=serper`, Gemini OFF
Own postgres aliased `local805-postgres` on own network `local805_net`, the
`audioura-tour-generator:latest` image with this worktree mounted (so the live run
measures THIS code). The 14 shared `audioura-*` containers were never touched; the
isolated stack was torn down afterwards. Cheap arm (gpt-4.1-mini + serper, Gemini
credit depleted per LEAD note). `run_local805_container.py`.

**2 live tours (≤ 3). Total paid-API spend $0.4998 < $1.00 cap** (LiveRunMeter,
all providers combined): spa tour $0.2548 (openai $0.2168 + serper $0.0380),
coffee tour $0.2450 (openai $0.2230 + serper $0.0220).

Every delivered stop Serper-Places-checked for distance from the geocoded landmark
centre (the harness prints it; OK ≤ 1.5 km, wide ≤ 3 km after the ×2 widen):

**"Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City" (3)**
— routed to the PLACES path (log `[LOCAL-805] business/activity subject … → places
path`); centre = Ben Thanh Market (10.7725, 106.6980):
| stop | real spa | km from Ben Thanh Market |
|------|----------|--------------------------|
| CiCi International Spa | ✅ | 0.24 |
| The Spa by SOLÉA – Head Spa & Massage (District 1) | ✅ | 0.27 |

Delivered 2/3 (one short; the LLM spa pool was thin — the honest D616 shortfall
line is spoken). Before the fix this request routed to WALKING and delivered **0**
real spas; after, both delivered stops are real spas within ~0.25 km of the
landmark. The landmark itself is not a stop.

**"coffee near Boston Common" (3)** — routed to the PLACES path; centre = Boston
Common (42.3550, -71.0661):
| stop | real café | km from Boston Common |
|------|-----------|-----------------------|
| Caffe Nero | ✅ | 0.36 |
| George Howell Coffee | ✅ | 0.38 |
| Tatte Bakery & Cafe | ✅ | 1.65 (within the ×2 widen band ≤ 3 km) |

Delivered 3/3 real cafés. The landmark is not a stop.

Both delivered tours were stored as additive `is_test` rows in the ISOLATED DB
(ids 3, 4). No live DB written. No `DELETE`.

## Files
- `generate_tour_text.py` — `_business_subject_of_request`,
  `_near_landmark_enclosing_area`, business-subject routing in
  `_classify_tour_category`, landmark-centre scope in `_scope_from_request`,
  enclosing-area containment in `_resolve_scope_for_check`.
- `places_search.py` — `LANDMARK` precision + `_LANDMARK_RADIUS_KM` (~1.5 km).
- `tests/test_local805_near_landmark.py` (new, 38 tests).
- `run_local805_container.py` (new, isolated live-run harness with Serper distance
  check).

## Process
Committed to `LOCAL-805-near-landmark` with explicit file paths (no `git add -A`).
No `DELETE`. No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE,
`.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`,
GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md. Branched from HEAD (db3e8051),
never from `origin/*`.
