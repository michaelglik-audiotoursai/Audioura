# SUBMISSION — LOCAL-481: A stop must be a real, named, findable place

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-481-stop-must-be-a-place` · **Base:** storied (92dac9e)

`git merge-base --is-ancestor 92dac9e HEAD` → exit 0 (verified before the first commit).

---

## The defect (tour 423, Logan Airport, 2026-09-15)

```
Boston Bruins Bar                    42.3656, -71.0188
Art Exhibits at Logan Airport        42.3656, -71.0173
Boston Logan Airport Virtual Tour    42.3656, -71.0096
Boston Logan Airport History Walk    42.3656, -71.0189
```

Two independent faults, both present here, neither caught by anything that runs today:

1. **Centroid collapse.** All four share latitude `42.3656` exactly — the venue centroid with
   the longitude jittered. That is not four independently located places.
2. **Non-places.** Three of the four names are not somewhere a listener can stand:
   `Art Exhibits at Logan Airport` is a *category*, `…Virtual Tour` and `…History Walk` are
   *formats* — the generator naming its own medium as a destination.

LOCAL-471's confidence signal already knew these coordinates were weak; the missing piece was
that **nothing rejects a stop for not being a place.** This task adds that, and the coordinate
collapse detector that would have caught all four before a word of narration was written.

---

## Part 1 — centroid-collapse detector (`geocode_stops.py`)

Two new deterministic functions, appended to `geocode_stops.py` (which already owns
`resolve_poi`):

- **`find_centroid_collapse(poi_list, category)`** — groups stops by latitude and by longitude
  rounded to 4 dp (≈ 11 m). Two or more stops sharing either axis is a collision. Returns the
  colliding indices and the groups. No network, no mutation.
- **`repair_centroid_collapse(poi_list, tour_location, category, tour_anchor, resolver)`** — runs
  the detector, sends **exactly the colliding stops** back through `resolve_poi` (the resolver is
  injectable for tests), then re-runs the detector to split `cured_indices` (moved off the shared
  line) from `still_colliding`. Repair over deletion: a stop that re-resolves is kept; the caller
  drops only those that stay collapsed **and** are not real places.

### Scope — which categories (acceptance criterion 3)

`COLLISION_CATEGORIES = {walking, driving, biking, cycling, restaurant, specialized, facility,
bus, boat, road_trip}`. These are tours whose stops are **distinct physical destinations** you
travel between. **`museum` is exempt** — two artworks in one room legitimately share a coordinate
and *should*. `find_centroid_collapse` returns `action: "none"` for any category outside the set,
so co-located museum objects are never flagged. Tour 423 is a `facility` tour (D563), which is in
the set. The test `test_co_located_artworks_WOULD_collide_without_the_scope` proves the scope is
load-bearing: the identical two points collide under `walking` and are clean under `museum`.

---

## Part 2 — reject category labels and non-places (`place_shape.py`)

New module, deterministic — whether a name is a category or a format is a fact about the words, in
the same spirit as D536's waypoint rule (and D526/D528 record what happens when a rule of this
shape is handed to a model). `classify_stop_name(name)` returns
`{is_place, shape ∈ {place, format, category}, reason}`.

- **Format** (`is_nonplace_format`): the name's semantic HEAD is a format word
  (`tour/walk/guide/timeline/route/…`) qualified as a *medium*
  (`virtual/self-guided/audio/history/walking/…`), or a standalone non-place phrase
  (`Virtual Tour`, `Audio Guide`, `Timeline`). A bare `Tour` is also caught.
- **Category** (`is_category_label`): a **plural / collection head noun** (`exhibits`,
  `restaurants`, `museums`, `shops`, …) followed by a **containing preposition**
  (`at/in/on/of/by/around/near/…`) and a place. "Art Exhibits at Logan Airport" → which exhibit?

### Conservative by design (acceptance criterion 2)

Flagging a real place is a bounce. Every rule fires only on an unambiguous shape:

- A **singular** proper head is never a category, even with a preposition: `Museum of Modern Art`,
  `Cathedral of Notre-Dame`, `Statue of Liberty`, `Church of the Gesù`, `House on the Rock` all
  survive. Only a *plural/collection* head triggers the category rule.
- A format word rejects only as the **head qualified as a medium**: `History Walk` (format) vs
  `Freedom Trail` / `Cliff Walk` / `Appalachian Trail` (real named routes, survive).
- `_CATEGORY_EXCEPTIONS` allowlists `roman ruins of cemenelum` (the Cimiez stop whose head noun
  "ruins" is plural but names one specific archaeological site).

The full approved Cimiez list (`TOUR_CIMIEZ_WALKING_20260830.md`) — Matisse Museum, Musée Matisse,
Cimiez Monastery, Musée Marc Chagall, Villa Leopolda, Roman Ruins of Cemenelum, Musée National du
Sport — passes in **both NFC and NFD** encodings (D243 accent folding).

---

## Part 3 — wiring: extend what runs, do not add a sixth gate

Before writing, I read `scope_memory.py`, `geocode_stops.resolve_poi()` and the PHASE 5.6 scope
judge (`_validate_stops_within_scope`), as instructed. The two new checks are wired into paths
that already run, not into a new gate:

1. **Non-place rejection → inside PHASE 5.6 (`_validate_stops_within_scope._check_one`).** A
   deterministic `classify_stop_name` check sits directly beside the existing D557 scope-memory
   pre-check, before the LLM. A non-place returns `(poi, False, "high", "[not-a-place] …")` — the
   same shape a high-confidence "outside" verdict uses, so the existing removal machinery handles
   it. This gate is *already* called by the replenishment loop (D558) to vet candidates, so
   replenishment now rejects non-place candidates for free.
   - **Guard:** a `[not-a-place]` rejection is **not** written to `known_out_of_scope.json` — a bad
     name is bad for every scope, not a `(name, scope)` fact. The `record_out_of_scope` call is
     guarded to skip it.

2. **Centroid collapse → inside the D559 geocode block.** Right after the existing per-POI
   `resolve_poi` loop, `repair_centroid_collapse` re-resolves the colliding stops through the same
   `resolve_poi` just used. Stops that stay collapsed **and** are not places are dropped; then
   `replenish_to_count` (D558) refills to `_requested_stop_count_original` with real places, and
   the new stops get coordinates via the existing `_fetch_coords` + `resolve_poi`.

3. **Gate extension for the no-replenishment case.** The D558/D559 block was gated on
   `_gp_names_now != _gp_initial` (i.e. only when replenishment changed the set). Tour 423
   collapses on the *original* set with no replenishment, so the gate is extended to also fire when
   `find_centroid_collapse` reports a collision on the original set. Same block, wider trigger — not
   a new gate.

Museum tours are untouched: they are excluded from the D559 block (`tour_category not in
{restaurant, museum}`) and exempt inside `repair_centroid_collapse`, so the museum path Michael
asked to protect is unchanged.

---

## Acceptance criteria — where each is proven

| # | Criterion | Test |
|---|---|---|
| 1 | 423: all four flagged; Bruins Bar survives, other three do not | `test_local481_place_shape::TestTour423Fixture`, `test_local481_centroid_collapse::TestFind::test_423_all_four_flagged`, `test_local481_wiring::…test_423_nonplaces_removed_bruins_bar_survives` |
| 2 | Cimiez approved stops NOT flagged | `test_local481_place_shape::TestCimiezApprovedNotFlagged`, `test_local481_wiring::TestCimiezApprovedNotRemovedByWiring` |
| 3 | Two artworks in one museum room not flagged by the collision rule | `test_local481_centroid_collapse::TestFind::test_museum_room_is_exempt` (+ `…WOULD_collide_without_the_scope`) |
| 4 | A tour that loses a stop comes back at the requested count via replenishment | `test_local481_wiring::TestReplenishmentRefillsAfterNonPlaceDropped` |
| 5 | Break the detector → a test goes red; disabled, the 423 fixture passes unflagged | `test_local481_place_shape::TestDetectorCanFail`, `test_local481_centroid_collapse::TestDetectorCanFail` |

### Wiring proved separately from the function (LOCAL-465)

`test_local481_wiring.py` proves the extension is actually *called*, not merely present:
- With a deliberately invalid API key the LLM branch fails open (keeps the stop). The three 423
  non-places are still removed and Bruins Bar survives — that removal can only be the deterministic
  place-shape check firing inside `_validate_stops_within_scope`. A control test
  (`…would_keep_all_four`) shows two real out-of-scope places are *kept* under the same bad key,
  witnessing the fail-open baseline.
- Source witnesses confirm `repair_centroid_collapse` is called in the generator, `place_shape` is
  imported, and `classify_stop_name` is consulted by the scope gate.

---

## Test output (real, `exit=0` is not the proof — the 23 named results are)

```
$ python3 -m pytest tests/test_local481_place_shape.py \
      tests/test_local481_centroid_collapse.py tests/test_local481_wiring.py -v

