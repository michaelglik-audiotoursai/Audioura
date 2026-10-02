# SUBMISSION — LOCAL-559: Translate with a small LLM instead of AWS Translate (behind a flag)

**Branch:** `LOCAL-559-llm-translation`
**Base:** `subscribed` (632f673 — LOCAL-558 forward-merge of storied).
`git merge-base --is-ancestor 632f673 HEAD` exits 0.

## Summary

`translation-service/translation_service.py` now:

1. Is **reconciled with the deployed overlay `origin/kiro/gcs-tr1` (522d25c)** merged
   with `subscribed`'s single-pass changes (LOCAL-142/162) — losing neither parent.
2. Dispatches `translate_text()` on env **`TRANSLATION_ENGINE`**: `aws` (DEFAULT) | `llm`.
   Default stays `aws`, so nothing deployed changes until the flag is set.
3. Adds an **LLM engine** (OpenAI `gpt-4o-mini`, temperature 0) with faithful,
   line-count-preserving, nav-line-preserving translation.
4. **Removes the silent truncation** in BOTH engines (the old live defect sent
   `Text=text[:5000]`). Texts over ~4,500 chars are split on blank lines, translated,
   and rejoined.
5. **Falls back to AWS** per call when the LLM errors / returns empty / returns a bad
   line-count or length ratio, logging `[TRANSLATE-LLM] FALLBACK <reason>`.
6. **Memoises** identical `(text, language)` pairs in-process.
7. **Meters cost**: `[TRANSLATE-LLM] tokens_in=.. tokens_out=.. cost=$..` per call plus a
   per-tour total, priced from `cost_rates.py`.
8. Keeps **voice-command preservation** working under the llm engine.

## Files changed

| File | Change |
|------|--------|
| `translation-service/translation_service.py` | Reconciled merge (gcs-tr1 + subscribed) + LLM engine, chunking, fallback, memo, cost metering. |
| `translation-service/Dockerfile` | `COPY ... cost_rates.py` so the rate table is importable in the image (build context is `./translation-service`, which cannot reach the repo-root copy). |
| `translation-service/cost_rates.py` | **New (vendored copy of the repo-root `cost_rates.py`).** Already contains `gpt-4o-mini` rates (`$0.15`/`$0.60` per 1M) and `llm_cost(input_tokens, output_tokens, model)`. |
| `tests/test_local559_llm_translation.py` | **New.** 12 unit tests with a mocked OpenAI client. |

---

## Part 1 — Starting from the deployed code (diff vs BOTH parents)

The production translation-service is an overlay of `origin/kiro/gcs-tr1` (522d25c),
which is on no release line. The merge base of this branch and gcs-tr1 is `7d94832`.
I did a 3-way merge (`git merge-file` of base + subscribed + gcs-tr1) and resolved the
six conflicts by hand, reconciling the two places both parents edited: the `track`
column and the `(id, cache_hit)` return contract.

**Line counts:** base `7d94832` = 1742 · `subscribed` = 1876 · `gcs-tr1` = 1870 ·
reconciled = 2279 (the +~400 over the parents is the LOCAL-559 LLM engine).

### gcs-tr1 features carried in (verified present)

- `class TranslationArtifactError` (error_code `TRANSLATION_ARTIFACT_FAILED`).
- R2 source-ZIP fetch whenever `audio_tour` is NULL and `tour_blob_uri` is set,
  **regardless of `tour_content`** (fixes R2-migrated tours 107/120/284).
- **Hard-fail, never insert an artifact-less row**: missing source ZIP, empty/None
  translated ZIP, and ZIP-build failure all `raise TranslationArtifactError` and
  `conn.rollback()`.
- **Cache requires an artifact**: the "already exists" query is
  `... AND (audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)`.
- `_create_mobile_compatible_zip` **returns `None` on error** (was `return original_zip_data`).
- `/translate-with-audio` returns **HTTP 502** with `error_code` when any language hit an
  artifact failure.
- The audio-pause-on-play JS block removed from `_generate_translated_html`.

### subscribed features carried in (verified present)

- `_restore_metadata_labels` rewrite (insert English metadata **after the title line**,
  LOCAL-5; coordinate/address value matching).
- `translate_tour_with_audio` returns **`(id, cache_hit)`** (LOCAL-60); the endpoint
  unpacks it and reports `cache_hit`.
