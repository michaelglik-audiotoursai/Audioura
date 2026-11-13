# SUBMISSION LOCAL-906J — hedge anywhere wins, evidence purity, record claims, dangling thing referent

Branch `LOCAL-906J-hedge-and-evidence-purity`, base c0a59a47 (LOCAL-906I). Offline, $0, no live run, no paid call.

## Which entry made the 552 Stop 2 scope check pass (item 1)
`check_claim("This statue is the largest reclining Buddha in <Region>.", ev)` returns `ok` as soon as the stop's evidence holds ONE
unhedged "the largest ... in <Region>" sentence (replayed in `test_replay_552_without_the_hedge_the_old_store_vouched_for_the_claim`:
hedged article alone -> `bad`; article + the fact-sheet fact -> `ok`). Two producers wrote model text into the 906H store:
1. **fact-sheet** (`generate_tour_text.py`, `_de906h.add(... confirmed_facts ..., "fact-sheet")`): the log's `fact-sheet:2` —
   the model-written `confirmed_facts`. This is the entry that vouched for the unhedged claim (the article only says "one of the largest").
2. **"889" / "904"**: the `_evf` blob (and `set_evidence_904`) joins the thin facts (`_THIN_FACTS_PER_STOP` / `_THIN_FACTS_SINK`), which are
   the LLM extractor's paraphrases (`thin_stop_search`), not the page text. The 880 signature story reaches the guards through
   `route_leftovers_906.set_signature_stories` (tone only), not the store.
The log's `889:1, 904:1, fact-sheet:2` therefore mixed source text and model text. I did not replay the original gen log (not in this
worktree); the replay above is a fixture, so "fact-sheet is the entry that made it pass" is proven for the fixture, not for the run itself.

## Changes
1. **Purity** (`delivery_evidence_906h.py`, `generate_tour_text.py`, `route_content_896.py`, `thin_stop_search.py`)
   - `add(ev, source, kind=None)` stores only kinds `article` / `web` / `user-article`; `fact-sheet`, `signature`, `refill`, `rewrite`,
     `llm`, `thin-fact`, `tour` (and any unknown source) are refused and counted in `refused()`. Registered LLM passages are scrubbed.
   - Per-entry provenance `{text, kind, domain}` (`entries()`), `kinds()`, `assert_pure()`. `[LOCAL-906H] delivery evidence` now ends with
     `kinds article:N, user-article:N, web:N`.
   - Generator: the fact-sheet feed is removed; `set_evidence_904` no longer feeds the store; the "889" feed is rebuilt from SOURCE text only:
     the thin facts' own source passage (`Fact.passage`, new, kept in `_THIN_PASSAGES_SINK`), wiki / article items, and direct search snippets
     (LLM records filtered by `llm_evidence`), each with its URL. The caller-passed evidence blob to the guards is unchanged.
2. **Hedge anywhere wins** (`leftovers_906c.hedged_by_evidence`, `_hedge_text`): an unhedged size superlative whose scope equals the scope of
   ANY hedged evidence sentence of the same class is rewritten ("the largest reclining Buddha in <Region>" -> "one of the largest reclining
   Buddhas in <Region>"; "is the largest" -> "is one of the largest"; possessive `<Region>'s largest X` -> `one of <Region>'s largest Xs`).
   Log `[LOCAL-906J] Stop N: superlative hedged to match the evidence: "<80>"`. A hedged possessive is now recognised as hedged in `scoped_claim`.
3. **Record claims** (`record_claim`, `record_support`): "holds the (world) record for", "a (Guinness) world record", "record-breaking",
   "record for the highest ...", and the world's superlatives (`the world's highest`). Scope = world unless stated. Supported only by a non-LLM
   entry that states a record for the same object; world scope needs an article / reference domain (encyclopedia, record body, `.gov`)
   OR 2 distinct registrable domains; one web snippet (or two snippets of one domain) is not enough. Otherwise the sentence is dropped,
   logged `[LOCAL-906J] Stop N: record claim unsupported ...`. The 906I thin-stop refill no longer pulls such a sentence back
   (`leftovers_906f.refill_thin_stops`), nor a scope-`bad` sentence.
   Caller-passed plain evidence (no provenance) is judged by text alone.
4. **Thing referent** (`repair_thing_referent`, in `final_pass` before the filler step): "The <generic noun>('s) ..." with the noun in neither
   the title nor an earlier sentence -> named from the stop's evidence when exactly one name ends in that noun, else the sentence is dropped.
   Logged `[LOCAL-906J] Stop N: "The pagoda" had no antecedent ...`.
5. `scoped_claim` is `lru_cache`d (the pass asks about the same sentence several times; the extra checks had added ~80% to a pathological-input
   perf test, now faster than base).

## Tests
`tests/test_local906j_hedge_and_evidence_purity.py` (35): purity/kinds/assert, 552 and 551 replays, hedge grammar, 3 record forms (unsupported ->
dropped, encyclopedia / record body / 2 domains -> kept, one snippet or one domain twice -> dropped), thing referent (named / dropped / left alone).
Three assertions in `tests/test_local906h_delivery_evidence.py` changed on purpose: a claim the evidence hedges is now rewritten, not dropped; the
904 stash no longer fills the store.

Required regression set (`env -u OPENAI_API_KEY -u SERPER_API_KEY THIN_STOP_SEARCH=0`): **2152 passed, 4 skipped, 0 failed.**
`-k "ground or conclusion or pin or itinerary or snap or pool or d533 or derepetition"` (minus tour_pollution): 706 passed, 4 failed — all 4
(`test_local378` x2, `test_local616` pool, `test_local666` no-pin) also fail on the base c0a59a47 (9 failures there in those files); not mine.

## Not verified
No live run. The real 551 record holder being another site is not detectable offline; the rule only demands source support. The 889 source feed
was checked by reading the code and an import, not by executing the generator.
