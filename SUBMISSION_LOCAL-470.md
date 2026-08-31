# SUBMISSION — LOCAL-470 — Bring Beta Geocoding Fixes Into Storied

**Branch:** `LOCAL-470-port-beta-geocode`
**Base:** storied = `d726c7e` (verified `git merge-base --is-ancestor d726c7e HEAD` → exit 0)
**ClickUp:** `wdvrdaxqte` (BETA-5)

## Summary

Ported Beta's whole-tour **reversed-coordinate** repair into Storied, wired into
the Storied generation path (`generate_tour_text.py`), and ported the two shared
address-parsing improvements it depends on. A Madagascar tour that emitted every
stop longitude-first (`47.5224, -18.9110` for the Rova of Antananarivo — 9,899 km
out, in the ocean off Somalia; 3.9 km when swapped) is now detected and corrected
before per-stop resolution. Correct tours (Sydney, Kyoto) are left untouched.

Nothing was clobbered: `resolve_point`/`resolve_poi`/`_parse_coords_pair` and the
`resolve_stop` wrapper (D559, shipped today) are unchanged, and their 15-test pin
`tests/test_d559_geocode_shared.py` still passes 15/15.

## Function-by-function drift analysis (`origin/main` vs `storied`)

I diffed `git show origin/main:geocode_stops.py` (843 lines) against Storied's copy
(604 lines) function by function. Findings:

### Present on main, absent from Storied

