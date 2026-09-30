# SUBMISSION_GCS-KS1 — env kill switch for user-chosen stops

**Agent:** Services Kiro **Base:** storied (HEAD = `a4e7583`) **Branch:** `kiro/gcs-ks1`
**ClickUp:** `wdvrdayh4c` / D591 **Deploy:** nothing. Staged only; LEAD reviews, Michael approves, a separate task applies.

`git merge-base --is-ancestor a4e7583 HEAD` → exit 0 (verified before and after the commit).

---

## 1. What the switch is

A single environment flag, **`USER_STOPS_ENABLED`**, default **OFF**:

* `"true"` (case-insensitive, trimmed) → the feature is ON (today's behaviour, unchanged).
* unset / empty / anything else → OFF.

Read fresh on every request (never cached at import), so a single process can be exercised
both ways and tests can flip it. The gate lives in the new module **`user_stops_flag.py`**:

* `user_stops_enabled() -> bool`
* `neutralize_if_disabled(raw, *, request_id=None, field=None, log=None)`
  * ON → returns `raw` unchanged.
  * OFF → returns `None` (request then behaves exactly as if no stops were sent) and, **if `raw`
    was non-empty**, logs exactly one line recording the field was present and ignored, **with the
    count**, so we can see whether any installed app is still sending it.

Igor's code is **untouched**; nothing is deleted or reverted. The mobile app is **untouched**.

## 2. Entry points found (verified, not assumed)

I traced the field end to end. The app sends `user_stops`; internal services use `stops`
(LOCAL-547 accepts both at the orchestrator). The value that ultimately drives generation is
the engine's `forced_stops` (generate_tour_text.py:6837), which only activates when the list is
non-empty. So neutralizing the field at each **HTTP entry point** makes the whole feature inert —
including all the downstream `user_explicit` handling, which is gated on `_forced_stops_active`.

The live path is: **app → orchestrator → generator → engine** (thread mode), or
**app → orchestrator → Cloud Tasks → worker → generator** (cloud mode). The three services that
read the field off a request are the three I guarded:

| # | File | Line (approx) | Read | Guard |
|---|------|------|------|-------|
| 1 | `tour_orchestrator_service.py` | ~1583 | `data.get('stops')` then `data.get('user_stops')` in `/generate-complete-tour` | `_neutralize_user_stops(...)` before `validate_stops`. Because everything downstream (`orchestrate_tour_async`, `_enqueue_cloud_task`, the `stops is None` mode dispatch) is gated on the stops being non-empty, dropping it here makes the entire onward chain inert. |
| 2 | `generate_tour_text_service.py` | ~627 | `data.get('stops')` in `/generate` | `_neutralize_user_stops(...)` before `validate_stops` → `forced_stops`. Holds even if the generator is called directly. |
| 3 | `tour_worker_service.py` | ~505 | `data.get('stops')` in `/run-job` | `_neutralize_user_stops(...)` before `run_generation`. Defence-in-depth on the Cloud Tasks path (the orchestrator already drops it before enqueue). |

**Out of scope, confirmed by inspection:** `user_stops_validate.py` and `stop_route_sequencer.py`
are pure library modules that only act on a list handed to them as a function argument — they do
**not** read any request field, and grep shows they are referenced only by their own unit tests
(not wired into the live pipeline yet). `generate_tour_text.py` receives `forced_stops` as a
parameter; its `user_explicit` marks are all downstream of `_forced_stops_active`. A diagnostic-only
read (`generate_tour_text_service.py:"stops_raw": data.get('stops')`, logged to api_call_logger)
does not feed generation and is excluded.

When **ON**, all three simply pass the value through unchanged.

## 3. Local Docker keeps the feature (Mac Mini unaffected)

`USER_STOPS_ENABLED=true` set on every service that runs this code locally:

* `docker-compose-beta-local.yml` — `tour-generator`, `tour-orchestrator`, `tour-worker`.
* `docker-compose.yml` — `tour-orchestrator` (the only one of the three it runs).

## 4. Red → green, by effect (no OpenAI spend)

`tests/run_gcs_ks1_killswitch_evidence.py` runs the **real** orchestrator Flask app in-process
against a test client, with quota/DB/generation-thread stubbed (no network, no OpenAI). The
decisive observable is the `stops` value handed to generation.

**Request A — flag UNSET (default OFF).** App sends `user_stops=["Bell Tower","Rose Window","Crypt"]`:

```
HTTP 200: {"job_id":"...","language":"en","status":"queued"}
Stops handed to generation: None
[USER_STOPS_DISABLED] USER_STOPS_ENABLED is off — ignoring user-chosen stops present on the
request (field=user_stops, count=3, request_id=gcs_ks1_tester). Stops will be chosen the normal way.
[A] stops is None (generated the normal way): True
[A] ignore log line recorded with count: True
```

The stops the tour is built from are **not** the named ones (the field was dropped), and the ignore
line is logged with `count=3`.

**Request B — `USER_STOPS_ENABLED=true`.** Same request:

```
HTTP 200: {"job_id":"...","language":"en","status":"queued"}
Stops handed to generation: ['Bell Tower', 'Rose Window', 'Crypt']
[B] stops == the named stops: True
[B] no ignore line when ON: True
```

The named stops are honoured, as today, and no ignore line is emitted.

```
RESULT
OFF ignores + logs : True
ON honours + quiet : True
PASS — kill switch governs user-chosen stops by effect.
```

## 5. A test that fails if the switch is removed (D242)

`tests/test_gcs_ks1_user_stops_killswitch.py` — 12 tests, all green:

```
python -m pytest tests/test_gcs_ks1_user_stops_killswitch.py -q
............                                                             [100%]
12 passed in 1.21s
```

* `TestOrchestratorEntryPoint::test_flag_off_by_default_ignores_user_stops` asserts that with the
  flag unset, `user_stops` does **not** reach generation. `TestGeneratorEntryPoint` asserts the
  same at the generator `/generate` boundary, and both assert the ON path honours the stops.
* `TestFlagHelper` pins default-OFF and the log-once-with-count contract.

**Proof it goes red without the switch:** I temporarily bypassed the neutralizer in the orchestrator
(re-read the raw field after the guard) and re-ran just that class:

```
FAILED ...TestOrchestratorEntryPoint::test_flag_off_by_default_ignores_user_stops
FAILED ...TestOrchestratorEntryPoint::test_flag_off_explicit_ignores_user_stops
2 failed, 1 passed
```

The temporary bypass was reverted immediately and the suite is green again (12 passed).

## 6. No other code path reads the field unguarded (AC#4)

* **By inspection:** see the table in §2. The three HTTP entry points are the only server-side reads
  of the incoming `user_stops`/`stops` field; the library modules take an already-vetted list as a
  function argument and are not wired into the live pipeline.
* **By test:** `TestNoUnguardedReader` greps the three service files for `data.get('user_stops'|'stops')`
  and fails on any read that is not the argument to (or assigned to a variable neutralized by)
  `_neutralize_user_stops`, excluding comments and `*_raw` diagnostic reads. It also asserts each
  service imports the switch. Green.

## 7. Full suite totals (AC#3)

```
python -m pytest tests/ -q --continue-on-collection-errors
133 failed, 3160 passed, 10 skipped, 107 warnings, 129 errors in 1829.83s
```

(`--continue-on-collection-errors` was needed only because two unrelated files fail to *collect* —
`test_boston_globe_auth_enhanced.py` imports a name that no longer exists in `browser_automation`,
and `test_d587_dispatcher_allowlist.py` imports a missing `kiro_dispatcher` module. Neither is mine.
The 129 "errors" are collection/setup errors of that kind, mostly missing deps / `@pytest.mark.live`.)

**The four failures called out as not-mine — `test_local368/369/370/373`.** Running just those four
files:

* On my branch (`kiro/gcs-ks1`): **9 failed, 88 passed** — all 9 failures are in
  `test_local373_live_extraction_gap.py` (`TestParagraphRegexPictureExclusion`,
  `TestFetchPageDeduplication`, `TestFixtureAndLiveAlignment`).
* On `origin/storied` (a throwaway detached worktree at `c5c5b7c`, **without** my change):
  **9 failed, 88 passed** — the identical 9 test IDs.

Identical before and after my change, so they are pre-existing and not introduced by GCS-KS1.
(368/369/370 pass; the named-but-passing ones are simply grouped in the same call.)

## 8. Staged deploy only — dry-run (AC#5)

`./deploy_storied_generator.sh --dry-run` (Git Bash) completed with **nothing changed**. The three
`*-storied` services each carry `USER_STOPS_ENABLED=false`:

* `tour-generator-storied` — `--set-env-vars '...,TOUR_TRACK=storied,USER_STOPS_ENABLED=false,DB_HOST=...'`
* `tour-modernized-storied` — `--set-env-vars 'TOUR_STORAGE_MODE=cloud,USER_STOPS_ENABLED=false,BLOB_STORAGE_TYPE=r2,...'`
* `tour-orchestrator-storied` — `--update-env-vars 'TOUR_TRACK=storied,USER_STOPS_ENABLED=false,TOUR_GENERATOR_URL=...,MODERNIZED_URL=...'`

and the run ends with: `dry run complete — nothing changed. No Beta service was named.`
(Full command block pasted in the task transcript; the orchestrator uses `--update-env-vars`, so the
flag is added without disturbing its other ~20 env vars.)

Note: the script's own `assert_image_content_clean` guard refuses to tag while unrelated `.py`
working-tree changes exist (two pre-existing deletions, `temp_auth_test.py` / `temp_iframe_test.py`,
not mine). I stashed **only** those two paths to obtain the dry-run, then `git stash pop` restored
them — no shared state was altered.

## 9. Process compliance

* **Deployed nothing.** No `docker push`, no `gcloud run deploy`, no store build. Dry-run only.
* Branched off `storied` HEAD (`a4e7583`, includes the regex fix `19358ae`). Committed; **not merged**.
* Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  `GCLOUD_STORIED_START_HERE.md`, `HANDOFF_20260924_MORNING.md`, `BUILD_NUMBERS.md`.
* Local only: no production DB writes, no `DELETE FROM audio_tours`.
* Windows: new files written UTF-8; the deploy script was run in Git Bash.

## Files changed

* **new** `user_stops_flag.py` — the gate.
* `tour_orchestrator_service.py`, `generate_tour_text_service.py`, `tour_worker_service.py` — guarded entry points.
* `docker-compose-beta-local.yml`, `docker-compose.yml` — `USER_STOPS_ENABLED=true` locally.
* `deploy_storied_generator.sh` — `USER_STOPS_ENABLED=false` on the three `*-storied` services.
* **new** `tests/test_gcs_ks1_user_stops_killswitch.py`, `tests/run_gcs_ks1_killswitch_evidence.py`.

## Blocking question

None. The task was completable as specified.
