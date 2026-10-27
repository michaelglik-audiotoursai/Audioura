# SUBMISSION_LOCAL-786.md — Scope radius too loose: Byblos (Norwood) in a West Roxbury tour

**Ticket:** LOCAL-786 · **Branch:** `LOCAL-786-scope-radius` · **Base:** `subscribed` @ `d69d8726`
**Agent:** Mac Mini Kiro

Verify base: `git merge-base --is-ancestor d69d8726 HEAD` → exit 0 (confirmed before commit).

---

## The defect

GCloud Subscribed tour **454** (2026-10-26 ~22:10), request *"middle eastern restaurants
near me, west Roxbury, MA"*, 2 stops → Stardust (West Roxbury, correct) + **Byblos Restaurant**.
The only nearby Byblos is in **Norwood, MA, ~10 km** from West Roxbury's centre. Real West
Roxbury options exist (Al Wadi, Bread Thyme, Rami's), so the in-scope check was accepting a
place far outside the neighbourhood.

**Root cause.** `places_search` is the one place-search provider for business/restaurant POIs.
Its scope-binding step (`_bind_in_scope`) dropped a spillover with a *fixed per-zoom radius*
(`14z = 4 km`). Two gaps let Byblos through:

1. **4 km is too loose for a neighbourhood.** West Roxbury is ~2.5 km across; a 4 km radius
   reaches well into neighbouring towns.
2. **The radius was silently skipped when no centre was geocoded** (`center is None` → every
   record kept). The gate's own in-scope check is a *string signal* test, and `_bind_in_scope`
   *stamps* the scope's locality onto survivors — so once a record survives, the string check
   always says "in scope". The distance test was the only geographic gate, and it could be a
   no-op.

## The fix

All geographic rejection now lives in `_bind_in_scope` — the choke point every path
(`dining_replenish_candidates`, `business_replenish_candidates`, `verify_listing_in_scope`,
`verify_listing_cuisine`) routes through — applied **before** the locality is stamped:

1. **Scope-precision radius** (`_scope_precision` → `_radius_for_precision`):
   - **NEIGHBOURHOOD** (West Roxbury, North End, Jamaica Plain — a known marker or a multi-word
     locality head) ≈ **2.5 km**
   - **CITY** (single-word locality) ≈ **8 km** small, up to **15 km** for a recognised large city
   - **REGION** (county/state/region word) ≈ wide (60 km) — unchanged, no tightening
2. **Bounding-box preference.** When the geocoder returns a `boundingbox`, a record must sit
   **inside it + a 500 m margin** (`_parse_bbox` / `_inside_bbox`) — tighter and truer than any
   fixed radius. `stop_existence_gate._geocode_scope_bbox` fetches it and threads it through
   `_places_lookup` → `map_lookup` → `places_search(scope_bbox=…)`.
3. **"near me" 3 km.** With device coordinates the radius is 3 km of the device (the scope's
   bbox is the *area's*, not the device's, so bbox is not applied on a near-me search).
4. **Town-name mismatch.** A record whose address names a town **different from the scope's
   town AND** which lies **outside the bbox** is rejected outright, even if a radius would allow
   it (`_scope_town` / `_address_town`). Byblos's "…, Norwood, MA 02062" is read from the raw
   Serper address (carried as `_serper_address`) and rejected for a West Roxbury scope.

## Files changed (only these were committed)

- `places_search.py` — precision/radius/bbox/town-mismatch helpers; `_bind_in_scope` rewrite;
  `scope_bbox` on `places_search` + `map_lookup`; `_serper_address` on the normalised record.
- `stop_existence_gate.py` — `scope_bbox` on `_places_lookup`; new `_geocode_scope_bbox`;
  `scope_bbox` threaded into the dining/business replenish and the two verify call sites.
- `tests/test_local786_scope_radius.py` — new (17 tests, red-first).
- `docker-compose.local786-proof.yml` — the isolated live-proof stack (reproducibility).

## Tests (red first, recorded Places JSON — no live web)

`tests/test_local786_scope_radius.py` (17 tests, all green):

- **Byblos Norwood rejected** for West Roxbury (with bbox, and by the 2.5 km radius alone
  without a bbox); Al Wadi, Bread Thyme, Stardust **kept**.
- **Town-name mismatch:** a "Norwood, MA" address is rejected; an in-town "West Roxbury, MA"
  address inside the bbox is kept.
- **City scope stays permissive:** two Brookline gyms ~3 km apart are both kept (a neighbourhood
  radius would wrongly drop the far one).
- **near-me 3 km:** keeps <3 km, drops >3 km.
- **North End Italian set unchanged** (regression reference).
- **Precision classification** for West Roxbury / North End / Jamaica Plain (NEIGHBOURHOOD) vs
  Brookline / Boston (CITY), and the radius values per level.

Regression suites green:

```
tests/test_local779_business_poi.py  tests/test_local779b_restaurant_places.py
tests/test_local783_serper_places.py tests/test_local786_scope_radius.py
→ 124 passed
```

Broader scope/places/gate sweep showed only **6 pre-existing failures** — `test_local359` ×4
(stale `tests/known_out_of_scope.json` "Test Stop"/"Test District" pollution, committed before
this ticket), `test_local25`, `test_local606` — **confirmed identical on the base commit** via
`git stash` (so not introduced here).

## Live test — isolated stack, never `-p audioura`

Own project `-p local786-tg`, spare ports **57xxx**, own postgres volume, every service **built
from this worktree** (confirmed the deployed image carries the LOCAL-786 code). Torn down with
`down -v`; the shared `audioura-*` and `development-postgres-2-1` containers were never touched
(both still up 23 h afterwards).

Three runs via `POST /generate-complete-tour` on `:57002` (user `local778-tester`, L2 seeded;
`tours_per_day` raised 1→10 in the throwaway DB only). Distances to the scope centre
(West Roxbury 42.2843,-71.1627 · Jamaica Plain ~42.3100,-71.1145):

| Run | Request | Stops (distance from centre) | $ |
|---|---|---|---|
| 1 | middle eastern restaurants, West Roxbury | Doyle's Cafe (1.45 km), The Greenhouse (1.42 km) | 0.4443 |
| 2 | middle eastern restaurants, West Roxbury | pool reuse → same 2 stops | 0.0000 |
| 3 | coffee shops in Jamaica Plain, Boston | Arnold Arboretum (0.99 km), Loring-Greenough House (0.16 km), Jamaica Pond (0.82 km) | 0.3472 |

**Total $0.7915 ≤ $1.20.** Every stop lies inside its neighbourhood. **No Byblos / Norwood /
out-of-neighbourhood stop in any run.**

> Note: run 3's LLM picked JP *landmarks/parks* rather than literal cafés — a poi-type concern
> outside LOCAL-786's scope (the cuisine/category filter, LOCAL-779B). All three are strictly
> inside Jamaica Plain, which is the scope requirement this ticket governs.

**audio_tours row counts:** 4 total — 1 seed (Salem Witch Museum) + 3 test tours (`is_test=true`).

### In-container proof against the exact defect

Run inside the live `tour-generator` container (deployed LOCAL-786 code), feeding a recorded
Serper body that includes Byblos Norwood at its real coords:

```
DEPLOYED places_search result: ['Al Wadi', 'Bread Thyme']
PROOF OK: Byblos Norwood (~10 km) REJECTED; Al Wadi + Bread Thyme kept
verify_listing_in_scope('Byblos Restaurant', 'West Roxbury, MA') = False
PROOF OK: LLM-candidate verify rejects Byblos for West Roxbury
```

Both the bulk places filter and the LLM-candidate existence check now reject the out-of-
neighbourhood place while keeping the real West Roxbury options.

## Process compliance

- Branched from HEAD (`d69d8726`), never from `origin/*`. Ancestry verified.
- Committed only the named files (no `git add -A`). Untracked artifacts in the tree
  (`db_step1_stored.txt`, `temp_auth_test.py`, …) are not mine and were left alone.
- No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md. No deletions.
- One heavy build at a time.
