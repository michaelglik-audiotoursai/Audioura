# SUBMISSION_LOCAL-480.md — The Facility Tour (a fifth tour category)

**Branch:** `LOCAL-480-facility-category` · **Base:** storied (`c665d53`)
**Agent:** Mac Mini Kiro

## The verdict this answers

Michael, tour 423 (Logan), 2026-09-15:

> "…the stories are really good! … Unfortunately, most people would want
> something related to airport itself: airlines, counters, terminals, lost and
> found, children playgrounds, app such as Lyft and Uber pickup locations,
> parkings, museum exhibits, WiFi, electric outlets, etc. But stories are good,
> funny."

**The story engine is not the defect — stop selection is.** A traveller in
Terminal E has an errand, not a sightseeing afternoon. `tour_category=='walking'`
means "sightseeing on foot", so the generator produced a sightseer's list,
including "Boston Logan Airport Virtual Tour" — a thing you cannot stand next
to. **The prose gates and the story engine are untouched.**

## What was built

A fifth `tour_category`: **`facility`**, for venues people pass *through* with an
errand (airports, terminals, stations, hospitals, convention centres, stadiums,
campuses). Its stop list is a **need-spine**, not an interest ranking.

### 1. `facility_spine.py` (new module)

The need-spine, ordered by the sequence a traveller actually hits each need:

```
orient → terminal & gates → security → food & water → rest (seating, outlets,
WiFi, quiet) → kids → art & exhibits → lost and found → baggage → ground
transport (rideshare, taxi, rental, transit, parking)
```

`fill_need_spine(lat, lng, want)` walks the spine in order and fills each slot
with the nearest **named, mapped OSM object** carrying a real coordinate. It
takes the N highest-value **unmet** needs — findable or cut. An unmet slot (no
mapped object, no venue-site entry) does **not** consume budget, so ground
transport surfaces within N when higher slots are unmapped (at Logan, security /
kids / lost & found / baggage are not standalone named nodes; parking is — 46 of
them, incl. `Central Parking`, the rideshare pickup).

- **No second Overpass client.** `fill_need_spine` defaults its Overpass client
  to `osm_venue_facts._overpass_request` — the existing rate-limited client with
  retry/backoff. The `around:radius,lat,lng` query shape matches
  `amenities_near_service.py`.
- **The four categories OSM misses** (lost & found, kids' play, airline check-in
  counters, charging/WiFi as stops) are marked `venue_site_only` and fill from an
  injectable `venue_site_lookup` (the Tier-1 "venue's own site" source LOCAL-23
  established). When absent, those slots simply do not fill — **we never
  fabricate a stop.**
- Each `FacilityStop.source_line()` **names its source** (`OSM node/way/relation/<id>`
  or `venue_site`) for the per-stop log (AC2).

### 2. `_detect_facility_class` + classifier (generate_tour_text.py)

A narrow venue-class detector: a small set of unambiguous facility phrases
(`airport`, `train station`, `convention centre`, `university campus`, …), a
word-boundary match for single nouns (`terminal`, `hospital`, `stadium`,
`arena`, `fairgrounds`), and an IATA/airport-word signal. `_classify_tour_category`
consults it as the **highest** priority — above the explicit "walking tour"
phrase — because tour 423 arrived phrased as *"Walking tour around Logan
Airport"*. It is deliberately narrow: it returns **False** for *"Walking tour
around Cimiez District, Nice, France"* (AC3).

A **FACILITY GUARD** runs after category convergence and overrides any museum
flip a `venue_name` inference (S15/CLASSIFY-FIX) might have applied to
"Logan Airport".

### 3. Wiring into stop selection

A **FACILITY NEED-SPINE FILL** block (mirroring the LOCAL-30 deterministic-fill
pattern) geocodes the facility anchor, calls `fill_need_spine`, fills `poi_list`,
and sets `_facility_fill_used = True` to **skip the Phase 3A GPT sightseeing
call**. The Phase 3A GPT gates now read
`not _deterministic_fill_used and not _facility_fill_used`.

**Findable or cut (AC5):** after the fill, each stop is resolved through
`geocode_stops.resolve_poi` (LOCAL-471 `_geo_confidence`). A stop that comes back
`low` is **dropped, not downgraded**, and the drop is logged with its need and
reason. Facility is also excluded from the sightseeing replenisher so the
need-spine stays authoritative.

### 4. Stories stay, bound to the facility

No prose machinery changed. Facility `poi_list` is the same dict shape, so the
storied block and `generate_spine` (which falls back to the walking template for
`facility` via `select_spine_template`) attach one grounded story per stop
exactly as before. **No prose gate touched.**

## Break the spine (AC6)

`facility_spine.spine_filling_enabled()` reads a module flag `SPINE_FILLING_ENABLED`
and env `FACILITY_SPINE_DISABLED=1` on every call. When disabled,
`fill_need_spine` returns `[]`, `_facility_fill_used` stays `False`, and execution
**falls through to the ordinary walking Phase-3A GPT list** — the old sightseeing
behaviour. The test flips the flag and asserts the fallback.

