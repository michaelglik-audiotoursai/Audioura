# SUBMISSION LOCAL-892 — an LLM's own output is never evidence

**Status: the rule is built and tested offline (23 new tests; replay on the 891 persisted bundle passes all four required absences). The one live run met the required absences and audit 0 unsupported, but it did NOT exercise the LLM path (see "Live run": zero LLM-sourced snippets existed in that run), so the live run does not prove the new rule by itself; the offline replay does. One live criterion failed: City Hall has 4 sentences (needs ≥ 5) and lost its "architect" key fact.** Branch `LOCAL-892-no-llm-evidence`, base `8efe2768` (verified `merge-base --is-ancestor` exit 0).

## Why 891 shipped the Pier evacuation (root cause)
`stop_knowledge_fallback.facts_as_snippets` shaped the LLM's answer like a search snippet (`source: knowledge_fallback:openai`, title = stop name). Every evidence sink (`stop_coherence.snippets_as_evidence_texts`, the `_ev883`/`_evf` blobs in `generate_tour_text`, `run_cloud_parity_proof_884._build_evidence_by_stop`, the `claim_provenance.SourcePool`) joined those dicts into the stop's evidence string. The gate judge and the audit then read "In 1975 … Bạch Đằng Pier was a significant evacuation point" as an about-stop item. The same path explains the **Cathedral basilica sentence**: the persisted Cathedral bundle holds `Cathedral In 1959, the Vatican anointed the Saigon Cathedral as a basilica` (an LLM item, `about_stop: true`); the real Vietnamese article ties 1959 to the Our-Lady-of-Peace statue and gives the basilica title separately (E15–E17). The 891 judge's reasoning was not logged, so "the LLM item was the support" is inferred from the bundle (it is the only item with both 1959 and basilica), not observed. `claim_provenance` called that sentence `parametric` yet the gate passed it — two components, two answers, and the gate was the one reading the LLM item. The **Wilson** sentence has the same origin (`War Remnants Museum Colonel William Wilson, a combat veteran …` is an LLM item).

## What changed
New `llm_evidence.py` (two layers):
1. **Record filter** — `is_evidence_record` / `filter_records` / `lore_is_evidence`: records whose `source` is `knowledge_fallback:*`, `parametric`, `spine`, `fact_extractor`, `llm`, `gemini`, `openai`… , flagged `llm`, or a `_lore` fact `{fact, confidence}` with no URL, are not evidence. `facts_as_snippets` now sets `llm: True`.
2. **Text registry + `scrub`** — every LLM passage is registered at creation; `scrub` removes it from any evidence blob. Called at the top of `apply_grounding_gate`, `ground_tour_text`, `aboutness.build_items`, `aboutness.clean_stop`, and in the harness' `_build_evidence_by_stop`.

Sinks now filtered: `snippets_as_evidence_texts` (→ wiki sink), `_ev883` and `_evf` (first and final grounding passes), `_lc_ev` (landmark claim gate), `_stop_evidence_876` (header consistency), the thin-stop detection (LLM facts no longer count as "sourced", so a stop held up only by LLM text now escalates to real search), the signature-story page facts, the org corpus, `claim_provenance._source_is_real` (LLM record ⇒ `parametric`), the provenance pool, `work_story_research`.

**Producers found** (docstring of `llm_evidence.py`): (1) `stop_knowledge_fallback.facts_as_snippets` → `_DIRECT_SNIPPETS_PER_STOP`; (2) `poi['_lore']` from `fetch_stop_knowledge` (D545/D548); (3) `spine_generator` / `fact_extractor` fact sheets (narrator input only, never in an evidence blob); (4) `work_story_research._serper_fallback` (LLM extractor over fetched pages, cached); (5) `claim_provenance` class `parametric`; (6) venue-part chain `lore` onto `_lore` (kept: it carries sources; filtered only if marked/registered).

The fallback still **guides** the narrator (leads) — nothing about search queries changed; it is never shown to the judge/audit as support.

