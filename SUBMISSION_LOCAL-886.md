# SUBMISSION LOCAL-886 — cloud-parity proof of subscribed 42d139ab (884+885+885B), cloud cache snapshot, warm only

**Result: WARM FAIL (3 PASS-checklist items fail). Audit: 0 unsupported. One live run; nothing fixed.**

## Spend
- Run 1: **$0.3411** (meter), recorded in the ledger. Ledger total (`task_budget.spent_so_far('LOCAL-886')`): **$0.341117 of $0.70**. Before the run it was 0.0.
- No second run (run 1 completed and produced tour text, so the task's condition for run 2 was not met). Default ledger dir; `AUDIOURA_TASK_BUDGET_DIR` unset.

## Code (commit cd5ee0e7)
- `run_cloud_parity_proof.py --snapshot DIR`: creates each cache table with the generator's own `CREATE TABLE IF NOT EXISTS` (`domain_tier_cache` has no SQL schema in the generator, so it gets a plain table; the snapshot has 0 rows for it), loads every `cloud_*_cache_*.csv.gz` through a temp staging table + `INSERT ... ON CONFLICT DO NOTHING` (no DELETE/TRUNCATE), prints rows before/after per table, refuses any non-local or 5432/5433 DB, then runs WARM only (no seed, no cold), the PASS checks, and the gpt-4.1 audit. Spend is recorded in the ledger in a `finally`.
- `run_cloud_parity_proof_884.py`: audit no longer truncates each stop's evidence to 6,000 chars (City Hall's bundle is 16,798), so it reads the same bundle the gate did.
- `docker-compose.local886-proof.yml` (project `-p local886`, port 55986); `tests/test_local886_snapshot_load.py` (empty DB -> 122 `landmark_wiki_cache` rows; passes).
- Note: the audit's evidence is read from the same per-job sinks the gate reads (`_THIN_FACTS`, direct snippets, `_WIKI_EVIDENCE_SINK`, which receives the 885 shared `EvidenceBundle` items).

## Snapshot load (rows before -> after)
landmark_wiki_cache 0->122, landmark_coord_cache 0->179, local_language_cache 0->2, thin_verify_cache 0->2, venue_preflight_cache 0->29, venue_works_cache 0->27, work_story_research_cache 0->26, domain_tier_cache 0->0.

## Per stop (final text)
Gate lines are from the first grounding pass (the pass that edits); "final" is the last re-pass.

| # | Stop | evidence_chars | labelled (1st pass) | kept / contradicted / unsupported (1st pass) | labelled (final) | kept/contr/unsup (final) | content sentences |
|---|---|---|---|---|---|---|---|
| 1 | Cathedral | 8765 | 6 | 4 / 0 / 2 | 4 | 2 / 0 / 2 | 5 |
| 2 | Post Office | 5662 | 6 | 3 / 0 / 3 | 3 | 3 / 0 / 0 | 6 |
| 3 | Book Street | none (not in bundle) | 2 (no evidence) | 0 / 0 / 2 | 0 | - | 5 (disclosed no-history) |
| 4 | Independence Palace | 3394 | 3 | 3 / 0 / 0 | 3 | 3 / 0 / 0 | 8 |
| 5 | War Remnants Museum | 4879 | 4 | 3 / 0 / 1 | 3 | 3 / 0 / 0 | 5 |
| 6 | Opera House | 11318 | 5 | 5 / 0 / 0 | 5 | 4 / 0 / 1 | 6 |
| 7 | City Hall | 16798 | 3 | **0** / 0 / **3** | 3 | 3 / 0 / 0 | 5 |
| 8 | Café Apartments 42 | 756 | 3 | 3 / 0 / 0 | 3 | 3 / 0 / 0 | 7 |
| 9 | Bạch Đằng Pier | none (not in bundle) | 2 (no evidence) | 0 / 0 / 2 | 0 | - | 5 (disclosed no-history) |
| 10 | Thi Bar | 950 | 1 | 1 / 0 / 0 | 5 | 3 / 0 / 2 | 8 |

Totals: first pass 35 labelled, 13 dropped; final re-pass 29 labelled, 5 dropped. 0 contradicted anywhere. Evidence chars are from the audit input (8 stops had evidence; Book Street and the Pier had none).

## PASS checklist (LOCAL-884)
| Item | Result | Evidence |
|---|---|---|
| 10/10 stops with wave-40 titles | PASS | Cathedral, Post Office, Book Street, Independence Palace, War Remnants Museum, Opera House, City Hall, Café Apartments 42, Bạch Đằng Pier, Thi Bar |
| Wave-40 pins | PASS | All 10 Coordinates lines equal the wave-40 pins |
| City Hall = Hôtel de Ville, Gardès, 1898–1909 | **FAIL** | No 1898, 1909, Gardès or "Hôtel de Ville" in the City Hall text. The first gate pass dropped "constructed between 1898 and 1909" and "L'hôtel de ville" as UNSUPPORTED (0 of 3 kept) despite 16,798 evidence chars. Text instead tells Ho Chi Minh's biography. |
| Palace states the 30 April 1975 tank | **FAIL** | Palace text covers 1962 commission, 1966 completion and the 1963 coup; no 30 April 1975 or tank. (The 885 bundle for this stop is 3,394 chars.) |
| Eiffel only as a myth | PASS | Post Office: "Gustave Eiffel ... was not responsible for this structure"; Foulhoux credited |
| Cathedral 1877–1880 | PASS (note) | Text states "Completed in 1880"; the 1877 start is not stated |
| No 1163 / 1182 / 1345 | PASS | none present |
| No Pier evacuation | PASS | no "evacuat"; Pier carries the no-history disclosure |
| Thi Bar at 224 Đề Thám, "Gay bar" | PASS | "Type/Specialty: Gay bar"; "located at 224 Đề Thám Street in District 1" |
| Harness extras: banned wave-40 strings absent, Diệm in full, Opera House not Ferret-alone, Stop 1 real directions, labelled>0 or disclosed, every stop ≥4 (≥5) content sentences | PASS | harness output |

## Independent gpt-4.1 audit (verbatim unsupported-claims list)
```
"unsupported": []
```
Model gpt-4.1, 16,813 prompt tokens. `evidence_chars` per stop: Café Apartments 42 756; Thi Bar 950; Independence Palace 3394; War Remnants Museum 4879; Post Office 5662; Cathedral 8765; Opera House 11318; City Hall 16798.

## Caveats for LEAD
- The empty audit list does not mean the text is clean. Book Street and the Pier had no evidence entry, so the audit was given nothing to check them against. The Pier text still says "Parties leaving from here set out to explore ... narrow tunnels", which looks unevidenced, and the audit did not flag it. The audit prompt tells it to judge only against provided evidence, and it has no entry for those two stops.
- City Hall and Palace lose their key facts in the gate even though the bundles hold 16.8 K / 3.4 K chars. Not investigated, per task ("do not fix").
- LLM variance: this is a single run; I did not re-run.

## Artifacts
`submission_artifacts/local886/saigon_warm.txt`, `saigon_warm_audit.json`. Run logs and meter logs are not committed.
