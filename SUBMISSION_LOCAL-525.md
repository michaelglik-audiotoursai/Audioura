# SUBMISSION — LOCAL-525: Expose user-chosen stops through the HTTP API

**Branch:** LOCAL-525-user-stops-api
**Base:** storied (e1341e6)
**Agent:** Mac Mini Kiro

## Summary

The engine already accepts an exact, ordered stop list:
`generate_tour_text(..., forced_stops=[...])` (LOCAL-357). It was deliberately
walled off at the HTTP layer because it was built as a verification harness, not
a product feature.

This change **promotes it to a product feature**. The `/generate` endpoints now
accept an optional `stops: [...]` list, validate it, and pass it through to the
engine's `forced_stops` path. When `stops` is omitted, behaviour is byte-for-byte
unchanged.

Motivation (Michael, 2026-09-23): Igor visited the MFA, recorded the stops he
wanted, and could not get them into a tour. Cramming them into the free-text
request string was cumbersome and not reliably honoured.

## What changed

### 1. `generate_tour_text_service.py` (tour-generator, the service that calls the engine)
- Added `validate_stops(raw)` → `(clean_list_or_None, error_or_None)`.
  - `None`/missing → `(None, None)` — normal generation, NOT an error.
  - Non-empty list of non-empty strings → stripped list, order preserved.
  - Not-a-list / empty list / non-string element / blank element / >50 entries →
    `(None, clear_message)`. Never silently ignored.
- `/generate` reads `data.get('stops')`, validates it, returns **400** with the
  message on failure, and threads the validated list to `generate_tour_async`.
- `generate_tour_async(...)` now takes `forced_stops=` and passes it to
  `generate_tour_text(..., forced_stops=forced_stops)`.
- When a stop list is present, `total_stops` is set to `len(stops)` so job
  tracking and the downstream count invariant agree with what the engine will
  actually generate (the engine sets `total_stops = len(forced_stops)`).

### 2. `tour_orchestrator_service.py` (the product entry point, /generate-complete-tour)
- Added the same `validate_stops(...)`, but each name is run through the existing
  `sanitize_input()` (same filesystem/injection safety every other user string
  gets).
- Parses `stops`, returns **400** on malformed input, stores it in the job, and
  forwards it to the tour-generator as `generate_data["stops"]`.
- `orchestrate_tour_async(...)` gained a `stops=None` parameter, threaded through
  both thread-mode spawns.
- Quota interaction: when `stops` is provided, `total_stops = len(stops)` **before**
  the quota check, so the visitor is metered for what they asked for. If the plan
  would clamp the count below the list length, the request is **rejected (429)**
  with an actionable message rather than silently dropping stops — silent
  truncation is exactly the "not reliably honoured" failure this ticket fixes.
- Cloud Tasks path: the enqueue path (`_enqueue_cloud_task` / tour-worker) does
  not yet carry a stop list. Rather than silently drop it, a request **with**
  stops runs in thread mode (which forwards them end-to-end). Requests without
  stops keep the configured mode unchanged. Default mode is `thread`.

### 3. `tests/test_local357_forced_stops.py` (test REPLACED, not deleted)
The old class `TestForcedStopsEndToEndStructure` asserted the HTTP API and the
orchestrator **must NOT** expose `forced_stops`. That decision was correct when
`forced_stops` was only a harness. LOCAL-525 changes the decision on evidence, so
those two assertions are **replaced** by `TestUserChosenStopsAPIContract`, whose
class docstring records the full history and reason. The new contract asserts:
- the service and orchestrator DO expose a validated `stops` input and forward it;
- a clean ordered list is accepted, stripped, order preserved (acceptance #1);
- malformed input is rejected with a clear message (acceptance #2);
- omitting `stops` is not an error and yields no forced list (acceptance #3);
- the orchestrator sanitizes each entry.

The engine-level LOCAL-357 tests (parameter exists, injection, gates not weakened,
banner, normal path unchanged) are retained untouched.

## Acceptance criteria

1. **POST accepts `{location, tour_type, stops:[...]}` and generates exactly those
   stops, in order.** — The validated list is passed to the engine as
   `forced_stops`, which bypasses candidate generation and injects the exact list
   in order (existing LOCAL-357 behaviour, now reachable from the API). Verified at
   the HTTP layer with the Flask test client (forwarded arg =
   `['Gallery A','Sculpture Court']`, stripped and ordered).
2. **Malformed input rejected with a clear message, never silently ignored.** —
   `validate_stops` returns a specific message for each malformed shape; both
   endpoints return HTTP 400 with it. Verified for not-a-list, empty list,
   non-string element, and blank element.
3. **Omitting `stops` behaves exactly as today.** — `validate_stops(None)` returns
   `(None, None)`; the engine receives `forced_stops=None` and runs the normal
   path. Verified (200, `forced_stops` arg is `None`).
4. **The old test is REPLACED, not deleted, and says why.** — See
   `TestUserChosenStopsAPIContract` and the updated module docstring.

## How verified

- `python3 -m py_compile generate_tour_text_service.py tour_orchestrator_service.py` → OK.
- `python3 -m pytest tests/test_local357_forced_stops.py -q` → **20 passed**
  (includes the new contract class, which imports and exercises both services and
  the engine signature).
- HTTP-layer proof via `svc.app.test_client()` with the background thread mocked:
  acceptance #1/#2/#3 all confirmed (see ticket notes / session log).

## Notes / scope

- The Flutter client is not modified here; this ticket is the HTTP API. The
  contract (`stops: [string, ...]`) is additive and backward-compatible.
- The Cloud Tasks enqueue path was intentionally left to fall back to thread mode
  when stops are present, to avoid a partial worker plumbing change; that can be a
  follow-up if cloud_tasks mode needs native stop-list support.
