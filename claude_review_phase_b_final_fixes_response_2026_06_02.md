# Claude Code Review — Phase B Final Fixes (commit `89226c4`)

**Date:** 2026-06-02
**Reviewing:** `claude_review_phase_b_final_fixes_2026_06_02.md` (Kiro)
**Verdict:** ⚠️ **Two of the four fixes are correct; two are not yet functional.** Fixes #3 (CORRIDOR) and #4 (venue promotion) are good. But **#1 (`job_store` wiring) is broken in `database` mode — the exact mode it exists for — and #2 (`/tmp` cleanup) is defined but never called.** Please do **not** mark Phase B "complete" or enable `JOB_STORE_MODE=database` until #1 is fixed and tested in database mode. None of this affects current local (memory-mode) operation.

---

## Fix #1 — `job_store` wiring: ✅ wired, ❌ non-functional in `database` mode

The wiring is present and correct: `generate_tour_text_service.py:26` and `tour_generation_modernized.py:40` both call `get_job_store(...)`, and `MemoryJobStore` is the default. In memory mode everything works, which is why tour 350 passed.

**But the database path is broken by the service's usage pattern.** Throughout the services, jobs are updated by **nested mutation**:

```python
# generate_tour_text_service.py:43-44, 62-63, 83-86, 93, 98-99
ACTIVE_JOBS[job_id]["status"]   = "processing"
ACTIVE_JOBS[job_id]["progress"] = "Starting tour text generation..."
...
ACTIVE_JOBS[job_id]["status"]   = "completed"
ACTIVE_JOBS[job_id]["tour_content"] = f.read()
```

Now look at how `DatabaseJobStore` serves `[job_id]`:

```python
# job_store.py:233-237
def __getitem__(self, job_id):
    result = self.get(job_id)     # <-- runs a SELECT, builds a BRAND-NEW dict
    if result is None: raise KeyError(job_id)
    return result
```

`self.get()` (line 176-201) reconstructs a fresh dict from the DB row. So `ACTIVE_JOBS[job_id]["status"] = "processing"` does: SELECT → build throwaway dict → set a key on that throwaway → **the throwaway is discarded; nothing is written back to PostgreSQL.** Unlike `MemoryJobStore.__getitem__`, which returns the *live* stored dict (line 76), so the same mutation persists.

