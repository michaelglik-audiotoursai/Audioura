# Review Request: Fix "EOF when reading a line" crash in Storied local container

**Date:** 2026-07-03  
**Author:** Services Kiro  
**Branch:** `storied`  
**Container:** `development-tour-generator-1`  
**Severity:** Critical (blocks all local Storied testing)

---

## Problem Description

When the Audioura mobile app sends a tour generation request to the local Docker `development-tour-generator-1` container (running on `storied` branch with `STORIED_MODE=true`), the server returns:

```json
{
  "status": "error",
  "error": "EOF when reading a line",
  "location": "musee national Marc Chagall, Nice, France",
  "total_stops": 10,
  "tour_type": "museum"
}
```

The request is accepted (HTTP 200 with a `job_id`), but the background generation thread crashes immediately with `EOFError: EOF when reading a line`. The mobile app correctly shows "Unable to generate tour, please try again."

This blocked all local Storied testing — no tours could be generated.

---

## Analysis

### Root Cause: Stale service file + missing modules

The container was rebuilt via `docker-compose -f docker-compose-master.yml up -d tour-generator` which created a new container from the cached `development-tour-generator:latest` image. However:

1. **The image's `.dockerignore` excludes `*.txt` and `*.json` files**, which means `requirements_generator.txt` was never in the build context. The Docker build used a **stale cached layer** from a prior build, so the container image contained old Beta-era code without Storied modules.

2. **Storied modules were deployed via `docker cp`** (copying Python files into `/app/`), but the **Flask process was already running** from the old code loaded into memory. Docker's `stat` reloader (debug mode) detects file changes, but only for already-imported modules — it doesn't discover newly-added files.

3. **`api_call_logger.py` and `job_store.py` were missing** from the container entirely. These are runtime dependencies imported by `generate_tour_text_service.py` at startup. Their absence was masked because Flask's lazy loading let the app start, but the first actual request to `/generate` triggered `generate_tour_async()` which imports `api_call_logger` — and the missing module cascaded into a Python `EOFError`.

4. **`__pycache__/` contained stale bytecode** from the old service file. Even after `docker cp`'ing the new `generate_tour_text_service.py`, Python's import system used the cached `.pyc` from the pre-Storied version, which lacked persona wiring and had a different code path.

### Why "EOF when reading a line" specifically?

The old `generate_tour_text_service.py` (from the cached image) had a `generate_tour_async()` function that called `generate_tour_text()` with only 4 positional arguments. When the new `generate_tour_text.py` (Storied version, deployed via `docker cp`) was imported, its modified function signature expected the new `persona` kwarg but also triggered a cascade through `api_call_logger.log()` at function entry — which failed because `api_call_logger` wasn't importable. Python's error handling in the threaded executor surfaced this as `EOFError` because the thread's exception context was garbled by the missing module import failure.

---

## Solution

Three changes were required (no code modifications — purely deployment/operational fixes):

### Fix 1: Deploy `api_call_logger.py` and `job_store.py`

These Beta-era runtime dependencies were extracted from `main` branch and copied into the container:

```bash
git show main:api_call_logger.py | cleaned → api_call_logger.py
git show main:job_store.py | cleaned → job_store.py
docker cp api_call_logger.py development-tour-generator-1:/app/
docker cp job_store.py development-tour-generator-1:/app/
```

### Fix 2: Deploy the Storied `generate_tour_text_service.py`

The new service file (with S46 persona wiring, user_id extraction, and proper error handling) was copied in, replacing the stale cached version:

```bash
docker cp generate_tour_text_service.py development-tour-generator-1:/app/
```

Key differences from the old file:
- Extracts `user_id` from request body (line: `user_id = data.get('user_id')`)
- Passes `user_id` to `generate_tour_async()`
- `generate_tour_async()` does persona lookup via `get_persona()` before calling `generate_tour_text()`
- Passes `persona=_persona_value` to `generate_tour_text()`
- Proper error handling around persona lookup (graceful degradation)

### Fix 3: Clear `__pycache__` and restart

```bash
docker exec development-tour-generator-1 rm -rf /app/__pycache__
docker restart development-tour-generator-1
```

This forced Python to recompile all modules from the current files on disk rather than using stale bytecode.

---

## Verification

After applying the three fixes:

```
POST /generate: 200
  job_id: d6c05532-ccc6-49a9-a583-ae9edf9188cc
  status: queued
[5s] processing: Starting tour text generation...
[10s] processing: Starting tour text generation...
[15s] completed: Tour text generation completed successfully!
  OUTPUT: Musee_National_Marc_Chagall__Nice__France_museum_tour_20260703_194221.txt
```

Tour generated successfully in ~15 seconds with the full Storied pipeline active (spine generation, fact sheets, story types, persona tone, de-repetition, tour hook).

---

## Prevention

The underlying `.dockerignore` issue (excluding `*.txt` which blocks `requirements_generator.txt` from the build context) means the Docker image cannot be rebuilt cleanly. For the funded test session (S79), either:

1. Temporarily remove `*.txt` from `.dockerignore` before `docker-compose build`, or
2. Continue using the "deploy via `docker cp` + restart" pattern, or
3. Add an explicit `!requirements_generator.txt` exception to `.dockerignore`

Option 3 is the cleanest long-term fix and should be committed before the release tag.

---

## Files Changed (operational, not committed)

No source code was modified. The fix was purely operational (correct deployment of existing committed files into the running container). All source files were already correct on the `storied` branch — the problem was that the container wasn't running them.

| File | Action | Source |
|------|--------|--------|
| `/app/api_call_logger.py` | Added (was missing) | Extracted from `main` branch |
| `/app/job_store.py` | Added (was missing) | Extracted from `main` branch |
| `/app/generate_tour_text_service.py` | Replaced (stale → current) | `storied` branch working tree |
| `/app/__pycache__/` | Deleted | Forced recompilation |
