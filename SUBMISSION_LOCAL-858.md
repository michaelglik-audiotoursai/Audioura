# SUBMISSION — LOCAL-858

**Walking-tour stops in Ho Chi Minh City all get the city-centre pin
("0 stops with coordinates")**

Branch: `LOCAL-858-hcmc-pins` (base `subscribed`, contains `5712c485`)
Budget: `TASK_BUDGET_ID=LOCAL-858 TASK_BUDGET_USD=0.40` — live run spent **$0.2602**.

---

## 1. The trace — where the real coordinate is lost and the centroid substituted

Traced one stop of the ticket request
`"Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City"` through the
generator:

1. **Discovery / PHASE-3B** — `generate_tour_text.py` (~`18975`): PHASE-3B asks
   the model for each stop's `"coordinates": "<lat, lng>"`. For a well-known
   landmark the model cannot place, it returns the **city centroid** — and it
   returns the SAME centroid for every stop. Tour 527 shipped Ben Thanh, the
   Opera House and the War Remnants Museum all at ≈ `10.776, 106.695`.
2. **Geocode** — `geocode_stops.resolve_poi` / `resolve_point`
   (`geocode_stops.py:551`): only **replaces** a coordinate when two independent
   sources agree within 200 m. A centroid guess corroborates nothing, so it is
   **kept** unchanged. The centroid survives.
3. **Route order** — `_compute_route_order` (`generate_tour_text.py:1146`,
   log at `:1176`): when the model emitted no parseable coordinate it logs
   `"0 stops with coordinates — skipping"`; when it emitted the shared centroid it
   routes through identical points.
4. **pin_snap / landmark_reference** — `snap_poi_coordinates`
   (`pin_snap.py`, called at `generate_tour_text.py:~28951`): snaps each stop to
   its authoritative Wikidata-P625 / Serper / Nominatim reference (the 791C/803
   machinery). **But** a stop with no in-scope reference took the
   `"no in-scope reference — left unsnapped"` branch and **kept whatever it
   shipped with** — i.e. the centroid.
5. **Stored ZIP/JSON**: that centroid shipped as a real pin; the app plots
   whatever number it is given, so it is indistinguishable from a true pin.

## 2. Root cause

The city centroid is substituted **upstream** by the model (step 1) and is never
recognised as "coordinates unknown" **downstream**. A stop whose own
authoritative reference lookup fails keeps the centroid guess and ships it as a
real pin. Confirmed: a made-up stop kept `10.776000, 106.695000` silently.

Note: the Wikidata-P625 landmark lookup itself (`wikidata_landmark_lookup.lookup`)
already returns the **correct** coordinate for these landmarks on this base
(Ben Thanh `10.7725,106.6980`, Opera House `10.7764,106.7028`, City Hall, Thien
Hau, Hoan Kiem, Temple of Literature, Boston Common, Old North Church — all
within target). The field failures (cloud gen 00030-c98 tour 527; the LOCAL-857
Mac run) measured **stale code** (`origin/storied` is many commits behind local
— the D358 warning). The defect that remained on the *current* base is the
silent-centroid fall-through above.

## 3. The fix

Two files, both on the walking path, both using the place's **own authority**
(Wikidata P625 by its name in the TOUR language **and** the LOCAL language —
Vietnamese for HCMC/Hanoi — then Serper/Nominatim):

### `pin_snap.py`
- **Never ship a city-centroid as a real pin.** After the per-stop snap loop,
  any **un-snapped** stop whose shipped pin is a centroid guess is **cleared**
  (`coordinates=''`), marked `_no_coordinate`, and announced
  **`[LOCAL-858] no coordinate <name>`**. A pin is a centroid guess when it is
  (a) already marked a fallback upstream, (b) the same point (≤ 30 m) as another
  stop's **shipped** pin, or (c) ≤ 30 m from the supplied `city_centroid`. The
  shared-point test reads the **original shipped** coordinates so the signal
  survives even after neighbours snap away. Snapped/authoritative stops are never
  touched; distinct well-placed stops are preserved.
- **Authority off-scope guard** (`_MAX_AUTHORITY_KM = 150`): a Wikidata-P625
  reference is normally exempt from the scope bounds, but a bare-name
  `wbsearchentities` hit can resolve a **same-name place in another country**.
  When a scope centre is known, a reference more than 150 km from it is refused
  even as an authority — so `"St. Joseph's Cathedral"` is never snapped to the
  cathedral in **Baghdad** (6,144 km).

### `generate_tour_text.py`
- `_establish_landmark_coordinates()` — runs the Wikidata-P625 lookup **early**,
  for every stop whose shipped pin is missing or a centroid guess, stamping the
  real coordinate **before** route ordering. This fixes the
  `"0 stops with coordinates"` log and routing through identical points: with it,
  `ROUTE-ORDER` counts every placed stop. Called right before the first
  `_compute_route_order` on the walking path.
