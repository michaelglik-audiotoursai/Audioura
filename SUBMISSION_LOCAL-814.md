# SUBMISSION — LOCAL-814

**Gemini "credit empty" (402) retried on every tour; `story_leads` ignored `RESEARCH_BACKEND=serper`**

Base: `subscribed` (55994cab) · Branch: `LOCAL-814-gemini-breaker`

---

## The bug

Gemini prepaid credit is depleted. On 2026-10-29 the Mac meter logged **329 Gemini
402s in one day** — 237 from `story_leads.py:380`, 57 from `story_leads.py:326`,
35 unattributed — **during runs with `RESEARCH_BACKEND=serper`**. GCloud_Storied's
key accounting showed 749×402 on the Mac key that day. Two root causes:

1. **No memory of a dead credit.** A 402 "prepayment credits are depleted" /
   `RESOURCE_EXHAUSTED` is an *account* state, not a transient blip — asking again
   a second later gets another 402. Every caller re-issued to the dead credit on
   every tour, adding latency and degrading output.
2. **The LEAD step ignored the cheap arm.** Grounded research already honours
   `RESEARCH_BACKEND=serper` through `research_with_sources`, but the LEAD
   fan-out (`story_leads.run` → `PROVIDERS['gemini'](prompt)`, called from
   `generate_tour_text.py`'s step-4 cross-model block) called `_gemini`
   **directly, ungrounded, regardless of the backend**. That is exactly the
   `story_leads.py:326`/`:380` ungrounded path that produced the 57+237 402s on
   the serper arm.

## The fix

### 1. A process-wide circuit breaker — `gemini_breaker.py` (new)

- `is_open()` — True means "skip Gemini, use the fallback". Checked by callers
  **before** issuing a request.
- `note_response(status, body)` — called with every Gemini HTTP status. A **402
  trips the breaker for 30 min**; a **429 for 2 min** (env-overridable via
  `GEMINI_BREAKER_402_MINUTES` / `GEMINI_BREAKER_429_MINUTES`). Any other status
  is ignored.
- **In-process + cross-process.** A trip opens a module-level singleton *and*
  UPSERTs one row into a small additive table `gemini_breaker_flag`, so sibling
  task containers sharing the same depleted key see the open state and stop too.
  `is_open()` checks the free in-process state first, then the DB flag
  (best-effort, 1 s timeout).
- **Logs exactly once** per trip edge: `[LOCAL-814] gemini disabled 30m: credit
  depleted` (or `disabled 2m: rate limited`). Re-confirming an already-open
  breaker is silent.
- **One `failure_events` row per trip edge (D723)** via `failure_log.record`.
  The message names the credit refusal ("out of credit / payment required"), so
  the nightly `failure_triage` classifies it as **`budget`** — the credit
  sub-owner of the `external` family, i.e. the ticket's **external/credit** — and
  the 429 trip classifies as `external`. (Verified against
  `failure_triage.classify_event`.)
- **Never raises** into a caller; **default-safe** (a healthy key never trips);
  `GEMINI_BREAKER_DISABLE=1` is a hard escape hatch.

### 2. Wired into the two Gemini HTTP sites — `story_leads.py`

- `_gemini` and `gemini_with_sources`: **skip when the breaker is open** (return
  `''` / an honest-empty `{…, 'error': 'gemini breaker open …'}`) so callers fall
  back to their non-Gemini path.
- Both sites call `note_response(status, body)` on the response (tripping on
  402/429) and `gemini_with_sources` also trips on the raised exception, so a
  402 surfaced by `raise_for_status()` still opens the breaker.

### 3. The leads path now honours `RESEARCH_BACKEND=serper` — `story_leads.py`

- `available_providers()` drops `gemini`/`gemini_grounded` when
  `research_backend() == 'serper'` **or** the breaker is open. The step-4 caller
  then sees fewer than two model families and **skips the fan-out gracefully**
  (its existing behaviour) — **zero Gemini calls**.
- `run()` applies the same filter even when a caller passes an explicit
  `providers=[…]` list naming gemini — belt-and-braces, guaranteeing zero Gemini
  calls on the serper arm.

## Tests

`tests/test_local814_gemini_breaker.py` — 16 tests, all pass, fully offline (the
Gemini POST is monkeypatched; no network, no DB):

- **Breaker:** 402→~30 min, 429→~2 min, 200 never trips; reset/expiry close it;
  `GEMINI_BREAKER_DISABLE=1` is a no-op; `status_from_error` extracts 402/429.
- **Record-once:** one `failure_events` row per trip edge; the 402 row classifies
  as `budget` (external/credit) and the 429 row as `external`.
- **Wiring:** a mocked 402 trips the breaker, and the next `_gemini` /
  `gemini_with_sources` calls **issue no further HTTP POST**.
- **Serper routing:** `available_providers()` → `['openai']` on the serper arm;
  `run()` issues **zero** gemini / gemini_grounded provider calls on the serper
  arm (asserted via a metered mock counting `PROVIDERS` invocations), even with
  an explicit `providers=['openai','gemini','gemini_grounded']`; default arm
  still calls gemini; an open breaker likewise drops gemini from the leads path.

## Regression

- `tests/test_local648_serper_research.py`, `test_local594_grounding_cost.py`,
  `test_local645_gemini_per_venue.py`, `test_local533_grounding_count.py`,
  `test_local664_cheap_arm_by_category.py`, `test_local692_artist_stories.py`,
  `test_local814_gemini_breaker.py` → **83 passed**.
- `test_local603_meter_and_l2.py`, `test_local674_serper_plus.py`,
  `test_local678_meter_httpx_aiohttp.py`, `test_local804_failure_triage.py` →
  **56 passed**.
- **One pre-existing failure, not caused by this change:**
  `test_local597_guard.py::test_ungrounded_gemini_not_blocked_by_guard`. It fails
  **identically at baseline** — swapping in the committed `story_leads.py` gives
  `1 failed, 12 passed` both ways. Cause: the depleted **live** `GEMINI_API_KEY`
  in `.env` makes a real 402 on the test's ungrounded `_gemini` call, which
  `raise_for_status()` raises as `HTTPError` (an environmental error, not the
  guard's `GroundingForbiddenError`). With no live key the test passes. The
  baseline `_gemini` raised the same 402; this change does not introduce it.

## Live (to run in own containers, paid-API cap $0.40 TOTAL)

One tour with the REAL (depleted) Gemini key and `RESEARCH_BACKEND=serper` should
complete, and the meter should show **0 Gemini calls**: the leads path drops
gemini on the serper arm, and if any residual grounded step touched Gemini the
first 402 trips the breaker so every subsequent call is skipped for 30 minutes.

## Files

- `gemini_breaker.py` (new) — the circuit breaker.
- `story_leads.py` — breaker hooks + wiring into `_gemini` / `gemini_with_sources`;
  `available_providers()` / `run()` honour the serper arm and the open breaker.
- `tests/test_local814_gemini_breaker.py` (new) — the unit suite.

## Notes

- No `DELETE` of user data; `gemini_breaker_flag` is a single additive row the
  breaker owns (reset deletes only that row). DB writes are best-effort, 1 s
  timeout, never stall a generation.
- Did not touch DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md,
  TRAVEL_PROJECTS.md. Did not write the live DB. Pre-existing `UU` unmerged files
  in the worktree (`audio_tour_app/pubspec.lock`, `db_step1_stored.txt`,
  `db_step2_retrieved_bytes.txt`) are not part of this change and were not staged.
