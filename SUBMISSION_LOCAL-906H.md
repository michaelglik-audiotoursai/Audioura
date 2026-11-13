# SUBMISSION LOCAL-906H — delivery always has the evidence ($0, offline)

Branch `LOCAL-906H-delivery-evidence`, base 3747262e (`git merge-base --is-ancestor 3747262e HEAD` = 0). No live run, no paid call.

## Cause
`generate_tour_text.py` called `ensure_bodies(final)` with no evidence; on a 2-stop tour `_EVIDENCE_904` is empty (pool skipped), so
`drop_unsupported_scope_claims(require_evidence_map=True)` returned the text unchanged: 906C/906F never ran.

## Changes
- New `delivery_evidence_906h.py`: job-scoped store (`rc._ScopedDict`, dropped by `end_job`, two jobs never share it).
  `add / get / resolve / coverage / report`; `report` logs once per job `[LOCAL-906H] delivery evidence: k/n stops (src:n,...)`.
- Producers fill it: 889 key-fact `_evf` (thin facts + direct snippets + wiki), `set_evidence_904` (904 refill), fact-sheet `confirmed_facts`,
  user-stop enrichment material (article/site/snippets). The pool path reaches it through `set_evidence_904`.
- Consumers use it when the caller passes none (a passed entry wins per title): `ensure_bodies`, `final_pass`,
  `route_leftovers_906.drop_unsupported_claims`, `leftovers_906c._ev_map`, `route_leftovers_906._merged_evidence`.
  The generator's delivery call site now passes `_de906h.get()` explicitly.
- No silent no-op: `final_pass` logs `[LOCAL-906C] final pass: evidence for k/n stops, <c> change(s)`; with k=0 it appends
  `NO evidence: scope/blocked/cross-stop checks skipped`.
- Dangling quantifier: source = `spoken_text_hygiene.audit_seating_capacity` (the `\x00MAG\x00` cut left "an additional" behind).
  It now removes the quantifier with the measure phrase. Delivery guard `drop_dangling_quantifier` (in `final_pass`): "an additional/a further/an extra"
  before a preposition/clause end; "another/some/about/around/..." only in a sentence about a measure (climb, steps, long, ...), so
  "Another from the same family..." is untouched. If nothing is left of the clause the sentence goes.
- One count: `fix_counts` calls `dedupe_count_sentences`: "You have now visited N stops (in all)." is removed when the closing "That's N stops" exists.

## Tests
`tests/test_local906h_delivery_evidence.py` (20): replay of the delivered shape with `ensure_bodies(text, log=...)` and no evidence
argument after a mocked 889 fill (sentence dropped, `[LOCAL-906C] ... superlative scope unsupported` logged); empty store -> NO evidence line;
job scoping; once-per-job report; dangling quantifier (strong, weak, legit-with-number, source cut); single count.

Regression: the listed local906/89x/90x/894/87x/88x/89[0-3]/lead905/791 set: 1889 passed, 4 skipped, 0 failed.
`-k "ground or conclusion or pin or itinerary or snap or pool or d533 or derepetition"`: 707 passed; 3 failed, all on the pre-existing list
(`test_local378…case_sensitive_surname`, `test_local378…mentions_person_case_sensitive`, `test_local666…no_pin_and_no_archive_is_v1`).

## Not verified
No live run (budget $0): the real-job fill order (889 `_evf` is built just before delivery) is read from code, not observed.