**Cache.** `work_story_research` now marks LLM-extracted passages (`LLM_CACHE_MARK`) when it writes a row, returns them as `llm_passages` (not `evidence_passages`), and on READ classifies legacy rows (`classify_cached_row`): a `k:` row (no QID ⇒ no Wikipedia article ⇒ only the LLM fallback can have filled it) and a QID row with < `MIN_PASSAGES` passages (the fallback fired, mix unknowable) are non-evidence; a QID row with ≥ 2 passages is verbatim Wikipedia. **Snapshot (`cloud_work_story_research_cache_20261109`): 26 rows, 16 with passages, 2 rows / 3 passages affected** (`k:9ce2…` Composition 10, 2 passages; `qid:Q1115514` The Story of Lucretia, 1 passage); 14 rows evidence. `venue_works_cache`: 27 rows, all `source=sparql`, 0 affected. `thin_verify_cache` (2 rows, LLM-verified museum works) was **not** examined or changed. Details: `cache_rows_affected.json`.

**Unanchored person.** `aboutness.unanchored_person`: a sentence whose subject is a named person with a speech/feeling verb ("Wilson expressed disbelief") and no role in the sentence, nor in any about-stop item, is a tangent. Applied in `clean_stop` (drop), the gate (UNSUPPORTED) and the audit. A role stated in the evidence ("Colonel William Wilson, a combat veteran") anchors it — the sentence is then kept.

**D769.** The hard-coded `{"city","saigon"}` is gone. `aboutness.set_location(location, evidence_by_title)` takes the tour's own location tokens ("Ho Chi Minh City, Vietnam") plus the proper nouns that run through ≥ 60 % of the tour's own stop evidence (≥ 3 stops) — that is how "Saigon" is found without naming it. `ground_tour_text` sets it. Only the generic noun "city" remains a constant. `Referent(..., location=)` accepts it explicitly.

