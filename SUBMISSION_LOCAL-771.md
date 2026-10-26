# SUBMISSION — LOCAL-771: Retire `gpt-3.5-turbo` on `storied`

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-771-retire-gpt35-storied`
**Base:** `storied` @ `354da345` (verified: `git merge-base --is-ancestor 354da345 HEAD` → exit 0)
**Ruling:** D716 (LEAD)

---

## 1. What broke and why

OpenAI retired `gpt-3.5-turbo` on 2026-10-26. A chat call with that model now returns
`The model 'gpt-3.5-turbo' has been deprecated` (HTTP 404). `TOUR_LLM_MODEL` is unset
everywhere, so every runtime site that defaulted to `gpt-3.5-turbo` — and every site
that hard-coded it — failed. On GCloud test tour 448 (Watertown) this showed as
`Fact sheet API error: 404`, `[Storied] Fact sheets: 0/1 generated`, and
`Stop 1 para 1: retry API error 404 → keeping original`.

## 2. Fix (per D716)

A new tiny, dependency-free module **`llm_fallback.py`**:

```python
RETIRED_MODELS      = {"gpt-3.5-turbo", "gpt-3.5-turbo-0301", … , "gpt-3.5-turbo-instruct"}
DEFAULT_FALLBACK    = "gpt-4o-mini"      # every runtime call that would send a retired model
SCOPE_GATE_FALLBACK = "gpt-4.1-mini"     # the two LOCAL-560 checker sites (recall dropped on 4o-mini)

def live_model(name, fallback=DEFAULT_FALLBACK):
    # retired name (or empty) -> fallback; any live name returned unchanged
