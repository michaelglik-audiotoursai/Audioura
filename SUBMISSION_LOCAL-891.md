# SUBMISSION LOCAL-891 — "supported" must also mean "about THIS stop"

**Status: the aboutness rule is built, tested offline and ran live once. The live run removed the Thích Quảng Đức passage, kept Opera 1944, removed the City Hall preview and reached WRM = 5. It did NOT meet the goal "no off-topic event in any stop": Book Street still carried the Tet-Offensive execution. The cause was found in the persisted bundle and fixed offline AFTER the run; the fix is NOT proven live (one live run only, no re-run).** Branch `LOCAL-891-aboutness`, base `097ba6fd`.

## What changed (generic, no venue named in code)
New module `aboutness.py`, wired into the gate, the audit, the narrator input and the coverage pass.

1. **Evidence items carry `about_stop`.** The stop's evidence is split into items (`id`, `text`, `about_stop`, `kind`, `source`, `why`).
   - `about_stop = true` for: every item of the stop's own article (890 `own_article`); a stop-language edition whose lead SUBJECT is the stop (the Cathedral's own article in this run was the Vietnamese one); any other passage or snippet that names the stop (name, alias, article title, the kind noun "the cathedral" when the title has no distinctive token, a street number from the title "at 42 …") with the weight of a subject (first sentence, or ≥ 2 mentions); a geo-tag ≤ 150 m on a passage that names the stop (`geo` argument, not fed by the live pipeline yet).
   - Everything else is CONTEXT (`about_stop = false`): city, neighbour, person. A neighbour's article whose lead only mentions the stop later ("… surrounds the Cathedral") is not the stop's own article.
   - A scraped snippet with the page title glued to its first words ("Book Street Associated Press photographer …") does not count as naming the stop.
   - Undecidable (no article in the bundle and no item names the stop, or a bare fact whose subject is a generic noun phrase) is NOT called context; the judge's verdict stands.
