# SUBMISSION — LOCAL-860 (wave-26 text findings)

Branch `LOCAL-860-text-polish`, base `subscribed` 9034cf0f
(`git merge-base --is-ancestor 9034cf0f HEAD` exits 0).

**Status: items 1–7 fixed and unit-tested. Live: Boston PASS. The Sophia live run was NOT run — the $0.35 task budget is spent (see Live).**

## What was wrong and what changed

| # | Finding | Root cause (verified) | Fix |
|---|---|---|---|
| 1 | "Sophias" | `tour_orchestrator_service.sanitize_input` ran `re.sub(r'[<>"\']', '', …)`, so every `'` was deleted from the location, request string and user-stop names. | Strip only `<`, `>`, `"`. Straight and curly (`’`) apostrophes survive. DB writes are parameterised and filenames are re-slugged separately. |
| 2 | "biking Tour" | When the generated header has no ` - <X> Tour` suffix (the tour_type word is already in the title), the orchestrator fell back to `f"{tour_type} Tour"`. | `text_polish.derive_tour_name` / `tour_type_display_label`: biking/bike/cycling → Cycling, walking → Walking, driving/vehicle → Driving. The header suffix still wins when present. |
| 3 | Orphaned "This juxtaposition…" | The LOCAL-855D verifier and the 855B scrubs dropped sentences independently and kept whatever followed. | `text_polish.apply_orphan_rule`: after any drop, the next kept sentence is dropped if it opens with This/These/That/Those/It/Its/His/Her/Their/Such/The contrast/The juxtaposition. It cascades until stable and never empties a stop. Wired into `user_stop_verify.verify_user_stops_in_text`, `scrub_user_stop_body` and `scrub_offpin_landmarks`. It fired in the live Boston runs. |
| 4 | Emoji read aloud | Nothing stripped pictographs before TTS. | `text_polish.strip_emoji_for_tts` is applied at the `polly_tts_service /synthesize` choke point (every caller: narration, spoken stop titles, directions, translation) and in `tour_generation_modernized._strip_nav_fields_for_tts`. Only the TTS copy is cleaned; stored and display text keep the emoji. |
| 5 | Boston named places replaced | Three independent causes, all seen in the live log. See below. | See below. |
| 6 | Serper query used the tour title | `_build_stop_query` took `location.split(",")[0]`, and for a user-stops tour `location` is the whole title. The same bug was in `_deterministic_orientation`, the fact-sheet `city` and `grounded_user_stop_body` ("…in Sophia's biking tour in HCMC."). | `text_polish.city_from_scope` (used in all four places). The query is now `"Rambutan" Ho Chi Minh City`; a District fragment from the address is still preferred. |
| 7 | Hanoi Temple of Literature | Same rule as item 5. | Covered by the same fix and tested from the exact string. |

### Item 5 and 7 root causes (Boston log, before the fix)
1. **Extraction gap.** `extract_named_places_from_clause` only parsed "including/featuring/…" tails. The LLM `named_places` is `[]` for this request; its prompt is about restaurants and venues and excludes areas. "X and Y walk, City" was never protected. Fix: `named_places_from_subject` (narrow: the first comma segment must be a tour phrase, ≥2 parts, every part place-like; "Food and Wine walk", "Beacon Hill walking tour" and "Dinner at X and Y in Z" return `[]`).
2. **Unresolvable area.** The area input was the place names themselves ("Boston Common and Old North Church"), so `resolve_area` failed and the walk ran "unverified". The unresolved branch only announced the places. Fix: `scope_without_named_places` resolves the area off the trailing locality ("Boston"). The unresolved branch now also geocodes named places into stops for place-anchor tours.
3. **Geocoded stops lost their pin.** `apply_named_place_policy` read `latitude/longitude/lng`, but `places_search` returns OSM-shaped `lat`/`lon` strings (and `latitude: None`). Inserted stops had no coordinate, and a later phase pinned Old North Church ~600 m away (-71.0622 instead of -71.0544). Fix: read `lat`/`lon` too, as floats.
4. **Geocode box.** The resolver's Boston centre is the boundary centroid, 7.6 km from the church, and `places_search`'s ~8 km radius rejected it intermittently. The named-place geocode is now bound to the resolved city extent (`bbox_from_center`).
5. **Silent rescue.** `reconcile_named_place_announcement` treats a place that is "on the map" as not-announced, so a place that was on the map but not a stop vanished without a word. The cause was fixed upstream (1–4). I added a loud `[LOCAL-860] WARNING … is on the map but is NOT a stop` log line so it can't be silent again.

