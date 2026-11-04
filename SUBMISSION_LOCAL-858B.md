# SUBMISSION — LOCAL-858B

**Bounce of LOCAL-858: on Cloud Run the HCMC landmark pins are still wrong**

Branch: `LOCAL-858B-cloud-pins` (base `subscribed` = `e92e94ce`; contains
`298b1a8a`, LOCAL-858 + LEAD's user-pin exemption).
Budget: `TASK_BUDGET_ID=LOCAL-858B TASK_BUDGET_USD=0.35` — live spend **$0.2963**.

---

## 1. Root cause (tour 532, "Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City")

The cloud log for tour 532 is explicit: the LLM intent's `geographic_scope` was
**"Ben Thanh Market and Saigon Opera House walk"** — the **city was lost**.
`area_resolver` logged "Could not resolve city". The city-less string then
geocoded to **Vietnam's COUNTRY centroid (15.93, 107.97)**, and that was taken as
the pin-snap / landmark **centre**. Consequences, all observed:

- the centroid guard "cleared 0 pins" — the three pins were ~150 m apart, not
  ≤ 30 m, and ~700 m from the (country) centre;
- the LOCAL-858 landmark lookup was **skipped with no log line**;
- the three stops shipped ~620–790 m off their real places.

The **Mac run passed** and **Hanoi (533) passed** because their scope happened to
carry the city — the defect only bites when the scope drops it and the fallback
reaches a country centroid.

Reproduced the cloud environment exactly (`K_SERVICE=local858b`,
`LANDMARK_LIVE_LOOKUP` inherited **empty** from `.env`) and found **three** silent
skips behind the one symptom — the ticket's item 0 plus two it predicted (item 1):

1. **Item 0 — a COUNTRY centroid was accepted as the centre.** `_city_center_for_request`
   geocoded the scope first and returned the first Nominatim hit with no type
   check; a city-less scope resolves to the country.
2. **`LANDMARK_LIVE_LOOKUP` setdefault is a NO-OP when the var is present-but-empty.**
   The `.env` carries `LANDMARK_LIVE_LOOKUP=` (empty). `os.environ.setdefault(...)`
   does **not** override an empty value, so the live Wikidata lookup stayed **OFF**
   on the walking path — the exact "unset at that point" silent skip the ticket
   named (item 1).
3. **PHASE-3B overwrote the established pin.** Even with the early pass setting the
   real coordinate, the PHASE-3B rebuild took the model's fresh `coordinates`
   first — and for a landmark it cannot place the model returns the city centroid
   again — silently undoing the fix.

## 2. The fix

### Item 0 — never a country centroid; resolve the city from the request tail
- `geocode_stops.geocode_detailed()` (new) returns Nominatim jsonv2
  `type`/`class`/`addresstype`; `is_city_like()` (new) rejects a `country` /
  `state` / `province` / `region` / `county` result.
- `generate_tour_text._city_center_for_request()` now tries the **ORIGINAL
  request's comma tails city-first** ("…, Ho Chi Minh City") **before** the
  city-less scope, and **refuses any non-city-like hit**. It returns `None` rather
  than a country centroid when no city resolves. A `[LOCAL-858B] landmark lookup
  skipped: <why>` line is logged for every skip, and a degraded-scope warning when
  no centre/bbox is known.

### Item 1 — the early pass fires, and LIVE lookup is actually on
- Both `LANDMARK_LIVE_LOOKUP` sites now **enable** the lookup when the var is unset
  **or empty/falsey** (not `setdefault`), logging `[LOCAL-858B] LANDMARK_LIVE_LOOKUP
  was unset/empty — enabled`.
- `_establish_landmark_coordinates` logs `[LOCAL-858B] landmark lookup skipped:
  <why>` per unplaced stop and an `established N` / `established 0` summary — never
  silent.
- PHASE-3B preserves an established authority coordinate (`_user_pin_merge_fields`
  keeps `orig['_landmark_coord']` verbatim, like a user pin), logging
  `[LOCAL-858B] landmark pin kept`.

### Item 2 — a second authority when Wikidata fails
- `landmark_second_authority.lookup_second_authority()` (new): **Serper `/places`**
  by name inside the city box, then **Nominatim** — name-matched (shared
  distinctive core) and in-scope (padded bbox, else metro radius). Cached in the
  same `landmark_coord_cache` table as P625 (`wikidata_landmark_lookup._cache_get/
  _put`, distinct `__2nd__` language tag). Wired into `pin_snap._landmark_reference`
  (after Wikidata, before the offline table) and into the early pass. It calls
  `places_search` with an **empty scope** so the dining town-match guard does not
  drop a valid landmark, and applies its own in-scope test.
- `LANDMARK_WIKIDATA_BLOCKED` env switch added to `wikidata_landmark_lookup` to
  simulate the Cloud Run 429/egress block for the live acceptance run.

### Item 3 — cluster detection, not equality
- `pin_snap.snap_poi_coordinates` adds `_CLUSTER_COLLAPSE_M = 250`: **≥ 2
  reference-less, unsnapped stops within 250 m of each other with DIFFERENT,
  non-same-building names** is a collapse — pins cleared and announced
  `[LOCAL-858B] cluster collapse`. The LOCAL-855E **user-pin exemption** and
  **same-building adjacency** are kept; the same-building check is now
  **identity-only** (shared QID / alias / located-in) so two generic centroid
  guesses ("Stop A"/"Stop B") are not falsely exempted. A stop that resolved to a
  real in-scope reference is never cleared.

## 3. Tests — `test_local858b_cloud_pins.py` (19, offline)

Built from the EXACT tour-532 request and shipped pins:
- `is_city_like` rejects country/state, accepts city/landmark;
- `_city_center_for_request` returns the HCMC centre from the city tail and
  **never** the Vietnam country centroid (and `None`, not a country, when no city
  resolves);
- the tour-532 Ben Thanh↔Opera shipped pins (152 m apart, no reference) are a
  **cluster collapse** — both cleared + announced — and it fires even with the
  centre at the country centroid; same-building stalls and user pins are exempt; a
  referenced in-scope stop in the disc is not cleared;
- the second authority resolves via Serper then Nominatim, rejects a name mismatch
  and an out-of-scope same-name place; pin_snap uses it when Wikidata is blocked;
- PHASE-3B preserves an established landmark pin, and a non-landmark stop still
  takes the model's coordinate.

321 relevant offline tests pass across LOCAL-858/858B + the 802/805/824/791-vietnam/
847/836/816/779/783/859/852/294 regression suites. (The pre-existing failures in
the full `tests/` tree — billing/wallet/newsletter/API/DB needing `postgres-2` —
are identical on a clean `e92e94ce`; this change adds **zero** new failures,
confirmed by `git stash`.)

## 4. Live run — `run_local858b_live.sh` (budget enforced)

Own container `-p local858b`, own throwaway postgres (`local778-initdb`), the
LOCAL-820 meter contract, `TASK_BUDGET_ID=LOCAL-858B TASK_BUDGET_USD=0.35`,
`K_SERVICE=local858b`, `LANDMARK_LIVE_LOOKUP` passed **empty** (so the self-enable
is exercised), `STORY_PASS_MODEL=gpt-4.1`, `RESEARCH_BACKEND=serper`. Never the
live DB, never a shared `audioura-*` container, no `DELETE`.

**PASS 1 — Wikidata reachable**, tour `"Ben Thanh Market and Saigon Opera House
walk, Ho Chi Minh City"`, 3 stops:
- `[LOCAL-858B] LANDMARK_LIVE_LOOKUP was unset/empty — enabled`
- `[LOCAL-858] landmark pin Ben Thanh Market → 10.772521,106.698019 (wikidata_p625)`
- `[LOCAL-858] landmark pin Saigon Opera House → 10.776390,106.702780 (wikidata_p625)`
- `[LOCAL-858] established 3 real landmark coordinate(s) before route ordering`;
  `[LOCAL-858B] landmark pin kept` (survives PHASE-3B)
- delivered: **Ben Thanh 0 m, Saigon Opera House 0 m** from real; **no country
  centroid**; `ROUTE-ORDER … 3 stops with coords` → **PASS**.

**PASS 2 — Wikidata blocked** (`LANDMARK_WIKIDATA_BLOCKED=1`), second-authority
probe `run_local858b_probe.sh` (cheap, ~Serper only, to stay inside the $0.35
cap):
- Wikidata lookup confirmed **`None`** when blocked;
- `Ben Thanh Market → serper_places 0 m`; `Saigon Opera House → serper_places
  49 m` — both name-matched and in-scope → **PASS**.

The probe exercises the exact `lookup_second_authority` path the blocked tour
uses; full-tour generation is already proven in PASS 1. Total spend **$0.2963 <
$0.35**.

## 5. Files

Changed: `generate_tour_text.py` (`_city_center_for_request`,
`_establish_landmark_coordinates`, both `LANDMARK_LIVE_LOOKUP` enablers,
`_user_pin_merge_fields` + PHASE-3B carry-through), `geocode_stops.py`
(`geocode_detailed`/`is_city_like`), `pin_snap.py` (second authority in
`_landmark_reference`; 250 m cluster collapse; identity-only same-building;
reference guard), `wikidata_landmark_lookup.py` (`LANDMARK_WIKIDATA_BLOCKED`).
New: `landmark_second_authority.py`, `test_local858b_cloud_pins.py`, and the
`run_local858b_*` harness.
