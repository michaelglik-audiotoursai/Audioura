# SUBMISSION LOCAL-906C: Wave 52 leftovers (offline, $0)

Branch `LOCAL-906C-superlatives-filler-stops`, based on 33def933 (`git merge-base --is-ancestor 33def933 HEAD` exits 0).
No live run, no paid call. Every replay ran as `env -u OPENAI_API_KEY THIN_STOP_SEARCH=0`, and no LLM or escalation function is reachable from the new code.

## Item 1: why the exclusivity claim survived
Replay of a generic Stop 3 ("<Country> is the only country in <Region> to grow <fruit> on a commercial scale.") through the route delivery order (`finalize_898` → `content_pass`, `apply_single_place_guards`, `ensure_bodies`):

| evidence for the stop | result |
|---|---|
| (a) lacks the claim, or no evidence at all | dropped (`[LOCAL-906] ... exclusivity claim not in the stop's evidence`) |
| (b) states the claim | kept |
| (b') states a similar claim for another region (`<Country B>` / `<Region B>`) | **kept before this change**, dropped now |

- The route path does call `drop_unsupported_claims` with the stop's evidence. `finalize_898(text, None)` (the delivery call) reads the `_EVIDENCE_904` stash that the generator fills with `set_evidence_904`, and the post-pass call passes `_ev889`.
- Three weaknesses could let the claim through, and each is closed:
  1. The old test accepted any evidence sentence with a cue word and 3 shared tokens, whatever its scope.
  2. The whole 906 claim guard sat behind `in_scope()` (a route or ≤ 2 stops). That depends on job-scoped route state, and a multi-stop tour outside it was never checked.
  3. Nothing re-checked after the later passes.
- Fix: `leftovers_906c.drop_unsupported_scope_claims` runs on any tour. It is called from `drop_unsupported_claims` (before the `in_scope` gate) and from the last step of `ensure_bodies`, which runs on every path.
- **Not proven offline:** which of the three caused the wave-52 cloud survivor. I only have the verbatim sentence, not the stop's evidence blob. If the cause was evidence containing a same-token claim, it is item 1 weakness (1), which is now scope-checked.

## Item 2: scope-matched superlatives
- Claims covered: "the only / first / sole / largest / longest / tallest / biggest / highest / oldest / deepest / widest / smallest … in|across|within|throughout <area>" and "no other … in <area>".
- Hedged forms ("one of the largest") and claims scoped to the stop's own place are not touched.
- Scope ranks, from the wording or the placeholder: world > continent/macro-region > country > province/state > city. The evidence scope must equal the claim's scope or be strictly wider. Two different names of the same rank, or unknown names, do not cover each other.
- Unsupported: the sentence is dropped, and the log reads `[LOCAL-906C] Stop N: superlative scope unsupported: "<80>"`. If the evidence has a narrower, supported superlative of the same thing, that sentence is used instead (log: `narrower supported version used`).
- "Largest … in <Country>" does not support "longest … in <Region>" (tested).
- Carve-out: when no evidence at all was handed in anywhere, a plain superlative (largest / longest …) cannot be judged and is left alone. `tests/test_local902_single_place_pin.py::test_replay_552_w49…` asserts exactly that. Exclusivity words (only / first / sole / no other) are still dropped, as in 906. A stop with no evidence entry while other stops have some states nothing, so its claim is dropped.

## Item 3: within-stop duplicate
`drop_within_stop_duplicates` takes the stop's evidence and calls `prefer_supported`:
- a sentence with an unsupported scope never wins;
- if both are wide, the narrower known scope stays;
- otherwise 906B specificity decides.
- A ranking claim ("largest … in <Country>") and a plain measurement ("49 meters long") are no longer treated as one fact. Otherwise the supported claim was dropped as less specific.

## Item 4: filler bodies (`distinct_filler_bodies`)
Body identity is the token set of the body minus the stop's title words and minus the disclosure sentence (≥ 0.8 overlap). Order:
- (a) an unused sentence from another stop's evidence that names this stop's subject. It reuses `neighbour_sentence` and must not already be delivered, so the sentence is grounded in evidence (D771).
- (b) a variant from `FILLER_VARIANTS`: 9 kinds (view, ascent, departure, market, shore, road, height, worship, neutral), 3–5 variants each, with the neutral pool as the fallback. It takes the first variant no other stop uses.
- (c) merge into the previous stop: header, Coordinates, Type and body dropped, the stop's Directions kept (the previous stop's Directions to it are removed), the last stop's closing kept, headings renumbered, and "That's N stops in all." recomputed through `fix_counts`.
- Each stop logs `[LOCAL-906C] Stop N '…': filler body repeats Stop M; branch (a|b|c): …`.
- Runs in `content_pass` before `drop_repeated_sentences`, so the 906 "left as is" case never survives. It also runs at the end of `ensure_bodies` (every path).

## Item 5: salvage and markers
- `_salvage_after_count`, `stop_like` and `_sentences906b` ignore `<!-- … -->` markers: they are neither kept, dropped, counted nor logged.
- A marker found in the replaced closing is put back as the last line by `rebuild_conclusion` (it was the last line before). Markers elsewhere in the body are left where they are.
- Not mine, and I did not change it: `finalize_898` on the route path already removes the editor marker from the text. I confirmed this on the base commit.

## Item 6: "You see the X here is …"
- **Cause:** no template or prompt writes it. The model writes "You see the X here, which is 49 meters long, …". The clause cutters (`cap_unsupported_numbers`, `cap_unsupported_facts`) split at ", which / , and / ;", keep the good parts and re-join them with a bare space, so the connector disappears.
- **Fix:** `_split_clauses` and `_join_kept_clauses` re-join neighbouring good clauses with their own connector. A good clause after a cut one stays only if it can stand alone ("and you can reach it by cable car" yes, "which is 49 meters long" no), and then starts a new sentence.
- **Safety net:** `repair_you_see_here` turns an existing "You see the X here is …" into "You see the X here. It is …".

## Tests
`tests/test_local906c_superlatives_filler.py`: 48 tests on generic fixtures (`tests/fixtures/local906c_route_w52.txt`, `local906c_single_w52.txt`). They cover items 1–3 on route, single-place and plain tours, items 4–6, and a full replay of both wave-52 shapes. The replays assert:
- no exclusivity claim or scope-less regional superlative;
- the narrower true claim is kept;
- no two stops share a body;
- the stop count equals the delivered stops;
- no marker in any log line;
- no "You see the X here is".

Regression run, same command as the task:
- The 906/896–90x/894/87x/88x/89x/lead905 files: 1295 passed, 1 failed. The failure is `test_local902…test_lead905_far_model_pin_snaps_to_in_scope_reference`. It passes alone, and it also fails on the unmodified base in the same combined run, so it is order-dependent and pre-existing.
- `-k "ground or conclusion or pin or itinerary or snap or pool"` (excluding `test_local88_tour_pollution.py`): 660 passed, 3 failed. All three are on the known pre-existing list (`test_local378…case_sensitive*` ×2, `test_local666…no_pin_and_no_archive_is_v1`).

## Not verified
No live run, so none of this is proven on a real wave-53 generation. The offline replays use the wave-52 shapes, not the real cloud texts.

Files: `leftovers_906c.py` (new), `route_leftovers_906.py`, `route_content_896.py`, `delivery_bodies_905.py`, `tour_conclusion.py`, the test and the two fixtures.
