# SUBMISSION — LOCAL-791B (English names, on-topic stops, pin proof)

**Branch:** `LOCAL-791B-names-category`
**Base:** `subscribed` @ `e75e698f` — `git merge-base --is-ancestor e75e698f HEAD` exits 0 (branched from HEAD, never `origin/*`).
**Ticket:** LOCAL-791 leftovers (LEAD, Mac e2e @ `a72f5ec5`: "Pagodas and temples of HCMC (Jade Emperor Pagoda, Thien Hau Temple)").

All four leftovers are implemented, each with a unit test using the exact ticket
strings, no new regression failures, and an isolated live run.

---

## Changeset (no `git add -A` — only these files)

Modified (1):
- `generate_tour_text.py` — wiring only: after PHASE 4 (and in the Part C
  replenish loop) call the off-category guard (item 2) and the titling helper
  (item 1). Additive prints; no existing logic changed.

New (6):
- `place_title_naming.py` — item 1 titling helper (pure, offline).
- `category_match_guard.py` — item 2 off-category guard (pure, offline).
- `pin_proof.py` — item 3 pin-proof (parse stops → geocode name → distance).
- `run_local791b_container.py` — isolated live-run harness with the pin table.
- `tests/test_local791b_names_category.py` — items 1 & 2 (15 tests).
- `tests/test_local791b_pin_proof.py` — item 3 (11 tests).

Moved (1, item 4):
- `test_local791_vietnam_round2.py` → `tests/test_local791_vietnam_round2.py`
  (`git mv`; `sys.path` repointed to the repo root; still 38 pass).

---

## Item-by-item

### 1. English tour, local name in parentheses
`place_title_naming.title_for_candidate(cand, tour_language, named_anchors)` chooses
and formats a stop's display title in the ticket's priority order:

1. **The user's own wording.** A NAMED anchor keeps EXACTLY the user's name —
   "Jade Emperor Pagoda" stays "Jade Emperor Pagoda", never re-labelled.
2. **The Wikidata label in the tour language**, with the local-language label in
   parentheses — "Mariamman Hindu Temple (Chùa Bà Ấn Độ)". For a Russian tour the
   Russian label leads: "Собор Сайгонской Богоматери (Nhà thờ Đức Bà Sài Gòn)".
3. **The Serper Places English title**, with any distinct local name in
   parentheses — "Vinh Nghiem Pagoda (Chùa Vĩnh Nghiêm)".

`format_place_title` never prints "X (X)" or empty "Name ()", and never double-wraps
a title that already carries a gloss. Wired in `generate_tour_text` right after
PHASE 4, over `poi_list`, with `tour_language='en'` (the base tour is generated in
English; the downstream translation path localises the primary name for other
languages) and the named anchors taken from `intent.named_places` +
`area_resolver.extract_named_places_from_clause`.

### 2. Off-category stop (Tao Dan Park in a pagodas-and-temples tour)
`category_match_guard`:
- `requested_categories(request)` reads the plural category nouns (reusing the
  LOCAL-790 vocabulary): "pagodas and temples" → `{"worship"}`; "temples and
  parks" → `{"worship","park"}` (a MIX widens, never narrows); a non-category
  request → `∅` (guard is a no-op).
- `classify_place(title, category_text)` classifies one candidate from its
  Serper/OSM category first, then its title — "Tao Dan Park" / "Park" → `park`;
  "Jade Emperor Pagoda" / "Buddhist temple" → `worship`; the Vietnamese local word
  "Chùa …" → `worship`.
- `filter_off_category(...)` drops a candidate whose class is a KNOWN other class,
  logging **`[LOCAL-791B] off-category <title> <category>`**; an UNKNOWN class is
  kept (never drop a real place we cannot classify); a user-named anchor is always
  kept. Wired after PHASE 4 **and** in the Part C replenish loop, so a replacement
  park cannot sneak back in.

