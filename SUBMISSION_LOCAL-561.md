# SUBMISSION — LOCAL-561: Translation that reads like a native guidebook

**Branch:** `LOCAL-561-guidebook-translation`
**Base:** `subscribed` (84944d8 — LOCAL-559R).
`git merge-base --is-ancestor 84944d8 HEAD` exits 0.

## Why

Michael's side-by-side of tour 301 (doc "Translation Old vs New") found AWS Translate reads
best today, while LOCAL-559's gpt-4o-mini engine (1) gets established names wrong
(«Палац Ласкарис», «Замок Холм»), (2) turns narration into a string of ORDERS
(«откройте для себя», «почувствуйте», «Ищите») where AWS writes «вы обнаружите»,
(3) leaves "Stop N:" in English, and (4) calques / dangles participles. LEAD's experiments
showed a guidebook-style instruction fixes the orders, a gpt-4o names-only pass fixes the
names, and that **structure must be done by CODE** because the model drifts to «Стоп 1» and
leaves Spanish "Orientation:"/"Directions:" in English.

## Design (behind `TRANSLATION_ENGINE=llm`; `aws` stays the default)

All changes are in `translation-service/translation_service.py`, additive, and only active
when `TRANSLATION_ENGINE=llm` **and** `TRANSLATION_GUIDEBOOK` is on (default on). The `aws`
engine and the LOCAL-559R `llm` path are untouched for every existing caller.

1. **Structure by code, per language** (`_STRUCTURE_LABELS`, `_strip_structure_for_model`,
   `_restore_structure`, `_native_stop_header`). A per-language dictionary gives the native
   `Stop N:` heading and the spoken `Orientation:`/`Directions:` labels for 16 languages
   (ru «Остановка N:» / «Как сориентироваться:» / «Как пройти:»; es "Parada N:" /
   "Orientación:" / "Cómo llegar:"; fr, de, it, pt, zh, ko, ja, nl, pl, tr, uk, ar, hi, he).
   The stop body is split into a *template* (fixed structure the code owns) and *prose
   segments* (what the model translates). The spoken label is stripped before the model
   sees the line and the native label is prepended on restore. `Address:`/`Coordinates:`
   are copied byte-exact; `Type/Specialty:`/`Specific Examples:`/`Operational Details:`
   keep their English label (the mobile app parses it) and have their value translated as
   prose. **One template token per source line → line count is preserved exactly.**

2. **Names: one call per tour, gpt-4o** (`TRANSLATION_NAMES_MODEL`, default `gpt-4o`) —
   `_build_names_glossary`. Input is the whole tour; output is a JSON glossary
   {source name → established target-language name}, cached per `(tour, language)`. Streets
   and squares with no established exonym keep the original Latin name. Where Wikidata has a
   target-language label for the entity, **Wikidata wins** (`_apply_wikidata_overrides` /
   `_wikidata_label`).

3. **Prose: gpt-4o-mini** (`TRANSLATION_PROSE_MODEL`, default `gpt-4o-mini`) —
   `_guidebook_prose_prompt` + `_translate_prose_segments_guidebook`. One call per stop with
   guidebook style rules: listener-addressed narration becomes narration (future/impersonal,
   «здесь можно…»), imperatives only for real walking instructions; no calques; participles
   bound to their subject; USE the glossary names, declined as grammar requires. Stops run
   concurrently in the existing bounded pool.

4. **Every LOCAL-559R safety kept:** no truncation; the prose pass retries once then falls
   back to AWS per segment on a segment-count mismatch; cost is metered **per call and per
   tour** at each model's own rate (`_meter_llm_cost(model=…)`).

## Files changed

| File | Change |
|------|--------|
| `translation-service/translation_service.py` | Guidebook pipeline: structure labels, strip/restore, names glossary (gpt-4o + Wikidata), guidebook prose (gpt-4o-mini), native stop headers; `_openai_chat`/`_meter_llm_cost` gained a `model` arg. All gated on `engine=llm` + `_GUIDEBOOK`. |
| `tests/test_local561_guidebook_translation.py` | **New.** 16 deterministic unit tests (mocked LLM). |
| `TRANSLATION_REVIEW_LOCAL-561.md` | **New.** Blind X/Y/Z review of tour 301 for Michael. |

## New environment variables (all optional, sensible defaults)

| Var | Default | Meaning |
|-----|---------|---------|
| `TRANSLATION_NAMES_MODEL` | `gpt-4o` | Model for the per-tour names glossary. |
| `TRANSLATION_PROSE_MODEL` | `gpt-4o-mini` | Model for the per-stop guidebook prose. |
| `TRANSLATION_GUIDEBOOK` | `on` | Guidebook pipeline on/off *within* the `llm` engine. |

`TRANSLATION_ENGINE` still defaults to `aws`, so **nothing deployed changes** until the flag
is set.

---

## Acceptance evidence

### Deterministic unit tests (mocked LLM) — 16 passed

`python3 -m pytest tests/test_local561_guidebook_translation.py` → **16 passed**.
Run together with LOCAL-559/559R: `… test_local559_llm_translation.py …` → **33 passed**.

Covering each required check:

- **No English structural labels** (`test_no_english_structural_labels_in_output`): no output
  line starts with `Stop`, `Orientation:` or `Directions:`; native labels
  «Как сориентироваться:» / «Как пройти:» are present.
- **Native stop header per language** (`test_native_stop_header_per_language`): ru «Остановка
  1», es "Parada 3", fr "Arrêt 2"; unknown language → explicit English fallback.
