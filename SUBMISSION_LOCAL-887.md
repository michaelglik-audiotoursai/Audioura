# SUBMISSION LOCAL-887: the gate drops true facts; two stops have no evidence

**Result: WARM FAIL (live run). Audit: 0 unsupported. One full-tour live run, made before the root cause was found. The root-cause fix is proven offline (recorded replay) and with one paid per-stop gate call. It is NOT proven by a full-tour run. Unproven, handing to LEAD.**

## Spend (ledger `LOCAL-887`, default dir, `AUDIOURA_TASK_BUDGET_DIR` unset)
- Before the live run: $0.000.
- Full-tour live run (`run_cloud_parity_proof.py --snapshot ~/Audioura/cloud_cache_snapshot` + 886 audit): **$0.0740** metered, recorded by the harness.
- One per-stop gate call (City Hall, fixed evidence, gpt-4.1-mini): **$0.0010**, recorded.
- **Ledger total: $0.075019 of $0.60.** No second full-tour run (cap = 1).
- One launch attempt failed before any paid call (`timeout` not installed; then the DB port was not up). $0 was metered and the ledger stayed at 0.0.

## Root cause: City Hall (Do §1)
The gate was **right**. The "16,798-char City Hall bundle" was the **biography of Ho Chi Minh (the person)**, not the building.
- Recorded from the 887 warm state (`landmark_wiki_cache`, rules `local885-fulltext`): the match name `Trụ sở Ủy ban Nhân dân Thành phố Hồ Chí Minh` was accepted as en "Ho Chi Minh" (no coordinate, 20,000-char full text). The vi edition "Hồ Chí Minh" was accepted as a *trusted* langlink. Neither contains 1898, 1909 or Gardè (`tests/fixtures/local887_recorded.json`, `test_recorded_887_article_was_the_biography`).
- Why it passed: the tour location is "Saigon centre landmarks", so "chi"/"minh" are not treated as city words. The strict distinctive-token test passed on them, even though the title covers only 2 of the stop's 8 name tokens (an eponym fragment).
- This also explains the 886 "Ho Chi Minh biography refill". The 6 KB truncation was a real but secondary issue.

