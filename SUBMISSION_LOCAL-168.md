##### READY FOR REVIEW

## LOCAL-168 — Re-adopt tour-editing-phase2 into compose (image rebuilt first)

### Commit

See `git log --oneline storied..HEAD` for hash.

### Summary

`tour-editing-phase2-1` was orphaned from compose — a `docker compose up -d` would
have created a duplicate on port 5022. The obvious fix (force-recreate from the
existing image) would have silently dropped the `update-stop` and `job-status` routes
added by LOCAL-151 (they lived only in the container's writable layer, not in the
image). This task rebuilt the image first so those routes survive recreation.

### What was done

1. **Confirmed source contains both routes** — `grep -c update-stop tour_editing_phase2.py` → 2
2. **Rebuilt `audioura-tour-generator:latest`** — `docker compose -f docker-compose-master.yml build tour-generator`
3. **Verified new image** — `docker run --rm --entrypoint sh audioura-tour-generator:latest -c "grep -c update-stop /app/tour_editing_phase2.py"` → 2
4. **Removed orphaned container** — `docker stop tour-editing-phase2-1 && docker rm tour-editing-phase2-1`
5. **Created through compose** — `docker compose -f docker-compose-master.yml up -d tour-editing-phase2`
6. **Verified adoption** — dry-run reports `Running`
7. **Verified all six routes** — structured JSON on all, no generic 404s

### Files changed

| File | Action | Lines |
|------|--------|-------|
| `SUBMISSION_LOCAL-168.md` | Created | this file |

No server code changes — the source was already correct (LOCAL-153 committed the shims).

### Evidence: Source routes present

```
$ grep -c update-stop tour_editing_phase2.py
2

$ git show storied:tour_editing_phase2.py | grep -c update-stop
2
```

### Evidence: New image contains routes

```
$ docker run --rm --entrypoint sh audioura-tour-generator:latest \
    -c "grep -c update-stop /app/tour_editing_phase2.py"
2
```

### Evidence: Route table BEFORE (container from writable layer)

| # | Route | Method | HTTP | Body (truncated) | Kind |
|---|-------|--------|------|------------------|------|
| 1 | `/health` | GET | 200 | `{"status":"healthy",...}` | structured |
| 2 | `/tour/<id>/update-multiple-stops` | POST | 400 | `{"error_code":"VALIDATION_FAILED","message":"Tour stops data is required..."}` | structured |
| 3 | `/tour/<id>/edit-info` | GET | 404 | `{"error_code":"TOUR_NOT_FOUND",...}` | structured |
| 4 | `/tour/<id>/download` | GET | 404 | `{"error_code":"TOUR_NOT_FOUND",...}` | structured |
| 5 | `/tour/<id>/update-stop` | POST | 400 | `{"error_code":"VALIDATION_FAILED","message":"stop_number and new_text are required",...}` | structured |
| 6 | `/tour/<id>/job-status/<jobId>` | GET | 200 | `{"status":"completed","tour_id":"test123","job_id":"job456",...}` | structured |

### Evidence: Route table AFTER (compose-created from rebuilt image)

| # | Route | Method | HTTP | Body (truncated) | Kind |
|---|-------|--------|------|------------------|------|
| 1 | `/health` | GET | 200 | `{"service":"tour_editing_phase2","status":"healthy","version":"1.2.6.234"}` | structured |
| 2 | `/tour/<id>/update-multiple-stops` | POST | 400 | `{"error_code":"VALIDATION_FAILED","message":"Tour stops data is required..."}` | structured |
| 3 | `/tour/<id>/edit-info` | GET | 404 | `{"error_code":"TOUR_NOT_FOUND",...}` | structured |
| 4 | `/tour/<id>/download` | GET | 404 | `{"error_code":"TOUR_NOT_FOUND",...}` | structured |
| 5 | `/tour/<id>/update-stop` | POST | 400 | `{"error_code":"VALIDATION_FAILED","message":"stop_number and new_text are required",...}` | structured |
| 6 | `/tour/<id>/job-status/<jobId>` | GET | 200 | `{"status":"completed","tour_id":"test123","job_id":"job456",...}` | structured |

All six routes return structured JSON (not generic Flask HTML 404). Feature preserved.

### Evidence: Compose adoption confirmed

```
$ docker compose -f docker-compose-master.yml up -d --dry-run tour-editing-phase2
 Container development-postgres-2-1 Running
 Container tour-editing-phase2-1 Running
```

`Running` — not `Creating`. Compose owns the container.

### Evidence: Container count unchanged

```
Before: docker ps -q | wc -l = 23
After:  docker ps -q | wc -l = 23
```

### Evidence: audioura-tour-generator-1 undisturbed

```
Before: audioura-tour-generator-1 | Up 2 hours (unhealthy)
After:  audioura-tour-generator-1 | Up 2 hours (unhealthy)
```

Uptime unbroken. Rebuilding the image does not affect running containers — only the
next recreate of `audioura-tour-generator-1` will pick up the new image.

### Rollback command

```bash
cd /Users/micha/Audioura
docker compose -f docker-compose-master.yml stop tour-editing-phase2
docker compose -f docker-compose-master.yml rm -f tour-editing-phase2
# To restore the pre-rebuild orphaned state (not recommended):
# docker run -d --name tour-editing-phase2-1 -p 5022:5022 \
#   -e DB_HOST=postgres-2 -e DB_NAME=audiotours -e DB_USER=admin \
#   -e DB_PASSWORD=password123 -e DB_PORT=5432 \
#   audioura-tour-generator:latest \
#   sh -c "pip install boto3 --quiet && python tour_editing_phase2.py"
```

### Limitations

1. **`audioura-tour-generator-1` will pick up the new image on next recreate.**
   The rebuild updated `audioura-tour-generator:latest` which that container also
   uses. Its current running state is unaffected (uptime unbroken), but the next
   `docker compose up -d tour-generator` or force-recreate will start it from the
   new image. This adds the tour-editing shim routes to its image but does not
   change its runtime behavior (it runs `generate_tour_text_service.py`, not
   `tour_editing_phase2.py`).

2. **`audioura-tour-generator-1` shows `unhealthy`.** This predates this task and
   is unrelated — its health state was already `unhealthy` before any changes.

3. **Subscribed containers (`subscribed-orchestrator`, `subscribed-generator`)
   remain orphaned.** Per task instructions, they are a separate concern.
