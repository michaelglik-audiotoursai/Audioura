# SUBMISSION — LOCAL-906K (offline, $0)

Branch `LOCAL-906K-refill-quality-hedge-clauses`, base `subscribed` 167f1c74 (ancestor check passes). No live run, no paid call,
no key; budget untouched.

## What changed
| # | Item | Where |
|---|------|-------|
| 1 | Refill quality bar: `refill_reject` refuses ellipsis/truncation, price / rating / "per adult" / "passengers/hour", video / click / book / package words, run-ons > 45 words, glued tokens (`top2`), world / record / exclusivity / unhedged-superlative claims, promo, another place's landmark that is not in the tour, sentences not about the stop (borrowed sentences), and search snippets that are not one clean complete sentence. Every refusal is logged `[LOCAL-906K] Stop N: refill candidate rejected (<reason>): "..."`. A refused candidate leaves the stop thin or on the D760 body. Wired into 906I `refill_thin_stops`, 906C filler branch (a) `_borrow_sentence`, 904 `refill_thin_stops.ok`, 905 own-evidence + neighbour refills. | `refill_quality_906k.py`, `leftovers_906f.py`, `leftovers_906c.py`, `route_content_896.py`, `delivery_bodies_905.py` |
| 2 | Hedge per clause: new `scoped_claims()` returns every superlative clause (split on and/but/while/;/, and "remains"/"is also"); clause tokens carry the sentence's subject words. `hedged_by_evidence` and `check_claim` scan all clauses; in the hedge, largest/biggest/longest are one size class (`cls_eq`). The hedge drops a bare "all" (`in all <Region>` -> `in <Region>`; `all of` is kept, 906J test). | `leftovers_906c.py` |
| 3 | Self-anchored thing: "The `<noun>` at/on/of/in/near/by ... `<Name>`" is kept; a bare "The `<noun>`" with no name is still dangling. | `leftovers_906c.py` `repair_thing_referent` |
| 4 | Exclusivity = record class: `record_claim` now catches "the only/sole country/place/... ", kind `exclusivity`; `record_support` always needs a reference source or 2 independent domains for it (no narrower-scope shortcut), and only another exclusivity statement whose scope covers the claim's backs it. | `leftovers_906c.py` |
| 5 | Venue promo ("you can visit `<Name>` restaurant/café/shop", "if you want to try ... you can ...", "Choose ... with or without a guide") dropped by `drop_promo`, unless the stop is that venue. | `refill_quality_906k.is_venue_promo`, `leftovers_906f.drop_promo` |
| 6 | Mode words: on a driving tour "as you walk here" -> "here"; other "walk around" -> "look around". Walking tours untouched. | `refill_quality_906k.fix_mode_words` (in `run_pass`) |
| 7 | Conflicting measures: article value replaces a conflicting web value (49 m long / 11 m high -> 7 m high); if only web pages disagree the measure is omitted (clause, else sentence). Logged. | `refill_quality_906k.resolve_measure_conflicts` |

## Decisions to know about
- The "about this stop" test (title token / object noun) is applied to sentences borrowed from a NEIGHBOUR's evidence (906C
  branch (a), 905 neighbour). Sentences from the stop's OWN evidence are keyed to it already and skip that one test; every other
  rule still applies. Applying it there broke the existing 906I refill test, whose valid evidence sentences ("Fog gathers in the
  valley ...") do not repeat the title.
- Unifying size/length is limited to the hedge. In `check_claim` it changed which of two sentences 906B keeps (906C 552 test), so
  support matching stays strict.
- "walk around" becomes "look around" (a literal "here" would break the sentence).

## Verification (all `env -u OPENAI_API_KEY -u SERPER_API_KEY THIN_STOP_SEARCH=0`)
- `tests/test_local906k_refill_quality.py`: 44 passed (551 Stop 5 / Stop 7 replays with generic names, 552 Stop 2 hedge in the
  second clause, "The statue at <Pagoda> was begun in 1963" kept, restaurant plug / "with or without a guide" dropped,
  "the only country" from one snippet dropped and kept with 2 domains or a reference, "as you walk here" on driving -> "here",
  7 m kept over 11 m, web-only disagreement omitted).
- Regression set from the task (906*, 907*, 89[6-9]*, 90*, 894*, 87*, 88[0-9]*, 89[0-3]*, lead905*, 791*; 88_tour_pollution
  deselected): 2286 passed, 4 skipped, 0 failed.
- `-k "ground or conclusion or pin or itinerary or snap or pool or d533 or derepetition or thin"` over `tests/`: 850 passed,
  4 failed, all on the known list (378 case_sensitive x2, 616 pool_path, 666). No new failures.

## Not verified
- No live Mac run; the 551/552 behaviour is shown only on generic offline replays, not on the real proof texts.
- Other-landmark detection needs a place noun in the name (village, bridge, mountain, ...); a landmark name without one passes.
