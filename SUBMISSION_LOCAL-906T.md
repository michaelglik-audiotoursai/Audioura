# SUBMISSION LOCAL-906T

Branch `LOCAL-906T-stub-personcap-promo`, base 2f7a9ffd (`git merge-base --is-ancestor 2f7a9ffd HEAD` = 0). Offline only, $0, no live run, no paid call.
Tests: `tests/test_local906t_stub_personcap_promo.py` (39) plus the usual set, deselecting `test_local88_tour_pollution.py`: 2909 passed, 4 skipped, 0 failed.
(`test_local893_preview_timeout` failed once in two earlier runs while other runs were using the machine, and passed alone and in the full set. It is a timing test; I did not change anything it reads.)

## What changed
New `stub_promo_906t.py`, called from `language_dest_906s.run_pass`, so it runs on every pass of 906S `last_word`, including after a refill.

| # | Item | Fix |
|---|------|-----|
| 1 | Stub "This site" | See "Not proven" below. Source hardening: `route_content_896._join_kept_clauses` drops a kept clause of fewer than three words that has no final punctuation; `cap_person_across_stops` rebuilt a body through `_split_into_sentences` (drops every sentence of 20 characters or fewer) and now splits without that floor. Final guard `drop_stub_tails`: a body's last sentence with no final punctuation and (under five words, no verb, or a fragment), or a verbless run of three words or fewer, is dropped and logged `stub tail dropped`. A body is never emptied. A whole sentence that only lost its full stop gets it back. |
| 2 | PERSON-CAP | `_person_names(sentence, place_tokens)`: a name is not a person when its last token is a landmark/common noun (pagoda, mountain, ... new `_LANDMARK_NOUNS`), a word of any stop title, the tour title or request (`place_text`, passed from `generate_tour_text`), or the object of in/near/at/outside/around/into without a person title. Cuenin test still caps. |
| 3 | Promo | `promo_reason`: ticket(s), price(s) with an amount, currency amounts, "for entry", admission, entry fee; "Visit ..." listings; "with a dedicated/private/English-speaking ... guide"; "visitors from all over the world". Dropped even when last in the stop (906S `factless_stops` then refills or discloses). |
| 4 | Record | `contested_record`: an unhedged size record is hedged ("one of the longest ... statues in Asia") when ANY evidence entry of the job (tour stop or not, e.g. the 552 stop) hedges the same class, or says "was the longest ... up to <year>". With no evidence anywhere in the job, a region-or-wider record is hedged. Comparatives ("bigger than", "surpassing", "exceeding", ...) need an evidence sentence that states a comparison naming the target; else dropped. |
| 5 | Closing | `Exploring/Visiting these sites/stops/places allows/lets/helps you ...` and `creating lasting memories` added to 906S `_VARIANTS` and to the promo list (body and tour closing). |
| 6 | Neighbour | `Nearby, you can ...` naming another stop (distinctive title tokens, folded) is dropped. |
| 7 | Bearing | `bearing_conflict`: "<N> km <dir> of <City>" vs the bearing City -> stop pin; more than 60 degrees off is dropped. City centres: `set_city_centers` (registered in `generate_tour_text` from the pipeline's city centre), else a stop of the tour whose title holds the city. A city with no known centre is never judged. |
| 8 | Coarse pin | `fix_coarse_pins`, run in `generate_tour_text` after the 906D last-resort block: a pin with both values on a 0.01 grid is replaced by a named-place geocode (stop name, then the hill/mountain/island the body names), accepted inside the province box and within 80 km, never a coarse-looking hit. Logs `[LOCAL-906T] stop=N pin ... -> ... via named-place geocode ('<query>')`; `_pin_source_906t` is set on the stop. |

## Findings
- Item 8 cause (from the log): the geocoder returned HTTP 429 for every Nominatim query in the drive ("Poshanu Cham Towers -> none ... found nothing inside 'Binh Thuan'"), so no place reference existed for stop 1. The tour pin fell back to 10.9, 108.1. Nothing retried after the limit. `fix_coarse_pins` asks again at the end with the body's hill name, but under a sustained 429 it also gets nothing and logs "no named-place geocode answered"; the pin then stays coarse.
- Item 4 cause: from the log, stop 3 of the drive had delivery evidence (`906H 3/3 stops`), but the tour-operator page "Ta Cu Mountain with the longest reclining Buddha statue in ..." is in that evidence (log 801), and 906C accepts an unhedged claim that evidence states. The other stops' hedge ("one of the largest ... Southeast Asia") and the encyclopedia's "was the longest ... up to 2020" were never consulted for it. `check_claim` itself correctly returns "bad" for "in Asia" against the 552 evidence, and for a stop with a missing evidence map, 906C marks a plain superlative "na" and keeps it. Both paths are now covered.
- The comparative check that already exists (`drop_unsupported_comparatives`) only asked whether the target's words appear anywhere in the evidence, and not for "surpassing". The new check wants a comparison sentence.

## Not proven (handing to LEAD)
- Item 1: I could not reproduce the origin of "This site". The delivered 551 text I have ends the stop with "This site is open all year round, ...", so the stub is not in the saved text, and none of the 906S, PERSON-CAP, pronoun or repeat-strip functions produce it from the logged inputs. The hardening above removes the two mechanisms I could find that leave a short or unpunctuated tail; the final guard covers the symptom whatever its source. A live 551 run would show whether the stub recurs; the log line `stub tail dropped` marks it.
- Items 7, 8 and 4 are unit-tested with mocks; none has run on a live tour. Item 7 only judges cities whose centre the pipeline registered or a tour stop holds; the pin snap is not changed.
- `fix_coarse_pins` replaces any 2-decimal pin that has a named-place hit, including a precise-looking user location with a coarse value. User pins flagged `_user_pin` or `user_explicit_pin` are skipped, but the existing snap stages may use other flags.

## Files
`stub_promo_906t.py` (new), `derepetition_guard.py`, `route_content_896.py`, `language_dest_906s.py`, `generate_tour_text.py`, `tests/test_local906t_stub_personcap_promo.py`, this file. The proof log was not committed.
