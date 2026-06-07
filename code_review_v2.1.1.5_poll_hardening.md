# Code Review — v2.1.1+5 Poll Hardening
**Date:** 2026-06-08
**Commit:** `5853b62` on `services-migration`
**File changed:** `lib/screens/tour_generator_screen.dart`
**Scope:** Flutter/Dart only — no services changes.

---

## Background

v2.1.1+4 introduced transient-error resilience (SocketException / ClientException → keep polling up to 3 blips, then soft give-up). Claude.AI reviewed it and identified 4 items. This build applies all 4 fixes.

---

## Changes Made (before → after)

### Q1 — `jobTimer` promoted to State field, cancelled in `dispose()`

**Before:**
```dart
Timer? jobTimer;
jobTimer = Timer.periodic(const Duration(seconds: 10), (timer) async {
  ...
});

// dispose() had NO timer cancel
@override
void dispose() {
  _tourRequestController.dispose();
  _stopCountController.dispose();
  super.dispose();
}
```

**After:**
```dart
// State field:
Timer? _pollTimer;

// In _pollAndAutoDownload:
_pollTimer?.cancel();
_pollTimer = Timer.periodic(const Duration(seconds: 10), (timer) async {
  ...
});

// In dispose():
@override
void dispose() {
  _pollTimer?.cancel();
  _tourRequestController.dispose();
  _stopCountController.dispose();
  super.dispose();
}
```

---

### Q2 — Non-200 HTTP responses now handled (most important fix)

**Before:** `if (response.statusCode == 200) { ... }` — no `else`. Any 429/5xx/4xx silently fell through and just waited for next tick → infinite silent polling on quota exceeded.

**After:** Added `else if` chain after the 200 block:
```dart
} else if (response.statusCode == 429) {
  // Quota exceeded — stop polling, tell the user
  timer.cancel();
  await DebugLogHelper.addDebugLog('TOUR_POLL: 429 quota exceeded for job $jobId: ${response.body}');
  if (mounted) {
    setState(() { _isGenerating = false; _progress = ''; });
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Daily tour limit reached. Please try again tomorrow or check your plan.'),
        backgroundColor: Colors.deepOrange,
        duration: Duration(seconds: 12),
      ),
    );
  }
} else if (response.statusCode >= 500) {
  // Server-side transient error (5xx) — treat like a network blip
  await DebugLogHelper.addDebugLog('TOUR_POLL: ${response.statusCode} server error for job $jobId — counting as transient');
  await handleTransient('HTTP ${response.statusCode}');
} else {
  // Other 4xx — likely permanent; log and stop
  timer.cancel();
  await DebugLogHelper.addDebugLog('TOUR_POLL: unexpected ${response.statusCode} for job $jobId: ${response.body}');
  if (mounted) {
    setState(() { _isGenerating = false; _progress = ''; });
  }
}
```

---

### Q3 — `maxTransientErrors` raised from 3 → 6

**Before:** `const int maxTransientErrors = 3; // tolerate up to 3 consecutive network blips`
(= 30s tolerance — shorter than the observed 60s DNS outage)

**After:** `const int maxTransientErrors = 6; // tolerate up to 6 consecutive blips (~60s)`
(= 60s tolerance — matches the observed outage; costs nothing in the normal case since counter resets on any success)

---

### Q4 — Duplicate handlers replaced with `handleTransient` closure

**Before:** Two nearly-identical blocks — `on SocketException catch (e)` and `on http.ClientException catch (e)` — each with copy-pasted increment + log + snackbar/setState logic (~20 lines each, divergence risk).

