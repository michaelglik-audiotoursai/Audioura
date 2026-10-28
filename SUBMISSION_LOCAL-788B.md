# SUBMISSION — LOCAL-788B — Place tours must come from the map, not the LLM

**Branch:** `LOCAL-788B-places-first`
**Base:** `subscribed` (de3cee08, contains LOCAL-788 merge acc75176)
`git merge-base --is-ancestor de3cee08 HEAD` → exit 0 (verified before commit).

## The defect
LEAD end-to-end on the Mac shared stack (acc75176, 2026-10-27): the request
"middle eastern restaurants near me, west Roxbury, MA" with tour_type "" (as the
app sends) shipped **Sultan's Kebab** and **Cafe Jaffa** — both fabricated. The
log chain showed:
- PHASE 3A asked the LLM for candidates → Al Wadi (REAL), Sultan's Kebab, Cafe Jaffa (invented).
- An LLM check EXCLUDED Al Wadi ("a common name … cannot be verified as such").
- `[VERIFIED] "Sultan's Kebab" — wikipedia_article: 'Kebab' is about the establishment+city`
  — a **generic-word** article (Kebab = the food) counted as evidence.
- `[UNVERIFIED] 'Cafe Jaffa'` → shipped anyway (gate LOG_ONLY for non-walking).

Known-good answer: Bread Thyme, Stardust, Al Wadi (all real, West Roxbury).

## The fix (what changed)

### `stop_existence_gate.py`
1. **Generic-word Wikipedia is never evidence.** New `_GENERIC_PLACE_WORDS`
   (venue classes + dishes + cuisine adjectives), `_distinctive_name_tokens()`
   (the tokens that make a name *that place* — "Sultan's Kebab" → {sultan, sultans};
   "Kebab House" → {} ), and `_article_title_has_distinctive_token()`. Every
   accept path in `_check_dining_existence` (en/fr summary, search-article,
   snippet, Wikidata) now also requires the article/snippet to carry the place's
   distinctive token. The "Kebab" article can no longer vouch for "Sultan's Kebab".
   A wholly generic name ("Kebab House") has no distinctive token → no Wikipedia
   article can ever verify it; it must be proved on the map.
2. **Place-type detection** `is_place_type_tour(tour_category, tour_type, poi_type,
   request_text)` — true for dining / business / "near me" / "<things> in/near
   <area>", **independent of the app-sent tour_type** (keys off poi_type /
   tour_category / request text). Museum & facility stay false.
3. **Existence gate ENFORCE for place-type tours.** `get_gate_mode_for_category`
   now raises the mode to `enforce` for any place-type tour (like LOCAL-662 for
   walking), so an unverified place-type stop is dropped and replenished from the
   map — never shipped. An explicit `off` kill-switch still wins.

### `generate_tour_text.py`
4. **PLACES-FIRST (PHASE 3C).** For a place-type tour, an LLM-proposed name is kept
   only if `verify_listing_in_scope(name, scope)` is True (places_search returns
   it within scope). A name the map does not carry is dropped and logged
   `[LOCAL-788B] llm name not on map <name>`; freed slots are refilled from the
   maps-first search that already runs **before** the LLM Part C loop. `None`
   (lookup failed) is UNKNOWN → kept (D162). Generalises the LOCAL-779B dining
   block to every place-type tour, unconditional of cuisine.
5. **PHASE 4 map override (the Al Wadi fix).** The LLM "is this really a
   `<type>`?" exclusion no longer drops a place the map confirms in scope: a
   `verify_listing_in_scope` hit overrides the LLM's low-confidence doubt, the
   stop is marked `_maps_verified` and kept, logged "LLM exclusion overridden".
6. The place-type signal (poi_type + request text) is also passed to the
   gate-mode call so a `tour_type=""` tour still forces ENFORCE.

## Unit / regression tests
- **New:** `tests/test_local788b_places_first.py` — 14 tests:
  - the exact field case: generic "Kebab" article/summary does NOT verify
    "Sultan's Kebab"; distinctive-token logic.
  - places_search is the authority: the two field fakes are NOT on the map in
    West Roxbury, the three real places ARE.
  - the JP coffee case: "Jamaica Plain Coffee" (generic LLM name) is not a
    distinct listing → dropped; Ula Café / Tres Gatos kept.
  - generator source invariants: exact log line present, drop driven by
    `verify_listing_in_scope`, PLACES-FIRST runs before Part C, `_maps_verified`
    stops exempt from the gate, PHASE 4 override present.
  - place-type detection + gate forces ENFORCE for dining/near-me; museum keeps
    global mode; explicit `off` wins.
- **Updated:** `test_local662_walking_v9_defects.py` (dining now ENFORCE, was
  "keeps global mode"); `test_local788_existence_place.py` (contradiction-guard
  cases use the distinctively-named "Sultan's Kebab" so both item-2 and item-5
  rules are co-tested).
- **Targeted regression (all pass):** 281, 285, 313, 320, 353, 557, 662, 662b,
  779, 779b, 783, 784, 786, 788 (×5), 788b, d538 → **300 passed, 13 skipped**.