| Function | Decision | Why |
|---|---|---|
| `fix_reversed_coordinates` | **PORTED** (text form) + new `fix_reversed_poi_list` | The BETA-5 fix. See below. |
| `_swap_coord_line` | **PORTED** | Helper for the above. |
| `_throttle` | **NOT ported** | Concurrency fix (a lock around Nominatim's 1 req/s limit under `--concurrency=5`). Real, but a *separate* concern from BETA-5 and out of this task's scope. It requires `threading` + the retry/parallel env knobs and rewrites `geocode`. Porting it here would enlarge the blast radius with no bearing on reversed coordinates. **Flagged for a follow-up task.** |
| `_stats_add` / `_stats_reset` / `get_stats` | **NOT ported** | Per-tour throttle metrics, used only inside main's `correct_stops`, which Storied does not call. Nothing on the Storied path consumes them. |

### Present on Storied, absent from main — MUST SURVIVE

| Function | Status |
|---|---|
| `resolve_point` (D559) | Unchanged |
| `resolve_poi` (D559) | Unchanged |
| `_parse_coords_pair` (D559) | Unchanged |
| `resolve_stop` wrapper form (D559) | Unchanged |

Confirmed by `tests/test_d559_geocode_shared.py` → 15/15 still pass.

### Shared functions — drift check (task step 3)

| Function / const | Verdict | Action |
|---|---|---|
| `_COUNTRIES` | **DRIFTED — main is better. PORTED.** | Storied had the OLD 16-name set; main has a comprehensive ~200-country set. This is **load-bearing for the fix**: `fix_reversed_poi_list` anchors on the city geocoded from the stops' addresses, and with the 16-name set `city_from_address("Rova, Antananarivo, Madagascar")` returned **"Madagascar"** (a country centroid, or a geocode failure) instead of "Antananarivo" — the reversal would be missed. |
| `_clean_component` | **DRIFTED — main is better. PORTED.** | Storied matched state codes with `[A-Z]{2}`, so 3-letter Australian states (NSW/QLD/VIC) fell through and `"Sydney NSW 2000"` was returned verbatim (un-geocodable). Main adds 3-letter states plus NL (`1071 DJ`), AR (`C1087`) and UK (`EH1 2NG`) postcode shapes. |
| `city_from_address` | **Body identical; docstring updated from main.** | The function body is byte-identical on both sides. I took main's corrected docstring, which retracts an unreproducible "12.75 km" measurement claim. Behaviour change comes only from the two constants above. |
| `geocode` | **NOT changed.** | Main's version is the `_throttle`+retry variant; taking it would drag in the concurrency machinery (see `_throttle` above). Kept Storied's simpler inline-throttle version. |
| `_candidates`, `_queries_for`, `location_hint`, `_is_junk_component`, `_parse_stop`, `haversine_m`, `correct_stop`, `_median_anchor`, module constants (`REPLACE_THRESHOLD_M`, `MAX_TOUR_RADIUS_KM`, `AGREEMENT_M`, the regexes) | **Identical.** | No change. |
| `correct_stops` | **Not used by Storied; left as-is.** | Main's version differs (adds the reversal call, stats, `ThreadPoolExecutor`). Storied doesn't call it; the equivalent wiring for Storied is `fix_reversed_poi_list` in `generate_tour_text.py`. Not modified. |

### A correction to my own first pass

My initial read mislabelled which file held the comprehensive `_COUNTRIES`. The
Madagascar acceptance test going red (`could not geocode the tour city 'Madagascar'`)
exposed it immediately: **main** has the comprehensive country list, **Storied** had
the stale 16-name set. This is exactly the shared-function drift the task warned about,
and it is why the port is a reconcile and not a copy.

## What was wired, and where

`generate_tour_text.py` resolves each POI via `resolve_poi` (≈line 9656). On main the
reversal check runs inside `correct_stops`, which Storied never calls. So I added a
**POI-list equivalent**, `fix_reversed_poi_list`, and called it **before** the per-POI
`resolve_poi` loop:

- The reversal rule itself is shared, not duplicated: both `fix_reversed_coordinates`
  (text) and `fix_reversed_poi_list` (POI dicts) call `_is_reversed` / `_swap_coord_line`.
- It must run first because `resolve_point`'s plausibility guard derives its anchor from
  the tour's own stops; if every coordinate is mirrored, the anchor lands in the wrong
  ocean and the guard would reject the *correct* geocoder answers.
- `REVERSAL_FACTOR` (default 10, env `GEOCODE_REVERSAL_FACTOR`) is the "10x closer when
  swapped, across a majority of stops" rule, extracted as a named constant so the two
  entry points share it and it is tunable/testable.

Impossible-latitude handling: `_parse_coords_pair` rejects `|lat| > 90`, which would
*hide* a longitude-first pair whose real latitude exceeds 90. `fix_reversed_poi_list`
therefore parses coordinates *loosely* (a local `_raw_pair`) so those pairs stay visible
and get corrected.

## Acceptance criteria — evidence

Test file: `tests/test_local470_reversed_coordinates.py` (geocoder stubbed; deterministic).

1. **Madagascar detected & corrected, log line names the reversal** —
   `TestMadagascarIsCorrected` (2 tests). Reason string contains "reversed" and
   "Antananarivo"; every stop lands < 20 km from the real city after the swap.
2. **Correct tours never "corrected"** — `TestCorrectToursAreLeftAlone`: Sydney
   (negative latitude) and Kyoto (high longitude) both come through byte-identical.
3. **Latitude outside ±90 rejected** — `TestImpossibleLatitude` (2 tests), incl. the
   no-city path and the counted-with-city path.
4. **D559 still passes 15/15** — see run output below.
5. **Break the fix → red** — `TestBreakTheFix` disables via `REVERSAL_FACTOR`; and I
   additionally sabotaged `_is_reversed` in the production code (`return False`) and
   confirmed the Madagascar tests go red, then restored. Output below.

### Run output

```
$ python3 -m pytest tests/test_d559_geocode_shared.py tests/test_local470_reversed_coordinates.py -v
...
25 passed in 0.13s
```
(15 D559 + 10 LOCAL-470; full per-test list captured in the session.)

Break-the-fix (sabotaged `_is_reversed` → `return False`), then restored:
```
$ python3 -m pytest tests/test_local470_reversed_coordinates.py -q   # with fix broken
FAILED ...::TestMadagascarIsCorrected::test_reversed_tour_is_swapped_to_antananarivo
FAILED ...::TestMadagascarIsCorrected::test_the_reason_names_the_reversal_and_the_city
FAILED ...::TestImpossibleLatitude::test_impossible_latitude_is_counted_even_with_a_city
3 failed, 7 passed
$ # restored geocode_stops.py; re-ran → 25 passed
```

### Wider regression check

Ran the whole `tests/` suite (`--continue-on-collection-errors`): **2914 passed**,
5 skipped. The 42 failures + 53 errors are all pre-existing and environmental
(missing `Crypto` module; live network/DB/newsletter-cloud tests; and the
`test_local359_scope_check_address.py` scope-memory tests, which fail identically on
the clean base `d726c7e` — confirmed by stashing my changes and re-running). None
relate to geocoding, addresses, or coordinates. Test-run artifact files
(`db_step*.txt`, `openai_simple_debug.txt`, `prompt_dump_stop1.txt`,
`tests/known_out_of_scope.json`) were reverted; they are not part of this change.

## Files changed

- `geocode_stops.py` — ported `_swap_coord_line`, `fix_reversed_coordinates`, comprehensive
  `_COUNTRIES`, improved `_clean_component`, updated `city_from_address` docstring; added
  `REVERSAL_FACTOR`, `_tour_city_ref`, `_is_reversed`, `fix_reversed_poi_list`.
- `generate_tour_text.py` — import `fix_reversed_poi_list` and call it before the
  per-POI `resolve_poi` loop.
- `tests/test_local470_reversed_coordinates.py` — new (10 tests).

## Process notes

- Worked only in the worktree on `LOCAL-470-port-beta-geocode`.
- Did not touch `scope_memory.py`, `_compute_route_order`, the prose gates, or any of
  the protected docs.
- Did not deploy to GCloud; did not rebuild or restart any container.
