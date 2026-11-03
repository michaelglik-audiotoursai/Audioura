# SUBMISSION — LOCAL-855

**User-chosen stops get narration about the wrong thing: bars narrated as
fruit/streets, a cross-tour "you saw" callback to a museum not on the tour,
filler, wrong transport mode.**

Branch: `LOCAL-855-user-stop-narration`
Base: `subscribed` (ad716811; contains 24671e41 / LOCAL-852 merge 4386ea6a) —
`git merge-base --is-ancestor ad716811 HEAD` exits 0.

Evidence reproduced from LOCAL-852's own 7/7 run:
`git show LOCAL-852-user-stops-safe:submission_artifacts/local852/live_tour_7stops.txt`.

---

## The six defects, each fixed at its source

### 1 — Wrong subject (bar narrated as the fruit / a street / a legend)
"Rambutan" (Type: Restaurant and Bar) was narrated as rambutan TREES; "Longan"
(Type: Bar) as "this street, named Longan" plus a dragon legend. The stop's own
Type/Specialty line knows the venue; the body ignored it.

- **New module `user_stop_narration.py` → `user_stop_subject_block()`**, injected
  into the non-museum stop body prompt at **`generate_tour_text.py:22307`** (right
  after the NO CONDESCENSION block). It states the venue name + Type/Specialty as
  the SUBJECT, and forbids narrating the literal/dictionary meaning of the name
  (fruit, tree, plant, river, legend, historical figure) or presenting a named
  venue as a natural feature — **unconditionally for a user stop**, because the
  Type metadata for a tiny private venue is itself unreliable.

### 2 — Cross-tour leak ("…which you saw at the Art Institute of Chicago")
No Chicago stop exists in this tour. The LOCAL-634/635 recall guards missed it:
the recall carried no "earlier/already" tail, and token-overlap anchoring falsely
anchored it on the generic word "street" (shared with "The Crazy street").

- **`cross_stop_reference_guard.py:399` `_SAW_AT_PLACE_RE` + `:408`
  `_saw_at_unseen_place()`**, wired into `_callback_names_unseen` BEFORE the
  generic recall-anchor test. It fires on "(you) saw/viewed/encountered … at THE
  <Proper Place>" when that place is not a delivered stop, trimming swept-in
  lowercase words and keeping a callback whose place tokens are a subset of a
  delivered title (generic words bar/street/spa excluded). Removed through the
  existing production guard chain (`strip_unseen_callbacks_in_text`).

### 3 — Filler unrelated to a thin venue (airport, Cần Thơ, 1975 offensive, Hồ Chí Minh pseudonyms)
With no sourced material about a small private venue, say less.

- The subject block (above) forbids padding with regional/national history that
  does not name the venue and, when no material is sourced, instructs a SHORT
  (2–4 sentence) stop.
- **Post-generation LOCAL-802 relevance scrub** `scrub_user_stop_body()` applied
  to each user stop's delivered body at **`generate_tour_text.py:24102`**: drops a
  sentence that names none of the venue / its kind / the tour city AND carries an
  off-topic marker (airport, provinces, municipality, army/offensive, a huge
  population count, a national-figure biography).

### 4 — Probable fabrications (Thi Bar 2016/VietPride 2018; Acoustic Bar 2015; An Spa address)
A dated claim about a user venue must be grounded in a retrieved source naming the
venue. The narration writer produces dates from its training data, never from
per-sentence retrieval.

- `scrub_user_stop_body()` drops **every dated sentence** (a specific year or full
  date) from a user-stop body, logged `[LOCAL-855] unsourced dated claim dropped`.
  A bare century ("19th century") is not a dated claim and is kept. The subject
  block also forbids stating an address on a specific street unless sourced.

### 5 — Invented street names in directions ("intersection with Le Van Sy Street")
Between two stops with no route data, directions invented a plausible street.

