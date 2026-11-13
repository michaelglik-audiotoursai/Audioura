# SUBMISSION LOCAL-906B — silent body loss on tour 552 (OFFLINE, $0 intended)

Branch `LOCAL-906B-silent-body-loss`, base `e03da1a8` (subscribed). Evidence: LEAD proof 552 (`lead_proof_552.txt`; the
generator log was read, never copied or committed).

## Budget disclosure (read this first)
The task budget was **$0**. While building a bisect fixture I called `thin_stop_delivery.rebuild_thin_delivered_stops`
without an `escalate_fn` and with `OPENAI_API_KEY` in the environment. For a fixture stop with no facts it ran the
real escalation (serper + one LLM call); its own log line reports **$0.0048** (`serper $0.0040 + llm $0.0008`). I noticed
it in the output, stopped, and recorded it: `task_budget.record_run('LOCAL-906B', 0.0048)` (ledger `spent_so_far` = 0.0048).
From then on every run used `env -u OPENAI_API_KEY THIN_STOP_SEARCH=0` and the tests stub the escalation
(`tests/test_local906b_silent_body_loss.py` sets `THIN_STOP_SEARCH=0` and passes an `escalate_fn` stub). That is the only
paid call; there was no generator run. The Serper charge is not metered by the ledger beyond what I recorded.

## 1. Which step removed Stop 2's 3 grounded sentences (bisect)
**Step: 873B `thin_stop_delivery` append, then 619B `tour_conclusion._split_tail` cut.** Not any of 889/890/901/904/898/906/905.

* Rule that lost them: `rebuild_thin_delivered_stops` appends the rebuilt fact sentences to `body_idx[-1]`, the LAST body
  paragraph of the stop. On the LAST stop that paragraph is the tour's closing (recap / `That's N stops in all.` / the
  restaurant offer), so the facts rode on the closing. The 880/883/884 gates then labelled and KEPT them (log: `labelled
  3, 3 kept`). `_split_tail` (called by `rebuild_conclusion`, 619B) cuts everything from the first thread opener / count
  line to the end as "the old conclusion", so the facts went with it. `_split_tail` logged nothing.
* Reproduced step by step: after 873B the three facts sit after the offer line (`tests/...::test_bisect_...`);
  after the old `_split_tail` Stop 2 has no body; 905 then refilled with the verbless evidence sentence. Every pass after
  619B (901 cap, 904 refill, 898, 906 `content_pass`, 905) was run on the fixture and none of them drops those sentences.
* Not verified: the real 552 text between 873B and 619B (only the generator log exists, not the intermediate text), so the
  exact paragraph the facts sat in is inferred from the code path and the log; the fixture reproduces the behaviour.

Fixes:
* `thin_stop_delivery`: the closing (count line, thematic recap, offer) is never "body"; facts are appended to the last real
  body paragraph, or inserted before the closing (both the deterministic and the narrated branch).
* `tour_conclusion._split_tail` (defence for other paths: pool/cache text): sentences in the cut span that are not
  conclusion are moved back into the stop body, and every sentence it does discard is logged
  `[LOCAL-619B] Stop N: dropped "<80>" (old conclusion replaced by the rebuilt one)`. Kept: text after the offer sentence
  (the offer is the closing's last sentence), and text after the count sentence that names no other stop and reads as
  neither a recap nor a list/label block (`Along the way:` + bullets and "Longan carries a tale…" recaps stay dropped; the
  existing 855b and lead double-conclusion tests pin this). Log: `[LOCAL-906B] Stop N: kept "<80>" (…)`.
* Every removal logs: `drop_carry_filler` (had no sentence/stop), `drop_orphan_work_paragraphs` (silent) now log
  `[LOCAL-xxx] Stop N: dropped "<first 80>" (<rule>)`. All other delivery passes already logged the sentence; a
  parametrised test now holds all 21 of them to it (`test_every_removed_sentence_is_logged[*]`): it runs each pass on a dirty
  fixture and requires the first 80 chars of every sentence the pass removed to appear in a log line.

## 2. A refill / kept sentence is a sentence
`route_content_896.is_fragment` now also returns True for a verbless sentence (`is_verbless`): >= 5 words, English-looking
(>= 2 English function words, so other languages are never judged), no form from a generic verb list (be/have/modals,
stands/lies/measures/…, common irregular pasts), no -ed word, no 3rd-person -s word that follows a noun-like word (not an
article/preposition/number/superlative). Imperatives and "That's N stops" are fine. Consequences: 905
`_own_evidence_sentence` and 904's `ok()` reject "49-meter-long, 7-meter-high reclining Buddha statue, one of the largest in
Southeast Asia." and take the next option (next valid evidence sentence → neighbour → honest body); `drop_fragments` drops a
kept verbless sentence with its usual log (never emptying a stop).
Caveat: this is a heuristic. A verbless but acceptable noun phrase ("Lush greenery along the trails of the old forest.") is
now dropped from bodies on every English tour; a sentence with an irregular verb outside my list could be wrongly dropped.

## 3. No near-duplicate within a stop
`same_fact(a, b, title)`: `_near` (>= 0.6) OR the same statement with a different date (date words/numbers and title words
set aside, >= 5 shared content words and >= 0.35 of the smaller set). Used by 904's refill `ok()` (so the thin refill no
longer appends "In the late 19th century, a great sage … " next to "In 1872, Master … "), and by the new
`drop_within_stop_duplicates` (in `content_pass`, both paths): keeps the more specific sentence (`specificity`: exact years
x3, numbers, proper names), later one on a tie, exact duplicates keep exactly one; logs
`[LOCAL-906B] Stop N: dropped "<80>" (same fact as "<40>…" in this stop; the more specific sentence stays)`.
Threshold risk: 5 shared words + 0.35 is tuned on the 552 pair and the unrelated-sentence tests; not calibrated on a corpus.

## 4. Address check covers every stop
`single_place_903._set_coord(..., donor=)` marks a stop moved to another stop's verified pin (`_pin_moved_to_stop`).
`pin_snap.verify_addresses`: a marked stop is no longer judged against its own (wrong) reference; it inherits the donor's
verdict (dropped there → dropped here), and when the donor had no address it is judged on the donor's pin. Log:
`[LOCAL-906B] address dropped for '<stop>': … inherits that stop's address verdict`. Unmoved stops behave as before.

