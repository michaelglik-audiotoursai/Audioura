# SUBMISSION — LOCAL-852: A user's own stops are dropped

**Branch:** `LOCAL-852-user-stops-safe`
**Base:** subscribed — `9ead5b87` (`git merge-base --is-ancestor 9ead5b87 HEAD` → 0)

## The defect

GCloud_Storied_1, Michael's own request (gen 00027-6sb, orch ef0cee57, tour 523,
ru 524): **"Sophia's biking tour in Ho Chi Minh City, Vietnam"** with **7 user-chosen
stops** pasted as *name + Google share link* — only **2 were delivered**. Three
independent causes:

1. **Provider-guard misfire.** LOCAL-835/835B read the tour NAME *"Sophia's biking
   tour"* as an activity-provider request (`biking` is a known activity + the weak
   trigger `tour`), so the guard dropped 3 forced user stops (An Spa, Thi Bar, Acoustic
   Bar) and its replenish rejected every normal sight as "not a 'sophia s biking'
   provider".
2. **Share links never resolved.** Names kept the URL junk (`Rambutan https___share.google_1v4x`);
   4 stops geocoded to the same fallback centroid ≈ 10.7769/106.6955 (CENTROID
   COLLAPSE). LOCAL-802 / LOCAL-790 dedupe then merged The Crazy street and A Star is
   Born into Rambutan.
3. **Scope fell back to 'Vietnam'** because the whole request string did not geocode.

## The fix

### 1. Provider-guard misfire — `category_match_guard.py`
`requested_activity(request, tour_type=None)` now returns `None` (a NO-OP, so no
downstream guard fires) when the request is:
- a **transport-MODE tour** (`_is_transport_mode_tour`: walk/bike/drive/boat/cycle/
  kayak/… + the word "tour", with no strong provider trigger like rental/lessons), or
- a **person's named tour** (`_is_persons_tour`: `"X's … tour"`, including the folded
  `"sophia s biking tour"`).

Both the request string **and** the `tour_type` label are checked, so the words are
caught wherever they arrive. Real provider requests are unchanged — "Kitesurf lessons
in Mui Ne", "bike rental in Hoi An", "scuba diving courses", "kayak hire" still return
a provider dict and the guard still drops off-category food/landmarks.

Call sites in `generate_tour_text.py` pass `tour_type=tour_type` to `requested_activity`.

