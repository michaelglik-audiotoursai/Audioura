# SUBMISSION — LOCAL-863R (reissue of LOCAL-863): city geocoding, user-pin provenance, user stops never dropped, emoji at the TTS egress

**Branch:** `LOCAL-863-user-stop-city` · **Base:** `acdbf278` (subscribed, contains 4f803d9c) — `git merge-base --is-ancestor acdbf278 HEAD` exits 0.

**Live result (Mac-local, budget-enforced): OVERALL PASS — $0.2873 of the $0.45 cap.**

## Root causes (wave 27, tour 534)

1. **HCMC → near Hanoi.** The pin-snap centre was `_sweep_anchor = geocode(location_hint(location))`, an unguarded free-text Nominatim geocode with `limit=1`. It was used *before* the guarded `_city_center_for_request`. For "…Ho Chi Minh City, Vietnam" it returned a Hồ Chí Minh–named feature at (20.9103, 105.5750). `is_city_like` (858B) rejects country/state rows but accepted attractions.
2. **Whole-country bbox.** `stop_existence_gate._geocode_scope_center/_bbox` walk the comma tails down to the bare country ("Vietnam") and take its bbox.
3. **Model coordinates as "user pins".** Three places treated *any* user stop's coordinate as authoritative:
   - `pin_snap._is_user_pin` (`user_explicit + coordinates` clause);
   - `generate_tour_text._user_pin_merge_fields` (`user_explicit or _anchor or _is_user_stop_title`);
   - the cluster-refetch exemption and the D559 `_gp_is_user_pin`, which also feeds the geo-repair restore.

   Separately, the Phase-3B merge relabelled every kept pin as `user_share_link`.
4. **Crazy street dropped.** The LOCAL-292 empty-stop gate removes any stop with no narration, user stops included.
5. **🌈 reached TTS.** Subscribed has no polly-tts of its own, so it calls another line's polly-tts, which may predate the LOCAL-860 server-side strip. The caller-side strip in `tour_generation_modernized` was wrapped in a silent `try/except: pass` and never logged. `tour_editing_phase2` and translation-service's direct boto3 Polly call did not strip at all.

## Changes

| # | File | Change |
|---|------|--------|
| 1 | `city_scope.py` (new) | Curated tour-city table: HCMC, Hanoi, Da Nang, Hoi An, Nha Trang, Mui Ne, Phan Thiet, Hue, Boston, Paris, Nice, Amsterdam. Each entry has centre, city-size bbox and country; matching is accent-folded on whole words. "Ho Chi Minh Mausoleum" does not match HCMC. Ordinary-word aliases (nice, hue) require the country to be named. A city whose country contradicts the request is rejected. Also: `requested_country`, `point_in_country`, `is_attraction_hit`, `is_country_level_hit`, `center_is_sane` (inside the country and ≤25 km of a named curated city), and `resolve_city_scope` (curated first, then Nominatim with `featuretype=city` + `countrycodes`). |
| 1 | `stop_existence_gate.py` | `_geocode_scope_center` and `_geocode_scope_bbox` now share `_resolve_scope_area`, in this order: (1) the curated city when it *is* the scope's most specific segment; (2) Nominatim on the full scope and its tails, **never a bare-country tail**, never a country/state row, never outside the requested country or the named city, and never an attraction when the candidate is only a city name; (3) a curated city named anywhere in the scope; (4) otherwise None. The whole country is never returned. A sub-area such as "West Roxbury, Boston, MA" still keeps its own tighter geocode (LOCAL-786). |
| 1 | `generate_tour_text.py` | `_city_center_for_request` answers from the curated table first, and its city-like check now also rejects attractions and wrong-country hits. `_sweep_anchor` (the pin-snap centre) and the D559 `_gp_anchor` now use that guarded resolver. A free-text fallback is accepted only if it passes `center_is_sane`. |
| 2 | `pin_snap.py` | `_is_user_pin` is True **only** for `coord_source ∈ {user_share_link, user_share_link_kg, user_name_lookup}`. |
| 2 | `generate_tour_text.py` | New `_has_real_user_coord`. `_user_pin_merge_fields` keeps the coordinate (`coord_kept`) only for a real user source. "Is a user stop" still drives the address rule. The Phase-3B merge now keeps the **real** source label and tags a user stop's model coordinate `coord_source='model'`, logging `[LOCAL-863] user stop … has a MODEL coordinate … not a user pin`. The cluster-refetch and D559 exemptions use the same predicate. |
| 3 | `generate_tour_text.py` | Empty-stop gate: a user stop with no narration is **kept** with the D760 short form (`user_stop_narration.grounded_user_stop_body`) and logs `[LOCAL-863] user stop KEPT with D760 short form`. |
| 4 | `text_polish.py` | `strip_emoji_for_tts_logged(text, where)` logs `[LOCAL-863] TTS emoji strip at <where>: removed N emoji run(s)`. |
| 4 | `tour_generation_modernized.py`, `tour_editing_phase2.py` | Logged, **fail-closed** strip inside `_strip_nav_fields_for_tts`, the actual `/synthesize` payload builder. If `text_polish` is missing from the image, an inline regex still strips and logs. |
| 4 | `translation-service/translation_service.py` | Logged strip before the direct `polly_client.synthesize_speech` call, which bypasses polly-tts. |

