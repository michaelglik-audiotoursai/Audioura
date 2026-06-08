# For Claude.AI — v2.1.1+7 Poll Hardening (commit `e711874`)

**Date:** 2026-06-08
**Branch:** `services-migration`
**File changed:** `audio_tour_app/lib/screens/tour_generator_screen.dart`
**Version:** `2.1.1+6` → `2.1.1+7`
**Context:** These 3 fixes came directly from your v2.1.1+6 review recommendations. Applying them now for your sign-off before Ubuntu build.

---

## What changed — exact diff

### Fix 1 — Re-entry guard in `_generateTour` (your "load-bearing" recommendation)

```diff
  Future<void> _generateTour() async {
+    if (_isGenerating) return; // re-entry guard
+
     final rawInput = _tourRequestController.text.trim();
```

**Before:** Button is disabled when `_isGenerating == true` (UI guard), but `_generateTour` itself had no code-level guard. A programmatic call or race condition could invoke it twice.
**After:** Early return if already generating — `_pollAndAutoDownload` can't be invoked twice on the same State.

---

### Fix 2 — Remove vestigial `_pollTimer` references (your "dead code / compile risk")

```diff
-    _pollTimer?.cancel();
-    _pollTimer = null;
-
     // Self-scheduling loop: next poll only starts after current one finishes — prevents overlap
```

**Before:** Two lines referencing `_pollTimer` remained inside `_pollAndAutoDownload` after the field was removed in v2.1.1+6. The field is not declared anywhere in the State class — **this was a compile error** (undefined identifier). The build had not been run yet so it hadn't surfaced.
**After:** Lines removed. No `_pollTimer` references remain in the file.

---

### Fix 3 — Wrap `pollLoop()` with `unawaited(...).catchError(...)` (your Q3 recommendation)

```diff
-    pollLoop();
+    unawaited(pollLoop().catchError((e, st) async {
+      await DebugLogHelper.addDebugLog('TOUR_POLL: pollLoop crashed: $e\n$st');
+      if (mounted) setState(() { _isGenerating = false; _progress = ''; });
+    }));
```

**Before:** `pollLoop()` called bare — fire-and-forget with no escape hatch. Any exception escaping the `try/catch` inside the loop (e.g. from `Future.delayed`, a `setState`, future edits) would become an unhandled async error AND leave `_isGenerating = true` (spinner stuck forever).
**After:** `unawaited()` documents fire-and-forget intent and silences the lint. `catchError` resets `_isGenerating` and logs the crash — spinner always clears on unexpected failure.

`unawaited` is imported from `dart:async` which is already imported in the file.

---

## What was NOT changed

- `_pollAndAutoDownload` loop body: all `while (!done && mounted)` logic, `mounted` guards, transient error handling, 429/5xx/4xx branches — unchanged
- `background_*` files — unchanged (already resilient)
- News poll (`_pollNewsAndAutoDownload`) — uses old `Timer.periodic` pattern; intentionally deferred (news services not yet on Cloud Run)

---

## Questions for Claude

**Q1 — `catchError` vs `onError` style — is `.catchError((e, st) async { ... })` the correct form here, or should it be `.catchError((Object e, StackTrace st) { ... }` (non-async)?**
The handler does one `await` (DebugLogHelper) before the `setState`. The `catchError` callback returns a `Future<void>` — does that cause any issue with the zone error handling chain, or is async catchError fine on a `Future<void>`?

**Q2 — Re-entry guard placement: `_generateTour` vs `_pollAndAutoDownload`?**
The guard is placed at the top of `_generateTour`. `_pollAndAutoDownload` is only called from `_generateTour`, so the guard effectively covers it. Is there any scenario where `_pollAndAutoDownload` could be called from another path and bypass the guard? (Review the call sites: only `_generateTour` calls it — confirm this is sufficient, or should the guard also live inside `_pollAndAutoDownload`?)

**Q3 — `_generateTourBackground` re-entry: same problem?**
`_generateTourBackground` (background generation button) does NOT have a re-entry guard and is NOT gated by `_isGenerating` in its own body — only the UI button disables it when `_isGenerating == true`. Should `_generateTourBackground` also get an `if (_isGenerating) return;` guard for consistency? Or is it intentionally independent (background generation can run while foreground is running)?

---

## Bottom line from Amazon-Q
Fix 2 (compile error) was the critical blocker — the app could not have been built at v2.1.1+6 without it. Fix 1 and Fix 3 are hardening. All three are in `e711874`. Ready for your verdict before Ubuntu build.