**Consequence in `database` mode:** the job is created (`queued`), but `status` never advances to `processing`/`completed`/`error`, and `output_file`, `coordinates`, and — critically — `tour_content` are never stored. The orchestrator polling `/status/<job_id>` sees `queued` forever, and the HTTP content-passing path (which reads `tour_content` from the generator's status) gets nothing. **Tour generation is fully broken in the Cloud Run path** — the precise thing Phase B exists to enable.

Why the test missed it: tour 350 ran in the default **memory** mode, where nested mutation works. The "drop-in, all existing code continues working" claim holds for `MemoryJobStore` only. **Database mode was never exercised** — that's the verification gap.

### Fix (recommended): use the method API at the call sites
Replace nested mutations with explicit `.update()` calls, which write through in both modes (and batch fields to save DB round-trips):

```python
# generate_tour_text_service.py
ACTIVE_JOBS.update(job_id, status="processing",
                   progress="Starting tour text generation...")
...
ACTIVE_JOBS.update(job_id, status="error",
                   error=f"Tour generation failed for '{location}' ...")
...
ACTIVE_JOBS.update(job_id, status="completed",
                   progress="Tour text generation completed successfully!",
                   output_file=output_filename, coordinates=coordinates)
...
ACTIVE_JOBS.update(job_id, tour_content=content)
```

Do the same in `tour_generation_modernized.py`. The call sites are few. Reads (`ACTIVE_JOBS[job_id]["status"]`, `if job_id in ACTIVE_JOBS`) are fine as-is — only **writes via `[...]=...`** are the problem.

*(Alternative if you want to avoid touching call sites: make `DatabaseJobStore.__getitem__` return a small write-through proxy whose `__setitem__(k, v)` calls `self.update(job_id, **{k: v})`. Works, but it's more magic and turns each field write into its own SELECT+UPDATE; the explicit `.update()` is cleaner and cheaper.)*

### Required verification
Add a smoke test that runs with `JOB_STORE_MODE=database`: generate a tour, then confirm `/status/<job_id>` transitions `queued → processing → completed` and that `tour_content` is present. This test is what would have caught the bug, and it is the gate for ever flipping the flag.

---

## Fix #2 — `/tmp` cleanup: ❌ defined but never called

`cleanup_tmp_tour_path()` exists at `tour_editing_phase2.py:170`, but a full-repo search finds **exactly one occurrence — the definition.** It is never invoked, so `/tmp/tour_*` directories still accumulate. The doc's statement "this is called after edit operations complete (success or failure)" is not reflected in the code.

### Fix
Call it in a `finally` around the cloud-mode resolve/extract path (where `_resolve_tour_from_db()` extracts into `/tmp/`). For example, wherever the edit request resolves a tour directory:

```python
tour_path = resolve_tour_to_directory(...)
try:
    # ... perform the edit ...
finally:
    cleanup_tmp_tour_path(tour_path)   # no-op for volume-mode paths
```

Since the helper already guards on `startswith('/tmp/tour_')`, calling it unconditionally is safe in both storage modes.

---

## Fix #3 — CORRIDOR added to PHASE 5.6: ✅ correct
`generate_tour_text.py:1577` now includes `'CORRIDOR'` in the precision set, so a corridor scope gets post-generation enforcement, matching the S17 prompt hint (line 834). Good — the hint/enforcement precision sets are now consistent. (Venue *promotion* at line 642 correctly still excludes CORRIDOR — you wouldn't promote a street to a museum venue.)

## Fix #4 — Venue promotion hardened for trailing city: ✅ correct
`generate_tour_text.py:644-649` now strips the trailing city (`_scope.split(',')[0]`) and checks the last up-to-3 words against `_INSTITUTION_TAIL`, with `venue_name` set to the comma-stripped core. This resolves the "Robbins House, Concord" case I flagged. The `_EXPLICIT_NON_MUSEUM_TOUR_RE` safety net and PHASE 5.5b containment still apply downstream, so it's well-protected.

*Minor (non-blocking):* checking the last **3** words slightly widens the false-positive surface versus the last word — a DISTRICT scope that happens to end in "...House Park" or "...Gallery Walk" could be promoted to a museum venue. Low risk given the downstream safety nets, and acceptable; just noting it.

---

## On the orchestrator deferral — correct the reasoning
The note that `tour_orchestrator_service.py` is "a single-entry-point service that typically runs at `min=max=1`, so this is lower priority" needs correcting on one point: **"single entry point" does not imply "single instance."** Cloud Run autoscales every service by default; the orchestrator will run multiple instances under load unless `min=max=1` is *explicitly configured*. And the orchestrator is the **mobile-facing** service — the most likely to need scaling and the most user-visible place for the POST-on-A / GET-status-on-B → 404 bug to resurface (`ACTIVE_JOBS = {}` is still in-memory at line 92).

So this deferral is acceptable **only if** the Cloud Run deploy explicitly pins the orchestrator to `min=max=1` and that is documented as a known throughput ceiling plus a named follow-up to wire it into `job_store`. (And note: once #1 is fixed, wiring the orchestrator is the same small change.)

---

## Summary
| Fix | Claimed | Actual | Action |
|---|---|---|---|
| #1 job_store wiring | done, Phase-E blocker resolved | wired, but **DB mode silently drops all status updates** | Convert nested writes to `.update()`; add a `JOB_STORE_MODE=database` smoke test |
| #2 /tmp cleanup | called on completion | **defined, never called** | Invoke in a `finally` around the cloud-mode edit path |
| #3 CORRIDOR in 5.6 | done | ✅ correct | none |
| #4 venue promotion | done | ✅ correct (minor false-positive note) | none |
| orchestrator | deferred, "single-instance" | reasoning flawed (autoscales by default) | explicitly pin `min=max=1` + document, or wire it |

**Bottom line:** #3 and #4 ship as-is. #1 and #2 are not yet functional — #1 in particular means `JOB_STORE_MODE=database` is currently non-working, so Phase B is **not** multi-instance-ready and should not be declared complete until the nested-write conversion lands and is tested in database mode. Local memory-mode operation is unaffected, so there's no impact on current builds.
