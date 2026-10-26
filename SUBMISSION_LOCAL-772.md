# SUBMISSION — LOCAL-772: retire `gpt-3.5-turbo` on `subscribed` (D716)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-772-retire-gpt35-subscribed`
**Base:** `subscribed` @ `6d6aeed7` (`git merge-base --is-ancestor 6d6aeed7 HEAD` → 0)
**Ruling:** D716 — same as LOCAL-771. `gpt-3.5-turbo` → **gpt-4o-mini** everywhere;
the recall-pinned scope/restaurant checkers → **gpt-4.1-mini**. Env overrides still win.

---

## 1. Why

OpenAI retired `gpt-3.5-turbo` on 2026-10-26: a chat call with that model returns
`The model 'gpt-3.5-turbo' has been deprecated` (HTTP 404). On `subscribed`,
`CHECK_LLM_MODEL` / `WRITE_LLM_MODEL` / `TOUR_LLM_MODEL` are all unset in the
container, so every site whose fallback/default was `gpt-3.5-turbo` called a dead
model. Because the scope/verify gates **fail open** (see §4), the failure was
silent: the tour kept broken stops and shipped without fact sheets rather than
erroring loudly.

LOCAL-560 had already centralised the model choice for most checker/writer sites
behind `llm_models.py` (`check_model` / `write_model` / `held_model`). The two
checker gates that lost recall on gpt-4o-mini in the LOCAL-560 replay
(is-restaurant verify, geography/venue scope) were deliberately held on their
pinned model via `held_model("gpt-3.5-turbo", …)` — which is exactly the value
that is now dead.

## 2. The fix

**One central change rescues every resolver-routed site.** `llm_models.py` now
imports `live_model` from `llm_fallback.py` and passes every resolver result
through it:

| resolver | fallback used | retired input (env unset) resolves to |
|---|---|---|
| `check_model()` | `DEFAULT_FALLBACK` | `gpt-4o-mini` |
| `write_model(site_default="gpt-3.5-turbo")` | `DEFAULT_FALLBACK` | `gpt-4o-mini` |
| `held_model("gpt-3.5-turbo", site_env=…)` | `SCOPE_GATE_FALLBACK` | `gpt-4.1-mini` |

`live_model` returns any **live** model name unchanged, so a genuine env override
still wins; a **stale** override still naming a retired model is also rescued
(mapped to the fallback) rather than passed through to a 404. The
`site_default="gpt-3.5-turbo"` and `held_model("gpt-3.5-turbo", …)` literals are
kept at the call sites on purpose — they are the documented historical pins that
the resolver now maps live, and they keep a clean forward-merge story with
LOCAL-560.

`llm_fallback.py` is copied **byte-for-byte** from `origin/storied`
(`git show origin/storied:llm_fallback.py > llm_fallback.py`;
md5 `70695c906f6e4c0003f2dd002d0cf537`; `git diff --no-index` = identical), so the
file is the same on `storied` (LOCAL-771) and `subscribed` and a forward merge is
clean.

**Runtime sites that do NOT route through the resolvers** (bare
`"model": "gpt-3.5-turbo"` or `os.environ.get("TOUR_LLM_MODEL","gpt-3.5-turbo")`)
are rewritten to `live_model(os.environ.get("TOUR_LLM_MODEL", DEFAULT_FALLBACK))`,
or — for the standalone coordinate script-generators — emit `gpt-4o-mini`
directly, mirroring LOCAL-771:

- `describe_point_of_interest.py` — default param + call site
- `generate_tour_path.py` — fallback POI default + 2 call sites
- `tour_hook_generator.py`, `derepetition_guard.py`
- `generate_tour_text.py` — `_tour_llm_cost` pricing fallback + the `coord_fetch`
  geocode site (the resolver-routed writer/checker/held sites are handled by §2's
  central change)