```

Every runtime site now reads
`live_model(os.environ.get("TOUR_LLM_MODEL", DEFAULT_FALLBACK))` (scope/verify gates use
`SCOPE_GATE_FALLBACK`). An env override still wins; `live_model` is applied on top so a
stray env var still set to a retired model is also rescued. Only the *fallback* changed.

**Scope/verify gates → `gpt-4.1-mini` (D716 exception):**

| Site (generate_tour_text.py) | Function | Gate |
|---|---|---|
| geography scope check | `_validate_stops_within_scope` | geography scope gate |
| venue scope check | `_validate_museum_stop_descriptions` | venue scope gate |
| is-restaurant verify | `verify_poi_matches_type` | is-restaurant verify |

All other runtime sites → `gpt-4o-mini`.

## 3. Per-gate behaviour at the time of the retirement (fail open / fail closed)

What each failing site did while the `gpt-3.5-turbo` call errored — i.e. what Stable
tours shipped without since the retirement. **Fail open** = the error was swallowed and
the stop/content passed through unchecked; **fail degraded** = the content it was meant
to add was simply dropped (tour continues, thinner).

| Site | File | On error it… | Classification |
|---|---|---|---|
| Geography scope gate | `generate_tour_text.py` `_validate_stops_within_scope` | returns `inside=True` ("API error … keeping") | **fail OPEN** — out-of-scope stops kept |
| Venue scope gate | `generate_tour_text.py` `_validate_museum_stop_descriptions` | returns `inside_venue=True` ("keeping stop") | **fail OPEN** — wrong-venue stops kept |
| Is-restaurant verify | `generate_tour_text.py` `verify_poi_matches_type` | returns `{"matches": true}` | **fail OPEN** — non-restaurants kept |
| Fact sheets | `fact_extractor.py` | returns `None` (`Fact sheet API error: 404`) | **fail DEGRADED** — stop ships with no fact sheet (the GCloud `0/1 generated`) |
| Style / de-repetition rewrite | `derepetition_guard.py` `rewrite_repeated_sentence` | returns the original sentence | **fail OPEN** — repetition left in |
| Directions (museum + outdoor) | `directions_generator.py` (×2) | returns `""` → fallback `"Continue to {next}."` | **fail DEGRADED** — generic directions |
| Tour hook | `tour_hook_generator.py` | returns `""` | **fail DEGRADED** — no spoken intro |
| Style retry (LOCAL-192/194) | `generate_tour_text.py` | keeps the pre-retry paragraph | **fail DEGRADED** — style violation left in |
| Prolog / rank / preview passes | `generate_tour_text.py` | keep original / skip | **fail DEGRADED** |
| Coordinate helpers | `get_coordinates_openai.py`, `import_tours_to_db.py`, `coordinates_fromAI/app.py`, generated endpoints | return no coords | **fail DEGRADED** — stop may lack a map pin |
| Voice command → search NLP | `voice_nlp_service.py`, `voice_control/app.py` | fall back to raw command | **fail DEGRADED** |

The three **fail-open** gates are the serious ones: since the retirement, Stable shipped
tours whose geography-scope, venue-scope and restaurant-type checks silently passed
everything. They now call live models again.

## 4. Files changed (19 — no `git add -A`)

**New (2):**
- `llm_fallback.py` — the fallback module.
- `tests/test_local771_retire_gpt35.py` — the red test (below).

**Modified runtime modules (17):**
`generate_tour_text.py`, `fact_extractor.py`, `derepetition_guard.py`,
`directions_generator.py`, `describe_point_of_interest.py`, `generate_tour_path.py`,
`tour_hook_generator.py`, `get_coordinates_openai.py`, `import_tours_to_db.py`,
`voice_nlp_service.py`, `voice_control/app.py`, `coordinates_fromAI/app.py`,
`coordinates_endpoint.py`, `verify_coordinates_endpoint.py`, `add_coordinates_direct.py`,
`add_coordinates_endpoint.py`, `tools/coordinates_direct_tool.py`.

Replacement styles:
- **Importable runtime callers** route through `live_model(...)` / `DEFAULT_FALLBACK`
  (scope gates `SCOPE_GATE_FALLBACK`).
- **Sub-directory micro-services** (`voice_control/app.py`, `coordinates_fromAI/app.py`)
  import the repo-root module when present (adding repo root to `sys.path`) and otherwise
  use an equivalent inline fallback, so a separate service container that does not ship
  `llm_fallback.py` still never sends a retired model.
- **Code-fragment / script-generators** (`coordinates_endpoint.py`,
  `verify_coordinates_endpoint.py`, `add_coordinates_*.py`,
  `tools/coordinates_direct_tool.py`) embed the model name inside a code *template* string
  (they write out a standalone script); there the embedded `gpt-3.5-turbo` was replaced
  with `gpt-4o-mini` directly.
- The `_tour_llm_cost` pricing helper default was moved to `DEFAULT_FALLBACK` (wrapped in
  `live_model`) so a call is priced at the model it actually used, not at 3.5 rates.

## 5. Deliberately left alone (with reasons)

- **`cost_rates.py`** — keeps its `gpt-3.5-turbo` *price* rows so old logs still price
  correctly. Not a runtime model selection. Untouched.
- **`geocode_stops.py`** — its only `gpt-3.5-turbo` is in a comment describing another
  file; no runtime model literal. Untouched.
- **`add_coordinates_to_tour.py`** — no `gpt-3.5-turbo` literal at all.
- **`run_local*` one-off scripts** — measurement scripts, not on any live path; left alone
  per ticket.
- **`modified_generate_tour_text.py`** — has 3 `gpt-3.5-turbo` literals and **is** imported
  by `modified_generate_tour_text_service.py`. **But** that service is **not** referenced in
  `docker-compose.yml` nor in any `Dockerfile` `CMD`. The live tour-generator
  (`Dockerfile.generator`) runs `generate_tour_text_service.py`, which imports the **real**
  `generate_tour_text.py` (fixed here). So `modified_generate_tour_text.py` is off every
  live/deployed path; left alone per the ticket's "leave it unless something imports them;
  say which." Flagging it here for LEAD: if `modified_generate_tour_text_service.py` is ever
  wired up, that file needs the same treatment.

## 6. Tests

**`tests/test_local771_retire_gpt35.py`** (red → green):

- An **AST scan** over every runtime module listed in the ticket. It fails if a retired
  model name appears as a `model` argument — either a direct literal
  (`model="gpt-3.5-turbo"` / `"model": "gpt-3.5-turbo"`) **or** embedded in a code-template
  string next to a `model` key (the script-generator case). Docstrings and loose prose /
  comment mentions are excluded.
- `live_model("gpt-3.5-turbo") == "gpt-4o-mini"`, scope-gate fallback == `gpt-4.1-mini`,
  live names pass through unchanged, empty → default, and the env-override pattern
  (`live_model(os.environ.get("TOUR_LLM_MODEL", DEFAULT_FALLBACK))`) is respected.

**On base (354da345):** 17 runtime modules FAIL the scan (literals present),
`geocode_stops.py` and `add_coordinates_to_tour.py` pass (no literal), 5 behaviour tests
pass. → **RED**, as required.

**On branch:** `24 passed` (19 module scans + 5 behaviour). → **GREEN**.

## 7. Regression — base vs branch (identical, no regression)

Run with the user's Python 3.9 / pytest 8.4.2. `test_sq4_merge.py` and
`test_palais_fix_lead_fixture.py` are standalone scripts (they `sys.exit()` at module end),
so they are run as `python3 <file>`, not under pytest.

| Suite | Base (354da345, via `git stash`) | Branch |
|---|---|---|
| `test_sq4_merge.py` | ALL TESTS PASSED | ALL TESTS PASSED |
| `test_palais_fix_lead_fixture.py` | 23/23 assertions hold | 23/23 assertions hold |
| `test_d370_story_pass_model.py` + `test_local411` + `test_local389` + `test_local407` | 52 passed | 52 passed |

Branch-only additional green: the red test (24), broader generate_tour_text tests
(`local24_regression`, `local27_truthfulness`, `local403`, `local419`, `local410` — 24
passed), and all 7 modified importable runtime modules import cleanly.

Runtime smoke of the selection pattern:

| `TOUR_LLM_MODEL` | default site | scope/verify gate |
|---|---|---|
| unset | `gpt-4o-mini` | `gpt-4.1-mini` |
| `gpt-4o` | `gpt-4o` | `gpt-4o` (override wins) |
| `gpt-3.5-turbo` (stray) | `gpt-4o-mini` (rescued) | `gpt-4o-mini` (rescued) |

## 8. Live test — my own container, one Watertown tour

Built my own image from this worktree and ran it isolated — never touched an `audioura-*`
container, never used `-p audioura`:

```
docker build -f Dockerfile.generator --build-arg GIT_SHA=LOCAL-771 -t local771-tg:latest .
docker run -d --rm --name local771-tg -p 5772:5000 --env-file ~/Audioura/.env -e STORIED_MODE=true local771-tg:latest
```

In-image verification: `llm_fallback.py` present, `live_model("gpt-3.5-turbo") = gpt-4o-mini`,
`0` `model …gpt-3.5-turbo` lines in `/app/generate_tour_text.py`. Health: `status healthy,
mode=true, version 2.2.0.1, code_sha=LOCAL-771`.

Request: `POST /generate {"location":"Watertown City Hall, Watertown MA",
"tour_type":"landmark","total_stops":2}` → job `b82bc93c`.

**Log evidence (pasted):**

```
[Storied] STORIED_MODE=true — generating spine + fact sheets...
SPINE_COST: category=walking venue=Watertown City Hall, Watertown model=gpt-4o tokens=1250 (in=839 out=411) cost=$0.0062
  [Storied] Fact sheets: 2/2 generated
  [LOCAL-576] Pre-writing scope check against 'Watertown City Hall, Watertown MA' (2 stop(s), want 2)...
  [LOCAL-576] Pre-writing scope check: all 2 stop(s) within 'Watertown City Hall, Watertown MA'.
