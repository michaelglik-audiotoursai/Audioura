##### READY FOR REVIEW

# LOCAL-108: Unwired Audit — Find Everything Defined and Never Called

**Branch:** `kiro/local108-unwired-audit`  
**Commit:** `737726a`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-01

---

## Summary

Systematic audit across all four categories found **8 UNWIRED** findings (features
that exist in code but have no live call path), **13 DEAD** (safe to remove), and
**8 INTENTIONAL** (correctly unwired for known reasons).

The three most severe UNWIRED findings are:
1. Three Flask Blueprints (`persona_bp`, `referral_bp`, `sharing_bp`) are defined,
   correct, and never registered — identical to the LOCAL-106 `register_preference_routes` pattern.
2. `register_preference_routes` itself is STILL not called (LOCAL-107 did not fix this one — it fixed a different wiring issue).
3. Two `except ImportError` blocks on health endpoints silently swallow the cost
   ceiling monitor — the exact pattern that hid corpus mining for two days.

---

## Per-File Changes

| File | Change |
|------|--------|
| `UNWIRED_AUDIT.md` | New — full audit document with 4 category tables, verdicts, justifications, proposed tasks, and limitations statement |
| `SUBMISSION_LOCAL-108.md` | New — this file |

---

## Acceptance Evidence

### AC1: All four categories audited with counts

| Category | UNWIRED | DEAD | INTENTIONAL |
|----------|---------|------|-------------|
| 1. register/init/setup functions | 1 | 4 | 5 |
| 2. Orphan modules (no importer) | 5 | 10 | — |
| 3. Dead public functions | 9 | 2 | — |
| 4. Silent `except ImportError` | 2 | 1 | 3 |

### AC2: Every UNWIRED row justified

Each UNWIRED finding in `UNWIRED_AUDIT.md` includes:
- Why it should be called (what feature it implements)
- What breaks because it is not called (user-visible failure mode)
- A proposed task (not a patch)

### AC3: Explicit statement of what the method cannot detect

Six limitations stated in the "What This Method Cannot Detect" section:
dynamic dispatch, external deployment scripts, mobile-to-server calls,
template references, Cloud Run differences, import-time side effects.

### AC4: Zero production files modified

```
git diff --stat storied..HEAD
```
Shows only `UNWIRED_AUDIT.md` and `SUBMISSION_LOCAL-108.md` — two new documents.

---

## Verbatim Evidence

### Evidence: `register_preference_routes` has zero call sites

```
$ grep -rn "register_preference_routes" --include="*.py"
./swipe_preference_service.py:302:def register_preference_routes(app):
```

One result — the definition itself. Zero calls.

### Evidence: Three Blueprints never registered

```
$ grep -rn "persona_bp\|referral_bp\|sharing_bp" --include="*.py" | grep -v "persona_endpoints.py\|referral_endpoints.py\|sharing_endpoints.py"
(empty — zero results)
```

No file outside the definition files references these Blueprint objects.

### Evidence: `get_operation_cost` write-only

```
$ grep -rn "get_operation_cost" --include="*.py"
./cost_meter.py:168:def get_operation_cost(job_id: str) -> Optional[dict]:
```

One result — the definition. Zero callers.

### Evidence: Silent ImportError in health checks

```python
# generate_tour_text_service.py:428-432
try:
    from cost_ceiling_monitor import get_ceiling_stats
    _ceiling_stats = get_ceiling_stats()
except ImportError:
    _ceiling_stats = {}       # ← no logging.error(), no print()

# tour_orchestrator_service.py:1212-1215
try:
    from cost_ceiling_monitor import get_ceiling_stats
    _ceiling_stats = get_ceiling_stats()
except ImportError:
    _ceiling_stats = {}       # ← same silent pattern
```

---

## Limitations

1. **Static analysis only** — no live containers were started or queried.
2. **Cannot detect dynamic dispatch** — `getattr`, string-interpolated imports,
   or plugin loaders would hide call sites from grep/AST.
3. **Scope is the local Docker stack** — GCloud production (`main` branch) may
   have different wiring. Per constraints, `main` was not examined.
4. **Flask route handlers counted as "called by framework"** — a route handler
   on an unregistered Blueprint is marked UNWIRED (the Blueprint registration
   is the missing call), not the handler itself.
5. **530 Python files examined** — with 528 at repo root level. The Flutter app
   (`audio_tour_app/`) was excluded as it is Dart, not Python.
