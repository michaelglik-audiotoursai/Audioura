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


---

# 855B — the bounce: the delivered Sophia text was still not shippable

LEAD read the delivered `submission_artifacts/local855/live_tour_7stops.txt` and
listed ten defects still present. The root problem was not ten separate bugs —
it was that **the user-stop scrub was regex-brittle and the live runner's checks
were vacuous substring bans**: the model re-wrote every defect in a NEW phrasing
on the 855B run, the old literal bans did not match the new wording, and the
runner reported PASS while the defects shipped. The fix is twofold: (a) make the
scrub catch the DEFECT CLASS, not a phrasing, and add a decisive grounded-body
substitution when a thin stop is fabrication end-to-end; (b) make the runner
HONEST — a semantic scan that re-runs the scrub and FAILS the old artifact.

## Diagnosis (why the first 855B run still shipped the defects)

- The scrub's `_LEGEND_/_ANECDOTE_/_ART_PROVENANCE_` markers were the exact
  strings from the 855 run. On 855B the model wrote *"the layered urban fabric
  Caillebotte studied"* (not "Art Institute of Chicago"), *"One account that
  lingers among regulars … opened doors to professional contracts … springboard"*
  (not "first record deal"), *"marks a turning point … opened a door … step into
  public view"* (not "pivotal night"), *"near Hồ Tràm, a coastal commune … a
  hundred kilometers southeast of Saigon"* (not "Đồng Khởi / Lam Sơn Square").
  None matched — zero sentences were dropped.
- The scrub's **never-empty rule** kept the WHOLE fabricated body when every
  sentence was off-venue (the delivered An Spa / Acoustic bodies).
- A phantom **cross-stop motif** — *"a launching point not unlike the sackbut you
  paused beside earlier"* — slipped the D636 callback budget ("paused beside" was
  not a recap verb and the budget had room).
- The closer read *"the history of the twenty-first century … they trace how this
  place changed across the twenty-first century"* — a FALSE period thread derived
  from the 2025 references the scrub left behind.
- `_NATIONAL_FIGURE_RE` had a global `(?i)` so `born [A-Z]` matched the lowercase
  "is" in the venue's OWN name — *"A Star is Born is known…"* was wrongly dropped.
- **Longan narrated as a Fruit Market, An Spa placed at Hồ Tràm beach ~100 km
  away** are RESOLUTION artifacts, not narration defects: in this offline
  reproduction the listener's Google share links are munged placeholders
  (`https___share.google_z20B`) that do not resolve, so "Longan" geocodes BY NAME
  to a real HCMC fruit market and "An Spa" to the Hồ Tràm resort. Narration is
  faithful to what resolved; the field request had working links. Documented in
  the runner (the fruit-market subject is deliberately NOT banned); the narration
  DEFECT for that stop (the dragon legend) is gone.

## The fixes, at source

1. **Title (defect 1):** `title_line_guard` reads the real category
   ("featuring a cycling tour" / "the biking category") and NEVER defaults to
   "museum" — delivered header is "… - Cycling Tour".
2. **Transit (defect 2):** generic prompt forbids naming a transit station
   unless sourced for THIS city (`generate_tour_text.py:18055`); no "T station".
3. **Legend (defect 3):** `_LEGEND_MARKER_RE` broadened to plural
   legends/dragons and the contentless legend-ALLUSION filler ("carries a tale",
   "legends of this land", "timeless narrative", "the tale is tangible").
4. **Art digression (defect 3 class):** `_ART_PROVENANCE_RE` now catches the
   painter + art vocabulary ("the canvas", "brushwork", a famous painter's
   surname, "<Name> studied the urban fabric"), not just "Art Institute".
5. **Fabricated anecdote / firsts (defect 4):** `_ANECDOTE_MARKER_RE` broadened to
   the rephrased discovery/launch story ("one account", "tells of", "fledgling
   artist", "opened doors to professional contracts", "springboard", "trajectory
   from local obscurity") and the pioneering claim ("turning point", "opened a
   door", "step into public view", "before this … confined to underground").
6. **Hedge / off-venue biography (defect 5):** `_NO_DIRECT_TIE_RE` already caught
   it; fixed the `_NATIONAL_FIGURE_RE` false positive ("born <Capital>" is now
   case-sensitive, so "A Star is Born is known…" is kept).
7. **Off-pin placement (defect 6):** `scrub_offpin_landmarks` keeps the
   ~300 m-radius landmark check; `_ADMIN_GEOGRAPHY_RE` extended for the Hồ Tràm
   relocation ("coastal commune", "N kilometers southeast", "Xuyên Mộc",
   "Bà Rịa–Vũng Tàu", "sprawling new wards") and a bare "population … N million".
8. **Crazy-street pin (defect 7):** resolves via `landmark_reference` + `pin_snap`
   to Bùi Viện (10.767, 106.693) — delivered pin is 0 m off.
9. **Date scope (defect 8):** the dated/anecdote drop is source-gated by the
   stop's KIND; the documented-kind set was TIGHTENED (dropped "market", "gallery",
   "park", "square", "tower", "theatre" — a thin/mis-resolved venue routinely
   carries one, e.g. "Fruit Market") so a monument (Notre-Dame, a cathedral) keeps
   "built 1863–1880" while a mis-resolved "Fruit Market" is still date-gated.
