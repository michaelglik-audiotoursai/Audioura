# SUBMISSION — LOCAL-907 Regional Topic Library ("fillings" between stops)

Branch `LOCAL-907-topic-library`, based on `subscribed` 6dffb0ef (`git merge-base --is-ancestor 6dffb0ef HEAD` exits 0).
Budget: **$0**. No live run, no paid call, no network, no DB write. `TASK_BUDGET_*` was never used for a paid run.

## SCHEMA DECLARATION (additive; NOT run anywhere)
`migrations/local907_topic_library.sql` — three NEW tables, `CREATE ... IF NOT EXISTS` only (no ALTER/DROP/DELETE; a test enforces this).
- `topic_segments` — id, region_key, theme, title, language, text, word_count, est_minutes, sources JSONB, credit_line, centroid_lat/lng, radius_km, audio_path (nullable), source_segment_id (FK, translations), status (draft|ready|rejected), cost_usd, created_at. Unique (region_key, language, title) so a re-run never pays twice for a segment.
- `listening_events` — id, user_id, tour_id, segment_id (FK), action (start|skip|finish|choose), at_sec, created_at. `user_id`/`tour_id` are TEXT (the app's ids are strings).
- `listener_theme_weights` — (user_id, theme) PK, weight, updated_at.
LEAD runs the migration after merge.

## What was built
| File | Role |
|---|---|
| `data/topic_regions.json` | Regions as data (D769): the 5 regions, centres, radius, Wikipedia seed titles per language, default themes. |
| `topic_library.py` | Themes, region loading, geometry, `MemorySegmentStore` / `PgSegmentStore` (parameterised SQL). |
| `topic_library_build.py` | CLI + library: plan, fetch (disk cache), write, ground, meter, translate, render audio. |
| `topic_picker.py` | `pick_fillings(tour, listener_weights=None, *, segments, recent_segment_ids)`; pure, deterministic. |
| `listening_events.py` | Validation, weight math, `PgRepo` / `MemoryRepo`, `apply_event`. |
| `fillings_payload.py` | The additive `fillings` field + read-only `fillings_for_tour` (never raises). |
| `tour_orchestrator_service.py` | +12 lines: computes fillings once at completion into the job, copies `fillings` into the memory-path status response only when non-empty. |
| `user_api_with_cors.py` | `POST /listening-events` (+ OPTIONS). |
| `Dockerfile.orchestrator` | COPY of the four new runtime modules. |
| `.gitignore` | `topic_source_cache/`, `topic_audio/` (cached source pages are never committed). |
| `tests/test_local907_topic_library.py` | 40 offline tests. |

## Builder behaviour
`topic_library_build.py --region <key> [--language en] [--max-segments N] [--budget-usd X] [--dry-run] [--render-audio]`, and `--language xx --from en` for translations.
- **Plan**: level-2 sections of the seed articles (sub-sections folded in, ≥500 source words) + linked articles to fill gaps, classified to the 9 themes by generic keyword cues, picked round-robin across the region's themes; overlap = shared title/section tokens over the smaller set (region-name tokens ignored), ≤ 0.30. `--dry-run` prints the plan and estimated cost and spends $0 (fetch is free).
- **Fetch**: MediaWiki action API (free, no key), cached in `topic_source_cache/`; revision id + CC BY-SA 4.0 recorded in `sources`. `voyage:Title` seeds read Wikivoyage.
- **Write**: `NARRATION_MODEL` (gpt-4.1-mini), asked for ~1,900 words, hook first; output scrubbed of citations/parentheses/markdown/tables.
- **Ground**: `strict_grounding_gate.apply_grounding_gate` (D771) in batches of whole paragraphs (~20 sentences) against the fetched passages; dropped sentences stay dropped. < 1,200 surviving words → `rejected`. The credit line is appended after grounding. If the judge returns nothing usable the segment is **rejected** (the gate would otherwise keep unjudged sentences).
- **Meter**: `BuildMeter` charges every write and judge call; stops at `--budget-usd` and at `TASK_BUDGET_*` (`task_budget.check_task_budget`), pre-reserving `max(estimate, last segment's real cost)`; appends the run to the task ledger on exit. A real build with no limit at all is refused.
- **Translations**: `translation_service` forced to the `llm` engine and its AWS fallback replaced by an error (an LLM failure fails the segment; AWS Translate is never called). Keeps `source_segment_id`; no re-grounding; title and credit line translated too; already-translated sources are skipped.
- **Audio**: `--render-audio` POSTs paragraph chunks to `KOKORO_URL` (`/render`, voice `TOPIC_VOICE`, default Joanna), concatenates the MP3 and stores a path relative to `TOPIC_AUDIO_DIR`.

## Picker / API
- Leg minutes: route data (`legs[i].minutes|distance_km`, or per-stop `leg_minutes`) wins; else haversine × 1.3 road factor at car 35 km/h (`area: rural`, the default for legs > 6 km) / 25 km/h (`area: city`), bike 14, walk 4.5.
- Legs < 8 min get nothing. Ranking = region closeness (leg midpoint inside the segment's radius, else excluded) + theme fit to the stops' Type/Specialty + listener weight (/5). Items chosen in rank order while the running total ≤ leg minutes + 5, max 5. First item = default auto-play. Segments never repeat within the tour or across `recent_segment_ids` (`PgRepo.recent_segment_ids` = last 5 tours of that user).
- Payload: `fillings: [{leg, after_stop, minutes, items: [{segment_id, title, theme, minutes, audio_url, credit_line}]}]`; `leg` is 0-based, `after_stop` 1-based. Added only when non-empty; no other field is touched (tested).
- `POST /listening-events` `{user_id, tour_id, segment_id, action, at_sec}` → 201 / 400 (invalid) / 404 (unknown segment). Weights: finish +1.0, skip < 60 s −1.0, skip ≥ 60 s −0.3, choose +0.5, start 0; ×0.95 decay on a listener's first event of each new tour; clamp [−5, 5] (also in the SQL upsert).

## Tests
- `python3 -m pytest tests/test_local907_topic_library.py` → **40 passed** (plan/dry-run $0 with ≥ 5 themes and no overlap > 0.30; write+ground drops unsupported sentences, credit line, source fields, short survivor rejected, unjudged rejected; budget stop incl. task ledger; translation LLM engine + `source_segment_id` + no AWS; picker 40-min leg → 3–5 items fitting, 5-min leg → none, no repeats, weights reorder, determinism; events→weights math; endpoint; additive payload).
- Required regression set `tests/test_local89[6-9]*.py tests/test_local90*.py tests/test_lead905*.py` → **345 passed**, no failures. Also `test_service_packaging.py`, `test_local894*` → 81 passed.

## NOT proven / for LEAD (honest limits)
1. **Nothing ran live.** Unverified: the exact MediaWiki responses (parser written to the documented shape), whether all seed titles exist as written (a missing one is skipped), real gpt-4.1-mini word counts (1,500–2,200 asked, not enforced) and how many sentences the real judge keeps — the 1,200-word survivor floor may reject thin-source topics; the plan prints `source words` per topic so you can see that before paying.
2. `make_llm_translate_fn()` default loader instantiates the real `TranslationService` (needs boto3 + OPENAI_API_KEY); tested only with a fake service of the same shape. `default_llm` and `default_render` are untested (network).
3. "3–5 items" is a target: the strict `total ≤ leg + 5` rule can yield 1–2 items on short legs or a thin library.
4. `fillings` appears on the **in-memory (thread-mode) status response** only; the cloud_tasks/DB status path does not carry it yet. Map-delivery JSON not changed.
5. `audio_url` is `TOPIC_AUDIO_BASE_URL` (default `/topic-audio`) + the stored path; **no route serves that directory yet** — LEAD decides where audio is hosted.
6. `user_api_with_cors.py` is not copied by any Dockerfile in this repo; the route is there, deploy wiring is unchanged.
7. The app does not yet call `/listening-events` or read `fillings` (backend only, per task).
8. Stop generation, the stop pool and existing tour text were not touched.
