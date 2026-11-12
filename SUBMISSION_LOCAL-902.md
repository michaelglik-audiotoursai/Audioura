# SUBMISSION LOCAL-902 — single-place pin / required stops / body hygiene (offline, $0)

Base b2e1a9fa (`git merge-base --is-ancestor b2e1a9fa HEAD` = 0). No live run, no paid call, network mocked in tests.

## 1. 791E refused the correct reference — fixed (`pin_snap.py`, `generate_tour_text.py`)
- The stops'-centroid test (and its adaptive bound) now uses **verified** pins only (user pin, or any pin not model-sourced: Wikidata/geocoded). With a scope known and either a verified pin or ≤ 2 pinned stops, model pins are excluded; with no verified pin there is no centroid, so the reference is judged by the scope: inside the scope bbox, else ≤ 100 km from the coarse centre (`coarse_center` is passed from the area resolver, place-level reference preferred).
- A **model** pin is replaced by an in-scope reference even beyond 900B's 15 km DISTRICT cap (≤ 100 km), logging
  `[LOCAL-902] snap accepted <title> <km> km: model pins unverified, reference in scope`.
  A reference outside the scope is refused for a model pin (the 155 km same-name pagoda stays rejected by 900B). Verified→verified moves keep the 15 km cap. Authority (Wikidata/landmark) references keep their own scope rules.
- Large-spread model-only tours (≥ 3 pinned stops, no verified pin) keep the old all-pins centroid (mutual agreement is evidence there and GEO-CHECK runs).

## 2. 901 first-named-place lookup (`area_resolver.py`, `geocode_stops.py`)
- Outcome always logged: `[LOCAL-901] place reference '<name>' → none (wikidata miss, geocoder miss…)`.
- On a Wikidata miss: the free geocoder (`geocode_stops.geocode`, Nominatim) with "<variant>, <province>", same acceptance rule (≤ 100 km of the coarse centre or inside the city bbox). Source `first_named_place_geocoder`.
- `place_name_variants`: the name; generic geographic word dropped at either end (mountain/mount/núi/đồi/hồ/chùa/… small multi-language list); "Mount X", "Núi X"; each also diacritics-folded. No place names.

## 3. Requested structure lost its stop (`required_places_902.py`, hook before PHASE 3B)
"A and the B, <Province>" → `required_places` = [A, B] when one name is a structure (statue, pagoda, Buddha, …); two districts ("A and B, City") are not touched. `ensure_required_stops` adds a missing name as its own stop (user_explicit, `_required_902`), replacing the last non-required stop if the tour is full; logs `[LOCAL-902] required place … was not a stop`.
**Where the name was dropped:** nothing ever required it. The location is only the area scope for Phase 3A; 901's 791E veto stopped the statue being *merged* into the mountain, but the selection step (3A/gates) never had "statue" as a mandatory stop, so a pagoda won the slot.

## 4. Neighbour splice (`place_names_900.py`, `route_content_896._neighbour_evidence`)
The neighbour evidence is now the neighbour's **delivered body** (prose lines, honest-skeleton bodies excluded). `neighbour_sentence` only returns a punctuated, single sentence that starts with a capital and a non-verb/conjunction subject, ≤ 30 words, no repeated n-gram (adjacent word or repeated 2–3-gram), `is_fragment` false; otherwise none. Two 900/900B tests that expected evidence-sourced text were updated to the new rule (the sentence now comes from the body).

## 5. Superlatives / comparatives (`route_content_896.py`)
- **Why 900 missed it:** (a) "longest" → group `long`, "biggest" → group `big`: different families, and (b) the claim "This Reclining Buddha is the biggest in <country>" has no object noun after the superlative, so `_SUP_RX` (which needs `<sup> <object> in <Region>`) never matched it at all.
- longest/largest/biggest/tallest/greatest = one `size` family; added an implicit-object pattern ("X is the biggest in <Region>", object = the sentence subject); plural-insensitive object matching.
- Comparatives naming capitalised places that are neither in the stop's evidence nor tour places (stop titles) are dropped, also for a stop with no evidence entry. When no evidence dict is handed in (delivery pass), unchanged.
- **Stop 6 with 2 sentences:** I cannot see the 8-stop text (not in the fixtures), so this is by code reading: none of the 897/898 caps (cap_unsupported, numbers, facts, superlatives, comparatives, fragments) has a sentence floor; each drops whole sentences, so they compound. I added `report_thin_bodies` to `finalize_898`: `[LOCAL-902] Stop N: body went from X to Y sentence(s)` whenever a stop ends under 3. Unproven which cap hit stop 6; the next live run will name it.

## 6. Single-place body (`route_content_896.py`, `pin_snap.py`, `geocode_stops.py`)
- `strip_invented_route` (in `apply_single_place_guards`, ≤ 2 stops, non-route): drops a sentence with a road code (ĐT/QL/TL nnn) or a directive ("head/go/drive/follow … <compass|left|right>", "until you see", "for N km … until") — neither end is pinned and the text is the model's. A body that would be emptied is left as it was.
- Address: `pin_snap.verify_addresses` (≤ 2-stop tours): when a stop has a reference, the model Address is kept only if more than half its district/commune parts (province/country/digit parts ignored) occur in the free reverse geocode (`geocode_stops.reverse_address`, Nominatim /reverse) or the scope string; otherwise the Address is dropped (`[LOCAL-902] address dropped …`). No reference → not judged.
- **Closing mood filler — why 901 missed it:** the closing paragraph is "supported by every stop's tokens", so "profound connection between the sacred … traditions and the reclining Buddha statue" shared content words and passed `_supported`; the second sentence's mood words ("reflect", "dedication", "invites you", "profound") were not in the mood list at all. Fix: those terms added, and in the closing a single mood term with no digit is filler.
- Replay of `tour552_w49` (generic fixture): no "ĐT", no "head south", no mood closing; "That's 2 stops in all." kept.

## Tests
`tests/test_local902_single_place_pin.py` (22 tests, mocked network): 552 shape (pins within 15 km of the mocked reference + `[LOCAL-902] snap accepted`, far same-name still rejected, verified→verified keeps the cap), Wikidata miss → geocoder, variants, "A and the B" → two stops, neighbour quality, superlative family, comparatives, thin-body report, road/route sentence, Address check, replay. Fixture `tests/fixtures/local902_tour_generic.txt` (generic names).
Required runs: `tests/test_local89[6-9]*… 88[0-9]… 89[0-3]*` → 999 passed, 4 skipped. `-k "local791 or local802 or snap or pin"` → 353 passed, 1 failed: `test_local666_translation_source_version::…no_pin_and_no_archive_is_v1` — fails on the base too (that file has 6 failures at b2e1a9fa), unrelated. The listed known failure (`test_local775…`) was not hit.

## Not done / unproven
- Item 3 insertion point (before PHASE 3B) and the pin/address wiring in `generate_tour_text.py` are import/unit-checked only, not exercised end-to-end (no live run allowed).
- Item 5 stop-6 cause unproven (above).