10. **Thread safety (defect 9):** `_USER_STOP_TITLES` lives in a per-job
    `contextvars` scope copied into the worker pool; a two-concurrent-jobs test
    proves isolation.
11. **Closer (defect 10):** for a user-stops tour `build_conclusion` forces the
    thread to "the places you chose across <city>" (no derived period/subject, no
    named example); `_COUNT_OPENER` now also matches a spelled-out count so the
    number-spelled spine recap ("That's seven stops …") is stripped before the
    thematic close.

**New, robust controls (the step past whack-a-mole):**
- `grounded_user_stop_body()` — when the scrub would drop EVERY sentence of a thin
  user stop, the body is REPLACED with a deterministic 2–4 sentence description
  built from what is known (name, kind, district, the listener's examples), which
  can carry no date/anecdote/legend/landmark.
- `strip_all_cross_stop_callbacks_in_text()` — a user-stops tour has no shared
  thread, so EVERY cross-stop callback is dropped (budget zero); this removes the
  phantom "sackbut you paused beside earlier".

## Runner is now honest

`run_local855b_live.py` adds the rephrased markers AND a **semantic defect scan**
that re-runs the scrub + the user-stops callback strip over each delivered body;
any sentence the scrub would still drop FAILS the run. The scan FAILS the old
855 artifact (14 residual) — proof it is not vacuous.

## Live — budget enforced, PASS

`TASK_BUDGET_ID=LOCAL-855B TASK_BUDGET_USD=0.50`, meter contract, own meter dir
`_local855b_meterlogs` (D753 Mac-local no-mount; never writes the live DB, never
touches the shared `audioura-*` containers).

**RUN A — Sophia's 7-stop biking tour** — `submission_artifacts/local855b/live_tour_7stops.txt`
- 7/7 delivered (Rambutan, Longan, The Crazy street, Thi Bar Saigon, A Star is
  Born, Acoustic Bar, An Spa);
- title "Ho Chi Minh City, Vietnam - Cycling Tour" (not Museum);
- all banned markers absent; **semantic defect scan clean**;
- The Crazy street pin (10.7672, 106.693) is **0 m** from Bùi Viện;
- closer: "the places you chose across Ho Chi Minh City" — no generic/century
  thread, no "carry with you", no "sackbut" callback.

**RUN B — 3-stop with a FAMOUS stop** — `submission_artifacts/local855b/live_tour_notredame_3stops.txt`
- Notre-Dame Cathedral Basilica of Saigon keeps its sourced dates **1863 / 1877 /
  1880** (defect 8 does not over-scrub a documented monument).

Metered **$0.041 / $0.50** (`submission_artifacts/local855b/meter_ledger.json`).

## Tests

`tests/test_local855b_fixes.py` — **37 passed** (offline/deterministic): the ten
defects plus the bounce rephrasings (Caillebotte/canvas, the rephrased Acoustic
anecdote, the Thi pioneering claim, the An-Spa Hồ Tràm placement, the vague
legend allusion), the national-figure false-positive guard, the grounded-body
substitution, the user-stops cross-stop callback strip, and the spelled-recap
strip. Full related regression (user-stop / conclusion / cross-stop / title
suites): **207 passed, 3 skipped (network)**.

## Files changed (855B)
- `user_stop_narration.py` — broadened legend/anecdote/art/admin-geography/
  national-figure detectors; `grounded_user_stop_body()`; tightened
  documented-kind date gate; synthetic-poi now carries Address + examples.
- `cross_stop_reference_guard.py` — `strip_all_cross_stop_callbacks_in_text()`
  (user-stops zero-budget callback strip + broadened "paused beside … earlier").
- `tour_conclusion.py` — user-stops thread override; `_COUNT_OPENER` matches a
  spelled-out count.
- `generate_tour_text.py` — wired the user-stops callback strip; passes
  `user_stops` into `rebuild_conclusion`.
- `run_local855b_live.py` (new) — budget-enforced two-run proof + the honest
  semantic defect scan.
- `tests/test_local855b_fixes.py` (new) — 37 tests.
- `submission_artifacts/local855b/` — both delivered texts + meter ledger.


---

# 855D — the second bounce: stop adding regexes; check sentences against a fact sheet, and fix the "Đ." address cut

LEAD read `submission_artifacts/local855b/live_tour_7stops.txt` and found three
defect classes still shipping. The headline is item 3: the fabrication was back
in NEW wording ("a quiet homage to that mythic past", "those tumultuous weeks
when the city's fate was being decided", "opened doors for acceptance",
"The story passed down through the neighborhood", "played a critical role for
many local artists"), which proves **regexes cannot win** — every phrasing the
scrub learns, the narrator re-invents. Base: `subscribed` (70737c2a);
`git merge-base --is-ancestor 70737c2a HEAD` exits 0 (the branch carried an older
subscribed, so 70737c2a was merged in first).

## 1 — Addresses cut at the abbreviation dot ("Address: 15 Đ.")

"Đ." is Vietnamese for *Đường* (Street); "P." = Phường (Ward), "Q." = Quận
(District), "TP." = Thành phố (City). The ONE shared splitter the whole pipeline
uses, `sentence_split.split_sentences`, cut "15 Đ. Nguyễn Văn Tráng, …" into the
stub "15 Đ." + "Nguyễn Văn Tráng, …": its abbreviation guard knew only English
titles, and its single-initial rule matched only ASCII `[A-Z]`, never the
Vietnamese "Đ". A later gate then kept/dropped one fragment and the stub shipped
(the directions line "Start by cycling along Đ." is the same cut, echoed).

- **Fixed at the splitter root** (`sentence_split.py`), so every one of the ~20
  gates that calls it is fixed at once — NOT a new regex in a scrub. Added
  `đ, p, q, tp, kp` (and `ave, blvd, rd, hwy`) to `_ABBREV`, and widened
  `_TRAILING_TOKEN` to recognise the Vietnamese "Đ/đ" so the abbreviation lookup
  can see it. Real sentence boundaries, English initials ("Isabella V."), and US
  acronyms ("U.S. Army") are unaffected.
- `tests/test_local855d_address_abbrev_dot.py` — 9 tests, incl. the ticket's
  `"15 Đ. Nguyễn Văn Tráng, Phường Bến Thành, Quận 1"`. Commit `d64fb550`.

## 2 — Walking words in a cycling tour

The delivered cycling tour read "about a 19-minute walk", "about a minute's walk"
and "the vibrant street life as you walk". The two distance phrases came from
`walking_directions_guard._approx_distance_phrase`, which was transport-mode
blind; the prose "walk" came from the narrator.

- `_approx_distance_phrase(km, mode)` is now **mode-aware**: on a bike tour it
  gives a distance (under ~400 m) or a **ride time** (~15 km/h), and NEVER says
  "walk"; walking behaviour is unchanged. Mode is an explicit arg or detected
  from the tour header ("… - Cycling Tour"), covering the container path.
- **`transport_word_guard.py`** (new) — a deterministic every-path pass that
  rewrites a pedestrian movement word in LLM prose ("walk"→"ride", "stroll"→
  "ride", "on foot"→"by bike") on a wheeled tour; no-op on a walking tour; matches
  whole words only, so "walkway/boardwalk/crosswalk" are untouched. Wired into
  the finalize block right after the directions guard.
- `tests/test_local855d_transport_words.py` — 14 tests. Commit `91cb90e2`.

## 3 — Fabrication (the approach change): fact sheet + ONE cheap verification call

The ticket's prescription, implemented in **`user_stop_verify.py`** (new):

- **`build_fact_sheet(poi, location, outdoor_facts)`** — the KNOWN facts only:
  resolved name, kind (Places type), address, district, the listener's examples,
  the city, and any retrieved source that names the venue.
- **`verify_user_stops_in_text(...)`** — ONE cheap **gpt-4.1-mini** call per tour,
  ALL user stops **batched in a single JSON request** (temperature 0, seed 7,
  `response_format=json_object`). It labels each body sentence **SUPPORTED** (by
  the fact sheet), **SENSORY** (what to notice, no claim of fact), or
  **UNSUPPORTED**. **UNSUPPORTED sentences are dropped**; if **fewer than 2**
  survive, the body is replaced with the deterministic **`grounded_user_stop_body()`**.
  Logs **`[LOCAL-855D] verify <stop> kept K dropped D`** per stop.
- The existing regex scrub (`scrub_tour_text_user_stops`) stays as the cheap
  **first pass**; **NO new fabrication regex is added** — the only regexes in the
  new module are the structural "Stop N:" block parsers (the same grammar the
  scrub already uses). A documented-monument kind (cathedral/basilica/palace/
  museum/landmark/…) is skipped so its sourced dates survive; the trailing tour
  conclusion absorbed into the last block is excluded from a stop's body.
- **Added cost: ~$0.001 per tour** (live run: in=1433 out=273 tok → $0.00101),
  well under the $0.005 budget.
- Wired into `generate_tour_text` immediately after the 855B scrub, before return.
- `tests/test_local855d_fact_sheet_verify.py` — 10 offline tests (the single call
  mocked): fact sheet, UNSUPPORTED drop, <2→grounded, log format, cost<$0.005,
  no-key no-op, structure preserved, documented-kind skip, conclusion exclusion.
  Commit `0a88a445` (+ refinements in `c53202cd`).

## 4 — Real inputs

The exact cloud share links (orch `ef0cee57` / tour 525/523) are not reachable
from this Mac-local worktree, and the task forbids reading/writing the live DB.
Per the ticket's stated alternative, the live run uses **REAL Google Maps place
URLs** for the District-1/3 venues, resolved through the **LOCAL-852 resolver**
(`user_stop_input`). Each URL carries `/maps/place/<Name>/@<lat>,<lng>` and
resolves **offline** (no paid API) to a real name + coordinate — which fixes the
prior run's munged placeholder links (`https___share.google_z20B`) that geocoded
"Longan" to a Fruit Cafe and "Rambutan" to a Boutique Hotel. Commit `4433674f`.

## Live — budget enforced, PASS

`run_local855d_live.py`: `TASK_BUDGET_ID=LOCAL-855D TASK_BUDGET_USD=0.40`, meter
contract, OWN meter dir `_local855d_meterlogs` (D753 Mac-local no-mount escape
hatch — never writes the shared/live DB, never touches the `audioura-*`
containers), cheap env + `STORY_PASS_MODEL=gpt-4.1`, pool OFF.

**RUN A — Sophia's 7-stop cycling tour** — `submission_artifacts/local855d/live_tour_7stops.txt`
- 7/7 delivered (The Crazy street, Thi Bar Saigon, Rambutan, A Star is Born,
  Longan, An Spa, Acoustic Bar);
- title "Ho Chi Minh City, Vietnam - Cycling Tour";
- **none of the eight quoted fabrications, or a paraphrase, appears** (checked
  literally AND by re-running the scrub as a semantic class scan — clean);
- **no "Đ." address stub**; **no walking words anywhere**; **each stop is about
  its venue**.

**RUN B — 3-stop with Notre-Dame** — `submission_artifacts/local855d/live_tour_notredame_3stops.txt`
- Notre-Dame Cathedral Basilica of Saigon **keeps its sourced dates 1877 & 1880**
  (1863–1880; the verifier skips a documented monument so it is not over-scrubbed).

Metered **$0.041 / $0.40** (`submission_artifacts/local855d/meter_ledger.json`).
The fact-sheet verification call added **$0.00101** on run B and a similar amount
on run A — comfortably under the $0.005-per-tour target.

## Tests

```
python3 -m pytest tests/test_local855d_address_abbrev_dot.py \
  tests/test_local855d_transport_words.py \
  tests/test_local855d_fact_sheet_verify.py -q          # 33 passed
```
Full related regression (855D + 855B + 855 + walking + splitter):
**150 passed, 3 skipped (network)**.

## Files changed (855D)
- `sentence_split.py` — Vietnamese address abbreviations; Đ/đ trailing-token.
- `walking_directions_guard.py` — mode-aware distance phrase; `_mode_from_text`.
- `transport_word_guard.py` (new) — pedestrian-word rewrite on a wheeled tour.
- `user_stop_verify.py` (new) — fact sheet + ONE batched gpt-4.1-mini verification
  call; UNSUPPORTED drop; <2→grounded; documented-kind skip; cost report.
- `generate_tour_text.py` — wired the transport-word guard and the fact-sheet
  verify pass (after the 855B scrub).
- `run_local855d_live.py` (new) — budget-enforced live proof + PASS checks.
- `tests/test_local855d_{address_abbrev_dot,transport_words,fact_sheet_verify}.py`
  (new) — 33 tests.
- `submission_artifacts/local855d/` — both delivered texts + meter ledger.

Commits: `d64fb550` (1), `91cb90e2` (2), `0a88a445` (3), `4433674f` (4),
`c53202cd` (5).