- **Full suite vs baseline:** ran `tests/` on de3cee08 (baseline) and on the
  branch. Failing **test nodes**: base 196, branch 197. The single delta is
  `test_local293_landmark_extraction.py::test_discover_landmarks_no_qidless_coordless`,
  which **passes in isolation** (it makes real Wikidata calls and is flaky under
  full-suite rate-limiting; unrelated to this change — it touches landmark
  extraction, not the dining/business path). **Zero genuine new failures.**

## Live test — END-TO-END (isolated `local788b-postgres`, tour_type "")
Three fresh paid tours via `run_local788b_container.py` through the real
`generate_tour_text` path (STORIED_MODE, cache off, pool off), each stored as one
additive `is_test` row. **Total paid-API spend recorded in `cost_ledger`
(user_id TEST-LOCAL-788B): $1.3746** + $0.011 Serper verification = **~$1.386,
under the $1.50 whole-task cap.**

Every delivered stop checked against Serper Places (`verify_local788b_stops.py`,
name / address / km from the geocoded scope centre):

**middle eastern restaurants near me, west Roxbury, MA (2 stops) — the field defect, now CLEAN**
| stop | on Serper Places | address | km from centre |
|------|------------------|---------|----------------|
| Stardust: Inspired Mediterranean, Persian | ✅ | 1753 Centre St, West Roxbury | in scope |
| Bread Thyme | ✅ | 1866 Centre St, West Roxbury | 0.85 |
| (Al Wadi, named in orchestration) | ✅ | West Roxbury | 1.92 |
| ~~Sultan's Kebab~~ | ❌ correctly NOT on map — **no longer shipped** | — | — |
| ~~Cafe Jaffa~~ | ❌ correctly NOT on map — **no longer shipped** | — | — |

**Kitesurfing schools in Mui Ne, Vietnam (3 stops) — CLEAN**
| stop | on Serper Places | address | km |
|------|------------------|---------|----|
| Vietnam Kiteboarding School | ✅ (VKS) | Mui Ne | 10.35 |
| Surfpoint Kiteboarding School | ✅ (Surfpoint Vietnam) | 16 Nguyễn Đình Chiểu, Mũi Né | 10.08 |
| C2Sky Kite Center | ✅ (C2Sky KiteSurfing) | 12 Nguyễn Đình Chiểu, Mũi Né | 10.45 |

(The ~10 km is the distance from the geocoder's town-centre point to the Mui Ne
beach strip where every school sits — inside scope.)

**coffee shops in Jamaica Plain, Boston (3 stops) — 2/3 verified; 1 pre-fix artifact**
| stop | on Serper Places | note |
|------|------------------|------|
| Ula Café | ✅ | 284 Amory St / Jamaica Plain, 0.92 km |
| Tres Gatos | ✅ | 470 Centre St, Jamaica Plain, 0.86 km |
| Jamaica Plain Coffee | ❌ not a distinct listing | generic LLM name |

**Honest note on the JP artifact.** The three live-run artifacts were generated
during the development session; the West Roxbury (the ticket's exact defect) and
Mui Ne tours are fully map-verified. The JP tour contains one generic LLM name,
"Jamaica Plain Coffee", that is not a distinct Serper Places listing — exactly the
kind of stop the PLACES-FIRST drop removes. I did **not** regenerate the JP tour
because a fresh full tour (~$0.34) would breach the $1.50 whole-task cap (spend was
already $1.386). Instead the committed fix is proven on this case deterministically:
`classify_business_vs_landmark("coffee shops") == "business"`,
`is_place_type_tour(tour_category="walking", poi_type="coffee shops") is True`, and
with Serper stubbed to the real JP response `verify_listing_in_scope("Jamaica Plain
Coffee", "Jamaica Plain, Boston") is False` (dropped) while Ula Café / Tres Gatos
verify True (kept) — see `TestJamaicaPlainCoffeeCase`. The committed code therefore
emits `[LOCAL-788B] llm name not on map Jamaica Plain Coffee` and replenishes from
the map.

## Files
- `stop_existence_gate.py` — generic-word rejection, place-type detection, ENFORCE.
- `generate_tour_text.py` — PLACES-FIRST drop + exact log line, PHASE 4 map override,
  poi_type/request passed to the gate-mode call.
- `tests/test_local788b_places_first.py` (new, 14 tests).
- `tests/test_local662_walking_v9_defects.py`, `tests/test_local788_existence_place.py` (updated).
- `run_local788b_container.py` (live harness), `verify_local788b_stops.py` (Serper check).
- Live evidence: `*_tour_20261028_*.txt` + `*_evidence.json`, `api_call_chain_20261028_*.txt`.

## Process
Committed to `LOCAL-788B-places-first` with explicit file paths (no `git add -A`).
No `DELETE`. No edits to DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE /
`.continuous_dev/` / SUBSCRIBED_COMMUNICATION_01.MD / `legal/` /
GCLOUD_STORIED_START_HERE.md / TRAVEL_PROJECTS.md.