- `get_coordinates_openai.py`, `import_tours_to_db.py`
- `coordinates_endpoint.py`, `add_coordinates_endpoint.py`,
  `add_coordinates_direct.py`, `verify_coordinates_endpoint.py`,
  `tools/coordinates_direct_tool.py`, `tools/coordinates_test_tool.py` → `gpt-4o-mini`
- `coordinates_fromAI/app.py`, `voice_control/app.py` → path-safe import of
  `llm_fallback` with an equivalent inline fallback (separate microservice
  containers that may not ship the repo-root module)
- `voice_nlp_service.py` — 2 call sites
- `directions_generator.py` — the two writer sites are
  `_write_model(site_default="gpt-3.5-turbo")` (rescued by §2); only the module
  docstring's "Uses GPT-3.5-turbo" wording was corrected.

**Left unchanged (intentional):** the *price* rows for `gpt-3.5-turbo` in
`cost_rates.py`, `cost_meter.py`, `cost_accumulator.py`, `reconcile_paid_api.py`,
`translation-service/*` and `_meter/*` — old logs are still priced against them.
`modified_generate_tour_text.py` still contains bare 3.5 literals but its service
is not wired into any compose file or Dockerfile (same call as LOCAL-771), so it
is not on a live path.

## 3. The fix is complete — no runtime site can still SEND a retired model

Verified two ways (see §5):
- **Resolver resolution** with every model env var unset: `check_model()`,
  `write_model(site_default="gpt-3.5-turbo")` and all three
  `held_model("gpt-3.5-turbo", …)` forms resolve to a **live** model.
- **AST scan** of the runtime modules: no retired model name survives as a bare
  `model` argument that bypasses the resolvers.

## 4. Per-site behaviour WHEN the call errored (fail open / fail closed)

Before this fix every one of these called the dead model; this is what each did
with the 404. This is why the breakage was silent — the gates fail **open**.

| Site (module) | Role | On a 3.5 404 it… | Fail-open / closed |
|---|---|---|---|
| `fact_extractor.generate_fact_sheet` | checker (extraction) | returns `None` → stop ships **without** a fact sheet (thin, ungrounded) | **fail-open** |
| `generate_tour_text` is-restaurant verify (`_held_model IS_RESTAURANT_MODEL`) | recall-pinned checker | returns `{"matches": True, …}` → keeps/accepts the stop | **fail-open** |
| `generate_tour_text` geography scope gate (`_held_model GEO_SCOPE_MODEL`) | recall-pinned checker | returns `(poi, True, "low", "API error … keeping")` → keeps out-of-scope stop | **fail-open** |
| `generate_tour_text` inside-venue scope gate (`_held_model VENUE_SCOPE_MODEL`) | recall-pinned checker | returns `(poi, True, "low", "API error — keeping stop")` → keeps the stop | **fail-open** |
| `generate_tour_text` other `_check_model()` JSON/list/rank/classify sites | checker | non-200 → empty/parse-fail → that check is skipped, pipeline continues | **fail-open** |
| `generate_tour_text` writer sites (`_write_model(site_default=…)`): style-retry, prolog, fact-rephrase, replacement/incremental JSON | writer | returns `""`/no JSON → that span is not written (missing narration / no replacement) | **fail-open (no output)** |
| `directions_generator.generate_real_directions` / `generate_walking_directions` | writer | non-200 → returns `""` → stop has no directions | **fail-open (no output)** |
| `describe_point_of_interest`, `generate_tour_path` POI/description + walking directions | writer | non-200 → `None`/empty description | **fail-open (no output)** |
| `tour_hook_generator.generate_tour_hook_audio` | writer | returns `""` → no spoken intro | **fail-open (no output)** |
| `derepetition_guard.rewrite_repeated_sentence` | writer (editor) | keeps the original (un-rewritten) sentence | **fail-open** |
| `get_coordinates_openai`, `import_tours_to_db.get_geo_coordinates`, `coordinates_endpoint`/`add_*`/`verify_*`, `coordinates_fromAI/app`, `tools/coordinates_*` | geocoder | non-200 → no coordinates for that location | **fail-open (no output)** |
| `voice_control/app`, `voice_nlp_service` (title / search-pattern) | helper | non-200 → falls back to raw text / no NLP title | **fail-open (no output)** |