## 5. Pins untouched
No change to pin selection/snap/agreement logic itself (only a marker key). 902–906 pin tests and the 905/906 replays pass.

## Tests
`tests/test_local906b_silent_body_loss.py` (51 tests, 21 fail on the base) + `tests/fixtures/local906b_single_dirty.txt`.
* Requested set (`test_local89[6-9]*`, `90*`, `894*`, `87*`, `88[0-9]*`, `89[0-3]*`, `test_lead905*`, deselect pollution):
  **1162 passed, 4 skipped, 0 failed.**
* `tests -k "ground or conclusion or pin or itinerary or snap or pool"` (deselect pollution): 659 passed, 3 failed — all
  pre-existing (`test_local378…case_sensitive` x2, `test_local666…no_pin_and_no_archive_is_v1`).
* Every other test file that imports the touched modules (34 files, incl. root `test_local620_story_types_prefs.py`,
  855b, lead_double_conclusion): 733 passed, 2 failed (the two pre-existing 378 ones).
  `test_lead_double_conclusion` and `test_local855b…spelled_out_recap` failed on my first salvage rule and drove the
  tighter rule above.

## Not verified
No live run (budget). The real 552 intermediate text, the 889/890 passes on real data, and the effect of the verbless rule
on real tours at scale are unproven; a field run should confirm Stop 2 keeps its grounded sentences and that no English
body loses a good sentence to the verb heuristic. Files: `thin_stop_delivery.py`, `tour_conclusion.py`,
`route_content_896.py`, `route_leftovers_906.py`, `single_place_903.py`, `pin_snap.py` + the test and fixture.
