# SUBMISSION LOCAL-906 — wave 51 content leftovers (route 551, single-place 552)

Branch `LOCAL-906-route-content-leftovers`, from `7fc272b0` (`git merge-base --is-ancestor 7fc272b0 HEAD` = 0).
Budget: $0. No live run, no paid call; every lookup mocked.

## What changed (per item)
| # | Change | Where |
|---|---|---|
| 1a | Exclusivity claim ("the only / sole / first / no other" + country/region/place word) dropped unless one evidence sentence states it (≥3 shared distinctive tokens). | `route_leftovers_906.drop_unsupported_claims` |
| 1b | Year + named builder ("began in 1958 by X") dropped unless the stop's evidence holds the year AND every token of the builder. No evidence entry = nothing stated = dropped. Log says `held neither` / `evidence lacks them`. | same |
| 1c | Out-of-scope comparative. **Why it survived:** `drop_unsupported_comparatives` (902 item 5) returned at `if not active()` — it only ever ran on a described route — and also returned when no evidence map was passed, which is how the delivery pass calls it. The single-place path met both conditions. Now `force=True` on the single-place path, with the 904 evidence stash merged in; a missing evidence map = empty, so the names must be tour places. | `route_content_896.drop_unsupported_comparatives`, `apply_single_place_guards` |
| 2 | Area stop (no venue of its own, unverified model pin) must project strictly between its neighbours and be ≤10 km from the segment, else it is placed on the segment at its share (a run of consecutive area stops is spread evenly), flagged `coordinates_approximate`. Log `[LOCAL-906] route area stop=N re-pinned between neighbours (was <km> km behind / off the segment)`. Poi-level hook right after the 903 reconcile (verified = snapped-verified / Wikidata / user pin, never moved); text-level safety net at the START of `finalize_898` so Directions distances use the final pins (only when the generator told it which pins are verified). | `repin_area_stops`, `repin_area_stops_in_text`, `generate_tour_text.py` |
| 3 | Directions keep `Continue to X.` / `Walk on to X.` / `It is roughly N km away.` plus at most ONE wayfinding sentence (a turn, a road type, a landmark; no compass, distance, minutes, mood). Scenery/mood dropped. Both paths (route `finalize_898`, single-place `apply_single_place_guards`) go through `normalize_directions`. | `_wayfinding_clause` |
| 4 | Orientation sentence "at the foot/base/bottom/entrance/gate of X" dropped when an earlier stop's title or Directions says ascent/summit/climb/cable car/Walk on/inside AND names X. Emptied Orientation line removed. | `drop_contradicting_orientation` |
| 5 | Sentence (or ≥0.85 word-overlap near-duplicate of the smaller set, ≥5 words) already delivered in an earlier stop is dropped from the later one, unless that would leave it with no content sentence. **Side effect (deliberate):** the 902/904 "same-site neighbour sentence" borrow *is* such a repeat (probably the Stop 4/5 source), so the 904 refill and the 900 honest-body rebuild no longer borrow it; they go on to the honest stage. | `drop_repeated_sentences`, `refill_thin_stops`, `rebuild_honest_bodies` |
| 6 | First stop only: pollution/trash/litter/garbage/crime/theft/disease/epidemic/disaster sentence — dropped on leisure tours (header `Tour-Category`: walking/driving/biking/cycling/family/…), moved after the first positive sentence elsewhere. Kept when it carries a year/historic word or shares ≥3 tokens with the stop's signature story (generator stashes the sink). | `tone_first_stop` |
| 7 | "Across these stops, …" / "Taken together, the stops add up …" dropped from the closing; `That's N stops in all.` and the restaurant offer stay. | `drop_template_closing` |
| 8 | `_STATE`, `_POINTS`, `_HONEST_DONE`, `_EVIDENCE_904` (and the new 906 stashes) are job-scoped containers with the old dict/set interface, keyed by a ContextVar job id. `generate_tour_text` is wrapped with `@job_scoped`: binds `job_id` (the already-bound job for a nested pool call, else a per-call token) and clears the job's state at the end (not while an outer scope of the same job runs). A context with no job bound uses the sole bound job (worker thread of a single job), else the default slot. | `route_content_896.job_scope/job_scoped/end_job` |
| 9 | `fetch_full_pages` no longer fetches facebook/youtube/tiktok/instagram/x/twitter (+fb.com, youtu.be, pinterest; host-suffix match, so `box.com` ≠ `x.com`), applied BEFORE the page cap so they do not eat slots; fetched pages whose first ~400 chars share no token with the stop/venue/place are not used. Logs `[LOCAL-906] fetch skipped <host>: <reason>`. | `story_first.py` |

Pass wiring: `finalize_898` (route) and `apply_single_place_guards` (every path) call `route_leftovers_906.content_pass`, which only acts on a described route or a tour of ≤2 stops. Museums/other multi-stop tours are untouched. 905's `ensure_bodies` still runs last as the floor.

## Report: did the evidence hold the year/builder?
Not answerable offline: the wave-51 evidence bundle is not in the repo and I ran nothing live. The route text said "completed in the 1960s" and earlier single-place texts said 1963 while this one said 1958, so at most one can be right; with this change none of them is spoken unless the stop's evidence holds the year AND the builder. The next live run will log `held neither` / `evidence lacks them` per dropped sentence — that is the answer.

## Existing tests updated (behaviour changed on purpose)
- `test_local898_route_text`, `test_local900_leftovers`: scenery clause no longer kept (item 3); wayfinding kept.
- `test_local900b_w47` (3 tests), `test_local904_single_place_polish` (2), `test_local900_leftovers` (1): template closing gone (7); neighbour sentence delivered once, not borrowed (5).
- `test_local901_progress_and_place_pin`: social hosts are now skipped, not just counted (9).

## Tests
- New: `tests/test_local906_route_leftovers.py` (26) — one+ test per item, thread test with two interleaved jobs, fixtures `tests/fixtures/local906_{route,single}_w51.txt` (generic tokens), and full replays of both through `finalize_898` + single-place guards + `ensure_bodies` (no exclusivity/comparative/year+builder, Stop 3 between 2 and 4, Directions without scenery, no "foot of", no repeat, no pollution, no template closing, "That's N stops in all." unchanged, no empty stop).
- Required set (`test_local89[6-9]*`, `test_local90*`, `894*`, `87*`, `88[0-9]*`, `89[0-3]*`, `test_lead905*`): 1071 passed, 0 failed. (At the base one run had `test_local893_preview_timeout::…still_gets_its_grace` fail on timing; it passed on re-run with my changes — not related.)
- `-k "ground or conclusion or pin or itinerary or snap or pool"` (deselect `test_local88_tour_pollution.py`): 650 passed, 3 failed, all pre-existing/known (`test_local378…case_sensitive` ×2, `test_local666…no_pin_and_no_archive_is_v1`).

## Not verified
- No live/cloud run: the poi-level area-stop hook and the `@job_scoped` decorator are exercised by import/signature check and unit tests, not by a real generation. First thing to check live: `[LOCAL-906] route area stop=` lines and that the final-text pin for the area stop is between its neighbours.
- Area-stop detection is word-based (Type/Specialty or title), not a geocoder class.
