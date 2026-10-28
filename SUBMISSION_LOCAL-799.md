# LOCAL-799 — Tour opens with "We could not confirm X" for places that ARE stops

**Branch:** `LOCAL-799-announce-reconcile`
**Base:** `subscribed` @ `28415e0f` (LOCAL-798 merge) — `git merge-base --is-ancestor 28415e0f HEAD` exits 0.
**Evidence source:** Tour 467 (Subscribed Preview), request
`"Mui Ne sights: Fairy Stream, Red Sand Dunes, White Sand Dunes, fishing village (by car)"`.

## The defect

Tour 467 SHIPPED 5 stops (Red Canyon, Red Sand Dunes, Mui Ne Fishing Village,
Mui Ne Market, Fairy Stream), yet Stop 1's **Orientation** opened with four
sentences:

> We could not confirm Fairy Stream, so it is not part of this tour. We could not
> confirm Red Sand Dunes, so it is not part of this tour. We could not confirm
> White Sand Dunes, so it is not part of this tour. We could not confirm fishing
> village, so it is not part of this tour.

Three of those four ARE stops ("fishing village" ⊂ "Mui Ne Fishing Village";
"Red Sand Dunes" = "Red Sand Dunes"; "Fairy Stream" = "Fairy Stream"). Only
**White Sand Dunes** was really missing. Michael (Russian, iPhone 84,
2026-10-28 11:36): *"bizarre — it obviously made the tour and the stops are
here."*

**Root cause.** The LOCAL-751 named-place announcement was decided **too early** —
against the *discovered-landmark* set, before replenish/dedup/renaming settled the
final stops — and emitted **one sentence per name**, spliced into the first stop's
**Orientation line**. A place the listener named that later shipped as a stop
(often under a renamed title) was still announced as "could not confirm".

---

## Changeset (no `git add -A` — only these files)

Modified (3):
- `area_resolver.py` — `reconcile_named_place_announcement(...)` and
  `build_named_place_intro_sentence(...)` (the FINAL-stop reconciliation + the one
  intro sentence); helpers `_haversine_m`, `_poi_latlng`, `_named_place_is_covered`.