- **`_strip_nav_fields_from_translated`** single-pass optimisation (LOCAL-142), with the
  two-pass fallback on line-count divergence.
- **`stops_count`** carried onto translation rows (LOCAL-162); `SELECT ... stops_count`.

### Conflicts and how they were reconciled

| Area | subscribed | gcs-tr1 | Reconciled |
|------|-----------|---------|------------|
| no `tour_content` + no ZIP | `return None, False` | `raise TranslationArtifactError` | **raise** (gcs hard-fail wins; endpoint catches it) |
| ZIP has no audio | `return None, False` | `raise` | **raise** |
| ZIP-fallback path return | `(id, False)` tuple | bare `id` | **`return _zip_result, False`** (keep tuple contract) |
| `track` on INSERT | env `TOUR_TRACK` | inherit `source_track` (information_schema guard) | **inherit `source_track`; fall back to env `TOUR_TRACK`, then `beta`** — plus **`stops_count`** in both the has-track and no-track INSERT branches |
| success return | `return new_tour_id, False` | `return new_tour_id` | **`return new_tour_id, False`** with gcs track logging |
| endpoint handler | tuple unpack + `cache_hit` | `try/except TranslationArtifactError` → 502 | **both**: tuple unpack inside the try, artifact failure → 502 |

The track reconciliation keeps gcs-tr1's correctness point (the service is shared, so a
translation inherits its source's track) while retaining subscribed's env fallback for
source rows that predate the `track` column, and still writes `stops_count`.

---

## Part 2 — LLM engine, chunking, fallback, memo, cost (the "Do" list)

- **Dispatch:** `translate_text()` memoises then calls `_translate_dispatch`, which chunks
  the input and runs `_translate_text_aws` or `_translate_text_llm` per chunk. Engine is
  read once in `__init__` from `TRANSLATION_ENGINE` (unknown value → `aws` with a warning).
- **System prompt** (temperature 0): translate faithfully into `<language>`; same meaning,
  no additions/omissions; keep every line break and the same number of lines; keep
  `Address:`/`Coordinates:`/`Type/Specialty:`/`Specific Examples:`/`Operational Details:`
  lines unchanged; keep venue/person names as commonly written; output only the translation.
- **No truncation (both engines):** `_split_for_translation` splits > 4,500-char input on
  blank lines (paragraphs) and rejoins with `\n\n`. The AWS path additionally splits any
  single chunk over the 10k-byte API limit on newlines — it no longer sends `text[:5000]`.
- **Fallback:** `_translate_text_llm` falls back to AWS for that call on error / empty
  output / line-count mismatch / length ratio outside `0.5–2.5`, logging
  `[TRANSLATE-LLM] FALLBACK <reason>`.
- **Memo:** `_translation_memo` keyed on `(engine, lang, preserve_voice_commands, text)`
  under a lock.
- **Cost:** `_meter_llm_cost` uses `cost_rates.llm_cost(input_tokens, output_tokens,
  model='gpt-4o-mini')`, logs per call, accumulates a per-process total and a per-tour
  total (reset at the start of `translate_tour_with_audio`, logged at the end).
- **Voice commands:** `_VOICE_COMMANDS` is a shared class constant. Under the llm engine the
  system prompt is extended to keep those phrases in English, and the existing
  `_preserve_voice_commands` AWS post-pass remains as a backstop.

---

## Acceptance evidence

### Unit tests (mocked OpenAI client) — 12 passed

`python3 -m pytest tests/test_local559_llm_translation.py -v` → **12 passed**.

- `test_default_engine_is_aws` — default engine is `aws`.
- `test_aws_engine_does_not_call_openai` — aws path never calls the LLM.
- `test_llm_preserves_line_count_and_nav_lines` — line count preserved; all five nav lines
  unchanged.
- `test_fallback_on_llm_error` / `_empty_output` / `_bad_ratio` / `_line_count_mismatch` —
  each returns the AWS result and logs `[TRANSLATE-LLM] FALLBACK <reason>`.
- `test_12000_char_input_not_truncated` — a 12,000-char input is split into multiple chunks
  and fully translated; **red on the old `text[:5000]` code** (asserts
  `total_in >= len(text) - 10`, which is ~5,000 vs 12,000 on the old path).
