# SUBMISSION LOCAL-904 — single-place polish (offline, $0)

Branch `LOCAL-904-single-place-polish`, base ae3453be (`git merge-base --is-ancestor ae3453be HEAD` = 0). No live run, no paid call, no network.

## Changes
1. **Floor under the single-place caps** (`route_content_896.refill_thin_stops`, called from `apply_single_place_guards` after the 901/902 caps and `drop_fragments`). A stop that LOST sentences and has < 3 content sentences is refilled in order: own evidence (`aboutness.refill_facts` → `snippet_facts` → `stop_coherence.evidence_fact_sentences`), then ONE same-site neighbour sentence (`neighbour_sentence` over the neighbour's delivered body), then the D760 honest disclosure + non-factual sentences. A dropped sentence (or a paraphrase of it) is never re-added; mood filler, travel claims and off-site suggestions are never used as refill. Log: `[LOCAL-904] Stop N thin (k sentences) -> refilled from evidence|neighbour|honest`.
   - Delivery has no evidence in hand, so `generate_tour_text.py` stashes the final-pass evidence bundle via `route_content_896.set_evidence_904(_evf)`; without it the evidence stage is skipped and the neighbour/honest stages apply.
2. **Address** (`pin_snap.address_part_matches`, used first by `address_agrees`): every non-numeric address part, folded and admin-prefix-stripped (Xã/Huyện/Phường/Quận/Thị trấn/Thị xã/Tỉnh/Thành phố/District/Ward/Province/Commune/…), is compared with the reverse geocode's parts, stripped the same way. A match on a part that is not the province or country (reverse geocode's last part, a province-prefixed part, a part named by the scope) keeps the address. The previous rules remain as fallbacks.
3. **Same rule for both stops**: `verify_addresses` already applies one rule per stop; test covers both addresses.
4. **Off-site suggestion** (`is_offsite_suggestion`, in `cap_single_place_filler`): "you might also visit …", "on your way back", etc., with no digit and an object not in the stop's support (title/Type/examples/evidence), is dropped on the single-place path. Log `[LOCAL-904] ... off-site suggestion with no support dropped`.

## Tests
`tests/test_local904_single_place_polish.py` (9 tests, generic fixture `tests/fixtures/local904_single_place_generic.txt`): address with/without prefix, wrong district still dropped, both stops same rule, off-site suggestion, replay (with evidence → Stop 2 has 3 sentences, no mood, both addresses kept, dragon-fruit gone; without evidence → neighbour then honest), neighbour stage, never re-add dropped, untouched stop, idempotence.
Requested regression run (88x tour_pollution deselected): **1021 passed, 4 skipped, 0 failed**.

## Notes / judgement calls
- Spec says the neighbour sentence must not duplicate "a sentence already in the tour"; a neighbour's sentence is by definition in the tour, so I read it as: not a duplicate/paraphrase of a sentence already in THIS stop, of a dropped sentence, or of one already borrowed. A borrowed sentence is therefore repeated across the two stops (as in 902).
- The proof text in `lead_proof_552.txt` is post-cap (Stop 2 has one sentence), so the replay fixture reconstructs the pre-cap body generically. The "calm" sentence is written with two mood terms because the 901 rule keeps a single supported mood term.
- The refill only touches stops that lost sentences in the same guard call (idempotent on delivered text).
- Not proven live; the `set_evidence_904` wiring is not exercised by a test beyond the explicit-argument path.