Policy note: the subject extractor does not check N against `total_stops`. If a request names more places than stops, they are inserted at the front and the tail trim applies as before.

## Tests
`tests/test_local860_text_polish.py`: 40 tests, all passing. They call the real functions and cover:
- apostrophe (straight, curly, injection chars still removed, user-stop names);
- labels and `derive_tour_name` for the field case;
- orphan rule: cascade, no-drop, never-empty, no mutation, real `scrub_user_stop_body`;
- emoji: the exact string, ZWJ/flag/keycap, diacritics untouched, the modernized TTS payload, and the Flask `/synthesize` route with a fake Polly;
- the exact Boston and Hanoi strings, including becoming stops with pins and the OSM `lat`/`lon` regression;
- Serper query: exact `"Rambutan" Ho Chi Minh City`, the retrieval call and the fallback orientation.

Regression: 272 passed across tests/test_local855*, 751, 799, 802, 857, 858, 357, 839, the orchestrator and storied-wiring tests. Not related to this change: `tests/test_local711_short_title.py` has 3 setup errors because `app.py` has a syntax error on the base.

## Live — BUDGET ENFORCED (`TASK_BUDGET_ID=LOCAL-860 TASK_BUDGET_USD=0.35`, own meter dir, no DB, no shared containers)

**Boston — PASS** (`run_local860_live.py boston`; delivered text in `submission_artifacts/local860/live_boston.txt`):
- stops: Old North Church (42.366325, -71.0544) and Boston Common (42.35509, -71.06573);
- both are real pins and match the true locations;
- before the fix the same request delivered the Massachusetts State House and Paul Revere House (reproduced, run 1).

**Sophia 3-stop (apostrophe / Cycling Tour / no emoji in TTS) — NOT RUN.** I spent the budget on Boston:
- the whole-task ledger (`task_budget`) reads $0.3493 of $0.35 after 4 Boston runs (~$0.087 each; the first reproduced the bug, two were fixes found along the way, the last passed);
- the next run was refused by the cap (`BudgetExceeded`, $0.3493 + $0.0100 > $0.35). I did not raise the cap, edit the ledger or switch task ids;
- my script's first "metered total" line (~$0.026) counted only metered HTTP rows and under-reported; the harness now reports the ledger.

The Sophia checks are covered offline by the unit tests above (sanitize → `Sophia's`, `derive_tour_name` → "… - Cycling Tour", the TTS payload with a 🌈 stop title → no emoji, the query → `"Rambutan" Ho Chi Minh City`), but they were not run end to end through `generate_tour_text`. `python3 run_local860_live.py sophia` is ready (3 user stops, one with 🌈); it needs roughly $0.09 of additional budget.

## Observed, not changed
The Boston header reads `… walk, Boston - walking tour` (lowercase "tour" suffix). This comes from the title builder on the "tour_type already in the location" path and is not part of these 7 items.

## Deploy note
`text_polish.py` is new. I added `COPY text_polish.py` to `Dockerfile.orchestrator`, `Dockerfile.polly-tts`, `Dockerfile.polly-tts-kokoro` and `Dockerfile.modernized`. The generator image already copies `*.py`. `polly_tts_service` degrades to a no-op (with a warning) if the module is missing, so it never loses audio.
