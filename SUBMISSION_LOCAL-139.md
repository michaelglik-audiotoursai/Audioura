##### READY FOR REVIEW

# LOCAL-139: Make it impossible for a test suite to create a user-visible tour

**Commit:** `df881a0` on branch `kiro/local139-test-tours-must-flag`
**Base:** `storied`

---

## 1. Root cause — why tour 132 was unflagged while 100/101/105/106 were not

The inconsistency is in `tour_orchestrator_service.py` lines 1274-1282.
The `/generate-complete-tour` endpoint has a **security gate** for `is_test`:

```python
_is_test_raw = data.get('is_test')
_server_test_mode = os.getenv('TOUR_TEST_MODE', 'false').lower() == 'true'
_allow_request_flag = os.getenv('TOUR_TEST_MODE_ALLOW_REQUEST', 'false').lower() == 'true'
if _is_test_raw and (_server_test_mode or _allow_request_flag):
    is_test_override = True
else:
    is_test_override = None  # falls back to env var (also false)
```

The test suites (`test_local49_tour_content_persist.py` etc.) send
`"is_test": True` in the HTTP body, but the orchestrator **silently drops
it** unless `TOUR_TEST_MODE=true` is set inside the Docker container. That
env var is ephemeral — it's set by `TestTourHelper.__init__()` in the
*host-side* test process, but Docker containers don't inherit it.

Tours 100, 101, 105, 106 were flagged because at the time of those runs,
someone had set `TOUR_TEST_MODE_ALLOW_REQUEST=true` in the container
environment (or the container was restarted with it). Tour 132 was created
during a run where it was **not** set. Same test suite, same code, different
outcome — purely environmental.

---

## 2. Every place a test creates a row in `audio_tours`

| File | Method | Flagged? |
|------|--------|----------|
| `tests/test_tour_helper.py` | Direct INSERT with `is_test=TRUE` literal | ✅ Always |
| `tests/test_local128_stop_metrics_tourid.py` | Direct INSERT with `is_test=true` literal | ✅ Always |
| `tests/test_local49_tour_content_persist.py` | HTTP to orchestrator with `"is_test": True` body | ⚠️ Depends on Docker env |
| `tests/test_translation_implementation.py` | HTTP to orchestrator with `"is_test": True` body | ⚠️ Depends on Docker env |
| `tests/test_user_tracking_fix.py` | HTTP to orchestrator with `"is_test": True` body | ⚠️ Depends on Docker env |
| `tests/test_user_integration.py` | HTTP to orchestrator with `"is_test": True` body | ⚠️ Depends on Docker env |
| `tests/test_user_tracking_simple.py` | HTTP to orchestrator with `"is_test": True` body | ⚠️ Depends on Docker env |
| `tests/run_local98_evidence.py` | HTTP to orchestrator with `"is_test": True` body | ⚠️ Depends on Docker env |
| `tests/test_tour_quota_integration.py` | HTTP to orchestrator (no `is_test` param) | ❌ Never flagged |

The ⚠️ rows are the bug class. The caller *thinks* it's being safe by
passing `is_test`, but the server-side gate silently drops it.

---

## 3. What was built

### `tests/test_tour_factory.py` — TestTourFactory

A replacement for `TestTourHelper` that makes the safe path structural:

- **No `is_test` parameter.** Every `INSERT` hardcodes `TRUE`. The unsafe
  path (is_test=FALSE) requires raw SQL outside the factory — and the guard
  will catch it.
- **`adopt_and_ensure_flagged(tour_id)`** — for HTTP-path tests that must go
  through the orchestrator. After the tour is created, this forces
  `is_test=TRUE` directly in the DB regardless of what the orchestrator did.
- Cleanup nulls lat/lng (never DELETEs), only touches IDs it created.

### `tests/test_no_unflagged_test_tours.py` — Guard test

Runs the D38 guard query:
```sql
SELECT id FROM audio_tours
WHERE tour_name ~ '(LOCAL[0-9]+|Regression Test|Acceptance Test|Selective Test|NoFlag Test)'
  AND is_test IS NOT TRUE
```
Fails (RED) if any row matches. Part of normal suite — no one needs to
remember to run it.

### `tests/test_local139_acceptance.py` — Proof

Demonstrates all four requirements in sequence.

### `tests/test_tour_helper.py` — Docstring update

Backward compat preserved; docstring points to the new factory.

---

## 4. Per-file changes

```
 tests/test_local139_acceptance.py   | 195 +++++++++++++++
 tests/test_no_unflagged_test_tours.py|  97 ++++++++
 tests/test_tour_factory.py          | 212 +++++++++++++++++
 tests/test_tour_helper.py           |   4 +- (docstring only)
```

---

## 5. Evidence

### 5a. Factory creates with is_test=TRUE (no caller involvement)

```
TEST 1: Factory creates tour with is_test=TRUE (no parameter for it)
  Created tour id=141
  DB row: id=141, is_test=True, lat=47.6098, lng=-122.3423
  ✅ PASS — is_test=TRUE without caller asking for it
```

### 5b. Guard goes RED on unflagged row

```
TEST 2: Unflagged test-named row → guard goes RED
  Inserted deliberately unflagged row: id=142, is_test=FALSE
  tour_name: LOCAL139 NoFlag Test 1785705263
  Guard query result: 1 unflagged row(s)
  → id=142 is_test=False name=LOCAL139 NoFlag Test 1785705263
  ✅ PASS — guard correctly detects unflagged test-named tour (RED)
```

### 5c. Guard goes GREEN after fix (row NOT deleted — set is_test=TRUE)

```
TEST 3: Set is_test=TRUE → guard goes GREEN
  UPDATE audio_tours SET is_test = TRUE WHERE id = 142
  Rows updated: 1
  Guard query result after fix: 0 unflagged row(s)
  ✅ PASS — guard is GREEN after setting is_test=TRUE
```

### 5d. adopt_and_ensure_flagged works

```
TEST 4: adopt_and_ensure_flagged forces flag on externally-created tour
  Created unflagged orphan: id=143
  Before adopt: is_test=False
  factory.adopt_and_ensure_flagged(143) → updated=1
  ✅ PASS — adopted tour now has is_test=TRUE
```

### 5e. Row counts

```
  audio_tours count BEFORE: 101
  audio_tours count AFTER:  104
  Rows added: 3 (all flagged is_test=TRUE, lat/lng nulled on cleanup)
  Guard: GREEN (0 unflagged test-named tours)
```

---

## 6. Limitations

1. **Existing HTTP-path tests not refactored.** The 6 suites that call the
   orchestrator still pass `"is_test": True` in the request body and still
   depend on the Docker env var to honor it. They should be updated to call
   `factory.adopt_and_ensure_flagged()` after receiving the tour ID. This
   commit provides the tool; migrating each suite is a separate PR.

2. **The orchestrator's security gate is not changed.** The gate (refusing
   to honor `is_test` from untrusted callers in production) is correct
   security design — the problem was that tests relied on it working when
   it's explicitly designed NOT to work without server-side opt-in. The fix
   is on the test side, not the service side.

3. **No Docker builds.** Per constraint, the orchestrator container was not
   rebuilt or env-var-patched. The fix is host-side: the factory and guard
   operate at the DB level.
