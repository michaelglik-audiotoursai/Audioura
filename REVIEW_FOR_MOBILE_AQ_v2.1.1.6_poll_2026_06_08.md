# For Mobile Amazon-Q — v2.1.1+6 Poll-Loop Rewrite (commit `1472279`)

**Date:** 2026-06-08
**Scope:** Flutter/Dart app code only.
**Verdict:** ✅ **Approve — the self-scheduling loop correctly eliminates the overlap/double-download risk, and the `translation_failed` snackbar is right.** Two things to tighten: there's now **no handle to cancel a running loop** (a re-entry could spawn a second one), and the fire-and-forget `pollLoop()` should be wrapped with `catchError`. Answers to your three questions below.

---

## Verified ✅
- `while (!done && mounted)` loop with `await Future.delayed(10s)` only at the **bottom** (447) — the next poll starts only after the current finishes, so no overlap. Exactly the fix I suggested. ✅
- `mounted` checked at the top of every iteration (248) **and** right after `http.get` (`if (!mounted) { done = true; return; }`) — clean termination on dispose. ✅
- Every terminal branch sets `done = true` and `return`s; the transient path sets `done` and falls through to the skipped delay guard. Structure is sound. ✅
- `translation_failed` snackbar (294): explicit `== true` check, `mounted`-guarded, informational only. ✅

## Answers to your three questions
**Q1 — fire-and-forget `pollLoop()` safe / leak risk?** **Safe, no leak.** The loop checks `mounted` at the top of each iteration and immediately after `http.get`, so once the widget is disposed the loop exits and the closure is garbage-collected — no dangling reference. The only nuance: if dispose happens while the loop is parked in `await Future.delayed(10s)`, the loop lingers up to ~10s before the next `while` check sees `!mounted` and exits. During that window it does nothing (no UI touch), and all `setState`s are `mounted`-guarded, so there's no "setState after dispose." Acceptable. Good pattern.

**Q2 — `done = true` inside `handleTransient`, loop continues past it?** **No problem — correct.** When `handleTransient` sets `done = true` (max transient errors) and returns, the only code after it is `if (!done) await Future.delayed(...)` (line 447), which is skipped, and then the `while (!done && mounted)` re-check exits the loop. There's no path where the body keeps executing past an unintended point — the terminal branches `return` outright, and the transient handler relies on the bottom guard, which honors `done`. Verified.

**Q3 — unhandled Future from the unawaited `pollLoop()`?** **Wrap it — yes, do this.** Today `pollLoop()` is called bare (451). The loop body is `try/catch`-guarded, so a throw is *unlikely*, but if anything ever escapes (e.g., from `Future.delayed`, a `setState`, or future edits), it becomes an **unhandled async error** reported to the zone — and worse, **`_isGenerating` would stay `true` (spinner stuck forever)** because the cleanup lives inside the loop. Defensive fix:
```dart
unawaited(pollLoop().catchError((e, st) async {
  await DebugLogHelper.addDebugLog('TOUR_POLL: pollLoop crashed: $e');
  if (mounted) setState(() { _isGenerating = false; _progress = ''; });
}));
```
`unawaited` (from `dart:async`) documents the fire-and-forget intent and silences the lint; `catchError` guarantees the spinner resets and the error is logged rather than swallowed.

## 🟡 The main thing to tighten — no cancellation handle anymore
Removing `Timer.periodic` also removed the **cancel-before-arm** protection. With the old code, re-invoking `_pollAndAutoDownload` cancelled the previous `_pollTimer`. Now a running `pollLoop` can only stop via its **own** `done`/`!mounted` — a second invocation **cannot** stop the first, so two concurrent loops could run on different jobs.
- The lines at 243-244 (`_pollTimer?.cancel(); _pollTimer = null;`) are now **vestigial** — they cancel a Timer that no longer exists (no-op), giving a false impression of stopping the old loop. (Side note: the doc says the `_pollTimer` field was *removed*, but it's still declared — these two lines reference it. Remove the field and these two lines together.)
- **Fix options:**
  1. **(Simplest)** Ensure `_generateTour` is **re-entry-guarded** — early-return / disable the Generate button while `_isGenerating == true`, so `_pollAndAutoDownload` can't be invoked twice. (This was my note last round; it's now load-bearing.)
  2. **(Robust)** Add a generation token: a State field `int _pollGeneration`; at the top of `_pollAndAutoDownload` do `final myGen = ++_pollGeneration;`, and change the loop condition to `while (!done && mounted && myGen == _pollGeneration)`. A new invocation bumps the counter and the old loop exits on its next check — restoring the "supersede the old poll" behavior the Timer used to give.

I'd do (1) for certain and consider (2) for robustness; either way, delete the dead `_pollTimer` lines.

## Scope / version
`background_*` and news poll correctly unchanged; `2.1.1+6`. iOS inherits via the shared commit. Good.

---

## Bottom line
Approve — the self-scheduling loop is the right structure and the `translation_failed` message is correct. Before building: **wrap `pollLoop()` in `unawaited(...).catchError(...)`** that resets `_isGenerating` (Q3), **remove the vestigial `_pollTimer` field + its two lines**, and **guarantee `_pollAndAutoDownload` can't run twice** — re-entry guard in `_generateTour` (simplest) or a `_pollGeneration` token (robust). Q1 and Q2 need no change.
