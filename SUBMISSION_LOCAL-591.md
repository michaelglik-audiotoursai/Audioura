# SUBMISSION — LOCAL-591: "Art and Architecture tour in Boston Athenaeum" turned into a city walking tour, cut to 3 stops by the building's walls; King's Chapel had no marker

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-591-in-building-tours`  (base **storied = 6bec63f**; verified `git merge-base --is-ancestor 6bec63f HEAD` → 0)
**Commits ahead of storied:** 5 (all pushed to `origin/LOCAL-591-in-building-tours`)

---

## The defect (Michael's phone, 2026-10-06, tours 395 en / 396 ru)

Request `Art and Architectual tour in Boston Athenaeum, boston, ma`, 5 stops → delivered **3 stops, walking tour**. Four distinct bugs chained:

1. **Wrong category.** `[S15] venue_name='Boston Athenaeum' overridden — location contains explicit non-museum phrase` → `category='walking'`. The "explicit non-museum phrase" that fired was the *theme* word **architectural**. A theme word is not a different place: "…tour **in** <named building>" is a tour of that building.
2. **Category and scope disagreed.** As a *walking* tour it picked city-wide stops (MFA, Trinity, BPL, Gardner, State House, Granary), then the scope check judged each against the **building** `Boston Athenaeum` and removed six.
3. **Verdict contradicted reasoning.** `OK 'King's Chapel' — inside '…Athenaeum…': King's Chapel is located outside the bounds of Boston Athenaeum… (conf=high)` — the boolean said inside, the reason said outside, and the code trusted the boolean.
4. **No marker for King's Chapel.** It was added late (`[D556] ADDED 'King's Chapel'` / replenishment) after coordinates were assigned, and was never geocoded.

---

## What was delivered

All code changes are in `generate_tour_text.py`. Each fix ships with a red→green test. The suites the ticket requires to stay green are green (exits pasted below).

### Fix #1 — "in/inside/at <named building>" → contained-venue tour  (commit `82faeda`, extended by `ed7bbd5`)

The "explicit non-museum phrase" set was conflating two different signals, so it was split:

- **ACTIVITY/mobility words** (`walking`, `restaurant`, `food`, `bike`, `shopping`, …) name a *different activity* — they are genuinely non-museum. `_ACTIVITY_NON_MUSEUM_TOUR_RE`.
- **THEME words** (`architecture`, `architectural`, `art`, `history`, `literary`, …) name a *subject*, not a place or an activity. `_THEME_TOUR_RE`.

New seams:
- `_INTERIOR_PREP_RE` — matches `tour in/inside/within/at/of <X>` (interior); `around/near/by` (perimeter) does **not** match.
- `_is_contained_venue_request(location, intent)` — True when an interior preposition binds the tour to a single **BUILDING-scope** venue.
- `_should_force_museum(location, tour_type, intent, transport_mode)` — the S15 decision: a theme word no longer blocks the museum flip for a tour inside one named building; an activity word still does; worship/civic (LOCAL-485) and multi-building (plural) exclusions preserved.

The S15 block now calls `_should_force_museum`. `"walking tour around Boston Athenaeum"` stays a city walking tour (around ≠ inside); `"architectural walking tour of Boston"` stays walking (activity word present).

**Live-run follow-ups (same principle, deeper layers), commit `ed7bbd5`:**
- The D1v2 verification was handed the whole themed request string instead of the clean venue name when `_museum_venue_name` lacked a comma — so it resolved `'Art and Architectual in Boston Athenaeum'`, found no Wikidata candidate, and clean-failed `unresolvable` even though the venue had resolved (Q478013) with 6 SPARQL works. Now it appends only the **city/state tail** from the location.
- PHASE 1 returned `requirements='Art and Architectural tour'`; LOCAL-362 read that as a *named exhibition*, searched the venue for it, found none, and discarded the 6 documented works. Added `_is_generic_theme_requirement()` and gated both the early and main exhibition-scope detection: a generic theme is **not** an exhibition — fall back to the venue's documented works.

Test: `test_local591_contained_venue.py` (15 tests).

### Fix #2 — one scope per tour  (commit `866aba0`)

`_assert_one_scope_per_tour(tour_category, scope, intent)` encodes the invariant and runs inside `_resolve_scope_for_check` on every scope it returns:
- a `museum`/`facility` tour is guarded by its venue (PHASE 5.5b) and gets no stop-by-stop scope (`''`);
- an area tour (`walking`/`biking`/…) is checked against its **own declared extent**, never a tighter different place, and never a single building for a city/district tour.

A city walking tour's stops can never again be judged against one building's walls.

Test: `test_local591_one_scope_per_tour.py` (8 tests).

### Fix #3 — the verdict IS its reasoning  (commit `9493ff5`)

`_reconcile_scope_verdict(inside, reason)`: when the containment judge's reason text clearly says OUTSIDE, the verdict is corrected to NOT inside — a reasoning text that says "outside" can never be recorded as inside. `_check_one` applies it before returning. Removal still requires high confidence downstream.

Test: `test_local591_verdict_equals_reasoning.py` (6 tests) — asserts the exact King's Chapel line, and an integration case using a non-memorized stop so only the reconciled verdict can remove it (and without touching `known_out_of_scope.json`). Confirmed true red→green (3 fail without the fix).

### Fix #4 — every delivered stop has coordinates  (commit `225bd01`)

`_geocode_missing_coordinates(poi_list, location, headers, …)` + `_poi_has_coordinates(poi)`, wired as a **final coordinate sweep just before PHASE 6 packing** — the point where the stop set is final. It geocodes any stop still lacking a parseable coordinate, whatever path added it (LOCAL-576 replenishment, D556, LOCAL-577/589 refills), corroborating through `geocode_stops.resolve_poi` when available. A stop that cannot be placed is **logged and kept** (never DELETE) and surfaced so the gap is announced.