2. **Gate** (`strict_grounding_gate.classify_sentences/apply_grounding_gate/_second_look`). The request lists every item with its id and `about_stop=true/false`; the judge returns `source` (the item id) per sentence. `aboutness.assess` checks the id by token overlap, re-sources to an about-stop item when one carries the sentence as well, and otherwise marks a context-only sentence `UNSUPPORTED(off-topic)`. Exception: the sentence itself ties the event to a different NAMED place ("a few blocks away, at …", "just steps away, near …"), at most ONE per stop. Event/person claims the old factual cue missed ("Thích Quảng Đức's heart was seized …") are now judged as claims.
3. **Audit** (`run_cloud_parity_proof_884.independent_audit`). The gpt-4.1 auditor gets the same flagged items and the same rule in its prompt, and the mechanical half (`aboutness.audit_tour`, same `assess`, same items) adds its findings to `unsupported`. The harness now persists the real per-stop bundle (`saigon_warm_evidence_bundle.json`); the 890 `saigon_warm_evidence.json` only held claim provenance (`landmarks` = {}), so **the 890 bundles themselves could not be replayed** (see below).
4. **Narrator input** (`aboutness.narrator_items`, wired at the 872C evidence feed). Default `NARRATOR_CONTEXT_MODE=drop`: context paragraphs never reach the narrator; `labelled` appends them as "CITY BACKGROUND — do not present as this stop's history". Offline measurement on the recorded Cathedral bundle: both modes pass the same 9,120 of 9,256 chars and the labelled block was empty, because that bundle holds no city-event passage. **I could not measure which mode narrates better** (needs paid runs); `drop` is the default because nothing of the context can then be misused.
5. **Guards after the gate** (`aboutness.clean_stop`, run inside `finalize_stop`, skipped for a no-evidence stop): empty filler ("making it easy to find", "As you look up, you can see the multiple floors"); tangent (subject neither the stop nor its parts, people or events, and not carried by the stop's own text); near-repeat inside a stop (same host/damage/build/rename fact about the same named entity, or ≥ 2 shared named entities with overlapping content; the dated sentence stays); a raw lead/infobox-style sentence at the end; "It is …" as the first sentence gets the stop name.
6. **Thin stop with a rich own article**: floor is 5 sentences when the stop has an own article; the refill reads the own article's lead + 885 `select_passages`, richest first (`refill_facts`), never a raw lead sentence. The 888 shortfall rebuild is fed the same facts first.

## Offline replay (required)
`tests/test_local891_aboutness.py`, 32 tests. Generic fixtures ("Some Church" with a city-event passage, "Some Street", "Some Post Office", "Some Hall") plus replays on the LEAD 890 text. **The 890 bundles were not persisted, so the replay uses stand-ins**: the recorded Wikipedia text (`local889_recorded.json`, `local890_recorded.json`) plus two clearly marked SYNTHETIC passages (the Buddhist-crisis passage reconstructed from the LEAD's quoted sentences, a stamp article). It is a replay, not a measurement.
- Cathedral: the immolation sentences are dropped (≥ 3 off-topic), 1880, Bourard, the Pigneau statue and the 1959 Our Lady statue stay when the bundle has them (tested with and without an own article).
- Post Office: no stamp/stork sentence, Foulhoux and 1886–1891 stay, no antecedent-less "It is often …".
- WRM: 4 → ≥ 5 sentences, no raw "… is a war museum at 28 …" ending (the recorded article is thin, so the ≥ 5 test uses 4 SYNTHETIC extra passages for the Agent-Orange jars / guillotine / aircraft yard / photographers the LEAD described).
- Opera: "People's Assembly" once, 1944 kept. City Hall: no preview.
- Real-bundle regression tests from this live run (`saigon_warm_evidence_bundle.json`): the title-glued Tet segment is context, the Vietnamese Cathedral edition is about the stop, the Café is named by its street number.
- Suite: `pytest tests/test_local87*.py tests/test_local88[0-9]*.py tests/test_local890_coverage_own_article.py tests/test_local891_aboutness.py` → **651 passed, 4 skipped**. (`test_local88_tour_pollution.py` needs the dev DB and fails the same 4 tests on the untouched base.) `run_cloud_parity_proof.py --selfcheck` PASS.

## Live run (1 full tour, cloud snapshot, `-p local891`, port 55991, `LOCAL_SNAPSHOT_TAG=891`)
Code at run time: commit `934583e1` (on `2da711e1`); the fixes listed under "Fixed after the run" were NOT in the run. **Meter: $0.0700 over 61 rows (meter ok). Ledger `LOCAL-891` = $0.07 of $0.50.** No re-run. Own stack torn down (`down -v`); shared audioura-* containers untouched.

| 890 checklist item | Result |
|---|---|
| 10/10 stops, every stop ≥ 4 | PASS |
| every stop ≥ 5 | **FAIL** (Cathedral 4, Post Office 4; WRM 5, Café 6) |
| Palace 30 April 1975 | PASS |
| City Hall 1898 and 1909 | PASS |
| no "intelligence headquarters" | PASS |
| Opera 1944 | **PASS (live)** — "suffered damage from Allied bombing in 1944" |
| no next-stop preview | PASS — City Hall ends on its own history |
| key facts k == K | PASS (all 0/0 or full) |
| ≤ 1 sensory per stop | PASS |
| no orphan openers | FAIL only on the Thi Bar closing "this route" (harness false positive on the closing paragraph, as in 889/890) |
| WRM ≥ 5 sentences | **PASS (5)**, no raw lead ending |
| People's Assembly once | PASS |
| no Thích Quảng Đức / immolation | **PASS** (Cathedral is 4 sentences: Colombert 1877, completed 1880, towers/bells, 1959 basilica) |
| no stamp tangent | PASS (post office text has Foulhoux/Eiffel, the maps, the letter-writer) |
| **no off-topic event in any stop** | **FAIL — Book Street**: "Just steps away from here, on 1 February 1968, during the Tet Offensive, … executed a handcuffed Viet Cong prisoner …" |
| audit 0 unsupported under the aboutness rule | **FAIL (1)**: the gpt-4.1 audit returned 0, the mechanical half added `Cathedral: "The church was completed in 1880."` (a FALSE positive, see below). It did NOT flag the Tet sentence. |

### Sentences the aboutness rule dropped live
**None.** The log has no `[LOCAL-891] off-topic` line. The other 891 guards dropped three sentences: Palace "Inside, you can find a well-preserved 1960s retro-modern interior …" (tangent, **wrong**: a legitimate sentence), Pier "The surface beneath your feet is smooth concrete …" (tangent, **wrong**), Pier "As North Vietnamese forces advanced on Saigon, the pier became a crucial evacuation point …" (repeat; reasonable but triggered by the shared entities "North Vietnamese"/"South Vietnamese").

### Why the live aboutness rule missed the Tet sentence and flagged the 1880 one (found in the persisted bundle)
1. **Book Street**: the snippet bundle is ONE long line, and the Tet text was glued to it as "Book Street On February 1, 1968 …". The 600-char item packed that segment with real Book Street sentences, so the whole item was `about_stop`. **Fixed after the run:** title-glued snippets are split into segments and judged on their own, a glued title is not a mention. On the real bundle the segment is `about_stop=false` and the sentence is off-topic.
2. **Cathedral 1880**: the stop's own article in this run is the VIETNAMESE edition (no English one), and its body and infobox ("architect: Jules Bourard; year completed: 1880") had been marked context because they do not contain the word "Cathedral". **Fixed after the run:** an article whose lead SUBJECT names the stop is the stop's article in any language.
3. **Café** (found while checking): its two snippets are named by the address ("the building at 42 Nguyễn Huệ"); a street number in the title now counts as naming the stop.
4. The tangent guard also now requires that the stop's own text does not carry the sentence and skips second-person sentences.

After these fixes the mechanical aboutness audit over the live text and the live bundle (`saigon_warm_aboutness_audit_postfix.json`) flags exactly one sentence: the Book Street Tet sentence. **This is an offline re-audit of a text produced by the old code, not a live measurement.**

### Not proven / honest limits
- The Cathedral live text is thin (4 sentences) and contains none of Bourard, Pigneau or the 1959 statue: its own article is Vietnamese, the key-fact patterns are English-only (K = 0), and the narrator wrote from the square article. The Vietnamese article does hold Bourard/1880/the Our Lady statue; nothing here injects them. Out of scope for this task, but it is the reason the Cathedral is not richer.
- "Thin" Café and Post Office: Post Office is 4 (harness wants 5) and its last sentence is a letter-writer anecdote.
- Whether `drop` or `labelled` narrates better is unmeasured.
- The geo ≤ 150 m path is implemented and tested but the pipeline does not yet pass `geo`.
- The Pier text still opens "Once, the French managed the pier under the Compagnies des Messageries fluviales" (awkward, grounded).
- The repeat guard can over-trigger on shared demonyms ("North Vietnamese"); the Pier drop above is that case.

## Artifacts (`submission_artifacts/local891/`)
`saigon_warm.txt`, `saigon_warm_audit.json` (gpt-4.1 + mechanical, items per stop), `saigon_warm_evidence.json` (the generator's claim provenance), `saigon_warm_evidence_bundle.json` (the REAL per-stop bundles with flagged items), `saigon_warm_aboutness_audit_postfix.json` (offline post-fix re-audit). Run and meter logs (`_local891_meterlogs/`) are not committed. `docker-compose.local891-proof.yml` is the own proof stack (project `local891`, port 55991).