Stop 1 API call cost: $0.0261 (5489 tokens, model=gpt-4o)
Stop 2 API call cost: $0.0261 (5488 tokens, model=gpt-4o)
```

- **`Fact sheets: 2/2 generated`** — N/N with N = 2 ≥ 1. ✔
- **No `404`, no model `deprecated`.** The only `deprecated` lines in the whole log are the
  unrelated `[LOCAL-197] llm_cost() called with total_tokens (deprecated)` signature
  warnings; grepping `404|deprecated` excluding those is empty. ✔
- **No `gpt-3.5` usage anywhere** in the log. ✔
- Models used: `gpt-4o` for the spine + stop story pass (pre-existing D186/D370 behaviour —
  the story pass runs on gpt-4o regardless). The fact-sheet and gate paths that used to hit
  `gpt-3.5-turbo` now resolve to live models and **succeeded** (fact sheets 2/2).

**Cost:** summed itemised LLM cost ≈ **$0.066** (spine $0.0062, stop 1 $0.0261, stop 2
$0.0261, plus small classification/retry/triage) — well under the $0.30 budget.

**audio_tours row count:** **BEFORE 523, AFTER 523 (unchanged)** — queried on
`development-postgres-2-1` (`audiotours` DB). The generator service writes `stop_metrics`
in STORIED_MODE, never `audio_tours`; and the container was run isolated (no shared docker
network), so its post-generation persistence step could not reach the test DB
(`audiotours_test` at `localhost:5433`) — that is why the job stayed `processing` after the
text + fact sheets had completed. This confirms **no write to the live `audio_tours`
table**.

Container stopped (`--rm` removed it); all `audioura-*` containers left running and
untouched.

## 9. Process compliance

- Branched from local `storied` HEAD (`354da345`), never from `origin/*`.
- No `git add -A`; only the 19 files above are committed.
- No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`, `.continuous_dev/`,
  `SUBSCRIBED_COMMUNICATION_01.MD`, `legal/`, `GCLOUD_STORIED_START_HERE.md`.
- No `DELETE` of anything. One heavy docker build. Container stopped when done.
