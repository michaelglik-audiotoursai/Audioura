##### READY FOR REVIEW

## LOCAL-153 — Fold Tour-Editing Shims Into Source Before Rebuild Erases Them

### Commit

```
3b7981e LOCAL-153: Fold tour-editing shims into source before rebuild erases them
```

### Summary

LOCAL-151 added `update-stop` and `job-status` shim routes to the running
`tour-editing-phase2-1` container via `docker cp`. The fix works but lives only
in the container's writable layer — any rebuild or recreation silently loses both
routes. This commit folds those shims into the repo source so the image will
include them on next rebuild.

### What was done

1. Applied `patches/LOCAL-151-tour-editing-shims.py` to `tour_editing_phase2.py`
   in the repo, making source match the container exactly.
2. Proved source matches container via `diff` (result: empty).
3. Added guard test `tests/test_local153_tour_editing_shims_guard.py` that:
   - Imports the Flask app and checks `app.url_map` (D35: exercise, don't inspect)
   - Break-probe confirms test catches route absence (D36: print replacement count)
   - 7 assertions, all pass

### Evidence: Diff repo vs container (empty)

```
$ docker cp tour-editing-phase2-1:/app/tour_editing_phase2.py /tmp/container_final.py
$ diff tour_editing_phase2.py /tmp/container_final.py
(empty — files match)
```

### Evidence: Test passes with routes present

```
$ python3 tests/test_local153_tour_editing_shims_guard.py

======================================================================
test_local153_tour_editing_shims_guard.py
LOCAL-153: Tour-editing shim routes (update-stop, job-status) guard
======================================================================

[BREAK PROBE] Verifying test detects missing routes
  Replacement count (update-stop decorator): 1
  PASS: Break-probe: update-stop found in source for removal
  Replacement count (job-status decorator): 1
  PASS: Break-probe: job-status found in source for removal
  PASS: Break-probe: update-stop absent in broken copy
  PASS: Break-probe: job-status absent in broken copy

[URL_MAP GUARD] Verifying shim routes registered in Flask app
  File: /Users/micha/audioura-worktrees/LOCAL-153/tour_editing_phase2.py
  PASS: Flask app loads
  PASS: POST /tour/<tour_id>/update-stop registered in url_map
  PASS: GET /tour/<tour_id>/job-status/<job_id> registered in url_map

  Registered routes containing 'update-stop' or 'job-status':
    {'POST'} /tour/<tour_id>/update-stop
    {'GET'} /tour/<tour_id>/job-status/<job_id>

======================================================================
Results: 7 passed, 0 failed
======================================================================
```

### Evidence: Break-probe fails with routes removed

The break-probe creates a copy with route decorators commented out, loads
it, and confirms `url_map` no longer resolves either path:
- `Break-probe: update-stop absent in broken copy` — PASS
- `Break-probe: job-status absent in broken copy` — PASS

Replacement counts both 1 (not 0 — probe applied, per D36).

### Evidence: HTTP routes still answer

```
$ curl -s -X POST http://localhost:5022/tour/fake-id-999/update-stop \
  -H "Content-Type: application/json" -d '{"stop_number": 1, "new_text": "test edit"}'
{"error_code":"TOUR_NOT_FOUND","message":"Tour with ID 'fake-id-999' could not be found for bulk save operation","recoverable":false,"status":"error","suggested_action":"Please verify the tour ID and try again, or contact support"}

$ curl -s http://localhost:5022/tour/fake-id-999/job-status/fake-job-123
{"job_id":"fake-job-123","message":"Operation completed synchronously","status":"completed","tour_id":"fake-id-999"}
```

### Evidence: Container not restarted

Before (start of task):
```
tour-editing-phase2-1 Up About an hour
```

After (end of task):
```
tour-editing-phase2-1 Up About an hour
```

### Evidence: git status clean

```
$ git status --short
(empty)
```

### Files changed

| File | Change |
|------|--------|
| `tour_editing_phase2.py` | MODIFIED — added 68 lines (update-stop + job-status shims) |
| `tests/test_local153_tour_editing_shims_guard.py` | NEW — url_map guard test with break-probe |

### Limitations

1. **Test mocks heavy dependencies.** The guard test mocks `boto3`, `psycopg2`,
   `flask_cors`, and `requests` because they are not installed on the host.
   This is safe — the test only needs Flask's route registration machinery,
   which is real. The mocks do not affect route registration.

2. **No integration test against the live container.** The test imports the
   source file and checks `url_map` locally. It does not HTTP-probe the running
   container. The HTTP evidence above is manual; the automated test uses the
   app import pattern from LOCAL-134.

3. **Shim behaviour unchanged.** Per the task constraint, shim logic was not
   altered. The `update-stop` shim delegates to `bulk-save` via `test_client`;
   `job-status` returns `{"status": "completed"}` unconditionally. Both match
   LOCAL-151's accepted design decisions.