No site **fails closed** (none rejects or hard-errors the tour on a model error).
That is the hazard D716 fixes: a fail-open checker on a dead model passes
everything, so the only visible symptom was degraded tours and 0/N fact sheets —
exactly what the live run below now shows as N/N.

## 5. Tests

New red test `tests/test_local772_retire_gpt35_subscribed.py` (two halves, because
on subscribed the literals are rescued by the resolvers rather than removed):

1. **Resolver unit test** — with every model env var unset, no resolver call form
   used at a runtime site returns a retired model; `held_model` maps the pin to
   `gpt-4.1-mini`; a live env override still wins; a stale retired override is
   rescued.
2. **Resolver-aware AST scan** — flags a retired model used as a bare `model`
   argument, but exempts literals handed to an `llm_models` resolver (those are
   rescued).

- On **branch**: `36 passed`.
- On **base** (`6d6aeed7`, with `llm_fallback.py` + the test present but the
  source changes reverted): `9 failed, 27 passed` — RED as required
  (`held_model`/`write_model` returned `gpt-3.5-turbo`; AST scan caught the bare
  literals).

Existing suites, **base vs branch** (temp detached worktree at `6d6aeed7`):

| Suite | base | branch |
|---|---|---|
| `tests/test_local560_checker_replay.py` + `test_local197_real_model_pricing.py` + `test_local143_cost_model_matches_deploy.py` + `test_d370_story_pass_model.py` | **29 passed** | **29 passed** |

Identical — no regression. (No existing test asserted a resolver returns
`gpt-3.5-turbo`, so none needed editing; none were deleted.)

## 6. Live container test — own image, isolated

Built `local772-tg:latest` from **this worktree** (`Dockerfile.generator`,
`GIT_SHA=6d6aeed7`, 737 files). Ran it isolated and never touched an `audioura-*`
container:

```
docker run --rm --name local772-tg --network development_default -p 5773:5000 \
  -e STORIED_MODE=true -e NARRATION_MODEL=gpt-4.1-mini -e TOUR_STORY_MODEL=gpt-4.1 \
  -e FAST_PIPELINE=1 -e RESEARCH_BACKEND=serper \
  -e DB_HOST=postgres-2 … -e OPENAI_API_KEY=<from ~/.env> \
  -e COST_HARD_LIMIT_USD=0.30 \
  local772-tg:latest python run_local772_container.py
```

`TOUR_LLM_MODEL` left **UNSET** on purpose (as in the subscribed container).
One 2-stop tour, "Watertown City Hall, Watertown MA".

Results (`/tmp/local772_run2.log`):
- resolver sanity (env unset): `check_model()→gpt-4o-mini`,
  `write_model(site_default=gpt-3.5-turbo)→gpt-4o-mini`,
  `held_model(gpt-3.5-turbo,…)→gpt-4.1-mini`
- **`[Storied] Fact sheets: 2/2 generated`**
- **No `404`, no `has been deprecated`, no `gpt-3.5` model call** (the only
  `gpt-3.5` strings in the log are the resolver sanity prints; the only
  `deprecated` strings are the pre-existing `[LOCAL-197] llm_cost() … total_tokens
  (deprecated)` internal cost-API warnings, unrelated to model retirement)
- **Total API cost $0.0326 ≤ $0.30**
- **audio_tours row count 523 BEFORE → 523 AFTER (DELTA 0)** — the driver does not
  write; the count proves no spurious insert
- DELIVERED 3584 chars

Container auto-removed (`--rm`); `audioura-tour-generator-1` left Up 11h healthy.

## 7. Process

- Branched from `subscribed` HEAD `6d6aeed7` (never `origin/*`); ancestry verified.
- Staged only the files this task touched (no `git add -A`). No `DELETE` of any
  kind. One docker build. Container stopped when done.
- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md.
