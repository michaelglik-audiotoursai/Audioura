# SUBMISSION — LOCAL-888 coherent refill (branch `LOCAL-888-coherent-refill`, base subscribed 81b99b7e)

## Root causes
1. **873C "0 rebuilt".** The gate's shortfall rebuild (`ground_tour_text` -> `rebuild_fn(title, facts)`) was given only the *thin-stop* fact list. Most stops have none (their evidence is an article or snippets), so `narrate_stop_body` got `[]` and returned None silently. Also: it demanded 5 traceable sentences, and facts that the post-narration rebuild escalated *itself* (Book Street) lived only in a local dict, so the gate saw no evidence for that stop.
   Fix: the rebuild is fed `evidence_fact_sentences(evidence)` when facts are fewer than 6; it tries 5 sentences, then 4; escalated facts are written to the process-global sink the gate merges.
2. **Café regression (887).** The narrator was fed the stop's snippets, but they sit in the job-scoped `_DIRECT_SNIPPETS_PER_STOP`, which the main-thread gate cannot see. A stop with rich retrieval but no thin-fact or Wikipedia entry (Café has no Wikipedia article: the cloud cache holds `found=f` rows for it) looked like a no-evidence stop and lost its history. In 886 it had 756 chars through the thin-fact path; 887 no longer escalated it. It was not `title_covers_name` (that returns True when the stop has no distinctive token).
   Fix: the worker records the stop's snippets into the per-job sink the gate (and the audit) merge.
3. **Orphan openers / bare names / missing event.** New `stop_coherence.py` + a post-gate pass in `ground_tour_text(coherence=True)`: dangling demonstrative/lead-in openers, bare surnames whose full name is in the evidence, and a dated defining event in the evidence lead (full date + event verb) that the kept text does not state. One mini call re-narrates from KEPT sentences + evidence (chronological, full names first, required event with date); the result is gated again; the evidence's own event sentence is inserted if still missing; a still-dangling opener is dropped only when >= 4 sentences remain.
4. **No-evidence stops** get the disclosure plus non-factual sensory sentences up to 4 (free, deterministic).
5. **Meter.** `sitecustomize` imports `paid_api_meter` at interpreter start, freezing `LOG=/meterlogs/...`; the harness's later `setdefault(PAID_API_LOG)` never reached it, so the run was metered into the void ("$0.0000"). New `meter_guard.py`: `repoint_meter_log` re-points the live module; `check_meter` compares rows captured with the gate/narrate/audit calls the run's own log proves; fewer rows => `METER FAILURE`, rc 3, and the ledger gets `max(metered, estimate, $0.08)`.
6. **Harness false negative.** "designed not by Eiffel but by Alfred Foulhoux" is now a correction (`_EIFFEL_CORRECTION_RE`).

## Tests (offline)
`tests/test_local888_coherent_refill.py`, 27 tests (non-Saigon fixtures): dangling openers, bare surnames, dated event incl. allusion vs plain, evidence-fed refill, coherence re-narration, deterministic event insertion, clean stop makes no extra call, no-evidence body >= 4, snippets reach the gate, escalated facts exposed, meter guard (0 rows never $0, partial capture, re-pointing), Eiffel check. 873B/873C/883-887 suites: 144 passed.

## Live run (1 full-tour run, cloud snapshot, `-p local888`, port 55988, tag 888)
Run **metered $0.3696 over 370 rows** (meter ok: 370 >= 30 logged calls); ledger `LOCAL-888` = $0.369576 of $0.60. No re-run. (Earlier harness runs reported ~$0.07; this is the first run where the meter was actually re-pointed, so the true cost per full run is about 5x what was recorded before.)

| # | Stop | evidence_chars | final gate labelled / kept | content sentences |
|---|---|---|---|---|
| 1 | Cathedral | 9744 | 4 / 3 | 4 |
| 2 | Post Office | 6109 | 4 / 4 | 8 |
| 3 | Book Street | 1632 | 4 / 4 | 6 |
| 4 | Independence Palace | 4216 | 4 / 4 | 5 |
| 5 | War Remnants Museum | 5033 | 7 / 7 | 7 |
| 6 | Opera House | 11596 | 6 / 4 | 5 |
| 7 | City Hall | 11799 | 2 / 2 | 5 |
| 8 | Café Apartments 42 | **299** (was none) | 2 / 2 | 4 |
| 9 | Bạch Đằng Pier | 10410 | 3 / 3 | 9 |
| 10 | Thi Bar | 1413 | 1 / 1 | 9 |

### Checklist
| Item | Result | Evidence |
|---|---|---|
| every stop >= 4 content sentences | **PASS** | table above (min 4) |
| every stop >= 5 (old 886 bar) | FAIL | Cathedral 4, Café 4 |
| Palace states 30 April 1975 plainly | **PASS** | "it was also the site of the fall of Saigon on 30 April 1975 that ended the Vietnam War, when a ... tank crashed through its gates." |
| Café evidence > 0 | **PASS** | 299 chars (was missing) |
| Diệm named in full; City Hall 1898-1909 Hôtel de Ville; Post Office Foulhoux; Opera not Ferret alone; Stop 1 directions | PASS | harness |
| no orphan openers | harness FAIL, **false positive** | sole hit is the tour-closing line "this route is the one you chose", which the closing paragraph places under Thi Bar; no stop body has one. Not yet exempted in the check. |
| audit 0 unsupported | **FAIL** | gpt-4.1 audit: 3 unsupported, all Cathedral (twin-tower brick style, "Paris Commune Square" renames, the Pigneau de Béhaine statue). They come from the Cathedral re-narration, which the mini gate judged supported and the stronger auditor did not. |
| no banned strings | FAIL | "established in the early 19th century" (Pier); not looked into |
| 873C refill ran | PASS | 2 stops narrated from facts (Thi Bar, Book Street); coherence pass acted on Cathedral, Book Street, Palace, WRM, City Hall (issues 3->0, 1->0 ...) |
| meter total | $0.3696 (370 rows) | see above |

## Not proven / for LEAD
- Audit is **not** clean: the coherence re-narration for the Cathedral produced sentences the gpt-4.1 auditor rejects. Suggested next step: gate the re-narration with the same evidence window the audit sees, or re-narrate only from KEPT sentences (no new evidence) when the stop is sourced.
- Café has only 4 sentences: the 873C narration kept 4 traceable (< 5) and fell back; evidence is just 299 chars.
- The 855B log says `'City Hall' ~9846483 m from pin` for every stop (the pin lookup for the landmark is wrong); I did not touch it.
- The harness orphan check should skip the tour-closing paragraph.

Artifacts: `submission_artifacts/local888/saigon_warm.txt`, `saigon_warm_audit.json`. Run and meter logs (`_local888_meterlogs/`) are git-ignored and not committed.