- **`directions_generator.py:533` `generate_walking_directions`** now branches on
  route data. With no address on either stop it uses a distance+compass-only
  prompt (`distance_and_compass()` at `:441`) and two post-guards reject any
  street/landmark the model slips in: `names_invented_street()` (`:481`, suffix
  form "X Street") and `names_navigation_landmark()` (`:506`, bare form "turn onto
  Võ Văn Tần"). On rejection the caller uses the deterministic fallback
  `_directions_fallback_855()` (`generate_tour_text.py:982`): "Head <compass> to
  <stop> — it is <distance> away." The call site (`:30431`) now passes the poi
  DICTS (not bare names) so coordinates/addresses are available. When stops carry
  geocoded addresses, real streets are allowed.

### 6 — Wrong transport mode (request says biking; tour said "walking tour")
The user-stops path is invoked as `generate_tour_text(location, "Sophia's biking
tour", …)` — the transport word lives in the TOUR_TYPE, but Layer-1 keyword
detection read only `location`.

- **`generate_tour_text.py:11800`** `_detect_transport_mode` is now run against the
  `tour_type` as well; a transport word in either sets the mode (keyword still
  beats intent). The delivered tour now opens on a "cycling journey".

### Robustness note (why the fixes fire)
Narration runs in a worker ThreadPool and `poi_list` is rebuilt several times
(the D571 hazard), which can drop a stop's `user_explicit` flag. The clean
user-stop titles are recorded once at seeding (`_set_user_stop_titles` at
`generate_tour_text.py:13190`) in a plain module global (NOT thread-local, so
workers can read it); the body-prompt injection re-marks a poi `user_explicit`
when its title matches a recorded user-stop title. This is why the subject block
and body scrub still fire for these stops.

---

## Unit tests (from the exact evidence strings)

`tests/test_local855_user_stop_narration.py` — 24 tests, deterministic/offline:
- bar-named-like-a-fruit narrated as the venue (subject block binds to Type,
  forbids the fruit/legend reading);
- no "you saw at <place not in the tour>" callback (Art-Institute-of-Chicago leak
  dropped; a callback to a delivered stop kept);
- unknown-venue stop stays short & on-topic (airport/Cần Thơ/1975 filler and all
  dated claims dropped; venue sentences kept; VietPride-2018 dropped even with
  attached material);
- invented street flagged (suffix and bare forms); distance+compass fallback;
- mode=biking from the tour type.

```
python3 -m pytest tests/test_local855_user_stop_narration.py -q   # 24 passed
```

Full guard + user-stop + directions regression (no regressions):
```
python3 -m pytest tests/test_local855_user_stop_narration.py \
  tests/test_local852_user_stops_safe.py \
  tests/test_local616_phantom_cross_reference.py \
  tests/test_local635_sentence_integrity.py tests/test_local640_invented_names.py \
  test_local627_cross_stop_bridges.py test_local634_title_line.py \
  test_local650_walking_route.py test_local638_directions_between_stops.py -q
# 125 passed, 3 skipped (network)
```

---

## Live — budget enforced

`run_local855_live.py`: `TASK_BUDGET_ID=LOCAL-855 TASK_BUDGET_USD=0.60`, meter
contract, OWN meter dir `_local855_meterlogs` (`METER_MOUNT_GUARD=0`, D753 Mac-local
no-mount escape hatch — never writes the shared/live DB, never touches the
`audioura-*` containers), cheap env + `STORY_PASS_MODEL=gpt-4.1`, pool OFF.
Same 7-stop "Sophia's biking tour in Ho Chi Minh City" request as LOCAL-852.

**RESULT: PASS** — `submission_artifacts/local855/live_tour_7stops.txt`
- 7/7 stops delivered (Rambutan, Longan, The Crazy street, Thi Bar Saigon, A Star
  is Born, Acoustic Bar, An Spa);
- each stop is about its venue (Types: Bar / Restaurant / LGBT Bar / Karaoke Bar /
  Live Music Bar / Spa / nightlife street);
- no cross-tour callback (Art Institute of Chicago gone);
- no invented street names (distance+compass fallback where there is no route
  data);
- mode is biking ("cycling journey");
- no dated unsourced claim in any body (89 scrub drops across the run: the airport
  project, the Cần Thơ 2025 merger, the 1975 offensive, VietPride 2018/2019, the
  Bức Tường 2015 performance all removed);
- metered **$0.04 / $0.60** (`submission_artifacts/local855/meter_ledger.json`).

---

## Files changed
- `generate_tour_text.py` — mode from tour_type; user-stop subject block + body
  scrub wired into narration; user-stop title store; directions call passes poi
  dicts + deterministic distance+compass fallback.
- `user_stop_narration.py` (new) — subject-binding prompt block + LOCAL-802
  relevance / ungrounded-date body scrub.
- `cross_stop_reference_guard.py` — "you saw … at <external place>" cross-tour
  callback detector.
- `directions_generator.py` — no-route-data distance+compass directions + two
  invented-street/landmark post-guards.
- `run_local855_live.py` (new) — budget-enforced live reproduction + PASS checks.
- `tests/test_local855_user_stop_narration.py` (new) — 24 tests.
- `submission_artifacts/local855/` — delivered text + meter ledger.