### 2. User stops exempt from every category/provider guard — `category_match_guard.py`
New `_is_user_explicit_cand`; `filter_off_category`, `filter_off_category_business`,
`filter_off_category_activity` (and the inline replenish guard in `generate_tour_text.py`)
now **keep any candidate flagged `user_explicit` / `_anchor`** — the listener's own stop
may be a private place no classifier recognises. The existence gate (LOCAL-245) also
exempts `user_explicit`/`_anchor` stops (closure/existence drops do not apply to a
listener's own choice).

### 3. User-stop input parsing / share-link resolution — `user_stop_input.py` (NEW)
Parses one raw "Name + URL" item into `{name, url, lat, lng, resolved_name, how,
needs_geocode}`:
- strips the URL from the display NAME, including the `https___host_path` underscore-
  mangled form (`unmangle_url`);
- resolves a Google-Maps share link (`share.google` / `maps.app.goo.gl` / `goo.gl/maps`
  / `google.com/maps`) by following the HTTP redirect (`default_resolver`, **no paid
  API**, injected for offline tests) and parsing the place name + `@lat,lng`
  (`parse_maps_place_url`);
- a plain website URL (`an-spa.vn`) keeps the name and geocodes by name in the city;
- logs `[LOCAL-852] user stop resolved <name> <lat,lng> via <how>`.

Wired into the `forced_stops` block of `generate_tour_text.py`: names are cleaned
**before** title-casing, every forced stop is stamped `user_explicit`+`_anchor`, and a
resolved share-link coordinate is pinned (`coord_source=user_share_link`) so a share-
link stop never falls to the city centroid.

### 4. Centroid-collapse dedupe — `identity_dedup.py`, `local802_relevance_gate.py`
A CENTROID COLLAPSE means "coordinates unknown", not "same building". Two
`user_explicit` stops are the listener's own explicit choices and now **never merge on
proximity** — only textual (same folded title) or same-QID identity merges them.
`dedupe_by_location_or_qid` suppresses its proximity rules (b, d) for a pair of user
stops (and when either carries a fallback/centroid coord marker); `same_building`'s
coords path does the same. A new `_is_fallback_coord_stop` recognises the fallback
markers. **Genuine non-user nearby duplicates still collapse** (verified).

### 5. Scope fallback — `area_resolver.py`
`resolve_area`: when the resolved area is a COUNTRY type, scan the original comma
segments for the most specific non-country place and adopt it as the city — so the
scope centre is "Ho Chi Minh City", never the Vietnam centroid.

## Tests

`tests/test_local852_user_stops_safe.py` — **18 tests, all pass**, built from the exact
7 stop strings:
- provider-guard misfire: person's/transport tour → `None`; "Kitesurf lessons" still a
  provider request and still drops a restaurant + fishing village;
- parsing: 7 clean names (no `http`/`___`), share links resolve to distinct coords
  (offline stub), website keeps name + geocodes by name, name-only unchanged,
  `unmangle_url`, mandated log line;
- dedupe: 4 user stops on the same centroid are NOT collapsed; a textual duplicate still
  collapses; a genuine non-user nearby pair still collapses; 7 resolved stops = 7 pins;
- fallback-coord marker recognition.

**Regression:** 354 tests pass across every suite that imports the changed modules
(LOCAL-46/357/481/521/522/669b/669c/751/779/790/791b/791c/799/802/805/818/830/835/835b/843/845/847,
gcs-ks1 kill switch, vietnam_round2). The only pre-existing failures are 2 in
`test_local351 TestNiceUnchanged` (a parenthetical-parse case in `_parse_location`,
which I did not touch) — confirmed present on base `9ead5b87` via `git stash`.

## Live — BUDGET ENFORCED

`run_local852_live.py`, `TASK_BUDGET_ID=LOCAL-852 TASK_BUDGET_USD=0.60`, cheap env +
`STORY_PASS_MODEL=gpt-4.1`, `DISABLE_STOP_POOL=1`, `USER_STOPS_ENABLED=true`. Exact
request reproduced: tour_type "Sophia's biking tour", location "Ho Chi Minh City,
Vietnam", the 7 pasted name+URL stops.

**Result — PASS:**
- **7/7 stops delivered** (field run delivered 2/7);
- **clean names**, no URL junk: Rambutan, Longan, The Crazy street, The LGBT bar
  🌈Thi Bar Saigon, A Star is Born, Acoustic Bar - Ngô Thời Nhiệm Quận 3, An Spa;
- **7 DISTINCT real HCMC pins** (10.7761/106.6950, 10.7765/106.6938, 10.7759/106.6935,
  10.7677/106.6940, 10.7746/106.6962, 10.7812/106.6899, 10.7740/106.6945) — no centroid
  collapse; scope = HCMC, not Vietnam;
- metered status-200 total **$0.04**; LiveRunMeter combined **$0.1643 < $0.60** cap.

The `COST_METER` `postgres-2` host error is the expected Mac-local condition (no shared
DB) — the LiveRunMeter JSON ledger is authoritative. The run wrote only its own meter
log under `./_local852_meterlogs` (`METER_MOUNT_GUARD=0`), never the shared/live DB and
never the shared `audioura-*` containers. The delivered tour and meter ledger are saved
under `submission_artifacts/local852/`.

## Files changed
- `category_match_guard.py` — transport/person-tour suppressors; user-stop guard exemption.
- `user_stop_input.py` *(new)* — "Name + URL" parsing + share-link resolution.
- `identity_dedup.py` — fallback/centroid + user-stop dedupe exemption.
- `local802_relevance_gate.py` — same-building coords exemption for user stops.
- `area_resolver.py` — country→city-part scope fallback.
- `generate_tour_text.py` — wire parsing into forced_stops; pass tour_type to the guard;
  exempt user stops in the replenish + existence-gate paths.
- `tests/test_local852_user_stops_safe.py` *(new)* — 18 unit tests.
- `run_local852_live.py` *(new)* — budget-enforced live reproduction.
- `submission_artifacts/local852/` — live tour text + meter ledger.
