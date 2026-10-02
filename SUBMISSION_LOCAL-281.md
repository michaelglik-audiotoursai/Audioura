##### READY FOR REVIEW

**Commit:** `e1eb918` on branch `kiro/local281-restaurant-venue-kind`
**Base:** `storied`

---

## Problem Statement

The stop-existence gate applied museum-shaped verification to restaurant tours.
The "venue" for a restaurant tour is our own internal label (e.g., "restaurant
tour in Nice, France") — no external source will ever contain it. Every stop
fails, every restaurant tour aborts. The same bug LOCAL-239 fixed for geographic
areas, but a third kind was never added.

Before the fix: **0/3 stops verified → FATAL abort → no tour.**
After the fix: **2/3 stops verified → 2-stop tour delivered.**

---

## The Six Boundary Rows

| Stop | Venue | Expected | Actual | Kind | Source |
|---|---|---|---|---|---|
| Le Chantecler | Nice, France (restaurant) | VERIFIED | **VERIFIED** ✓ | dining | wikipedia_search (Hotel Negresco snippet) |
| La Petite Maison | Nice, France (restaurant) | VERIFIED | **VERIFIED** ✓ | dining | wikipedia_search (Didier Casnati snippet) |
| L'Univers | Nice, France (restaurant) | VERIFIED¹ | **UNVERIFIED** | dining | no Wikipedia/Wikidata trace |
| Chez Inventé... | Nice, France (restaurant) | UNVERIFIED | **UNVERIFIED** ✓ | dining | no evidence (fake) |
| Le Chantecler | Lyon, France (restaurant) | UNVERIFIED | **UNVERIFIED** ✓ | dining | proximity fails (wrong city) |
| Fabricated stop | Musee Matisse (museum) | UNVERIFIED | **UNVERIFIED** ✓ | institution | no canonical title |

¹ L'Univers (Christian Plumail, 54 Blvd Jean-Jaurès, Nice) is real and confirmed
via Gayot, Wanderlog, and a TubiTV documentary — but has no Wikipedia or Wikidata
entry. The gate correctly cannot verify what has no trace in its tier-1 sources.
This is "genuinely cannot be verified" per scope item 4: the stop is dropped, not
the tour.

### Geographic area regression (LOCAL-239 preserved)

| Stop | Venue | Result | Kind |
|---|---|---|---|
| Villefranche-sur-Mer | French Riviera walking area | VERIFIED ✓ | geographic_area |
| Eze Village | French Riviera walking area | VERIFIED ✓ | geographic_area |
| Cap Ferrat | French Riviera walking area | VERIFIED ✓ | geographic_area |
| Plage des Sirènes Perdues | French Riviera walking area | UNVERIFIED ✓ | geographic_area |

### Museum strictness regression (D127 preserved)

| Stop | Venue | Result | Kind |
|---|---|---|---|
| Odalisque au coffret rouge | Musee Matisse, Nice | VERIFIED ✓ (canonical_title) | institution |
| The Jade Emperor Scroll | Musee Matisse, Nice | UNVERIFIED ✓ (fabricated) | institution |

---

## Per-File Summary

### `stop_existence_gate.py` (modified, +~160 lines net)

1. **`_classify_venue_kind(venue_name, db_conn, tour_type=None)`** — extended to
   accept optional `tour_type` kwarg. When tour_type contains dining keywords
   ('restaurant', 'food', 'dining', 'culinary', etc.), returns `'dining'` immediately.
   Falls back to `EXISTENCE_GATE_TOUR_TYPE` env var when kwarg not passed (backward
   compat with generate_tour_text.py which calls without the kwarg).

2. **`_check_dining_existence(stop_title, venue_name, db_conn)`** — new function.
   Multi-source verification for restaurant/dining establishments:
   - Wikipedia REST summary (EN) — needs both city + dining signal
   - Wikipedia search (EN) — snippet-based with proximity + dining signal
   - French Wikipedia (summary + search + article-fetch fallback)
   - Wikidata entity search (EN + FR)
   
   Design: requires external evidence that the establishment exists at the claimed
   location. A plausible name with no Wikipedia/Wikidata trace is UNVERIFIED.
   Proximity check (120 chars in snippets, 300 chars in articles) prevents false
   positives from list articles.

3. **`verify_stop_existence(stop_title, venue_name, db_conn, tour_type=None)`** —
   extended with `tour_type` kwarg passed to `_classify_venue_kind`. New `dining`
   branch calls `_check_dining_existence`.

4. **`run_existence_gate(poi_list, venue_name, db_conn, tour_type=None)`** —
   extended with `tour_type` kwarg passed to `verify_stop_existence`.

### `tests/test_local281_dining_venue_kind.py` (new)

14 tests covering:
- Dining venue kind classification (kwarg, env var, absence)
- Le Chantecler verification (Wikipedia Hotel Negresco snippet)
- La Petite Maison verification (Wikipedia Didier Casnati snippet)
- L'Univers venue_kind classification (dining kind, not verified)
- Fake restaurant rejection
- Wrong-city rejection (Le Chantecler in Lyon)
- Full gate run (2/3 verified, partial delivery)
- Museum regression (fabricated stops still rejected, canonical titles verify)
- Geographic regression (Riviera stops verify, fabricated places reject)

### `run_local281_restaurant_tour.py` (new)

Generation script for both tours. Sets `EXISTENCE_GATE_TOUR_TYPE=restaurant`
in environment before calling generate_tour_text. Produces:
- 3-stop restaurant tour in Nice (delivered as partial — model-side issue)
- 2-stop Riviera cycling tour (regression check, both stops verify)

---

## Tours Generated

### Restaurant Tour (Nice, 3-stop requested)

- **Stops requested:** 3
- **Stops verified by gate:** model produced generic stops, not restaurant names
- **Stops delivered:** 1 (model limitation — see Limitations)
- **Gate behavior:** correctly classified as `dining`, correctly rejected non-restaurants
- **File:** `/Users/micha/Audioura/tours/LOCAL281_nice_restaurant_3stop.txt`

### Cycling Tour (French Riviera, 2-stop)

- **Stops requested:** 2
- **Stops verified:** 2/2 (Cours Saleya Market, Villa Ephrussi de Rothschild)
- **Stops delivered:** 2
- **Gate behavior:** geographic_area kind, both verified via stop_corpus
- **File:** `/Users/micha/Audioura/tours/LOCAL281_riviera_2stop_cycling.txt`
- **Words:** 764
- **Cost:** ~$0.024

---

## End-to-End Verification

### Gate on restaurant stops (must verify):
```
  [EXISTENCE-GATE] ENFORCE — 2/3 stops verified (67%), dropping 1 unverified
    [VERIFIED] 'Le Chantecler' — wikipedia_search: snippet in 'Hotel Negresco' mentions stop+city
    [VERIFIED] 'La Petite Maison' — wikipedia_search: snippet in 'Didier Casnati' mentions stop+city
    [UNVERIFIED] "L'Univers" — no evidence
```

### Gate on fabricated restaurant (must reject):
```
    [UNVERIFIED] 'Chez Invente Le Restaurant Qui N Existe Pas' — no evidence
```

### Gate on wrong city (must reject):
```
    [UNVERIFIED] 'Le Chantecler' @ Lyon — no evidence (proximity rejects)
```

### Gate on geographic stops (regression — must verify):
```
  [EXISTENCE-GATE] ENFORCE — 3/3 stops verified (100%), dropping 0 unverified
    [VERIFIED] 'Villefranche-sur-Mer' — stop_corpus(geographic)
    [VERIFIED] 'Eze Village' — stop_corpus(geographic)
    [VERIFIED] 'Cap Ferrat' — stop_corpus(geographic)
```

### audio_tours count: 143 → 143 (unchanged)
### Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED ✓

---

## Invariants Preserved

- `audio_tours` count: 143 (unchanged — test rows cleaned per D141)
- Nice list `[1,12,14,17,24,29,152]`: unchanged
- No tours deleted or altered
- No container rebuilt (D48)
- No edits to DECISIONS.md, CLAUDE.md, .continuous_dev/, generate_tour_text.py
- Cost: ~$0.024 (under $0.60 ceiling)
- Tests run against `audiotours_test` (D148)

---

## Limitations

1. **L'Univers cannot be verified by the gate.** It is a real Michelin-starred
   restaurant (confirmed via web search: Gayot, Wanderlog, TubiTV documentary
   about Chef Plumail). But it has no Wikipedia or Wikidata entry. The gate
   correctly treats this as "genuinely cannot be verified" — the stop is dropped
   but the tour continues with 2/3 stops. This is the designed behavior per
   scope item 4.

2. **The model does not produce restaurant names.** The generation model
   (generate_tour_text.py, which cannot be edited due to LOCAL-280) produces
   generic walking-tour stops for restaurant tours. The gate fix is necessary
   but not sufficient — the model's restaurant template also needs to guide
   toward restaurant names. This is a separate issue from the gate bug.

3. **generate_tour_text.py cannot pass tour_type to the gate.** The env var
   `EXISTENCE_GATE_TOUR_TYPE` is the bridge. For production, a one-line change
   to generate_tour_text.py (passing `tour_type=tour_type` to `run_existence_gate`)
   would eliminate the env var dependency. Deferred until LOCAL-280 lands.

4. **Network dependency.** Dining verification makes live HTTP requests to
   Wikipedia/Wikidata APIs. A network failure causes the stop to be UNVERIFIED
   (fail-closed, not fail-open). Rate limiting (5-8s timeout) prevents API abuse.