**Existing tests changed (requirement changed, not weakened):**
- `tests/test_local847…::test_geocode_center_falls_back_when_full_fails` asserted the bare-country centroid (16.0, 108.0) for "Mui Ne beach area, Vietnam". That is exactly what this ticket forbids. It now asserts the Mui Ne centre and that "Vietnam" is never queried.
- `test_local858b_cloud_pins.py::test_no_city_tail_returns_none_not_country` asserted `None`. The request names "Ho Chi Minh City", so the curated table now correctly returns HCMC. The guarded invariant is unchanged and still asserted: the result is never the country centroid.

## Tests

- New: `tests/test_local863_user_stop_city.py` (27 tests, offline). Covers HCMC from the Sophia request; aliases; mausoleum ≠ HCMC; ordinary-word and country-mismatch guards; Nominatim rows (attraction / wrong country / `featuretype=city` + `countrycodes`); the wave-27 bad hit rejected at the gate; no bare-country bbox; West Roxbury keeps its own bbox; `_is_user_pin` for the 3 real sources and for 5 model-source shapes; a real `snap_poi_coordinates` run logs no "user pin kept" for a model coordinate; merge fields; the call-site predicates; the gate keeps user stops; the logged strip; the modernized payload with no 🌈 (including the fallback when `text_polish` is unimportable); the editing payload.
- Neighbouring suites (786, 788*, 791*, 803, 805*, 813, 815, 847, 855*, 858, 858B, 859, 859B, 860, 862, 862B, 591, 605, 839–857): **843 passed, 1 skipped** (one de-duplicated run, including the 27 new tests).
- Full `tests/` suite, diffed against a baseline run of untouched `acdbf278` in a temporary worktree: **2 new failures, both live-network**. `test_local294…::test_no_administrative_divisions` (SPARQL) passes on rerun. `test_local320…::test_dining_does_call_nominatim` hit Nominatim HTTP 429 on the venue lookup after two back-to-back full-suite runs; that venue lookup is unchanged by this patch. All other failures exist on the base too.

## Live run — `run_local863r_live.py`

- **Budget:** `TASK_BUDGET_ID=LOCAL-863R TASK_BUDGET_USD=0.45`, set at interpreter start so the network meter's sitecustomize enforces it. Own meter dir.
- **Own DB (D753):** `docker-compose.local863r-proof.yml`, project `local863r`, port 55963, seeded with `local821-initdb`. Every `DATABASE_URL` / `VENUE_CACHE_DB_URL` / `DB_*` was pointed there. The generator's default is `localhost:5433`, the **shared** dev postgres, so it must not be left at its default. Torn down (`down -v`) after the run.
- **Never touched:** the shared `audioura-*` containers, the shared dev DB, the live DB.
- **Generator:** ran in-process from this worktree (the 859B pattern), not as its own container.
- **Cloud-like env:** `K_SERVICE` set, `LANDMARK_LIVE_LOOKUP=""`.

**Sophia — "Sophia's biking tour in Ho Chi Minh City, Vietnam" (exact).** Seven stops:
- 🌈 Thi Bar Saigon and Acoustic Bar: share.google-style links;
- An Spa: Maps `/place/@lat,lng`;
- Ben Thanh Market: Maps search URL with no coordinate;
- Saigon Opera House: maps.app.goo.gl short link;
- Crazy street and Saigon Central Post Office: two plain names.

| Criterion | Result |
|---|---|
| City centre within 10 km of 10.776,106.700 | (10.7769, 106.7009), **0.14 km**. Bbox `[10.70, 10.88, 106.60, 106.82]`; 0 whole-country fallbacks. **PASS** |
| 7/7 delivered | **7/7. PASS** |
| Every pin is a user source within 50 m, or announced | Thi Bar 0 m · Acoustic Bar 0 m · An Spa 0 m · Post Office 8 m · Opera House 15 m · Ben Thanh 3 m (150 m building limit). All are `user_name_lookup` / `user_share_link`. **PASS** |
| Zero "user pin kept" for model coordinates | All 12 "kept" lines name a real source. Crazy street's model coordinate was flagged and **not** kept, then snapped 874 m to Bui Vien's Wikidata P625 (16 m from the street reference). **PASS** |
| No 🌈 in any TTS payload | None. **PASS** |

**Ben Thanh walk (regression):**
- Ben Thanh Market: 3 m; Saigon Opera House: 37 m. **PASS.**
- The Post Office refill snapped 684 m from a model coordinate to Wikidata P625.
- Delivered 3 of 4 requested: the existing LOCAL-818 refill fell short. I did not compare this count with the earlier revision.

## Limits — what this run does NOT prove

- **share.google links.** A real share.google link can only be minted from a browser (859B), so these ids were synthetic and unresolvable. Thi Bar and Acoustic Bar therefore went through the typed-name lookup, not the KG parse, which 859B already proved.
- **Circular truth values.** An Spa's truth value equals its Maps-URL coordinate by construction. The Thi Bar, Acoustic Bar and An Spa truth values are the 859B-verified pins.
- **Empty-stop gate.** The fix for item 3 was **not exercised live**: all 7 stops had narration (`[LOCAL-292] … PASSED`). It is proven by unit tests only.
- **TTS path.** The deployed cloud Subscribed TTS route could not be inspected from here, so the strip was added at **every** caller-side egress in the repo. The live 🌈 check applied the real modernized payload builder to every delivered stop; no audio was synthesised.
- **Container stack.** The live run used an own DB with the generator in-process, not a full own container stack.

## Not committed

Run logs and tour outputs live in `_local863r_meterlogs/` (untracked). Side-effect rewrites of tracked artifacts from the test and live runs (`prompt_dump_stop1.txt`, `openai_simple_debug.txt`, `db_step*.txt`, `tests/known_out_of_scope.json`) were reverted.