### 3. Pin proof (distances were missing from the LOCAL-791 submission)
`pin_proof`:
- `parse_tour_stops(text)` pulls each stop's title + shipped coordinate.
- `reference_for_name(name, scope, scope_center)` geocodes the stop NAME
  independently — Serper Places first (the authority the places path itself uses,
  biased by the scope-centre `ll`, not scope-bound, so a real place a few km from
  the centre is accepted), then Nominatim. It strips a trailing architectural
  feature word ("… facade", "… grand staircase", "vestibule") so a narration
  sub-part title still resolves to its building, and it REJECTS a same-name match
  in another city with a 50 km scope-sanity bound (bare "City Hall" was resolving
  to Florida).
- `pin_report` / `format_pin_table` produce the per-stop distance table and a
  pass/fail against `PIN_TARGET_M = 100` m, using `geocode_stops.haversine_m` so
  the numbers match the repair gate's.

### 4. Move the round-2 test into `tests/`
`git mv` to `tests/`, `sys.path.insert(0, dirname(dirname(abspath(__file__))))` to
reach the repo root (the pattern every other `tests/` module uses). **38 pass.**

---

## Tests

```
python3 -m pytest tests/test_local791b_names_category.py -q    # 15 passed
python3 -m pytest tests/test_local791b_pin_proof.py -q         # 11 passed
python3 -m pytest tests/test_local791_vietnam_round2.py -q     # 38 passed (moved)
```

Regression (786/788/788-D545/788B/790 + 779 + the moved 791 + new 791B):
**139 passed, 2 skipped** (the 2 are `@network`, skipped by default). Related
dining/places/anchor set (779/779B/783/784/576/481/470/529): **147 passed**.

**Full `tests/` suite vs baseline — ZERO new failures.** The same suite
(`-m "not service and not network"`) was run on the branch and on a baseline tree
(the base `generate_tour_text.py` restored, the new files hidden): **184 failing
nodes on both; `comm -23` of the two failure lists is empty.** Every one of the
184 is a pre-existing environment failure (psycopg2/DB down, wallet, billing,
connectivity, translation meter) unrelated to the touched module. The only tracked
change is additive wiring + prints in `generate_tour_text.py`, so the baseline
result holds.

---

## Live run (isolated container, $2.00 whole-task cap)

Ran `run_local791b_container.py` through `audioura-tour-generator:latest` on the
isolated `local788b-postgres` (network `local788b_default`; never shared
`audioura-*`), cache + pool off, `STOP_EXISTENCE_GATE_MODE=log_only`. The OpenAI
Mac key **worked** (no `project_spend_limit_exceeded`). Cumulative LOCAL-791B spend
**$1.80** of the $2.00 cap (cost_ledger `TEST-LOCAL-791B`: $0.322 + $0.5507 +
$0.9268; mostly Gemini grounding, OpenAI ≈ $0.54). Each delivered tour stored as
one additive `is_test` row (ids 5, 6). No `DELETE`.

### Tour 0 — "Pagodas and temples of HCMC (Jade Emperor Pagoda, Thien Hau Temple)" (row 5)
Intent `poi_type: "pagodas or temples"`; classified `tour_category='walking'` (a
LOCAL-790 plural-category-in-area request → multi-venue walking tour). **3 stops,
all pagodas — Giac Lam Pagoda, Xa Loi Pagoda, Phuoc An Hoi Quan Pagoda. NO Tao Dan
Park** → **item 2 proven on-category** (the exact Mac-e2e defect no longer appears).

Pin proof (item 3), scope centre geocoded HCMC `(10.7737, 106.7166)`:

| # | Stop | Shipped pin | Serper/Nominatim reference | Source | Distance | ≤ 100 m |
|---|------|-------------|-----------|--------|----------|----------|
| 1 | Giac Lam Pagoda | 10.77910, 106.62810 | 10.77871, 106.64919 | serper | 2304 m | ❌ |
| 2 | Xa Loi Pagoda | 10.75750, 106.63610 | 10.77803, 106.68646 | serper | 5956 m | ❌ |
| 3 | Phuoc An Hoi Quan Pagoda | 10.75930, 106.64440 | 10.75515, 106.65885 | serper | 1645 m | ❌ |

