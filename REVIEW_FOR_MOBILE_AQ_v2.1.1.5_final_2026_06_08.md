# For Mobile Amazon-Q — v2.1.1+5 Poll Hardening (final), commits `5853b62` + `14f11eb`

**Date:** 2026-06-08
**Scope:** Flutter/Dart app code only.
**Verdict:** ✅ **Approve.** Both items from my prior review are applied and verified — the `mounted` guard after `http.get` (line 272) and the red 4xx snackbar (line 421). The full poll method is now solid. Answers to your three questions below; one optional structural improvement, no blockers.

---

## Verified ✅
- `if (!mounted) { timer.cancel(); return; }` immediately after the status `http.get` (272) — closes the "setState after dispose" gap from the prior round. ✅
- Other-4xx now shows a red "Tour generation unavailable" snackbar (421) instead of a silent spinner-clear. ✅
- `_pollTimer` State field, cancelled in `dispose()` and before re-arm; 429/5xx/4xx branching; `handleTransient` closure; `maxTransientErrors = 6`; 15-min `maxAttempts` cap — all present.

## Answers to your three questions

**Q1 — `_pollTimer?.cancel()` before re-arm: any double-timer race?** **No double-timer — the pattern is sufficient.** Cancelling the old timer stops it from ticking again, and a new timer is assigned to `_pollTimer`. The old timer's *already-in-flight* callback can finish once more, but its `timer.cancel()` refers to the (now-cancelled) old timer — idempotent no-op — and it won't re-schedule. So you never get two periodic schedules running.
- *One residual edge (not a timer race):* that last in-flight old-callback could still execute the **success branch** (download/play the *old* job) after a new generation started, since `mounted` is still true. The clean guard is to prevent re-entry: make sure `_generateTour` can't start a second generation while `_isGenerating == true` (disable the Generate button / early-return if already generating). You very likely already do this — just confirm it, and the edge disappears.

**Q2 — `TourStatusService.updateTourStatus(jobId, 'completed')` after the long awaits, no `mounted` guard (line 322): safe?** **Yes — correct as-is, leave it unguarded.** That call is a **non-UI operation** (a SharedPreferences write + an HTTP POST to `/tour-status`); it doesn't touch `setState`/`context`, so there's no "after dispose" risk. And you positively *want* it to run even if the user navigated away — the tour completed, so its status should be recorded regardless of whether the screen is still visible. Adding a `mounted` check would be wrong here (it would skip a write you want). The UI ops around it (Navigator push, setState at 83-97) are correctly `mounted`-guarded; the persistence call should not be.

**Q3 — Anything structurally wrong/missing?** It's in good shape; edge cases are well covered. One **optional** structural improvement worth noting:
- **`Timer.periodic` + an async callback can overlap.** `Timer.periodic` fires every 10s regardless of whether the previous callback's `await http.get` (or the post-completion `_autoDownloadAndPlay`) has finished. On a slow network (poll > 10s), a second tick can start while the first is still running → concurrent `/status` calls, and in a rare case two callbacks both see `completed` and both trigger a download. The shared `transientErrors`/`attempts` counters could also be touched by overlapping ticks (harmless in Dart's single isolate, but logically double-counted). **A self-scheduling loop avoids this entirely:** instead of `Timer.periodic`, do one poll, then `await Future.delayed(10s)` and poll again in a `while (!done && attempts < max)` loop — the next poll only starts after the current finishes, so no overlap. This is an enhancement, not a bug for typical fast polls; mention it for a future cleanup if you see double-download symptoms.
- Minor: the timeout check (`attempts >= maxAttempts`) increments `attempts` after the check, so it's an off-by-one (~15 min ±10s). Negligible.

Otherwise: the `mounted` guard placement, the non-200 split, the transient closure, and the soft give-up are all correct. No edge cases missing.

## New info from the services side (read the `translation_failed` flag)
Kiro added a `translation_failed: true` field to the `/status` response when a multi-language tour's translation step fails (the tour falls back to English). Right now your completed-branch downloads the English tour silently in that case. **Consider reading `status['translation_failed']`** and, if true, showing a brief "Translation unavailable — showing English version" message, so a RU/KO user isn't confused why they got English. Small UX add; do it when convenient.

## Scope / version
News poll and `background_*` files correctly unchanged; `2.1.1+5`. iOS inherits via the shared commit. All good.

---

## Bottom line
Approve — the prior fixes are correctly in, and the method is solid. Q1: cancel-before-arm is sufficient; just confirm `_generateTour` is re-entry-guarded. Q2: leave `updateTourStatus` unguarded — it's a non-UI write you want to run regardless. Q3: optionally switch `Timer.periodic` → a self-scheduling `Future.delayed` loop to prevent rare overlap/double-download, and read the new `translation_failed` flag for a cleaner multi-language message. No blockers — build and test.
