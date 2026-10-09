# SUBMISSION — LOCAL-647: Replay harness + narration MODEL bake-off

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-647-narration-bakeoff` (created from `subscribed` @ `531a5219`)
**Base verified:** `git merge-base --is-ancestor 531a5219 HEAD` → exit 0.
**Full report:** `.continuous_dev/bench/BAKEOFF_LOCAL-647.md`

## What was asked
Build a replay harness that writes a stored museum stop's narration from saved research (no new
research calls), reusing the production prompt; run five model arms on identical inputs; score every
output with Kiro + the deterministic detectors; report cost/quality/latency per arm; run a
prompt-diet experiment; stay under $3.00; live-run in an own container with additive `is_test` rows
only.

## What was delivered
1. **`replay_harness.py`** (new module). Rebuilds each stop's narration INPUT from
   `venue_corpus.pages_json` + `venue_corpus.story_elements_json` + the work's **free, disk-cached**
   English Wikipedia extract. **No Serper, no Gemini/Serper research.** Builds the prompt by
   **reusing the production builder**, and calls the model under test. Commands:
   `run` / `run-all` / `build-only` / `measure` / `store`, flags `--diet` / `--fixed-first` /
   `--arms` / `--limit`.
2. **Model-selection env hook** — `generate_tour_text.narration_model_route()`
   (`NARRATION_PROVIDER` / `NARRATION_MODEL`). **Default is unchanged**: with nothing set it returns
   `("openai", story_pass_model())`, i.e. today's gpt-4.1 path. Only the harness opts into other arms.
3. **Prompt reuse, not rewrite** — the museum narration prompt body was lifted verbatim from the
   inline f-string in `generate_tour_text._generate_description()` to a module-level
   `build_museum_stop_prompt()`, **proven byte-for-byte identical** (diff test against `HEAD`).
   Production and the harness share one definition.
4. **5 arms, 12 stops, 1 draft each, no retries** — 60 drafts, all HTTP 200.
   A gpt-4.1 · B gpt-4.1-mini · C gpt-4.1-nano · D Gemini 2.5 Flash-Lite · E Gemini 2.5 Flash.
5. **Scoring** — `score_stops.py`: Kiro single-stop critique (critique.sh rubric adapted) +
   per-stop deterministic detectors (stop-level subset of detectors.py).
6. **Report** — `report.py`: per-arm mean/min score, detector + HTTP failures, $/stop (from the
   `paid_api_calls` ledger), median seconds, mean output tokens, and which arms are within 0.3 of
   arm A. `diet_report.py`: the prompt-diet comparison.

## Result (one line)
**gpt-4.1-mini matches/beats gpt-4.1 (7.83 vs 7.58) at ~1/6 the cost** ($0.00184 vs $0.01030/stop).
Gemini 2.5 Flash (7.88) and Flash-Lite (7.83) are within 0.3 of gpt-4.1 too; nano (6.12) is not.
Diet trims the prompt 20.6% (−32–38% $/stop) for a small score dip; fixed-first caching caches 84%
of gpt-4.1's prompt tokens.

## Spend & safety
- **Total metered spend: $0.70937** (181 calls, `job=LOCAL-647`), under the $3.00 cap. Every paid
  call went through the network meter (`paid_api_calls`); $ per arm reported from it.
- **Live run in my OWN container** `local647-gen` (`docker run --rm`); never `docker compose -p
  audioura`, never renamed/replaced an `audioura-*` container.
- **Additive `is_test` rows only** (ids 566–570, one per arm). `audio_tours` 371→376 total, is_test
  307→312. **No UPDATE, no DELETE. No GCloud.**
- No default behaviour change: the production narration default stays gpt-4.1.

## Decisions / notes
- **Why extract a shared prompt builder?** The ticket requires "import and reuse" the production
  prompt. It was embedded in a 1.48 MB function's closure, so the faithful, behaviour-preserving
  move was to lift the exact f-string to a module-level function both callers use (verified
  identical). This is the only honest way to reuse rather than reimplement it.
- **Gemini 2.5 ids:** the dated `gemini-2.5-flash[-lite]` ids are 404 "no longer available to new
  users" on this key; the `-latest` aliases resolve to the same 2.5 Flash family (per
  `cost_rates.py`), so arms D/E use the working aliases. `gemini-flash-lite-latest` rejects
  `thinkingConfig` (400), so the harness omits it for the lite model. All Gemini calls are
  **ungrounded** (no `tools`/`google_search`).
- **Identical inputs:** the free Wikipedia extract is fetched once and disk-cached (`_wiki_cache/`),
  so all five arms (and the diet/fixed-first re-runs) see byte-for-byte identical inputs.
- **Detector caveat:** the 2 detector "failures" (arms C, D) are the inherited noisy
  `truncated_snippet` heuristic firing on a legitimate sentence boundary — borderline false
  positives, not real truncation.

## Process
- Committed after each step (10 commits). `git rev-list --count origin/subscribed..HEAD` ≥ 1.
- Did NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or .continuous_dev/STATUS.md.
- Branch pushed to `origin/LOCAL-647-narration-bakeoff`.

## How to reproduce
```bash
# in the metered generator image, own container:
docker run --rm --name local647-gen --network development_default \
  -e DB_HOST=postgres-2 -e DB_NAME=audiotours -e DB_USER=admin -e DB_PASSWORD=password123 \
  -e PYTHONPATH=/opt/meter -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl \
  -e METER_SERVICE=replay_harness.py -e METER_JOB=LOCAL-647 -e HOSTNAME=local647-gen \
  -e OPENAI_API_KEY=... -e GEMINI_API_KEY=... \
  -v $PWD/replay_harness.py:/app/replay_harness.py:ro \
  -v $PWD/generate_tour_text.py:/app/generate_tour_text.py:ro \
  -v /path/to/_meter:/opt/meter:ro -v $PWD/bench_out:/app/bench_out \
  audioura-tour-generator \
  python3 replay_harness.py run-all --out /app/bench_out
# then on the host:
python3 score_stops.py all --dir bench_out
python3 report.py --dir bench_out --host local647-gen
python3 diet_report.py --dir bench_out
```
