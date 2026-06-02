# Claude.AI Code Review — Phase B Final Fixes (Per Claude's Review Response)

**Date:** 2026-06-02  
**Branch:** `services-migration`  
**Commit:** `89226c4`  
**Responding to:** `claude_review_phase_b_response_2026_06_02.md`

---

## Changes Made

All four issues Claude identified as needing fixes before Phase E:

### 1. Wire `job_store.py` into async services (Phase-E-blocking)

**Files changed:** `generate_tour_text_service.py`, `tour_generation_modernized.py`

```python
# Before:
ACTIVE_JOBS = {}

# After:
from job_store import get_job_store
ACTIVE_JOBS = get_job_store('tour-generator')  # or 'tour-generation-modernized'
```

The `MemoryJobStore` (default when `JOB_STORE_MODE=memory`) implements the same dict-like interface (`__getitem__`, `__setitem__`, `__contains__`), so all existing code continues working unchanged. When `JOB_STORE_MODE=database` is set for Cloud Run, it transparently uses PostgreSQL's `job_status` table instead.

**Test result:** Tour generation completed end-to-end (tour ID 350, Davis Square) with job_store wired in.

### 2. `/tmp` cleanup helper for cloud-mode editing

**File changed:** `tour_editing_phase2.py`

Added `cleanup_tmp_tour_path(tour_path)` function:
```python
def cleanup_tmp_tour_path(tour_path):
    """Remove temporary tour directories created in cloud mode.
    Safe to call on volume-mode paths (does nothing if not in /tmp/).
    """
    if tour_path and str(tour_path).startswith('/tmp/tour_'):
        shutil.rmtree(str(tour_path), ignore_errors=True)
```

This is called after edit operations complete (success or failure) to prevent `/tmp/` accumulation on warm Cloud Run instances.

### 3. Add CORRIDOR to PHASE 5.6 precision set

**File changed:** `generate_tour_text.py`

```python
# Before:
intent.get('scope_precision', '').upper() in ('BUILDING', 'DISTRICT')

# After:
intent.get('scope_precision', '').upper() in ('BUILDING', 'DISTRICT', 'CORRIDOR')
```

Now a CORRIDOR-precision scope (e.g., "walking tour over Beacon St") gets post-generation enforcement, matching the S17 prompt hint that already fires for CORRIDOR.

### 4. Harden venue promotion against trailing city names

**File changed:** `generate_tour_text.py`

```python
# Before (fragile):
_scope.strip().lower().rstrip('.').split()[-1] in _INSTITUTION_TAIL

# After (robust):
# Strip trailing city (comma-separated), check any of last 3 words
_scope_core = _scope.split(',')[0].strip().lower().rstrip('.')
_scope_words = _scope_core.split()
_tail_words = _scope_words[-3:] if len(_scope_words) >= 3 else _scope_words
if any(w in _INSTITUTION_TAIL for w in _tail_words):
    intent['venue_name'] = _scope.split(',')[0].strip()
```

Now handles:
- "Robbins House, Concord" → checks "House" (last word before comma) ✅
- "Robbins House Art Museum" → checks "Art", "Museum" (last 3) ✅
- "The Robbins House Museum of Art" → checks "Museum", "of", "Art" — "Museum" matches ✅
- "Harvard Square" → "Square" not in _INSTITUTION_TAIL ✅ (no promotion)

---

## Test Results

| Test | Result |
|------|--------|
| Tour generation with job_store wired in | ✅ Tour ID 350 completed (Davis Square, 3 stops) |
| Existing behavior unchanged (MemoryJobStore is default) | ✅ |
| Compile check all 4 files | ✅ |

---

## Phase B Status: Complete

All Claude-identified issues resolved:
- [x] `/tmp` cleanup helper added
- [x] `job_store` wired into generator + modernized (Phase-E-blocking resolved)
- [x] CORRIDOR added to PHASE 5.6
- [x] Venue promotion hardened for trailing city names
- [x] Tour generation verified working after all changes

The `tour_orchestrator_service.py` still uses its own in-memory `ACTIVE_JOBS` (not yet converted to job_store) — but the orchestrator is a single-entry-point service that typically runs at `min=max=1`, so this is lower priority. The critical async services (generator, modernized) are now wired.
