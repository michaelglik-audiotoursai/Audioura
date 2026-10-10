# SUBMISSION — LOCAL-664: Cheap arm per tour category (`CHEAP_ARM_CATEGORIES=museum`)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-664-cheap-arm-by-category`
**Base:** `subscribed` @ `07f6509d` (verified: `git merge-base --is-ancestor 07f6509d HEAD` → exit 0)

## Why (D645 follow-up)
`~/Audioura/COST_TIME_RESULTS_2026-10-09.md` (AB5–AB7) and `DECISIONS.md` D645:
`NARRATION_MODEL=gpt-4.1-mini` + `RESEARCH_BACKEND=serper` cut a 3-stop museum tour
from ≈ $0.50 to ≈ $0.30 at equal Kiro quality (5 pairs), but on the Boston WALKING
request it scored one point lower (6.5 → 5.5). LEAD wants the cheap arm ON for
**museum tours only**.

## What was delivered

### 1. New env `CHEAP_ARM_CATEGORIES` (comma list)
A single gate env, e.g. `CHEAP_ARM_CATEGORIES=museum` or `museum,facility`.

* **UNSET** → today's behaviour EXACTLY. `NARRATION_MODEL`, `NARRATION_PROVIDER`,
  `RESEARCH_BACKEND` apply to every tour whatever its category (byte-for-byte
  unchanged — the controlled env reads return the raw `os.environ` value).
* **SET** → those three envs apply ONLY when the current tour's category (the same
  `tour_category` that writes `Tour-Category:`) is in the list. For any other
  category the production defaults are used (OpenAI + `story_pass_model()` for
  narration; `gemini` for research).

### 2. Category known at every call site (contextvar, propagated into pools)
New module **`cheap_arm.py`**:
* Holds the current tour's category in a `contextvars.ContextVar`
  (`set_tour_category` / `tour_category`), set ONCE on the tour's own thread at
  generation start — the point in `_generate_tour_text_impl` where `tour_category`
  becomes final (right before the LOCAL-655 block).
* `effective_env(name, default)` is the ONE hook every controlled env read goes
  through. It returns the raw env when the gate is unset or the category is
  in-list, and the production default when the gate is set and the category is
  excluded.
* Propagation into thread-pool workers is automatic: `generate_tour_text` installs
  `cost_accumulator.install_executor_context_propagation()` at import, which runs
  every `ThreadPoolExecutor.submit` callable inside `contextvars.copy_context()` —
  copying this ContextVar along with the cost scope, exactly as LOCAL-651/656 rely
  on. An explicit `run_in_category_context` / `copy_category_context` helper
  (same shape as `dead_host_breaker.run_in_tour_context`) is provided for raw
  pools/threads that bypass that patch. **No module global holds the category**, so
  two concurrent tours of different categories never cross-contaminate.

Call sites wired to the gate:
* `narration_model_route()` in `generate_tour_text.py` (the narration/story-pass
  provider+model hook — the task's `_narration_provider_and_model()`).
* `research_backend()` in `story_leads.py` (serper vs gemini).
* The per-stop story pass and gates fan out through `ThreadPoolExecutor`; they read
  these two functions inside the workers and inherit the category via the patch
  above.

### 3. One log line per tour
At tour start, after the category is final:
```
[LOCAL-664] cheap arm: ON|OFF for category=<c> (categories=…; NARRATION_PROVIDER=…, NARRATION_MODEL=…, RESEARCH_BACKEND=…)
```
(When the gate is unset the line records `categories=UNSET — controlled envs apply
to all tours`.)

## Files
* `cheap_arm.py` — new module (gate, contextvar, `effective_env`, logging, pool helpers).
* `generate_tour_text.py` — `narration_model_route()` routes through `effective_env`;
  category set + decision logged once at tour start.
* `story_leads.py` — `research_backend()` routes through `effective_env`.
* `test_local664_cheap_arm_by_category.py` — new test suite.

## Tests
`python3 test_local664_cheap_arm_by_category.py` → **9 passed** (exit 0). Covers:
* museum → mini + serper (cheap arm ON);
* walking → production defaults (`openai` + `story_pass_model()`, `gemini`);
* gate UNSET → the envs apply to every category (museum, walking, restaurant,
  facility, unknown);
* gate SET without controlled envs → defaults everywhere;
* **two concurrent tours of different categories do NOT cross-contaminate** (fake
  workers under a barrier);
* contextvar propagation into a `ThreadPoolExecutor` worker via the cost_accumulator
  patch;
* explicit `run_in_category_context` helper for raw threads;
* log-line shape; category parsing edge cases (whitespace, dupes, empty/commas).

### Regression — full default suite (`python3 run_tests.py`)
Measured against the actual `subscribed` base `07f6509d` (both runs in matching
worktrees):
* Clean base (`07f6509d`): **492 passed, 67 failed, 4 infra-skipped** (563 total).
* This branch: **494 passed, 66 failed, 4 infra-skipped** (564 total).
* My change adds exactly one new passing suite
  (`test_local664_cheap_arm_by_category.py`, +1 total). Diffing the two failure
  sets shows **no failure attributable to this change**: the handful of tests that
  differ run-to-run (`test_d539_closure_regression.py`,
  `test_local313_dining_nominatim.py`, `test_local483_gate_fold_and_boundary.py`,
  `run_local189_style_ab_museum.py`) are live network tests (Gemini-with-sources,
  Nominatim, live generation) that flip on their own — none touch narration
  routing or research-backend selection. The net is one more pass, one fewer fail.

Related existing suites run green with the change:
* `tests/test_local648_serper_research.py` + `test_local631_concurrency_isolation.py` → 13 passed.
* `test_d370_story_pass_model.py` → 7 passed.

## Live
NONE paid. Behaviour proven with fakes (concurrent isolation + pool propagation).
No container run was needed.

## Guardrails honoured
No DELETE. No GCloud. No `docker compose -p audioura`; no `audioura-*` container
touched. DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE.md /
`.continuous_dev/STATUS.md` NOT edited.