## Offline replay (891 persisted bundle) — `offline_replay.json`
Replay runs the 891 shipped text through the REAL `apply_grounding_gate` with a judge that says SUPPORTED only when the evidence it was shown carries the sentence's distinctive words. **Caveat:** 891 persisted no per-item source, so the LLM passages are *reconstructed* from their glued-title shape (`facts_as_snippets` puts the stop title in front of each fact); `claim_provenance` confirms the Pier ones; Book Street's two Tet segments are an inference; Thi Bar's glued segments are real SERP titles and were left alone. Replay, not a measurement.
- Pier: evacuation sentence, 1945 clash sentence and the "1975 … significant" sentence dropped → 6 → 3 sentences. ✔
- Cathedral: no "1959 … basilica" sentence. ✔ 
- Book Street: no Tet execution (891's title-glue split already marks it context; the registry now also removes it). ✔
- WRM: no Wilson. ✔
- `test_replay_judge_is_never_shown_an_llm_passage` is discriminating: without the registry the judge prompt contains the LLM passages; with it, none.
- Counter `aboutness.llm_only_supported` on the 891 text finds 7 shipped sentences resting only on LLM passages (Pier 2, Book Street 1, WRM 1, Café 2, Opera 1 — the Opera one is a coverage false positive: the real article states the 1944 bombing; the LLM sentence only adds "World War II/occupied").

## Live run (1 full tour, cloud snapshot, `-p local892`, port 55992, `LOCAL_SNAPSHOT_TAG=892`, code `1e49d681`)
**Meter: $0.1010 over 92 rows (meter ok). Ledger `LOCAL-892` = $0.101 of $0.50.** No re-run. Own stack torn down (`down -v`); shared audioura-* containers untouched; run/meter logs not committed.

| Item | Result |
|---|---|
| 10/10 stops delivered, every stop ≥ 4 | PASS |
| every stop ≥ 5 | **FAIL — City Hall 4** |
| key facts k == K | **FAIL — City Hall 1/2 (missing "architect")**; all others full |
| Palace 30 April 1975 / Diệm full name / City Hall 1898+1909 / Post Office Foulhoux / Opera 1944 / no "intelligence headquarters" / ≤ 1 sensory per stop | PASS |
| no orphan openers | FAIL only on the Thi Bar closing "this route" (harness false positive on the closing paragraph, as in 889–891) |
| Pier: no evacuation, no 1945 clash | **PASS** (Pier has real material this time: 11,289 chars incl. the Vietnamese edition) |
| Cathedral: no 1959 basilica | **PASS** (the only 1959 is the Our Lady statue, 15 Feb 1959) |
| Book Street: no Tet execution | **PASS** (no Tet text in this run's evidence) |
| WRM: no Wilson | **PASS**; 5 sentences |
| audit unsupported (gpt-4.1) / mechanical off-topic | **0 / 0** |
| shipped sentences supported only by an LLM item, per stop | **0 for all 10 stops** — but see below |

**Honest limit of the live proof.** In this run `llm_leads = 0` for every stop: the D533 knowledge fallback never fired (log shows no "asking the knowledge fallback" line; `fetch_stop_knowledge` was prefetched but its results were not appended), so there was no LLM item to exclude. The Pier/Cathedral/Book Street/WRM results are therefore due to this run's evidence, and the "0 LLM-only" row is vacuous. The live run does NOT demonstrate the exclusion firing; the offline replay and the unit tests do. `claim_provenance` reports 78/78 `parametric` because that counter only knows the snippet pool, not the Wikipedia evidence (same blind spot as before; not changed here).

**Failure to own:** City Hall dropped to 4 sentences with no architect (Fernand Gardè) although the evidence has it (891 had City Hall ≥ 5). No LLM item was involved; I did not find the cause and did not re-run. Possible: narrator variance, or the D534 repeat-regeneration (log: "Stop 7 repeats 1 thing(s)"). Unproven.

**Observation, not fixed:** the Pier closes on "The name Bạch Đằng itself recalls the historic river where Vietnamese forces won legendary battles" — supported (a snippet says it) but a name-etymology aside rather than the pier's history.

## Tests
`tests/test_local892_no_llm_evidence.py` (23): source classifier, `facts_as_snippets` flags/registers, provenance pool, bundle with only a `knowledge_fallback` item ⇒ UNSUPPORTED (gate, no-evidence path, audit), control (same words from a real source stay), cache classification + marking, unanchored person (positive/negative, role from evidence), D769 (no hard-coded token, regional tokens), the four 891 replays + the discriminating judge-prompt test + the LLM-only counter. Suite: `pytest tests/test_local87*.py tests/test_local88[0-9]*.py tests/test_local890_coverage_own_article.py tests/test_local891_aboutness.py tests/test_local892_no_llm_evidence.py tests/test_local543_claim_provenance.py test_local840_work_story_research.py` → **711 passed, 4 skipped**. `run_cloud_parity_proof.py --selfcheck` PASS.

## Not done / risks
- Narrator-facing paths still receive LLM leads by design; the gate/audit now drop what only they support, which can shorten a stop that leaned on them (not seen in the live run because none existed).
- `thin_verify_cache` rows not audited. Other readers of `_DIRECT_SNIPPETS_PER_STOP` (museum paths) are covered only by the registry scrub, not by an explicit filter.
- Registry is process-global (one tour per process); a multi-tour worker would carry earlier registrations (harmless: only removes text that was LLM-generated).
- The D769 regional-token heuristic needs ≥ 3 stops with evidence; below that only the location string is used.

## Artifacts (`submission_artifacts/local892/`)
`saigon_warm.txt`, `saigon_warm_evidence.json` (claim provenance), `saigon_warm_evidence_bundle.json` (real per-stop bundles + items), `saigon_warm_audit.json`, `saigon_warm_llm_only_support.json`, `offline_replay.json`, `cache_rows_affected.json`. `docker-compose.local892-proof.yml` is the own proof stack.