**Finding:** the references resolve (item 3 now reports real distances — the gap
the LOCAL-791 submission left), and they show the SHIPPED pins are 1.6–6 km off the
authoritative coordinate for each named pagoda. This is a real coordinate-quality
gap: the LLM-written pins were not geocoded to the real place. LOCAL-791 item 3
(`repair_inherited_coordinates`) only corrects a pin INHERITED from a neighbour —
it does not geocode an independent-but-wrong LLM pin — so the ≤ 100 m target is
NOT met here. The pin proof is what makes this visible with numbers.

### Tour 1 — "Old Saigon walking tour, District 1, HCMC (Notre-Dame Cathedral, Central Post Office, Opera House, City Hall)" (row 6)
**6 stops, all four requested landmarks present** — Notre-Dame Cathedral Basilica,
Saigon Central Post Office, Saigon Opera House, City Hall — plus Saigon Notre-Dame
Basilica.

Pin proof (item 3), scope centre geocoded District 1 `(10.7754, 106.6996)`:

| # | Stop | Shipped pin | Reference | Source | Distance | ≤ 100 m |
|---|------|-------------|-----------|--------|----------|----------|
| 1 | Notre-Dame Cathedral Basilica facade | 10.77610, 106.69590 | 10.77977, 106.69904 | nominatim | 533 m | ❌ |
| 2 | Saigon Central Post Office portico | 10.77650, 106.69510 | 10.77985, 106.69984 | serper | 638 m | ❌ |
| 3 | Saigon Opera House grand staircase | 10.77520, 106.69560 | 10.77661, 106.70317 | serper | 842 m | ❌ |
| 4 | City Hall | 10.77630, 106.69540 | — (no in-scope match) | — | — | — |
| 5 | vestibule | 10.77650, 106.69510 | — (no in-scope match) | — | — | — |
| 6 | Saigon Notre-Dame Basilica | 10.77610, 106.69590 | 10.77979, 106.69902 | serper | 533 m | ❌ |

**Findings:** (a) every landmark with a correct-city reference is ~500–850 m from
its shipped pin — the Old Saigon stops are all clustered on nearly one coordinate
(the Notre-Dame block), another pin-quality gap the proof exposes; (b) the generic /
sub-part titles "City Hall" and "vestibule" have no in-scope reference — the 50 km
scope-sanity bound correctly rejected the global same-name matches (Florida /
Illinois) rather than reporting a nonsense 15 000 km distance. The titles also show
narration appends architectural features ("facade", "portico", "grand staircase",
"vestibule") to the place name — the pin-proof's bare-name stripping handles the
lookup, but the feature-word titles themselves are a separate titling issue noted
for a follow-up.

### Tour 2 — "Kitesurfing schools in Mui Ne, Vietnam"
**NOT RUN — budget.** After tours 0 and 1 the whole-task spend was **$1.80 of the
$2.00 cap**; a third generation (~$0.5–0.9) would breach it. This is a budget stop,
not the OpenAI spend-limit error (the key worked throughout). The code path for a
business/activity request → places path is covered by the moved
`test_local791_vietnam_round2.py::TestDefect2BusinessActivityRouting` and was proven
live in the LOCAL-791 submission.

---

## Process notes
- Branched from HEAD (`e75e698f`); `git merge-base --is-ancestor e75e698f HEAD` exits 0.
- Isolated container only; never `-p audioura`, never touched `audioura-*` services.
- No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`,
  `.continuous_dev/`, `SUBSCRIBED_COMMUNICATION_01.MD`, `legal/`,
  `GCLOUD_STORIED_START_HERE.md`, `TRAVEL_PROJECTS.md`.
- No `DELETE`; one heavy build at a time; committed specific files (no `git add -A`).