**After:** Single local closure inside `_pollAndAutoDownload`, both catch clauses reduced to one-liners:
```dart
Future<void> handleTransient(Object e) async {
  transientErrors++;
  await DebugLogHelper.addDebugLog('TOUR_POLL: transient error ($transientErrors/$maxTransientErrors): $e');
  if (transientErrors >= maxTransientErrors) {
    timer.cancel();
    await DebugLogHelper.addDebugLog('TOUR_POLL: too many consecutive errors — soft give-up for job $jobId (tour may still complete on server)');
    if (mounted) {
      setState(() { _isGenerating = false; _progress = ''; });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Network connection lost. Tour may still be generating — check My Tours shortly.'),
          backgroundColor: Colors.orange,
          duration: Duration(seconds: 10),
        ),
      );
    }
  } else {
    if (mounted) setState(() { _progress = 'Network hiccup — still waiting for tour...'; });
  }
}

...
} on SocketException catch (e) { await handleTransient(e); }
  on http.ClientException catch (e) { await handleTransient(e); }
```

**Note:** 5xx responses also route through `handleTransient('HTTP ${response.statusCode}')`, so the same tolerance/give-up logic applies uniformly.

---

## Confirmed: Overall Poll Duration Cap

Claude asked to confirm a cap exists. ✅ `maxAttempts = 90` × 10s = 15 minutes. On `attempts >= maxAttempts`: timer cancelled, status → `timeout`, `_showTimeoutError()` snackbar, `_isGenerating = false`. The `tour_id_$jobId` mapping is preserved (same soft-stop as transient give-up).

---

## Scope

- ✅ Changed: `tour_generator_screen.dart` — `_pollAndAutoDownload`, `_pollTimer` field, `dispose()`
- ✅ Changed: `pubspec.yaml` — version `2.1.1+5`
- ❌ Not changed: `background_tour_monitor.dart`, `background_service.dart` — already resilient (re-queue on exception)
- ❌ Not changed: `_pollNewsAndAutoDownload` — news is LAN-only, out of scope for cloud hardening

---

## Questions for Claude

### Q1 — `handleTransient` closure captures `timer` by reference — is that safe in Dart?
The closure captures the `timer` parameter passed to the `Timer.periodic` callback. Since Dart closures capture variables by reference and `timer` is the live timer object, calling `timer.cancel()` inside `handleTransient` should correctly cancel it. But: does the closure's capture of `timer` create any risk of it being stale or null if `handleTransient` is called asynchronously after the timer has already been cancelled by another path?

### Q2 — 429 handling: should we also write a status to TourStatusService?
Currently on 429 we: cancel timer, log, show snackbar, clear spinner. We do NOT call `TourStatusService.updateTourStatus(jobId, 'failed')` or any other status. The `tour_id_$jobId` mapping is left intact (same as transient give-up). Is this correct? Or should 429 write a distinct status (e.g. `'quota_exceeded'`) so the background monitor doesn't re-try this job?

### Q3 — Other 4xx stop path: should we show the user a snackbar?
Currently for unexpected 4xx (not 429): cancel timer, log, `setState(_isGenerating = false)` — but NO snackbar shown to user. The spinner just disappears silently. Should we show a generic "Tour generation unavailable (server error)" snackbar so the user knows why the spinner stopped?

### Q4 — Is `_pollTimer?.cancel()` in `dispose()` sufficient, or does the timer callback need a `mounted` guard on `handleTransient` itself?
The `handleTransient` closure checks `if (mounted)` before `setState` and `showSnackBar`. But `_pollTimer?.cancel()` in `dispose()` fires synchronously — can the already-running async callback (awaiting `http.get`) still complete and call `handleTransient` after `dispose()` returns? If so, the `mounted` check inside `handleTransient` covers the setState, but what about `timer.cancel()` inside the closure — is that safe after dispose?

---

## Reviewer Checklist
- [ ] Q1 — Dart closure / timer capture safety
- [ ] Q2 — 429 TourStatusService write or not?
- [ ] Q3 — Silent spinner-stop on other 4xx — show snackbar?
- [ ] Q4 — dispose() + async callback interaction
- [ ] Overall: any other concerns with the non-200 branching logic?