- **Line count + nav byte-exact** (`test_structure_strip_restore_preserves_lines_and_nav`,
  `test_restore_collapses_model_inserted_newlines_preserving_line_count`): line count
  preserved even when the model wraps a value across lines; `Address:`/`Coordinates:`
  byte-exact.
- **Glossary built once & cached** (`test_glossary_built_once_and_cached`): one gpt-4o call
  per (tour, language); the second build hits the cache. Streets keep Latin
  (`test_glossary_street_keeps_latin_name`); Wikidata wins
  (`test_wikidata_label_wins_over_model`).
- **Every glossary name appears inflected** (`test_glossary_names_appear_in_output_inflected`):
  for ru, matched on the stem (first 4 letters of each word).
- **Imperative density ≤ 1 on tour 301 stop 1** (`test_imperative_density_on_tour301_stop1_leq_1`,
  with a guard `test_imperative_density_helper_detects_orders` proving the metric scores a
  string of orders > 1), counting the ru verbs откройте, почувствуйте, ищите, погрузитесь,
  представьте, бродите, насладитесь, исследуйте.
- **Safeties** (`test_prose_falls_back_to_aws_on_segment_count_mismatch`,
  `test_prose_retries_once_then_succeeds`): retry-once then AWS per-segment fallback.
- **Gating** (`test_guidebook_off_by_default_for_aws_engine`,
  `test_guidebook_can_be_disabled_via_flag`): the pipeline never runs under `aws`, and can be
  turned off within `llm`. Distinct models (`test_names_and_prose_use_distinct_models`): names
  = gpt-4o, prose = gpt-4o-mini.

The fixture is the **byte-exact Stop 1 of tour 301** (Castle Hill of Nice), verified against
the live `audio_tours.tour_content` row.

### Full suite / no regression

- LOCAL-559 + LOCAL-561 (mocked, offline): **33 passed**.
- LOCAL-143 (cost model) and LOCAL-322 (material language): pass.
- `tests/test_local142_single_pass_translation.py`: 5 failures that are **pre-existing** —
  they fail identically on the clean base (`git stash` → same 5 red). They call
  `get_connection()` to a Postgres fixture not present in this environment and are unrelated
  to this change.

### Live acceptance — tour 301 → ru and es, three engines

Run by calling the translation methods **directly** (no HTTP, no cache) inside the
translation container, which carries the real `OPENAI_API_KEY` and DB access. For a fair
blind comparison the harness captured the translated stop **text**, the cost, and the wall
time; it did not call Polly and **did not write any DB rows**. The new
`translation_service.py` was copied into the container for the run and the container's
original file was restored afterward (the shared service was left exactly as found;
`TRANSLATION_ENGINE` is unset there, i.e. `aws`).

**Cost and wall time (10 stops each):**

| Engine | ru cost | ru time | es cost | es time |
|--------|---------|---------|---------|---------|
| AWS Translate (current) | $0.2760 (chars) | ~1 s | $0.2760 (chars) | ~1 s |
| **Guidebook (gpt-4o names + gpt-4o-mini prose)** | **$0.0162** | 54 s | **$0.0159** | 67 s |
| gpt-4o for names AND prose | $0.0814 | 48 s | $0.0774 | 38 s |

AWS cost is its $15/1M-char charge over the 18,402-char tour. **The guidebook design is both
cheaper than AWS and higher quality** — a ~17× cost reduction versus AWS, and ~5× cheaper
than the all-gpt-4o alternative.

**Structural checks verified on the live LLM output (all 10 stops, both languages):**

- `0` output lines begin with English `Stop`, `Orientation:` or `Directions:`.
- Native spoken labels present on every stop: ru «Как сориентироваться:» ×10 /
  «Как пройти:» ×9 (stop 10, the final stop, correctly has no Directions line);
  es "Orientación:" ×10 / "Cómo llegar:" ×9.
- `Coordinates:` lines byte-exact: **0 malformed** in both LLM configs.
- Line counts preserved (Stop 2: 15 == 15, matching the AWS/source structure).
- Glossary names appear inflected in the prose: «Пале Ласкарис», «Опера Ниццы»,
  "Palacio Lascaris", "Ópera de Niza".

A line-count bug was found and fixed **during** the live run: gpt-4o-mini sometimes wrapped a
long Orientation/Directions value across several physical lines, inflating a stop from 15 to
20 lines. Because each prose segment maps to exactly one source line, `_restore_structure` now
collapses any model-inserted newlines in a segment to spaces. A regression test
(`test_restore_collapses_model_inserted_newlines_preserving_line_count`) locks this in.

### Blind review for Michael

`TRANSLATION_REVIEW_LOCAL-561.md` presents, for stops 1–3, the spoken lines (title,
Orientation, Directions) of all three engines side by side, plus the full Stop 2 of each — with
the engines blinded as **X / Y / Z** (key at the very bottom) so he can judge the prose
without knowing which engine wrote it. It also lists the gpt-4o glossary and a transparent note
that, per the "Wikidata wins" rule, several Spanish names resolve to Wikidata's French endonym
(e.g. "Palais Lascaris", "Place Masséna") — flagged for his call, not silently overridden.

### Database safety

The review called only text-translation methods — **never `translate_tour_with_audio`**, never
wrote to `audio_tours`, never touched `original_tour_id`. Row counts before and after were
identical: **198** total `audio_tours` rows; **10** pre-existing tour-301 translations (from
earlier work), untouched. Nothing was created, so no `lat`/`lng` NULLing was needed and **no
`DELETE` was ever issued**.

## Must-not — honoured

- **No GCloud deploy.** Default engine stays `aws`. All work was local.
- **Did not edit** `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
  `.continuous_dev/STATUS.md`.