- `screen_work_tour.py` — `inject_named_place_after_welcome(...)` (places the one
  sentence AFTER the welcome, never in a stop's Orientation line; idempotent).
- `generate_tour_text.py` — three job-scoped stash slots
  (`_LAST_NAMED_PLACES`, `_LAST_NAMED_PLACE_COORDS`, `_LAST_WALK_SCOPE`); the
  walking path stashes the raw named places + any resolved coords + scope; the
  single every-path delivery guard (`_apply_delivery_hours_guard`) now reconciles
  against the FINAL stop list (`_LAST_POI_LIST`) and injects at most one sentence.

New (3):
- `test_local799_named_place_reconcile.py` — the exact 467 case + all-covered +
  token/geocode/places_search/one-sentence/placement/idempotence (19 tests).
- `run_local799_container.py` — isolated live-run harness ($1.00 cap).
- `run_local799_live.sh` — spins up an OWN throwaway postgres under `-p local799`
  and runs the exact 467 request in a disposable container (never `-p audioura`,
  never the live DB).

The LOCAL-751 helpers (`build_named_place_announcement`,
`apply_named_place_policy`, `extract_named_places_from_clause`,
`inject_orientation_disclosure`) are **kept** — `apply_named_place_policy` still
does the KEEP/INSERT work that gets a named place INTO the tour, and the LOCAL-751
tests continue to exercise those symbols directly.

---

## Fix, mapped to the ticket's three points

### 1. Decide the announcement against the FINAL stop list
`area_resolver.reconcile_named_place_announcement(named_places, final_pois,
name_coords=None, places_search_fn=None, scope=None, …)` is called from the
delivery guard, LATE — after every other guard has settled the text and
`_LAST_POI_LIST` holds the final, renamed/replenished/deduped stops. A named place
is **covered** (→ not announced) when a final stop matches it by either:
  * **normalized / diacritic-folded TOKEN match** — every content token of the
    shorter name appears in the other (reusing `_normalize_landmark_name`), so
    `"fishing village" ⊂ "Mui Ne Fishing Village"` and `"Red Sand Dunes" =
    "Red Sand Dunes"`; a joined-substring check catches token-order/glued cases;
  * **geocode within 300 m** — when the named place has a coordinate (captured
    from the matched discovered landmark) and a stop carries one.
"Red Sand Dunes" and "White Sand Dunes" are **not** confused — the colour token
keeps them distinct.

### 2. One natural sentence, after the welcome, never in the Orientation line
`build_named_place_intro_sentence(uncovered)` returns exactly one sentence:
  * 1 name  → `"One place you asked for, White Sand Dunes, could not be confirmed, so it isn't included."`
  * 2 names → `"A couple of places you asked for, A and B, could not be confirmed, so they aren't included."`
  * 3+      → `"Some places you asked for, A, B and C, could not be confirmed, so they aren't included."`

`screen_work_tour.inject_named_place_after_welcome` places it as its OWN paragraph
immediately after the tour-level welcome/prolog (located structurally via
`prolog_structure_validator.extract_prolog_from_tour_content`), falling back to
after the Stop 1 Orientation PARAGRAPH (still outside the Orientation line), then
to opening the text. Idempotent — the sentence is never doubled.

### 3. `places_search` rescue before announcing (LOCAL-790/788B)
For a name no final stop covers, the guard tries `places_search` **once** (only
when Serper is actually configured, so the offline tests and the museum canary
never touch the network). Any non-empty result suppresses the announcement — a
name that was only "unconfirmed" because Overpass/Wikidata timed out is on the map
and must not produce a false "could not confirm". Exceptions and empty results
fall through to announce.

---

## Tests

`python3 -m pytest test_local799_named_place_reconcile.py -q` → **19 passed**.

- **Exact 467 case:** `reconcile_named_place_announcement(["Fairy Stream",
  "Red Sand Dunes", "White Sand Dunes", "fishing village"], FINAL_467)` →
  `["White Sand Dunes"]`; the delivered sentence is "One place you asked for,
  White Sand Dunes, could not be confirmed, so it isn't included.", appears
  **once**, **after** the welcome, and the Stop 1 Orientation line is unchanged.
- **All four covered** (White Sand Dunes also a stop) → `[]` → delivered text
  unchanged, no "could not be confirmed".
- Red≠White not confused; duplicate names collapse; "fishing village" token
  subset; 300 m geocode in/out; places_search hit suppresses / miss announces /
  exception non-fatal; one-sentence shapes (1/2/3 names); placement idempotent.

### Regression — only NEW failures count
- `test_local751_named_place.py`, `test_local751_named_place_delivery.py`,
  `test_local791_vietnam_round2.py`, `tests/test_local790_walking_gate_intl.py`
  → **76 passed, 2 skipped**.
- `tests/test_local616_hours_guard_every_path.py` (delivery guard),
  `tests/test_local260_prolog_structure.py` (welcome/prolog),
  `test_local744_screen_work_disclosure.py`,
  `test_local631_concurrency_isolation.py`, and every other test importing the
  three changed modules → pass, **except two PRE-EXISTING baseline failures**
  (confirmed identical with `git stash`):
    * `test_local744 …::test_live_salem_places_verify_when_network_available` —
      a LIVE Wikidata/Nominatim test that returns nothing in this sandbox;
    * `tests/test_local351 …::TestNiceUnchanged` ×2 — `_parse_location` drops a
      parenthetical; `_parse_location` is untouched by this change.
  No NEW failures. All three changed modules and the new test import cleanly; the
  new `_J` slots are registered.

---

## Live (OWN containers `-p local799`, cap $1.00)

`./run_local799_live.sh` — disposable `local799-postgres` + `local799-tg` on an
isolated `local799_default` network, `audioura-tour-generator:latest` with the
branch code bind-mounted; `DISABLE_TOUR_CACHE=1`, `DISABLE_STOP_POOL=1`,
`TEST_GEMINI_MAX_USD=COST_HARD_LIMIT_USD=1.00`. Never `-p audioura`, never the
live DB (the script writes no `audio_tours` row). Two fresh runs of the exact 467
request (5 stops):

**Run 1 — $0.3726.** Final stops included **Fairy Stream**. Engine log:
`[LOCAL-799] named-place reconciliation: 4 named, 2 uncovered
(['Red Sand Dunes', 'fishing village']) — one sentence placed after the welcome`.
Fairy Stream (a real stop) was **correctly left OUT** of the announcement; the two
places that genuinely were not stops that run were announced in ONE sentence —
*"A couple of places you asked for, Red Sand Dunes and fishing village, could not
be confirmed, so they aren't included."* — placed AFTER the welcome, **not** in
the Orientation line.

**Run 2 — $0.3117.** Final stops covered all four named places (incl. a
"Mui Ne Sand Dunes Resort" and "Fairy Stream"). Engine log:
`[LOCAL-799] named-place reconciliation: all 4 named place(s) covered by final
stops — no announcement.` The delivered tour carried **no** "could not be
confirmed" sentence.

Both runs prove the announcement is decided against the **FINAL** stop list — the
exact behaviour the field tour (which announced places that were stops) lacked.
Cumulative real spend ≈ $0.68 < $1.00.

---

## Process
Committed to `LOCAL-799-announce-reconcile` (no `git add -A`; only the six files
above). No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`,
`.continuous_dev/`, `SUBSCRIBED_COMMUNICATION_01.MD`, `legal/`,
`GCLOUD_STORIED_START_HERE.md`, `TRAVEL_PROJECTS.md`. No `DELETE`; the live DB was
never written.