tests/test_local481_place_shape.py::TestTour423Fixture::test_bruins_bar_is_the_only_survivor PASSED
tests/test_local481_place_shape.py::TestTour423Fixture::test_each_423_name_classifies_as_expected PASSED
tests/test_local481_place_shape.py::TestCimiezApprovedNotFlagged::test_all_cimiez_stops_are_places PASSED
tests/test_local481_place_shape.py::TestConservativeSurvivors::test_survivors_all_pass PASSED
tests/test_local481_place_shape.py::TestCategoryLabels::test_category_labels_are_rejected PASSED
tests/test_local481_place_shape.py::TestFormats::test_formats_are_rejected PASSED
tests/test_local481_place_shape.py::TestDetectorCanFail::test_disabling_the_rules_lets_423_nonplaces_through PASSED
tests/test_local481_centroid_collapse.py::TestFind::test_423_all_four_flagged PASSED
tests/test_local481_centroid_collapse.py::TestFind::test_co_located_artworks_WOULD_collide_without_the_scope PASSED
tests/test_local481_centroid_collapse.py::TestFind::test_distinct_stops_are_clean PASSED
tests/test_local481_centroid_collapse.py::TestFind::test_longitude_collision_is_caught_too PASSED
tests/test_local481_centroid_collapse.py::TestFind::test_museum_room_is_exempt PASSED
tests/test_local481_centroid_collapse.py::TestRepair::test_a_resolver_that_cannot_move_a_stop_leaves_it_still_colliding PASSED
tests/test_local481_centroid_collapse.py::TestRepair::test_a_resolver_that_spreads_the_stops_cures_the_collision PASSED
tests/test_local481_centroid_collapse.py::TestRepair::test_museum_repair_is_a_noop PASSED
tests/test_local481_centroid_collapse.py::TestDetectorCanFail::test_disabled_detector_lets_423_through_unflagged PASSED
tests/test_local481_wiring.py::TestNonPlaceRejectionIsWiredIntoPhase56::test_423_nonplaces_removed_bruins_bar_survives PASSED
tests/test_local481_wiring.py::TestNonPlaceRejectionIsWiredIntoPhase56::test_without_the_wiring_the_bad_key_would_keep_all_four PASSED
tests/test_local481_wiring.py::TestCimiezApprovedNotRemovedByWiring::test_cimiez_stops_all_survive PASSED
tests/test_local481_wiring.py::TestReplenishmentRefillsAfterNonPlaceDropped::test_a_nonplace_candidate_is_replaced_not_just_dropped PASSED
tests/test_local481_wiring.py::TestSourceWitnesses::test_d559_block_calls_repair_centroid_collapse PASSED
tests/test_local481_wiring.py::TestSourceWitnesses::test_generator_imports_place_shape PASSED
tests/test_local481_wiring.py::TestSourceWitnesses::test_validate_scope_uses_classify_stop_name PASSED

