# SUBMISSION LOCAL-893 — D762 /preview-stops timeout (wave-43 root cause)

Branch `LOCAL-893-preview-timeout`, based on `subscribed` @ 5adabfcd
(`git merge-base --is-ancestor 5adabfcd HEAD` → 0).

## Root cause (confirmed)
The orchestrator's D762 call to the generator's `/preview-stops` had `timeout=20`. LOCAL-882
added a canonical-venue lookup per stop (a WDQS "around" query, sometimes Places), run
**sequentially after each pin**. On the cloud snapshot I measured the old code path at
**24.5 s** for Michael's 10 raw strings: pins 10.9 s, canonical 13.6 s (Café 12.3 s, Post
Office 6.7 s). That ran past the 20 s timeout, so the orchestrator fell back silently and the
generator got RAW strings (`name_only` ×10). It also showed a second bug: the parser did not
treat `_` as a street qualifier. So `Opera House_Đồng Khởi` was looked up whole and Serper
returned **"Dong Khoi Street"** (8.3 s, 850 m off).

## Changes
1. **Orchestrator** (`tour_orchestrator_service._d762_gen_preview`):
   - read timeout of **60 s** (`D762_PREVIEW_TIMEOUT_S`), **one retry on timeout** (no retry on an HTTP error);
   - on failure it logs `ERROR [D762] PREVIEW FAILED — generating from raw strings (...)` to stdout and `logging.error`;
   - logs `[D762] /preview-stops OK in Xs (try n)` on success.