- `test_aws_engine_also_untruncated_over_5000` — the AWS path sends every character.
- `test_memo_avoids_second_llm_call` — second identical call hits the memo (1 LLM call).
- `test_cost_metered_and_logged` — cost accumulated and logged with tokens in/out.
- `test_voice_commands_preserved_under_llm` — `Play` survives the llm engine.

### Live, local Docker

Built `local559-translation:test` from this branch and ran two containers on the
`development_default` network against the live DB (`postgres-2` / `audiotours`), with the
same AWS + OpenAI creds as the deployed service:
`local559-tr-llm` (`TRANSLATION_ENGINE=llm`, :5531) and `local559-tr-aws` (`aws`, :5532).
Both `/health` healthy; `cost_rates` imported in-container with gpt-4o-mini rates
`{input_per_1m: 0.15, output_per_1m: 0.6}`. **The shared `audioura-translation-service-1`
was never touched.** No GCloud deploy.

**Stop 1 side by side — tour 301 "Nice, France - Walking Tour" (10 stops, 18,402 chars):**

| engine | lang | src chars | out chars | src→out lines | wall | cost | nav lines |
|--------|------|-----------|-----------|---------------|------|------|-----------|
| llm | ru | 2136 | 2068 | 17→17 | 8.22s | $0.000437 | **kept English** (`Address:`,`Coordinates:`,`Type/Specialty:`,`Specific Examples:`) |
| aws | ru | 2136 | 2080 | 17→17 | 0.67s | $0 | translated to Russian, restored later by `_restore_metadata_labels` |
| llm | es | 2136 | 2331 | 17→17 | 10.03s | $0.000425 | kept English |
| aws | es | 2136 | 2433 | 17→17 | 0.91s | $0 | translated, then restored |

The llm engine keeps the nav lines in English in a single pass (as the prompt instructs)
and preserves the line count exactly.

**Full pipeline `/translate-with-audio` (fresh rows, `cache_hit=false`):**

| engine | source tour | lang | new id | wall |
|--------|-------------|------|--------|------|
| llm | 301 (10 stops) | ru | 373 | ~102s |
| llm | 301 | es | 374 | ~111s |
| aws | 71 (7 stops) | ru | 375 | ~11s |
| aws | 71 | es | 376 | ~17s |

(Two source tours were used so neither engine's run cache-hit the other — the cache keys on
`original_tour_id + content_language`.)

**Per-tour LLM cost (from container logs):** tour 373 (ru) total **$0.003863**, tour 374
(es) total **$0.003720**. A 10-stop tour translated for **under $0.004** — against Michael's
~$0.17 AWS Translate figure for a 5-stop tour. **No `[TRANSLATE-LLM] FALLBACK` lines fired.**

**Download verification** (`localhost:5005/download-tour/<id>`, served by map-delivery):

| id | HTTP | mp3 files | all non-zero |
|----|------|-----------|--------------|
| 373 | 200 | 10 | yes |
| 374 | 200 | 10 | yes |
| 375 | 200 | 7 | yes |
| 376 | 200 | 7 | yes |

### Live-DB rule (CLAUDE.md)

Only one table was written: **`audio_tours`**.

- **Row count before = 186, after = 190 (+4)** — exactly the four translation rows. No drop.
- New rows **373, 374, 375, 376**. `track=beta` (inherited), `stops_count` 10/10/7/7.
- **Hide test rows:** all four rows have `lat IS NULL AND lng IS NULL`. Translations inherit
  their source's lat/lng, and source tours 301 and 71 both already have `lat=NULL, lng=NULL`,
  so the rows were created **already hidden** from the `tours-near` query. There were no
  non-null values to back up.
- **Backup record (for the file):**

  ```
  id | original_tour_id | lang | lat  | lng
  373|       301        |  ru  | NULL | NULL
  374|       301        |  es  | NULL | NULL
  375|        71        |  ru  | NULL | NULL
  376|        71        |  es  | NULL | NULL
  ```

- **NEVER DELETED.** The four rows remain in the live DB.

### Cleanup

Both test containers removed; the temporary in-container probe script and downloaded ZIPs
deleted. The shared live translation-service is still up and untouched.

## Must-not — honoured

- **No GCloud deploy.** All testing was local Docker against the local DB.
- **Did not edit** `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
  `.continuous_dev/STATUS.md`.
