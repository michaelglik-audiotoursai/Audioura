# SUBMISSION — LOCAL-779S: backport LOCAL-779 + 779B to `storied` (D720)

**Branch:** `LOCAL-779S-backport-storied`
**Base:** `storied` @ `cece3763` (`git merge-base --is-ancestor cece3763 HEAD` → exit 0)
**Agent:** Mac Mini Kiro

## What this is
D720: the generic tour fixes LOCAL-779 (business POIs — "gyms near me") and
LOCAL-779B (restaurants "near me" + cuisine match + honest refusal) must also
reach Stable/`storied`. `storied` has the same existence gate forced to ENFORCE
for walking tours and the same PHASE 3C check that compared each address with the
**whole request** (`generate_tour_text.py`), so "gyms near me, <town>" and
"<cuisine> restaurants near me, <town>" fail on `storied` exactly as they did on
Subscribed.

A straight `git cherry-pick f9ca9db0 454a24a0` conflicts in `area_resolver.py`,
`generate_tour_text.py` and `stop_existence_gate.py` because the files have
diverged. I ported the **behaviour**, not the diff, and kept storied's own
differences intact. No Subscribed-only features (plans, by_reference, pricing)
were brought over, and the Subscribed-only live-run runner scripts were skipped.

## Files changed
| File | Change |
|------|--------|
| `stop_existence_gate.py` | business classification + maps existence + replenish; dining maps-refill + cuisine match + listing verify; `verify_stop_existence`/`run_existence_gate` take `poi_type`; `business` venue-kind + `coords` in the verdict; ported `_city_signals_from_venue`/`_geocode_city_center` (pre-existing Subscribed helpers the new code depends on, absent from storied). |
| `generate_tour_text.py` | `_scope_from_request`; raw-token-first `_address_matches_location`; PHASE 3A business exempt; area-resolve on the clean scope; PHASE 3C compares against the resolved scope (first pass + Part-C); gate call passes `poi_type` + attaches `business_maps` coords; CUISINE-VERIFY + MAPS-FIRST top-up; Part C skipped for business/dining; maps-first refill from empty; `_maps_verified` exempt from the gate; business + dining replenishment in LOCAL-290; `_LOCAL779B_DINING_REPLENISH_MARKER`; PHASE 4 cuisine-match prompt. |
| `area_resolver.py` | `_parse_location` strips a leading `"<type>:"` label and `"near me"`. |
| `actionable_failure.py` | `no_matching_places_in_area` error code + `_ADJACENT_AREAS` + `_widen_area_suggestion` + the branch in `build_actionable_failure`. |
| `tests/test_local779_business_poi.py` | **New** — 36 fixtures-only tests (verbatim from Subscribed; uses only ported internals). |
| `tests/test_local779b_restaurant_places.py` | **New** — 52 fixtures-only tests (verbatim). |

---

## Conflict hunks and how each was resolved

The cherry-pick conflicts because storied's copies of the three files have drifted.
Below is each conflicting region and the resolution. "Ported as behaviour" means
the hunk applied cleanly against storied's surrounding code once anchored to the
right storied lines; the other entries note where storied differs and what I did.

### `area_resolver.py`
1. **`_parse_location` head.** Subscribed inserts the `"<type>:"`-label and
   `"near me"` stripping right after an `including|featuring|…` cleanup line that
   **does not exist in storied** (storied's `_parse_location` begins directly with
   the `clean = re.sub(r'\b(?:walking tour|…)` tour-type strip, then LOCAL-46 /
   LOCAL-3 transport-word strips). **Resolution:** inserted the same two
   `re.sub(...)` strips on the raw `location_string`, immediately after the
   docstring and **before** storied's first `clean =` line — the same point in the
   pipeline (strip label + "near me" before parsing). Behaviour identical.

### `stop_existence_gate.py`
2. **Business classification block + `_BUSINESS_*` constants.** No conflict of
   content, but the Subscribed anchor (`# ──── END LOCAL-320 ───`) is shared.
   **Resolution:** inserted `classify_business_vs_landmark` + the keyword/OSM
   constant tuples right after storied's `END LOCAL-320` marker.
3. **`_classify_venue_kind` signature + poi_type branch.** storied's signature is
   `(venue_name, db_conn, tour_type=None)` and its dining-detection block is
   byte-identical to Subscribed's pre-image. **Resolution:** added the
   `poi_type=None` kwarg + the docstring lines + the `classify_business_vs_landmark`
   poi_type branch (returns `'dining'`/`'business'`) immediately after the
   tour_type dining block, before the `_find_venue_corpus_rows` lookup.
4. **New existence/replenish/cuisine functions.** Inserted the whole block
   (`_check_business_existence`, `business_replenish_candidates`, the 779B dining
   block — `_DINING_OSM_TYPES`, `_CUISINE_SYNONYMS`, `_GENERIC_DINING_WORDS`,
   `_extract_cuisine_qualifier`, `_cuisine_from_request`, `_listing_cuisine_tokens`,
   `cuisine_matches`, `cuisine_conflict`, `dining_replenish_candidates`,
   `verify_listing_cuisine`, `verify_listing_in_scope`, `_haversine_km_local`)
   after storied's `_check_dining_nominatim`, exactly where Subscribed places them.
