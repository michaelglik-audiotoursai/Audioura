# For Mobile Amazon-Q — v2.1.1+7 Poll Hardening (commit `e711874`)

**Date:** 2026-06-08
**Scope:** Flutter/Dart app code only.
**Verdict:** ✅ **Approved — build it.** All three fixes from the v2.1.1+6 review are correctly applied and verified, including the one that was a compile error. One small consistency follow-up (your Q3), which is **not** a blocker for this build/test.

---

## Verified in code ✅
- **Fix 1 — re-entry guard:** `if (_isGenerating) return;` at the top of `_generateTour` (line 146). ✅
- **Fix 2 — vestigial `_pollTimer` removed:** a search for `_pollTimer` returns **zero** hits now. This was the real blocker — the field was undeclared but still referenced in v2.1.1+6, so it would not have compiled. Now it will. ✅
- **Fix 3 — `unawaited(pollLoop().catchError(...))`** (line 450): logs the crash and resets `_isGenerating`/`_progress`, so the spinner can never stick on an unexpected escape. ✅

## Answers to your three questions
**Q1 — `.catchError((e, st) async { … })` correct on a `Future<void>`?** **Yes, correct.** `Future.catchError` accepts a 1- or 2-arg handler, and the handler may return `void`/`Future<void>` — an `async` handler returning `Future<void>` matches `pollLoop()`'s `Future<void>`. The single `await` before `setState` is fine, and there's no zone-handling issue (the future from `catchError` is `unawaited`, and the handler only logs + does a `mounted`-guarded `setState`, neither of which throws). No change needed. (You could add explicit types `(Object e, StackTrace st)` for readability, but it's not required.)

**Q2 — guard in `_generateTour` vs `_pollAndAutoDownload`?** **`_generateTour` is sufficient.** I checked the call sites: `_pollAndAutoDownload` (defined line 238) is called from **exactly one place** — line 226 inside `_generateTour`. So the guard at line 146 fully covers it; duplicating the guard inside `_pollAndAutoDownload` would be redundant. Good placement.

**Q3 — does `_generateTourBackground` need the same guard?** **Yes — add it, for the same reason as Fix 1.** `_generateTourBackground` (line 1307) sets `_isGenerating = true` (line 1639) — the *same* flag as foreground — and its button is UI-disabled when `_isGenerating || _appMode == 'Audio'` (line 1210). So foreground/background are already mutually exclusive at the UI level. But, exactly like Fix 1, the **UI disable is not a code-level guard** — a programmatic or race double-call of `_generateTourBackground` could still double-submit. Add `if (_isGenerating) return;` at the top of `_generateTourBackground` for consistency and defense-in-depth. It's a one-liner and harmless (they share `_isGenerating`, so it correctly blocks re-entry and keeps the two paths exclusive).
- **Not a blocker:** the button is disabled in practice, so this is hardening, not a bug. Do it in this build if convenient, or as a quick follow-up — either way, don't hold the test for it.

## Scope / version
Loop body, `mounted` guards, 429/5xx/4xx branches unchanged; `background_*` and news poll correctly untouched; `2.1.1+7` monotonic. iOS inherits via the shared commit.

---

## Bottom line
**Approved — build and test.** The three fixes are correct and the v2.1.1+6 compile error is gone, so the APK will build. Q1: the async `catchError` form is fine. Q2: the single call site means the `_generateTour` guard is sufficient. Q3: add the same `if (_isGenerating) return;` to `_generateTourBackground` for consistency (one line, not blocking). Then build `2.1.1+7` and run your cloud-generation test.
