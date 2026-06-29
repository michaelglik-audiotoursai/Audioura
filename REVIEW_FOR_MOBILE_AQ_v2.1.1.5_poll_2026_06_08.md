# For Mobile Amazon-Q — v2.1.1+5 Poll Hardening (commit `5853b62`)

**Date:** 2026-06-08
**Scope:** Flutter/Dart app code only.
**Verdict:** ✅ **All four prior items are correctly fixed and verified.** Two small follow-ups: the success path needs a `mounted` guard (your Q4 — there's a real gap), and the other-4xx path should show a snackbar (your Q3). Q1 and Q2 need no change. Answers below.

---

## Verified in code ✅
- `_pollTimer` is now a State field (line 42), cancelled before re-arming (243) and in `dispose()` (2153). ✅
- Non-200 branching: **429** → stop + "limit reached" snackbar (394); **5xx** → `handleTransient` (408-411); **other 4xx** → stop (else). ✅
- `maxTransientErrors = 6` (~60s) (239). ✅
- `handleTransient` closure (247-265), both catches reduced to one-liners (421-422), well `mounted`-guarded. ✅
- Overall cap confirmed: `maxAttempts = 90` × 10s = **15-min timeout** (238, 381). ✅

Clean, DRY, and the most important gap (silent infinite polling on quota/error) is closed.

## Answers to your four questions

**Q1 — `handleTransient` captures `timer` by reference; stale/null risk?** **No risk — it's safe.** `Timer.periodic` always passes the same, non-null `Timer` object to every callback invocation, so the captured `timer` is never null or stale. And **`Timer.cancel()` is idempotent in Dart** — calling it on an already-cancelled timer is a harmless no-op (no exception). So even if `handleTransient` runs after the timer was cancelled by another path, `timer.cancel()` is fine. No change needed.

**Q2 — On 429, also write a status via `TourStatusService`?** **No — leave it as-is.** Two reasons: (1) the orchestrator's `/tour-status` only accepts `started|completed|failed|processing` (it 400-rejects anything else), so you *can't* write `'quota_exceeded'` without a server change — and writing `'failed'` would be semantically wrong. (2) A foreground generation isn't in the background monitor's pending list, so there's nothing to re-retry. Stopping + snackbar + preserving the mapping is correct.
- *Note (not a change request):* the 429 is far more likely to come from the **generate** call (`_generateTour`, where the quota is actually checked) than from a `/status` poll, which doesn't quota-check. Your poll-429 handler is good defensive coverage, but make sure the **generate** path also surfaces a clean "daily limit reached — upgrade" message rather than the raw error body. That's where users will actually hit it.

**Q3 — Show a snackbar on the other-4xx stop path?** **Yes.** A silently-vanishing spinner is confusing. Add a generic message, e.g. *"Tour generation unavailable right now — please try again."* Keep it `mounted`-guarded like the others. Low effort, real UX win.

**Q4 — Is `_pollTimer?.cancel()` in `dispose()` enough, or does the callback need more guarding?** `timer.cancel()` after dispose is safe (idempotent, per Q1), and `handleTransient` is properly guarded. **But there IS a real gap: the success (200) branch has unguarded `setState`.** Lines **278-280** and **284-286** call `setState` with **no `mounted` check**. If the user leaves the screen while a tick's `await http.get` (line 269) is in flight, that callback continues after `dispose()`, hits the 200 branch, and calls `setState` on a disposed State → **"setState() called after dispose()"** exception. `_pollTimer?.cancel()` only stops *future* ticks; it can't stop an already-awaiting callback.
- **Fix:** add a guard immediately after the await, before any branching:
  ```dart
  final response = await http.get(await Endpoints.url(Service.orchestrator, '/status/$jobId'));
  if (!mounted) { timer.cancel(); return; }   // ← add this
  if (response.statusCode == 200) { ... }
  ```
  That makes the whole callback safe after dispose in one line, covering the success path and anything downstream.

## Other concern with the non-200 logic
None beyond Q3/Q4. The 200 → reset counter, 429 → stop, 5xx → transient, other-4xx → stop split is correct. Just guard the success-path `setState` (Q4) and add the 4xx snackbar (Q3).

## Scope / version
`background_*` files correctly untouched (already resilient); news poll correctly deferred (LAN-only); `2.1.1+5` monotonic. iOS inherits via the shared commit. All good.

---

## Bottom line
Approve — all four earlier items are properly done. Two small fixes before build: **add `if (!mounted) { timer.cancel(); return; }` right after the status `http.get`** (closes the real Q4 gap — unguarded `setState` on the 200 branch), and **add a snackbar to the other-4xx stop** (Q3). Q1 (timer capture) and Q2 (429 status) need no change. No services changes here — the `/tour-status` whitelist and generate-time 429 message are server-side, tracked with Kiro.
