# SUBMISSION LOCAL-906P — measure owner, hedge-last, junk, glue, pins, cable car (OFFLINE, $0)

Branch `LOCAL-906P-measure-owner-junk`, base 4bcdd1a9 (`git merge-base --is-ancestor 4bcdd1a9 HEAD` = 0). No live run, no paid call
(budget $0; tests run with `env -u OPENAI_API_KEY -u SERPER_API_KEY THIN_STOP_SEARCH=0`).

| # | Fix | Where |
|---|-----|-------|
| 1 | An elevation ("above sea level", "summit/altitude/elevation N", "rises N") is never a measure; a value is used only when its evidence sentence shares an object noun (statue/tower/…) with the body sentence (title as fallback); the body keeps its own wording (`rewrite_measure` swaps only number+unit, never splices "height of N meters"); a `which is height of N …` splice already in a body is cut and stays grammatical (`fix_bad_splice`). | `refill_quality_906k.py` |
| 2 | `_owner`: of the titles a sentence names, the object (statue) wins over the containing place (mountain/park/island…), so the statue's facts stay on the statue stop and are cut from the mountain stop. | `leftovers_906f.py` |
| 3 | `hedge_guard` runs LAST (end of `final_pass`, end of `ensure_bodies` after the thin refill): an unhedged size superlative becomes "one of the …" when the stop's evidence hedges it in any scope / says it WAS the longest until a year, or the same stop already says "one of the …". Log `[LOCAL-906P] … record claim hedged`. | `owner_junk_906p.py` |
| 4 | Photo captions ("A person observes …", "pictured", "photo of"), list stubs (ends ":", ": -", "as follows", " - " bullets) dropped; also refused as refills. | `owner_junk_906p.py`, `refill_quality_906k.refill_reject` |
| 5 | Glued sentence: a lowercase -ed/-ing/that/which word then capital "The <2+ capitalised words>" → cut fragment dropped. "The Hague", "in The New York Times" kept (tests). | `owner_junk_906p.fix_glued` |
| 6 | `rereference_pins` (pin over water per `reverse_is_land`, or > 10 km from the 906D place reference → re-resolved by the same chain as the destination; tour pin recomputed). `replace_detours` (detour > 60 % of A→B replaced from a pool when a better one exists; before writing, in `order_poi_list`). "Tours from X often include …", "as part of day trips" = operator copy. Closing "Exploring these … highlights …" filler; closing superlative no stop states is dropped. | `route_order_909.py`, `generate_tour_text.py`, `scope_906o.py`, `route_leftovers_906.py`, `owner_junk_906p.closing_claims` |
| 7 | `cable_car_numbers`: a rise above the place's known elevation, or a cable-car number no evidence of the stop carries, is dropped; logs `[LOCAL-906P] … cable car / ascent number dropped (reason)` (the path had no log line). | `owner_junk_906p.py` |

Wiring: `owner_junk_906p.run_pass` is the tail of `leftovers_906f.run_pass` (every delivery path); `final_pass` (hedge) ends
`leftovers_906c.final_pass` and `delivery_bodies_905.ensure_bodies`.

## Tests
`tests/test_local906p_measure_owner_junk.py`: 39 tests. Usual set (+ it), `--deselect tests/test_local88_tour_pollution.py`:
**2557 passed, 4 skipped, 0 failed.**
I also ran the guards over the three LEAD texts (no evidence store): caption, list stub, glued sentence, raw splice and the closing
superlative are logged and removed; the cable car needs the evidence store (elevation) so it is covered by tests only.

## Not proven / to field-test
- **Detour pool is not wired live.** `replace_detours` is tested with a mock pool; `generate_tour_text` passes
  `locals().get('_detour_pool_906p')`, which nothing sets (there is no candidate-pool variable at that point), so live it logs
  "kept" for a detour. Needs a pool producer (replenish proposer) — handing to LEAD.
- The pin re-reference uses `_res906m` (needs `_coarse_center_902`); without it the chain returns None and a water pin falls to the
  909 restore (flagged `_pin_water_909`).
- No live run; the 552 / 551 / drive texts were not regenerated.
