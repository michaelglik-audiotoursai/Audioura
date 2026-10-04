# LOCAL-578 — Meter translations: translation LLM + its Polly audio write cost_ledger rows

**Branch:** `LOCAL-578-translation-metering`
**Base:** subscribed (`0242af3`) — verified `git merge-base --is-ancestor 0242af3 HEAD` exits 0.
**Agent:** Mac Mini Kiro

## Problem (D605)
A Russian copy of a tour left **no `cost_ledger` rows**. The translation service
logged `[TRANSLATE-LLM] … cost=$…` per LLM call (≈ $0.009) but never wrote the ledger,
and its audio went through its **own** boto3 Polly client
(`translation-service/translation_service.py`, Tatyana standard, ≈ $0.03), also unmetered.
So per-tour price reports undercounted every translation.

## What changed

### 1. `translation-service/translation_service.py` — write the ledger
- **One `translation_generate` row per translation job.** Written at the end of a
  successful fresh `translate_tour_with_audio`, via `cost_meter.record_operation`.
  `our_cost_usd` = summed LLM cost (all passes/models) + summed direct-boto3 Polly TTS cost.
  `breakdown` carries exactly the shape the ticket asked for:
  ```json
  {"llm": .., "models": {"gpt-4o-mini": .., "gpt-4o": ..}, "tts": .., "tts_engine": "standard",
   "chars": .., "source_tour_id": 363, "target_language": "ru", "translated_tour_id": 390, "stops": 3}
  ```
  New helper `_meter_translation_row(...)`; LLM cost is accumulated **by model** in
  `_llm_tour_cost_by_model` (reset per tour, guarded by `_cost_lock`) inside the existing
  `_meter_llm_cost`.
- **One `tts_generate` row per synthesized stop** in the direct-boto3 path. `generate_audio`
  now meters each Polly call via new `_meter_tts_cost(...)`: `breakdown={chars, engine,
  voice_id, language, source_tour_id}`, with the Polly price from `cost_rates.tts_cost`
  (engine-aware). This matches polly-tts's LOCAL-323 rows (`operation_type='tts_generate'`,
  `{chars, engine, voice_id}`). Neural-voice detection mirrors polly-tts's `NEURAL_VOICES`;
  the translation path uses standard voices (ru → Tatyana → `standard`).
- **Attribution:** `/translate-with-audio` reads `job_id`/`user_id` from the request body
  and `translate_tour_with_audio(..., job_id, user_id)` threads them onto every row.
- All metering is **best-effort** — a metering failure (or a missing `cost_meter`) logs a
  warning and never breaks a translation. `cost_meter` is imported softly.

### 2. `tour_orchestrator_service.py` + `tour_worker_service.py` — forward attribution
Both now include `"job_id"` and `"user_id"` in the `/translate-with-audio` payload, so the
translation rows tie to the same job/user as the English generation and the translation
wallet charge the orchestrator already records.

### 3. `translation-service/Dockerfile` — the COPY trap
`cost_meter.py` copied into the build context and **added to the explicit COPY list**
(`COPY translation_service.py blobstorage.py build_manifest.py cost_rates.py cost_meter.py ./`).
The list is explicit, so a runtime dep missing from it is absent in the image — this trap
bit twice this week, so it is called out in a comment.

## Tests — `tests/test_local578_translation_metering.py` (boto3 + LLM stubbed; no network/DB)
- **4-stop Russian translation → exactly 1 `translation_generate` + 4 `tts_generate`.**
  Asserts tts rows carry `{chars, engine, voice_id}` priced by `cost_rates.tts_cost`
  (Tatyana/standard); the translation row's breakdown has `{llm, models:{...}, tts,
  tts_engine, chars}` + source tour id / target language / job id; and the sums reconcile:
  `sum(tts rows) == breakdown.tts`, `our_cost_usd == llm + tts`, `models total == llm`.
- **Endpoint test:** `/translate-with-audio` threads `job_id`/`user_id` into
  `translate_tour_with_audio`.

```
$ python3 -m pytest -q tests/test_local578_translation_metering.py
2 passed
```
Regression check: `tests/test_local559_llm_translation.py`,
`tests/test_local561_guidebook_translation.py`, `tests/test_local323_tts_metering.py` all
pass (44 passed). `tests/test_local142_single_pass_translation.py` has 5 failures that are
**pre-existing and environmental** — they call `db_connection.get_connection()` and query a
live Postgres (`WHERE id = 14`), which isn't available in the unit-test env; they do not
touch any signature I changed.

## Live run (measured the branch code, not stale subscribed — D358)
The stock `docker-compose.subscribed-local.yml` pins the translation build context to
`/Users/micha/audioura-subscribed-local`, a detached `origin/subscribed` checkout **without**
LOCAL-578. I added a worktree-local override (`docker-compose.local578.yml`, an untracked
live-run artifact — not committed) that repoints the translation-service build context at
this worktree, then rebuilt ONLY translation-service:

```
GIT_SHA=$(git rev-parse --short HEAD) docker compose -p audioura \
  -f docker-compose-master.yml -f docker-compose.local578.yml \
  up -d --no-deps --build translation-service
```

Verified the running container is the branch build: `/app/.git_sha` = `f569d18` (= HEAD),
`cost_meter.py` present, `/health` healthy.

Translated an existing English **test** tour (id **363**, "LOCAL49 Regression Test", 3 stops —
not Michael's 388) to Russian → new tour **390**, `cache_hit=false`:

```
job_id = local578-live-1791137879   user_id = local578-tester
```

### Ledger rows written (job_id = local578-live-1791137879)
| operation_type        | our_cost_usd | breakdown (key fields) |
|-----------------------|-------------:|------------------------|
| tts_generate          | 0.008604     | chars 2151, standard, Tatyana, src 363 |
| tts_generate          | 0.009344     | chars 2336, standard, Tatyana, src 363 |
| tts_generate          | 0.012000     | chars 3000, standard, Tatyana, src 363 |
| translation_generate  | 0.038155     | llm 0.008207, tts 0.029948, chars 7487, stops 3, models{gpt-4o 0.00609, gpt-4o-mini 0.002116}, tts_engine standard, src 363, target ru, translated 390 |

Reconciliation: tts rows sum `0.008604+0.009344+0.012000 = 0.029948` = the translation
row's `tts`; `llm 0.008207 + tts 0.029948 = 0.038155` = `our_cost_usd`; models sum ≈ llm.

### Caps (both satisfied)
- **OpenAI:** $0.0082 < $0.10 ✓
- **Polly:** $0.0299 < $0.10 ✓

### audio_tours counts
`total 200 → 201`; `ru 20 → 21` (the one new translation). Breakdown after:
en 169, es 6, fr 5, ru 21.

### Test-row hygiene (no DELETE)
New tour **390** inherited **NULL** `lat`/`lng` from the regression source tour 363 (it has
no coordinates), so it is already hidden (no map pin) — nothing to null, nothing to restore.
A timestamped note is in `scratchpad/testrows_backup.txt`. Nothing was deleted.

## Commits
1. `LOCAL-578 step 1` — meter translation LLM + boto3 Polly into cost_ledger; endpoint
   job_id/user_id; Dockerfile COPY.
2. `LOCAL-578 step 2` — orchestrator + worker forward job_id/user_id.
3. `LOCAL-578 step 3` — the 4-stop test.

`git rev-list --count subscribed..HEAD` = 3. Pushed to
`origin/LOCAL-578-translation-metering`.

## Not touched
DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, `.continuous_dev/STATUS.md`. No GCloud.
`docker-compose.local578.yml` is left untracked (a live-run artifact) and intentionally not
committed.
