# SUBMISSION LOCAL-898 — route-tour text leftovers (offline, $0)

Base 9dc4ced7 (verified ancestor). No live run, no paid call, no budget spent.

## Changes
- `route_content_896.py`
  - `_MINUTES` / `_has_travel`: hyphenated "N-minute / N-hour", number words (two…thirty, a few, several, a couple of, half an hour). Item 1, 2.
  - `normalize_directions`: a Directions line on a route is `Continue to <next>.` (`Walk on to <next>.` when the next stop is < 1 km away or shares the pin, no distance) + `It is roughly D.D km away.` only when both ends are pinned and >= 1 km, + at most ONE scenery sentence (no turn/road/route number/compass/number/time/back/descend/cable car). The model's time and distance are never kept next to the computed one. Items 2, 3, 5, 6c, 6d, 6e.
  - `consistent_creators`: two stops naming different people for the same role (built/carved/created = maker, designed, founded) of the same object (>= 2 shared content words, names aside) → keep the sentence the evidence of the two stops states; neither stated → drop both; both stated → untouched. Skipped when no evidence map is available (first delivery pass passes none). Item 4.
  - `distinct_type_specialty`: a Type/Specialty equal to the previous stop's line gets a label from its own title, or is removed when the title gives no kind. Item 6a.
  - `order_directions_last`: body above Directions, closing line stays last. Item 6b.
  - `finalize_898` chains them; called from both route passes in `generate_tour_text.py` (final delivery pass; late pass after `cap_unsupported`/`strip_body_travel`, which has the evidence map).
- `strict_grounding_gate.py` `_replace_block_body` — **root cause of 6b**: when a stop's body was empty, the header-keeping loop consumed the Directions line as a "field line", so the honest body was appended after it. Directions now ends the head.

## Evidence for item 4
`submission_artifacts/local897/evidence_bundle.json` (commit 394eb112) names neither "Truong Dinh Y" nor "Truong Dinh Tri" (grep: no match), so in the proof both sentences are dropped.

## Not found
Item 6a: I could not isolate offline which upstream pass copies Type/Specialty from the previous stop (stop_headers only fills missing/empty lines; the stop_header_consistency pass has no neighbour logic). The fix is a delivery-side guard; the origin is unproven.

## Tests
`tests/test_local898_route_text.py` (30 tests) with generic fixtures `tests/fixtures/local898_tour.txt` (lead proof) and `local898_cloud_tour.txt` (cloud 551), names replaced. Replays assert: no minute/hour in any body; no turn instruction, road number or "Route N" in any Directions; no "Drive" between stops < 1 km apart; one (here: no) sculptor name; body before Directions; own Type/Specialty.
Regression: `tests/test_local896*.py 897* 894* 87* 88[0-9]* 89[0-3]*` (deselect local88_tour_pollution): 825 passed, 4 skipped.