```
=== SPINE ENABLED (green: need-spine fills, GPT skipped) ===
stops: [('orient','Terminal E'), ('terminal_gates','Gate E1B'), ('food_water','Dunkin'),
        ('rest','Air France Lounge'), ('art_exhibits','Boston Landing Mural'),
        ('ground_transport','Central Parking')]
count: 6 -> _facility_fill_used = True -> Phase 3A GPT SKIPPED

=== SPINE BROKEN (red: fill empty -> falls back to sightseeing GPT list) ===
stops: []
count: 0 -> _facility_fill_used stays False -> Phase 3A GPT sightseeing list runs
```

## Wiring proven separately from the function (LOCAL-465)

The `TestWiring` class asserts on `inspect.getsource(generate_tour_text)` — a
revert of the integration breaks these even though `facility_spine`'s own
functions still pass. Proof they are non-vacuous:

```
present in real source : True
present after revert   : False  <- wiring test would FAIL (red)
```

## Test output (D242 — real output, not exit=0)

`python3 -m pytest test_local480_facility_category.py -v`

```
TestFacilityClassification::test_ac1_logan_walking_phrasing_classifies_facility PASSED
TestFacilityClassification::test_ac3_cimiez_walking_tour_is_untouched          PASSED
TestFacilityClassification::test_detector_is_narrow_no_false_positives         PASSED
TestFacilityClassification::test_facility_words_and_iata                       PASSED
TestNeedSpineOrderAndSources::test_ac1_six_facility_stops_with_coords_and_the_required_kinds PASSED
TestNeedSpineOrderAndSources::test_ac2_each_stop_source_is_named_in_the_log_line PASSED
TestNeedSpineOrderAndSources::test_gate_number_becomes_a_findable_name          PASSED
TestNeedSpineOrderAndSources::test_need_order_is_the_sequence_a_traveller_hits  PASSED
TestBreakTheSpineFallback::test_env_flag_disables_filling                       PASSED
TestBreakTheSpineFallback::test_module_flag_disables_filling                    PASSED
TestBreakTheSpineFallback::test_red_green_demonstration                         PASSED
TestFindableOrCutRule::test_low_confidence_stop_is_dropped_high_is_kept         PASSED
TestFindableOrCutRule::test_resolve_poi_marks_low_when_uncorroborated           PASSED
TestWiring::test_classifier_wires_the_facility_detector                         PASSED
TestWiring::test_facility_branch_calls_fill_need_spine                          PASSED
TestWiring::test_facility_branch_is_gated_on_the_category                       PASSED
TestWiring::test_facility_excluded_from_sightseeing_replenishment               PASSED
TestWiring::test_facility_fill_sets_skip_flag_and_gpt_call_respects_it          PASSED
TestWiring::test_facility_guard_overrides_museum_flip                           PASSED
TestWiring::test_low_confidence_facility_stop_is_dropped_in_wiring              PASSED
======================== 20 passed, 1 warning in 1.02s =========================
```

### Regression — the Cimiez walking tour is unaffected (AC3)

`python3 -m pytest tests/test_local474_empty_tour_type.py -v` → **13 passed.**
The classifier still returns `restaurant`/`museum`/`walking` exactly as before,
and `_classify_tour_category("Walking tour around Cimiez District, Nice, France", "")`
returns `walking`. The Cimiez fixture (`TOUR_CIMIEZ_WALKING_20260830.md`) is
`Tour-Category: walking`; nothing in the facility path fires for it.

## Acceptance criteria

| # | criterion | evidence |
|---|---|---|
| 1 | Logan, 6 stops → six *facility* stops with real coords (terminal, ground transport, food/water, art), no "Virtual Tour" | `test_ac1_*`, break-the-spine demo |
| 2 | Every stop is in OSM (or venue site), source named in its log line | `test_ac2_each_stop_source_is_named_in_the_log_line`, `FacilityStop.source_line()` |
| 3 | A normal walking tour is unaffected (Cimiez) | `test_ac3_*`, `test_detector_is_narrow_*`, LOCAL-474 13/13 |
| 4 | Each facility stop carries a story tied to that facility | storied block + `select_spine_template` fallback, no prose change |
| 5 | A `low`-confidence stop is dropped and logged | `test_low_confidence_*`, `DROPPED facility stop` in wiring |
| 6 | Break the spine → falls back to the old sightseeing list (red) | `TestBreakTheSpineFallback`, red/green demo |

## Files

- `facility_spine.py` — new: the need-spine + OSM query per slot.
- `generate_tour_text.py` — `_detect_facility_class`, `facility` in the classifier,
  the FACILITY GUARD, the FACILITY NEED-SPINE FILL block, Phase-3A skip gates,
  replenisher exclusion. **No prose gate or story-engine change.**
- `test_local480_facility_category.py` — new: 20 tests, six ACs + LOCAL-465 wiring.

## Notes

- Michael is testing on Preview: **no container was rebuilt or restarted, and
  nothing was deployed.** All verification is offline (mocked Overpass; no
  network; no OpenAI).
- `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `unglossed_reference_gate.py`, and
  the other protected files were not touched.