Fixes (generic, no venue or date named):
1. `title_covers_name()`: a coordinate-less page whose title's distinctive tokens are a strict subset covering under half of the stop's tokens is rejected. This applies in `_pick`, in cache re-validation, and before a langlink is trusted in `_default_fetch`.
2. `geo_fallback_article()`: when no name search accepts an article in a language, the free MediaWiki geosearch within 150 m of the pin is used. A hit must share a distinctive token with the stop name or an alias, carry its own coordinate, and pass `_pick`. It is cached under `geo:<names>`.
   - City Hall now gets en "Ho Chi Minh City Hall" (18 m) and vi "Trụ sở Ủy ban nhân dân Thành phố Hồ Chí Minh": 1898 start, 1908 completion, 1909 opening, architect Fernand Gardè (Wikipedia's spelling), "Hôtel de ville".
3. Gate evidence window (`focus_evidence`): the lead is kept, then the window is filled with the chunks sharing the most year/name tokens with the sentences, instead of the first 6,000 chars.
   - Second look: before an UNSUPPORTED sentence is dropped, chunks the first window left out are shown to the judge once (at most one extra call).

Proof that the gate keeps the sentence: in a paid per-stop gate call on the fixed evidence, gpt-4.1-mini labelled 4 and **kept 4/4** (including "between 1898 and 1909", "L'hôtel de ville" and "Fernand Gardè"). The sentences are reconstructed, because the live log truncates dropped sentences at 80 chars.

## Palace signature event (Do §2)
- `event_sentences()` / `_famous_event_score()`: generic cues (tank, crashed/smashed through, stormed, fall of, coup, bombed, captured, surrender, …, plus vi equivalents). A cue sharing a sentence with a full date or year raises the score.
- `select_passages` uses this score. The signature prompt now lists up to 3 such sentences from the WHOLE evidence ahead of the evidence, and keeps them even when the evidence exceeds `MAX_INPUT_CHARS`.
- Generic test: the fixture "Harbour Fort" (not the Palace) has its event as the last of 41 paragraphs (12 March 1848). It is ranked first, kept by a 700-char passage cap, and present in the signature prompt.
- Note: the Palace's own en lead already contains the 30 April 1975 tank.

## Local-language evidence (Do §3)
- `escalate_local_language` also tries the name without its "(qualifier)" and the local name, geo-gated on the pin.
- `thin_stop_search` returns `local_wikipedia_items`. When a stop has no en article, the generator uses them as `poi['_wiki_evidence']`, feeds them to the narrator (`narrator_block` renders a local item in full when there is no en item) and records them in the gate sink. The passage stays in the original language, as in 875/879.
- The geo fallback above covers the 872C path that every landmark stop takes. The Pier now gets en "Bạch Đằng Quay" (11 m) and vi "Bến Bạch Đằng".
- **Correction to the task:** "Đường sách Nguyễn Văn Bình" does **not** exist on vi Wikipedia (API returns `missing`). No en/vi article for Book Street was found by title, search or geosearch within 150 m. Book Street's evidence comes from the 873 thin-stop search. In this run that was 1,562 chars, and 5/5 sentences were kept.

## Departure cue (Do §4)
- `_DEPARTURE_CUE_RE`: "Parties leaving from here…", "Boats depart from this pier…" and "Tours start at this pier…" are FACTUAL. Pure navigation ("Follow the path from here and head north") stays exempt.
- Also added plurals and defeat/invasion verbs to the event cue: the live Pier text kept "famous for legendary battles where Vietnamese forces defeated invaders" because only the singular "battle" matched.

## Tests (offline)
- `tests/test_local887_gate_keeps_supported.py` (25 tests): recorded City Hall replay, Pier geo fallback, eponym coverage, famous-event fixture, vi-article use, departure cue, plural cue.
- 882–886 + 87x + 86x suites: **734 passed, 4 skipped**.
- `tests/test_local88_tour_pollution.py` fails 4 tests on base `ab1f19db` too; these are not related to this task.

## Live run (one run, cloud snapshot, project `-p local887`, port 55987; before the root-cause fix)
Code at run time: commit with the focus window, second look, famous-event ranking, local-language thin path and departure cue. It did **not** yet have the eponym rejection or the geo fallback.

| # | Stop | evidence_chars | 1st pass labelled | kept/contr/unsup (1st) | final labelled | kept/contr/unsup (final) | content sentences |
|---|---|---|---|---|---|---|---|
| 1 | Cathedral | 8765 | 9 | 3 / 1 / 5 | 3 | 2 / 0 / 1 | 4 |
| 2 | Post Office | 5662 | 5 | 5 / 0 / 0 | 5 | 5 / 0 / 0 | 6 |
| 3 | Book Street | **1562** | 5 | 5 / 0 / 0 | 5 | 5 / 0 / 0 | 6 |
| 4 | Independence Palace | 3394 | 7 | 5 / 0 / 2 | 5 | 5 / 0 / 0 | 8 |
| 5 | War Remnants Museum | 4879 | 4 | 1 / 0 / 3 | 1 | 0 / 0 / 1 | 2 |
| 6 | Opera House | 11318 | 4 | 3 / 0 / 1 | 3 | 3 / 0 / 0 | 5 |
| 7 | City Hall | 16820 (Ho Chi Minh biography) | 5 | **0** / 0 / **5** | 0 | - | 1 |
| 8 | Café Apartments 42 | none | 4 (no evidence) | 0 / 0 / 4 | 0 | - | 1 (disclosed) |
| 9 | Bạch Đằng Pier | **none** | 4 (no evidence) | 0 / 0 / 4 | 0 | - | 2 (disclosed) |
| 10 | Thi Bar | 1104 | 1 | 1 / 0 / 0 | 1 | 1 / 0 / 0 | 8 |

### PASS checklist
| Item | Result | Evidence |
|---|---|---|
| audit 0 unsupported | **PASS** | `"unsupported": []` (gpt-4.1, 16,463 prompt tokens) |
| City Hall has Gardès / 1898–1909 | **FAIL** (live) / fixed offline | Live text has 1 sentence. The bundle was the biography (root cause above). Offline + paid gate call on the fixed evidence: 4/4 kept |
| Palace has 30 April 1975 tank | **PASS** | "best known for the dramatic end of the Vietnam War here on 30 April 1975. The tank's path through the gate…" |
| Book Street evidence chars > 0 | **PASS** | 1,562 |
| Pier evidence chars > 0 | **FAIL** (live) / fixed offline | No article accepted in the run. The geo fallback (committed after the run) finds en "Bạch Đằng Quay" + vi "Bến Bạch Đằng" at 11 m |
| 10/10 stops | PASS | harness |
| every stop ≥ 5 / ≥ 4 content sentences | FAIL | Cathedral 4, War Remnants 2, City Hall 1, Café 42 1, Pier 2 |
| Post Office Foulhoux / Eiffel-as-myth | FAIL | harness found neither credit in the final text |
| No banned strings, Diệm in full, Opera not Ferret-alone, Stop 1 directions, labelled>0 or disclosed | PASS | harness |
| No Pier evacuation / Cu Chi tunnels sentence | PASS | no "evacuat", no "tunnel" in the final text |

## Caveats for LEAD
- The full-tour run measured the pre-root-cause code, so the City Hall and Pier fixes are proven only offline and by one per-stop gate call. I did not re-run, per the task's cap. A second full-tour run is needed to prove them end to end.
- The Palace text has an orphan "These marks are a physical trace…" sentence (no antecedent). I did not touch it.
- War Remnants Museum lost 3 of 4 factual sentences (photo by Associated Press, Haeberle). That was not investigated.
- `run_cloud_parity_proof.py --snapshot` is now parametrised by `LOCAL_SNAPSHOT_TAG` (default 887: ledger `LOCAL-887`, port 55987, `submission_artifacts/local887/`). The 886 test pins tag 886. The harness log prefix still reads `[LOCAL-886]`.

## Artifacts
`submission_artifacts/local887/saigon_warm.txt`, `saigon_warm_audit.json`, `tests/fixtures/local887_recorded.json`. Run and meter logs are not committed.