Test: `test_local591_every_stop_has_coordinates.py` (8 tests).

---

## Tests (red→green) — pasted exits

LOCAL-591 new suites:
```
test_local591_contained_venue.py            exit=0  (Ran 15 tests)
test_local591_one_scope_per_tour.py         exit=0  (Ran 8 tests)
test_local591_verdict_equals_reasoning.py   exit=0  (Ran 6 tests)   # true red→green: 3 fail without the fix
test_local591_every_stop_has_coordinates.py exit=0  (Ran 8 tests)
```

Required-green suites kept green:
```
tests/test_local576_named_anchors.py        exit=0
tests/test_local577_museum_refill.py        exit=0
test_local580_structural_extraction.py      exit=0
test_local580_actionable_failure.py         exit=0
test_local580_fabrication_guard.py          exit=0
test_local582_museum_overview.py            exit=0
test_local583_documented_works.py           exit=0
test_local583_chrome_rejection.py           exit=0
test_local583_speed.py                      exit=0
test_local584_venue_bound_hours.py          exit=0
test_local584_practical_facts_currency.py   exit=0
tests/test_local586_harness_banner.py       exit=0
test_local589_fill_the_count.py             exit=0
test_local589_chrome_field_names.py         exit=0
test_local589_canonical_set_chrome_free.py  exit=0
test_local589_no_invention_on_fetch_failure.py exit=0
test_local589_site_first_observable.py      exit=0
test_local46_transport_scope.py             exit=0
test_local394_never_drop_a_stop.py          exit=0
```
Also kept green (touched by the refactor / adjacent): `test_local485_venue_class_routing.py` (behaviour preserved; its break-the-routing revert-guard still passes), `test_local425_exhibition_discovery.py`, `test_local465_exhibition_not_found.py`, `test_local480_facility_category.py` — all exit=0.

---

## Live, ISOLATED acceptance

Ran my **own** container, never `audioura-*`:
```
docker run --rm --name local591-gen \
  --network development_default \
  --env-file <env of audioura-tour-generator-1> \
  -e DISABLE_TOUR_CACHE=1 -e COST_HARD_LIMIT_USD=3.00 \
  -v .../generate_tour_text.py:/app/generate_tour_text.py:ro \
  -v .../run_local591_live.py:/app/run_local591_live.py:ro \
  -v /tmp/local591_tours:/app/tours \
  audioura-tour-generator  python run_local591_live.py
```
- OpenAI hard cap **$3.00**; tour-output cache OFF (so the fixed code runs, not a cached pre-fix tour).
- `audio_tours` row count **202 → 202** across runs — **never DELETE** (`generate_tour_text` does not insert/delete tour rows).
- All 13 `audioura-*` containers left running and untouched; `local591-gen` is `--rm` and gone.

### CASE A — the exact field request → tour INSIDE the Athenaeum, 5 stops, every stop with coordinates
`Art and Architectual tour in Boston Athenaeum, boston, ma`, 5 stops:
```
[S15/LOCAL-591] Forced tour_category=museum from venue_name='Boston Athenaeum'
                — request is a tour INSIDE one building (a theme word is not a different place)
[venue_resolver] Resolved 'Boston Athenaeum' → Q478013;  SPARQL: 6 works
[LOCAL-30] DETERMINISTIC BYPASS: 6 documented works

CASE A_ATHENAEUM: delivered 5 stop(s):
   [OK] Picture Gallery with Views of Modern Rome   coord=42.3588, -71.0647
   [OK] Hudson River from Fort Putnam               coord=42.3588, -71.0647
   [OK] Annie Adams Fields                          coord=42.3588, -71.0647
   [OK] Blind-Man's Bluff                           coord=42.3588, -71.0647
   [OK] Landscape with Cottages and Pond            coord=42.3588, -71.0647
CASE A_ATHENAEUM: every stop has coordinates = True
Tour total: ~$1.58
```
(All five stops are works held inside the one building, so they share the venue's coordinate — correct for a single-building museum tour. Full log: `LOCAL591_ATHENAEUM_5STOPS.log`.)

### CASE B — the control → still a walking tour, 4 stops, every stop with coordinates
`walking tour of Beacon Hill, Boston, MA`, 4 stops:
```
[LOCAL-474] tour_type='' → category='walking'
PHASE 4: skipped (tour_category='walking')

STOPS 4
   Louisburg Square                                   | 42.3587, -71.0681
   Nichols House Museum                               | 42.3581, -71.0686
   Massachusetts State House                          | 42.3586, -71.0637
   Boston African American National Historic Site     | 42.3601, -71.0653
```
Still a walking tour, 4 distinct Beacon Hill stops, all with coordinates. (Full log: `LOCAL591_BEACON_HILL_4STOPS.log`. The stop-count varies run to run inside the pre-existing LOCAL-212 coverage-selection stage, independent of the LOCAL-591 fixes; the category stays `walking`.)

Evidence artifacts committed: `LOCAL591_LIVE_RUN.log`, `LOCAL591_ATHENAEUM_5STOPS.log`, `LOCAL591_BEACON_HILL_4STOPS.log`, and the driver `run_local591_live.py`.

---

## Process

- Branched from HEAD (storied 6bec63f), never from `origin/*`. `git rev-list --count storied..HEAD` = 5.
- `git add` + `git commit` + `git push -u origin LOCAL-591-in-building-tours` after each step; first commit within the window.
- Did **not** edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, or .continuous_dev/STATUS.md.
- No GCloud. No `audioura-*` container touched. No tour deleted.