======================== 23 passed, 1 warning in 0.68s =========================
```

### Regression check (existing suites touching the paths I extended)

```
$ python3 -m pytest tests/test_d558_replenish_loop.py tests/test_d536_waypoint_scope.py \
      tests/test_d559_geocode_shared.py tests/test_local472_stop_specificity.py
======================== 49 passed, 1 warning in 0.78s =========================

$ python3 -m pytest tests/test_d557_scope_memory.py
======================== 16 passed, 1 warning in 0.16s =========================
```

### One pre-existing failure, not mine

`tests/test_local359_scope_check_address.py` has **3 failures that reproduce on the clean base**
with all my changes stashed (`git stash push -u`). Cause: that suite reuses the stop name
`"Test Stop"` / scope `"Test District"`, and one test writes that pair into the shared
`known_out_of_scope.json` corpus via `record_out_of_scope`; later tests in the same file then hit
the scope-memory entry and see the stop removed deterministically. It is an intra-file
test-isolation bug in that suite, independent of LOCAL-481. I restore the corpus with
`git checkout tests/known_out_of_scope.json` after any run so no pollution is committed; the
committed corpus holds only its two legitimate entries (Villa Leopolda, Chapelle du Rosaire).

---

## Files changed

- `geocode_stops.py` — added `find_centroid_collapse`, `repair_centroid_collapse`,
  `COLLISION_CATEGORIES` (Part 1).
- `place_shape.py` — NEW deterministic non-place / category classifier (Part 2).
- `generate_tour_text.py` — three wiring edits (Part 3): place-shape check in
  `_validate_stops_within_scope`; collapse-aware D558/D559 gate; `repair_centroid_collapse` +
  refill in the D559 geocode block.
- `tests/test_local481_place_shape.py`, `tests/test_local481_centroid_collapse.py`,
  `tests/test_local481_wiring.py` — NEW.

Not touched: `unglossed_reference_gate.py` (LOCAL-479); no `facility` category added (LOCAL-480,
D563 already defines it); `DECISIONS.md`/`CLAUDE.md`/`BACKLOG.md`/etc. left alone. No container was
rebuilt, restarted, or deployed — Michael is testing on Preview.
