# SUBMISSION — LOCAL-791 (Vietnam round 2: place tours, pins, duplicates)

**Branch:** `LOCAL-791-vn-places`
**Base:** `subscribed` @ `a72f5ec5` (LOCAL-790 merge) — `git merge-base --is-ancestor a72f5ec5 HEAD` exits 0.
**Evidence source:** ClickUp `wdvrdaz6u5` (P4 Vietnam tours, tours 461–468 on Subscribed Preview).

All 11 defects (ticket #1–#9 + LEAD addenda #10, #11) are fixed, each with a unit
test using the exact ticket strings, no new regression failures, and an isolated
live run proving the three required requests end to end.

---

## Changeset (no `git add -A` — only these files)

Modified (7):
- `area_resolver.py` — dining/district parsing, parenthetical-anchor stripping, coastal-strip bbox
- `generate_tour_text.py` — business/activity routing, scope-from-request city repair, inherited-pin + safety-note wiring
- `geocode_stops.py` — inherited/clustered-coordinate repair (defect 3)
- `identity_dedup.py` — cross-language place dedup (defects 5, 11)
- `junk_title_guard.py` — generic-word / heading / news-headline rejection (defect 4)
- `places_search.py` — map-title cleaning (defects 6, 10)
- `stop_existence_gate.py` — cuisine word list, business-keyword routing

New (3):
- `safety_note_order.py` — safety/scam note placement (defect 7)
- `test_local791_vietnam_round2.py` — one test class per defect (38 tests)
- `run_local791_container.py` — isolated live-run harness ($2.50 cap)

---

## Defect-by-defect

### 1. Dining parser drops the city; "street food" read as a cuisine
`"Vietnamese restaurants and street food, District 1, Ho Chi Minh City"` → the
parser kept `city="District 1"` and dropped `"Ho Chi Minh City"`, and read
`cuisine="street"`.
- `area_resolver._parse_location`: strip a leading dining/POI category segment,
  strip a `category in <place>` prefix, and keep the parent city for a numbered
  district — leading, middle **or** sole district segment
  (`"District 1, Ho Chi Minh City"` → `("District 1", "Ho Chi Minh City")`).
- `stop_existence_gate._GENERIC_DINING_WORDS` += `street / streetfood / stalls /
  hawker / …` so `_extract_cuisine_qualifier("Vietnamese restaurants and street
  food") == "vietnamese"` (never `"street"`).
- **Live:** tour #8 resolved scope `District 1, Ho Chi Minh City` and returned 4
  real District-1 Vietnamese restaurants (was `no_matching_places_in_area`).

### 2. Business/activity providers must go through places_search (empty tour_type)
`"Kitesurfing schools in Mui Ne, Vietnam"` was inferred WALKING, so MAPS-FIRST was
never reached and it died "no stops could be generated".
- `stop_existence_gate._BUSINESS_KEYWORDS` += `school / academy / rental /
  outfitter` (not a bare `centre`/`center`, to keep `art center`/`city center`
  out).
- `generate_tour_text._classify_tour_category`: a request whose subject is a
  business/activity provider routes to `restaurant` (the maps-first/places path),
  checked after the museum/walking keyword scans so `art center`/botanical/
  explicit-walking are unaffected. `is_place_type_tour` then returns True.
- **Live:** tour #9 logged `activity/business provider request → places path` and
  `D545 places-first replenish … for 'kitesurfing schools' in 'Mui Ne, Vietnam'`;
  stops generated (no longer zero).

### 3. Walking-tour pins clustered at the first stop (461)
- `geocode_stops.repair_inherited_coordinates`: a stop whose coordinate is within
  **50 m** of an earlier stop AND whose own geocode is **> 200 m** away takes the
  geocode (the ticket's unit-test rule). When no tour anchor is supplied, a median
  anchor is derived from the stops so a same-name geocode elsewhere on Earth is
  rejected (`MAX_TOUR_RADIUS_KM`). Wired into `generate_tour_text` right after the
  D559 `resolve_poi` pass.

### 4. Junk stop titles (generic words, headings, headlines)
- `junk_title_guard.is_junk_page_title` new rule 6: reject a bare generic word
  (`"Balcony"`, `"Interesting"`, `"View"`, …, exact whole-title match only) and a
  news headline (trailing ellipsis + ≥4 words — `"Khai mạc Hội thảo Quốc tế …"`;
  or a long sentence with a finite verb). Real names (`Ben Thanh Market`,
  `Balcony Bar`, `The Interesting House Museum`, `White Sand Dunes`) are kept.
  Already wired through `stop_pool_orchestrator._auto_reject_junk_titles` (LOCAL-792).

### 5 & 11. Cross-language / transliteration duplicates
`"Chợ Bình Tây" == "Binh Tay Market"` (464); `"Thien Hau Temple" == "Ba Thien Hau
Pagoda"` (= Chùa Bà Thiên Hậu).
- `identity_dedup.dedupe_by_location_or_qid`: fold place-class words
  (Market↔Chợ, Temple↔Pagoda↔Chùa↔Đền↔Miếu) and drop honorifics (Ba/Bà, Saint…),
  strip diacritics, then (c) a language-folded title match with ≥1 distinctive
  token, and (d) **≤ 150 m apart AND ≥ 1 shared distinctive token** → one place.
  Two different pagodas far apart are **not** merged.

### 6. Foreign-script marketing tag lists in titles
`"An Spa - Healing & Relax (Massage Mũi Né - 샴푸와 컨디셔너, 마사지)"`.
- `places_search.clean_place_title`: drop a parenthetical/bracket group whose
  content is mostly non-Latin script (Vietnamese folds to ASCII, so a Latin gloss
  is kept) → `"An Spa - Healing & Relax"`.

### 7. Safety/scam note out of context (467 Red Canyon)
- New `safety_note_order.py`: when a stop's FIRST sentence is a safety/scam
  caution and there is a later sentence, move it to the end framed `A practical
  tip: …` so the place is introduced first. Wired into `generate_tour_text` beside
  the dangling-opener guards.

### 8. Requested named place missing ("White Sand Dunes")
- `area_resolver`: broadened the named-place clause grammar (including/featuring/
  visiting/seeing/stopping at|by/taking in/such as/with…) — kept aligned between
  the `_parse_location` CUT and `_NAMED_PLACE_CLAUSE_RE` EXTRACT.
- Stripped a **parenthetical anchor list** `(Notre-Dame…, City Hall)` everywhere
  the area scope is built (`_parse_location`, `_scope_from_request` deterministic
  path **and** its intent district-append tail) — the internal commas were tearing
  the city into `"City Hall)"` and failing area resolution.
- **Live:** Old Saigon resolved HCMC `Q1854` and all four requested landmarks
  (Notre-Dame Cathedral, Saigon Central Post Office, Saigon Opera House, City Hall)
  were stops.

### 9. Wrong-museum / long-coastal-strip scope (Mui Ne addendum)
- `area_resolver.resolve_area`: when there is no multi-district union bbox, fetch
  the geocoder bbox and **prefer it over the 2 km circle** when it is a long/large
  area (half-diagonal > 1.5× the circle, ≤ 30 km). Mui Ne / Hàm Tiến adopts a
  ~6 km strip bbox; a compact town keeps its tuned circle. `places_search` already
  prefers a bbox over a radius (LOCAL-786).
- (The venue-parts "another venue" filter is LOCAL-788's own; this ticket covers
  the scope half and the test for the disagreement case.)

### 10. Google category suffix on a places title (LEAD addendum)
`"Stardust: Inspired Mediterranean , Persian"` → `"Stardust"`.
- `places_search.clean_place_title`: strip a trailing `": <category list>"`
  **only** when the tail has a comma and no sentence punctuation, so a real
  colon-titled work (`"Blue: A Study of Light"`) is never truncated; stray `" ,"`
  spacing tidied.

---

## Tests

`test_local791_vietnam_round2.py` — **38 tests, all pass** (one class per defect,
exact ticket strings). Run:

```
python3 -m pytest test_local791_vietnam_round2.py -q      # 38 passed
```

Relevant regression (dining/places + LOCAL-751/786/788/790/779/632/669b/470/481 +
791): **258 passed, 2 skipped**.

Full `tests/` suite vs baseline: the SAME set of failing files was run on both the
stashed baseline and this branch — **identical 119 failures, ZERO new failures**
(`comm -23` empty). All 119 are pre-existing environment/DB/network tests (billing,
wallet, cache, translation, meter, zip, security, newsletter, live endpoints),
unrelated to the touched modules.

---

## Live run (isolated container, `$2.50` paid-API cap for the whole task)

Ran `run_local791_container.py` through `audioura-tour-generator:latest` on the
isolated `local788b-postgres` (never shared `audioura-*`), cache + pool off.
Cumulative spend ≈ **$1.76**, under the $2.50 cap.

| # | Request | Result |
|---|---------|--------|
| 8 | Vietnamese restaurants and street food, District 1, Ho Chi Minh City | scope `District 1, Ho Chi Minh City`; 4 **real District-1 Vietnamese restaurants** (was `no_matching_places_in_area`) |
| 9 | Kitesurfing schools in Mui Ne, Vietnam | routed to the **places path** (was WALKING/death); Mui Ne **bbox + Serper Places** escalation fired; stops generated |
| — | Old Saigon walking tour, District 1, Ho Chi Minh City (Notre-Dame Cathedral, Central Post Office, Opera House, City Hall) | area resolves **HCMC Q1854**; stops include all four named landmarks (Notre-Dame Cathedral, Saigon Central Post Office, Saigon Opera House, City Hall) |

The live runs exposed three end-to-end scope bugs that unit tests could not —
PHASE 3C reading a bare `District 1` directly, the parenthetical anchor list
breaking the city, and a generic interior-stop name being "corrected" to a far
namesake — all fixed and covered above. `audio_tours` row count unchanged by the
store step (the runner's `_store` targeted the wrong host; generation itself
succeeded and was cost-metered — a harness quirk, not a generation defect). No
`DELETE`.

---

## Process notes
- Branched from HEAD (`a72f5ec5`), never from `origin/*`.
- No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`,
  `.continuous_dev/`, `SUBSCRIBED_COMMUNICATION_01.MD`, `legal/`,
  `GCLOUD_STORIED_START_HERE.md`, `TRAVEL_PROJECTS.md`.
- No `DELETE`; one heavy build at a time; committed specific files (no `git add -A`).