2. **Graceful degradation:**
   - `itinerary_import.resolve_user_stop_pins` now always returns cleaned titles when no pin resolved (`clean_raw_stop_titles`, which is the preview's own parser, offline);
   - the generator applies the same cleaning to `forced_stops` (`[LOCAL-893] raw stop title … -> …`), so a direct or raw caller never gets `_street`, `& street` or `(…)` titles;
   - when the preview fails, pins fall to the generator's existing LOCAL-859 name lookup in the city box, using the cleaned name.
3. **Fast /preview-stops** (`itinerary_import.preview_stops`):
   - each stop's canonical lookup goes to a bounded pool (`PREVIEW_CANON_WORKERS`=5) as soon as its pin resolves, so it overlaps the remaining sequential pin phase;
   - one shared deadline (`PREVIEW_CANON_DEADLINE_S`=6.5 s) plus a minimum grace per lookup (`PREVIEW_CANON_MIN_GRACE_S`=2 s). A lookup past both is **abandoned loudly** and the stop keeps the pin resolver's name. The lookup keeps running and warms caches;
   - per-stop timing (`pin Xs, canonical Ys`) and a total `[LOCAL-893] preview timing:` line;
   - the parser treats `A_B` (outside a protected URL) like `A/B`, giving title `Opera House` and alt name `Đồng Khởi`.
4. **Real-path parity harness:**
   - `run_local893_real_path.py` plus `docker-compose.local893-proof.yml`: own project `-p local893`, ports 25000/25002/25003, DB 55993, never audioura-*;
   - it POSTs `/generate-complete-tour` with the 10 RAW strings to our own orchestrator, then asserts on the orchestrator log, the generator log and the stored tour;
   - generator hook `EVIDENCE_BUNDLE_DUMP` (off by default) writes the per-stop evidence the grounding gate saw, for the audit.
5. **Tests** (`tests/test_local893_preview_timeout.py`, 15, offline):
   - concurrency and order;
   - 60 s plus one retry; ERROR and no silent fallback; no retry on 500;
   - a **slow preview (past the old 20 s)** through the real `/generate-complete-tour` intake: `pins resolved 10/10`, all 10 pins, clean titles;
   - a **dead preview**: clean titles, ERROR line;
   - cleaner edge cases; underscore parsing; deadline abandonment; last-stop grace (also checks that grace 0 reproduces the bug);
   - the harness's own log assertions.
   - Related suites: 138 passed. The broad `test_local85*–89*` sweep has 6 failures (`test_local85_venue_coherence`, `test_local88_tour_pollution`). They fail the same way on base 5adabfcd, so they are not from this branch.

## Live run (1 full tour, real orchestrator path, cloud cache snapshot loaded into :55993)
| Check | Result |
|---|---|
| `/preview-stops` timing, orchestrator's own call | **6.5 s** (`[D762] /preview-stops OK in 6.5s (try 1)`) |
| `/preview-stops` timing, harness profile before the tour | 4.6 s and 4.5 s in two pre-run profiles; **14.6 s** in the run's own profile. In that one the *pin* phase took 14.58 s (sequential Nominatim/Serper latency) and the canonical tail was 0.05 s. See risk below. |
| `pins resolved 10/10` | **PASS** (`[D762] user-stop pins resolved 10/10`) |
| no `name_only` fallback | **PASS** (0 lines) |
| clean titles | **PASS**: Cathedral, Post Office, Book Street, Independence Palace, War Remnants Museum, Opera House, City Hall, Café Apartments 42, Bạch Đằng Pier, Thi Bar |
| Opera pin within 50 m of 10.776390,106.702780 | **PASS, 0 m** (landmark_table; was "Dong Khoi Street") |
| Café Coordinates present | **PASS**: 10.774089, 106.704056 (evidence 1527 chars) |
| 10/10 stops, ≥ 4 content sentences each | PASS |
| City Hall 1898 **and** 1909, no hotel / Gia Long / 1945 | **FAIL**: has 1909, **no 1898**; no hotel, Gia Long or 1945; the wave-43 "1901" is gone |
| Palace "30 April 1975" + tank | PASS |
| Eiffel only as myth, Foulhoux credited | **FAIL**: Post Office has no architect (no Eiffel either) |
| no Pier evacuation / War Remnants "intelligence headquarters" | PASS / PASS |
| no Tet execution / Thích Quảng Đức at Book St / Cathedral | PASS |
| Thi Bar at 224 Đề Thám, "Gay bar" | PASS |
| `[LOCAL-883] grounding gate: 10 stop(s)`, `[LOCAL-889] coverage total` | PASS |
| ≥ 5 content sentences (stricter wave-40 bar) | FAIL: Cathedral, Post Office, Café have 4 |
| orphan openers | FAIL: Thi Bar ("this route") |
| independent gpt-4.1 audit, 0 unsupported | **NOT RUN, unproven.** At the end of the tour the ledger was $0.477 of $0.50, and the audit (~$0.06) would have gone over the cap, so I stopped the harness before it. |
| meter | this run **$0.4193**; task ledger cumulative **$0.477256 / $0.50** (two `/preview-stops` profiles $0.030, an aborted `--run` that got a 429 for an unseeded user $0.028, the tour $0.419) |

Not re-run. The tour text is in `submission_artifacts/local893/saigon_real_path.txt`, the
checks in `offline_checks.txt`, and the log excerpts in `log_excerpts.json`.

## Item 4: City Hall "1898" and the Post Office architect (traced; not caused by the raw-string path)
- **City Hall "1901"** was a raw-string artefact. It is gone on the clean path.
- **City Hall 1898:** the evidence has it (4 hits; "built … from 1898 to 1908"). The narrated sentence "The grand building before you was completed in 1908 after a decade of construction that began in 1898…" was removed twice:
  - by `[LOCAL-652] REMOVED foreign work/artist sentence stop='City Hall' entities=['On April']`. "On April" is a false entity from a neighbouring sentence, and the gate removed the whole span;
  - then, in the final pass, by `[LOCAL-890] final dropped an orphan opener in 'City Hall'`, which treated "The grand building before you…" as a dangling opener.
  - `[LOCAL-889] coverage City Hall: 1/2 … still missing years` shows the coverage step did not re-inject the 1898 fact. Fix pointers: LOCAL-652's entity extractor (a capitalised sentence-initial "On April" is not an entity), and LOCAL-890's orphan rule (a sentence naming its own subject is not an orphan).
- **Post Office architect:** the evidence has "Auguste Henri Vildieu, Foulhoux (Current building)" and "Gustave Eiffel (Former building)" in infobox form. The narrator wrote "Contrary to popular belief, the architect was Alfred Foulhoux, not Gustave Eiffel…". Then:
  - `[LOCAL-652] REMOVED foreign work/artist sentence stop='Post Office' entities=['Gustave Eiffel', 'Governor General']` and `[LOCAL-472] UNGROUNDED entity … 'Gustave Eiffel'` removed it. **The myth correction is what kills the Foulhoux credit**;
  - `[LOCAL-889] coverage Post Office: 2/2` lists only years: `key_fact_coverage` does not extract an architect from the infobox-style "architect: … (Current building)" text, so nothing re-injects it.
  - Fix pointers: exempt a sentence that negates or corrects the entity (`_EIFFEL_CORRECTION_RE` style) from LOCAL-652/472, and parse the infobox `architect:` field in `key_fact_coverage`.
- I did **not** change these gates in this task. It is a separate fix and there was no budget left to prove it live.

## Risk / not verified
- The pin phase is still sequential: a shared Serper cap and the 1 req/s Nominatim limiter. On a slow network it alone took 14.6 s once. The 60 s timeout plus retry and the loud ERROR cover this, but the < 8 s target is not guaranteed under network variance.
- The minimum-grace fix (Thi Bar's canonical lookup was abandoned in 3 of 3 snapshot calls) came **after** the live run. It is unit-tested only.
- The cloud's `/preview-stops` time with this code is not measured; this was a local Docker run against the cloud cache snapshot.
- No live DB write, no DELETE, no shared container touched. Logs, meter files and the tar are not committed (the tar was extracted to /tmp only).