- `_city_center_for_request()` — a robust city-centre resolver. The plain scope /
  location strings (`"… walk, Hanoi"`) do not geocode, which left `scope_center`
  **None** and disabled every identity guard. This falls back to the **city
  tail** (`"…, Ho Chi Minh City"`, `"…, Hanoi"`, `"…, Boston"`), which does
  geocode. Used by both the early pass and the pin-snap block.
- Passes `city_centroid` into `snap_poi_coordinates` and logs
  `"<N> centroid pin(s) cleared [LOCAL-858]"`.

A stop with no real coordinate is therefore **logged and announced, never
silently centroided** — matching the ticket ("prefer dropping or announcing it").

## 4. Not wider than HCMC — Hanoi + Boston

`wikidata_landmark_lookup.local_lang_for_scope` returns `vi` for HCMC **and**
Hanoi, `''` (English) for Boston. All three requests resolve real P625 pins and
collapse no centroid:

| request stop | real P625 | result |
|---|---|---|
| Ben Thanh Market | 10.7725, 106.6980 | snapped, 0 m |
| Saigon Opera House | 10.7764, 106.7028 | snapped, 0 m |
| Hoan Kiem Lake | 21.0289, 105.8525 | snapped |
| Temple of Literature | 21.0286, 105.8356 | snapped |
| Boston Common | 42.355, -71.0656 | snapped (control) |
| Old North Church | 42.3664, -71.0544 | snapped (control) |

Boston (the non-Vietnam control) is unaffected: English scope, real pins, no
centroid.

## 5. Tests — `test_local858_hcmc_pins.py` (13, offline)

Built from the exact ticket strings. Cover: every pin within 150 m of the real
P625; no pin is the city centroid; all snapped to authority; an unresolvable stop
is **cleared + `[LOCAL-858] no coordinate <name>` logged**; three shared-centroid
stops with no reference are all cleared; distinct well-placed stops preserved;
Hanoi generality; Boston control; `local_lang_for_scope` vi/vi/''; the early pass
stamps three real coordinates before route order; and the authority off-scope
guard (the Baghdad case). 102 tests pass across LOCAL-858 + the 791E/810/481/591/
605/852 regression suites.

## 6. Live run — `run_local858_live.sh` (budget enforced)

Own container `-p local858`, own throwaway postgres (`local778-initdb`), the
LOCAL-820 meter contract, `TASK_BUDGET_ID=LOCAL-858 TASK_BUDGET_USD=0.40`,
`STORY_PASS_MODEL=gpt-4.1`, `RESEARCH_BACKEND=serper`, `LANDMARK_LIVE_LOOKUP=1`.
Never the live DB, never a shared `audioura-*` container, no `DELETE`.

**HCMC tour, `"Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City"`,
3 stops — PASS:**
- `[LOCAL-858] established 3 real landmark coordinate(s) before route ordering`
- `[ROUTE-ORDER] Computed route for 3 stops with coords (0 without): 1.22km total`
  → **ROUTE-ORDER counts every stop**
- Ben Thanh Market **0 m** from real; Saigon Opera House **0 m** from real;
  Saigon Notre-Dame Basilica real P625 `10.7797,106.6992` — **no centroid pins**
- cost **$0.2602 < $0.40**

The live run also **surfaced and fixed** the Baghdad cross-city bug (§3): the
pin-snap `scope_center` was `None` for every tour, which is why
`_city_center_for_request` + the authority off-scope guard were added. With the
resolved Hanoi centre, `"St. Joseph's Cathedral"` is refused and announced
`[LOCAL-858] no coordinate` (no Baghdad, no centroid), while Ngoc Son Temple and
the Water Puppet Theatre get real pins. The Hanoi/Boston tours in the budget-
exhausted second run returned no text (the $0.40 cap + per-run LLM
non-determinism), so their coordinate behaviour is proven through the real
snap + live-Wikidata path, which is unmetered.

## Files changed

- `pin_snap.py` — centroid-collapse guard (`_coord_is_marked_fallback`,
  `_SHARED_FALLBACK_M`, `city_centroid` param, `[LOCAL-858] no coordinate` log)
  and the authority off-scope guard.
- `generate_tour_text.py` — `_establish_landmark_coordinates`,
  `_city_center_for_request`, early landmark pass before route order,
  `city_centroid` wired into the pin-snap call + cleared-count log.
- `test_local858_hcmc_pins.py` — new (13 tests).
- `run_local858_live.sh`, `run_local858_container.py` — new live harness.
