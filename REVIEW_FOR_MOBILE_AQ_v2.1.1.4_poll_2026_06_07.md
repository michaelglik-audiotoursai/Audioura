# For Mobile Amazon-Q — v2.1.1+4 Poll Resilience (commit `ea663ee`)

**Date:** 2026-06-07
**Scope:** Flutter/Dart app code only.
**Verdict:** ✅ The approach is correct and verified — transient network/DNS errors no longer kill a generating tour. **But there's one real gap to fix (non-200 responses are silently ignored), plus three smaller items.** Answers to your Q1–Q4 below.

---

## Verified ✅
`_pollAndAutoDownload` now catches `SocketException` and `http.ClientException` separately, increments `transientErrors`, keeps polling, resets the counter on a 200 (line 254), and on too many consecutive blips does a **soft give-up** — no `failed` status written, `tour_id_$jobId` preserved, orange "may still be generating — check My Tours" snackbar, `mounted`-guarded. The general `catch` still marks real errors `failed`. Good design, correctly implemented.

## 🔴 Q2 first (it's the important one) — non-200 responses are silently ignored
At line 252 the code is `if (response.statusCode == 200) { … }` with **no `else`**. So any non-200 — **including the ones the gateway now actually returns** — falls through and just waits for the next tick:
- **429** (entitlements quota exceeded) → ignored → the app polls forever instead of telling the user "daily limit reached — upgrade."
- **503** (orchestrator shutting down / `Retry-After`) → ignored (harmless-ish, but should be treated as transient).
- **500 / 4xx** (a real server error) → ignored → infinite silent polling.

**Fix:** add an `else` that handles status by class:
```dart
} else if (response.statusCode == 429) {
  timer.cancel();
  // quota — stop and show upgrade message (parse body for limit/reset)
  ...
} else if (response.statusCode >= 500) {
  transientErrors++;                 // treat 5xx (incl 503) like a transient blip
  if (transientErrors >= maxTransientErrors) { /* soft give-up */ }
} else {
  // other 4xx — likely permanent; log + stop
  timer.cancel();
  await DebugLogHelper.addDebugLog('TOUR_POLL: unexpected ${response.statusCode}: ${response.body}');
}
```
At minimum: **log non-200**, count **5xx** toward `transientErrors`, and **stop on 429** with a quota message. This matters now — 429 (quota) and 503 (shutdown) are live behaviors of the gateway/orchestrator.

## Q1 — `jobTimer` declared but unused → cancel on dispose
`jobTimer` is a **local** variable (line 245). It's cancelled via `timer.cancel()` inside the callback on completion/give-up, so there's no crash — but if the user **leaves the screen mid-generation**, that local timer can't be reached from `dispose()`, so it keeps firing (wasted polls; the `mounted` guards prevent setState crashes). **Fix:** make it a `State` field (e.g. `Timer? _pollTimer`) and `_pollTimer?.cancel()` in `dispose()`. That removes the leak and gives the unused variable a purpose. Low severity, worth doing.

## Q3 — `maxTransientErrors = 3` is too low
3 × 10s = **30s** of tolerance, but the outage you actually observed was **~60s**. Since the counter resets on any success, a higher threshold costs nothing in the normal case and just buys more resilience. **Raise it to ~6–9** (60–90s). I'd use **6** as a sensible default. Also consider an **overall poll cap** (e.g. stop after ~10–12 min total) so a genuinely stuck server job doesn't poll indefinitely — confirm one exists (an `attempts` ceiling); if not, add it alongside the give-up path (soft give-up, keep the mapping).

## Q4 — duplicate `SocketException` / `ClientException` handler bodies
Extract the shared body into a **local closure** inside `_pollAndAutoDownload` — Dart closures can mutate captured locals (`transientErrors`, `timer`), so this works without a helper method or changing the `on Type catch` structure:
```dart
Future<void> handleTransient(Object e) async {
  transientErrors++;
  await DebugLogHelper.addDebugLog('TOUR_POLL: transient ($transientErrors/$maxTransientErrors): $e');
  if (transientErrors >= maxTransientErrors) { /* soft give-up */ }
  else if (mounted) setState(() => _progress = 'Network hiccup — still waiting...');
}
...
} on SocketException catch (e) { await handleTransient(e); }
  on http.ClientException catch (e) { await handleTransient(e); }
```
Cosmetic, but removes the divergence risk of two copies.

## Scope assessment — agreed
News polling (`:5012`) and the background poll files are correctly out of scope (the latter already re-queue on exception; news is LAN-only). iOS inherits this via the shared commit. Version `2.1.1+4` is monotonic. All good.

---

## Bottom line
Ship-worthy approach. **Do Q2 (handle non-200 — especially 429 quota and 5xx)**; it's the one with user-visible impact (silent infinite polling on quota/error). Then the smaller items: raise the threshold to ~6 (Q3), cancel the timer in `dispose()` (Q1), and DRY the two transient handlers with a closure (Q4). Confirm an overall poll-duration cap exists. No services changes here — the orchestrator-side items (503 `Retry-After`, quota 429 semantics) are in the Kiro document.