5. **Missing helper dependencies — `_city_signals_from_venue` /
   `_geocode_city_center`.** The 779 diff **uses** these but does not define them;
   on Subscribed they are pre-existing helpers that **do not exist in storied**.
   **Resolution:** ported both verbatim from the Subscribed merge (they depend only
   on `_nominatim_request`, `_strip_accents`, `re` — all present in storied),
   placed right after `_haversine_km_local`. This is infrastructure the ported
   code needs, not a Subscribed-only feature.
6. **`verify_stop_existence` signature + `business` branch + `coords`.** storied's
   body matches the Subscribed pre-image (same `_check_dining_existence` dining
   branch). **Resolution:** added `poi_type=None`, threaded it into the
   `_classify_venue_kind` call, added `'coords': None` to the result dict, and
   inserted the `elif venue_kind == 'business':` branch (→ `_check_business_existence`
   with `_city_signals_from_venue(venue_name)`, `source='business_maps'`, coords)
   immediately before the existing `elif venue_kind == 'dining':`.
7. **`run_existence_gate` signature + both call sites.** **Resolution:** added
   `poi_type=None` to the signature and threaded it into the first-pass and retry
   `verify_stop_existence(...)` calls.

### `generate_tour_text.py`
8. **`_scope_from_request` + the 779B marker.** Inserted after `_compute_route_order`
   (before `_address_matches_location`), as on Subscribed.
9. **`_address_matches_location` raw-token-first.** storied's loop
   (`for token in text_parts: effective = _NEIGHBORHOOD_TO_CITY.get(token, token)`)
   is identical to Subscribed's pre-image. **Resolution:** inserted the raw
   `token_words.issubset(loc_words)` early-return **before** the neighbourhood→city
   alias lookup.
10. **`verify_poi_matches_type` cuisine prompt.** storied's prompt is the
    Subscribed pre-image. **Resolution:** ported the `_pt`/`_pt_singular` guard, the
    cuisine-qualifier paragraph, and the two-example block (incl. the "Mamma Maria
    is Italian, not Middle Eastern" example).
11. **PHASE 3A LOCAL-329 hollow-reason filter.** storied's
    `if reason and tour_category in ('restaurant','walking'): … reason_has_substance`
    matches the Subscribed pre-image. **Resolution:** inserted the `_is_business_poi`
    classification (via `classify_business_vs_landmark` on `intent['poi_type']`) and
    the business-exempt branch before `elif reason_has_substance(reason):`.
    (`intent` is bound at the top of `generate_tour_text`, in scope here.)
12. **Area resolution off the clean scope.** storied: `_area = resolve_area(_location_normalized)`.
    **Resolution:** compute `_area_input = _scope_from_request(_location_normalized, intent)`
    and resolve that.
13. **PHASE 3C — resolved scope.** This is the D720 crux. storied passed the whole
    `location` to `_address_matches_location` (first pass **and** the Part-C
    replacement re-check). **Resolution:** compute `_p3c_scope` (intent's
    `geographic_scope`, else `_scope_from_request(location, intent)`) and compare
    against it in both places; Part-C uses `_rep_scope = _p3c_scope if … else location`.
14. **779B CUISINE-VERIFY + MAPS-FIRST top-up + honest refusal.** Inserted after the
    PHASE 3C "all stops pass" print and before `if len(poi_list) == 0:`; Part C
    gated by `_partc_skip_maps_sourced`. **storied divergence:** Subscribed records
    the structured clean-fail via a `_J._LAST_CLEAN_FAIL_EVIDENCE` job-state module
    that **does not exist in storied**. **Resolution:** adapted every reference to
    storied's module-global `_LAST_CLEAN_FAIL_EVIDENCE` using the `.clear()` +
    `.update({...})` pattern storied already uses for its other clean-fails. The
    `error_type: 'no_matching_places_in_area'` + `poi_type`/`cuisine`/`locality`
    keys flow to `build_actionable_failure` → `_widen_area_suggestion`.
15. **Existence-gate call site + business coords attach.** storied's gate call is
    `run_existence_gate(_seg_stop_names, _seg_venue, _seg_conn, tour_type=tour_category)`.
    **Resolution:** threaded `poi_type=_seg_poi_type` (joined from `intent['poi_type']`),
    added the empty-result `'verdicts': []` default, and the `business_maps` coords
    attach loop (fills only still-missing coords via `_poi_has_coordinates`).
16. **Gate exemption for maps-verified stops.** storied exempts only
    `page_sourced`. **Resolution:** also exempt `_maps_verified` so a map-sourced
    restaurant is not re-checked by the Wikipedia-shaped dining path.
17. **MAPS-FIRST refill when the list is empty.** Inserted between the
    `END [LOCAL-245]` gate comment and the `[LOCAL-290 Fault 4]` block — storied's
    LOCAL-290 top-up only runs when `len(poi_list) > 0`, so a PHASE-3C-emptied list
    never refilled. Adapted `_LAST_CLEAN_FAIL_EVIDENCE` as in #14.
18. **Business + dining replenishment inside LOCAL-290.** storied's LOCAL-290 block
    (`_rep_needed`/`_rep_tried`/`_REP_MAX_ROUNDS`) matches the Subscribed pre-image.
    **Resolution:** inserted the LOCAL-779 business block and the LOCAL-779B dining
    block after the `_rep_tried.update(...)` line, re-computing `_rep_needed` after,
    and added `_bp['_maps_verified'] = True`.

### `actionable_failure.py`
19. **`ERROR_CODES` + `_ADJACENT_AREAS` + `_widen_area_suggestion` + branch.**
    storied's `ERROR_CODES` and `build_actionable_failure` match the Subscribed
    pre-image. **Resolution:** added the `no_matching_places_in_area` code, the
    `_ADJACENT_AREAS` map + `_widen_area_suggestion` helper (before
    `build_actionable_failure`), and the `elif error_code == 'no_matching_places_in_area':`
    branch.

---

## Tests — fixtures only (no live web), base vs branch

### Ported suites (branch)
- `tests/test_local779_business_poi.py` — **36 passed**.
- `tests/test_local779b_restaurant_places.py` — **52 passed**.
- Combined with the storied restaurant suites
  (`test_local557_named_restaurant.py`, `test_local285_restaurant_selection.py`,
  `test_d557_scope_memory.py`) — **132 passed** together.

### Regression (base vs branch → no regression)
`git stash` of the six changed files, run on base `cece3763`, then restored:
- `tests/test_local557_named_restaurant.py` + `test_local285_restaurant_selection.py`
  + `test_d557_scope_memory.py` — **44 passed on BOTH base and branch**.
- `test_sq4_merge.py` — **PASS** (script) on both.
- `test_palais_fix_lead_fixture.py` — **23/23** on both.

The new behaviour is reached only for a `business`/`dining` `poi_type`
(`classify_business_vs_landmark` returns `'landmark'` for everything else), so the
landmark/museum paths are byte-for-byte unchanged — which the regression battery
confirms.

---

## Live test — own isolated container `local779s-tg`, plain storied, STORIED_MODE=true

Each tour ran in its **own** throwaway `--rm` container built from **this worktree**
(mounted `-v "$PWD":/app`) on `--network development_default`, with **plain storied
env** — no `/opt/meter` PYTHONPATH and no `METER_ROLE_TOKEN` (the Subscribed
override was NOT applied). Never `-p audioura`; the `audioura-*` containers were
never touched and remained up. The container is gone after each run.

| # | Request | Stops delivered | $ (api + grounding) |
|---|---------|-----------------|---------------------|
| 0 | `walking tour: gyms near me, west Roxbury, MA` (2) — **the LOCAL-779 bug case** | **Planet Fitness** — 1175 Washington St, West Roxbury, MA 02132 (42.2847, -71.1447); **YMCA of Greater Boston – West Roxbury** — 15 Dorr Rd, West Roxbury, MA 02132 (42.2833, -71.1455) | $0.1128 + $0.0700 = **$0.1828** |
| 1 | `Italian restaurants in the North End, Boston` (3) | **Mamma Maria** — 3 North Square, Boston, MA 02113 (42.3634, -71.0547) — correctly Italian; **Pizzeria Regina** — 11 1/2 Thacher St, Boston, MA 02113 (42.3635, -71.0550); **Giacomo's Ristorante** — North End (42.3643, -71.0545) | $0.1873 + $0.3500 = **$0.5373** |

**Total spend = $0.7201 ≤ $1.00 cap.**

Before the fix, tour 0 clean-failed ("no stops could be generated" — a gym is not
on Wikidata, so the walking existence path dropped every stop). After the fix it
delivers 2 verified in-scope gyms. Tour 1 delivers 3 real North-End Italian
restaurants, with "Mamma Maria" correctly accepted as Italian.

**`audio_tours` rows:** read 535 before and 535 after via a throwaway driver —
`generate_tour_text()` itself does not persist (the service layer writes the
is_test row), so the driver wrote no rows. **No `DELETE` of any kind.**

The throwaway driver and the generated `.txt`/`_evidence.json` artifacts were
removed after the run; debug files the generator touched
(`openai_simple_debug.txt`, `prompt_dump_stop1.txt`) were restored with
`git checkout`. Final `git status` = only the 4 modified sources + 2 new tests.

---

## Process
- Branched from `storied` @ `cece3763` (local HEAD, not `origin/storied` which is
  behind); `git merge-base --is-ancestor cece3763 HEAD` → 0.
- No `git add -A`; only the six files above were staged. No `DELETE` of any kind.
- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md.
- One heavy build at a time; `audioura-*` containers never touched.
