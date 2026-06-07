# Code Review Request — v2.1.1+4 Poll Resilience Fix
**Date:** 2026-06-07
**Reviewer:** Claude.AI
**Scope:** Flutter/Dart — `tour_generator_screen.dart` only
**Commit:** `ea663ee` on `services-migration`
**Version:** `2.1.1+4`

---

## Background

In smoke testing v2.1.1+3, a cloud generation was queued successfully (HTTP 200, job `f087ec79`), then ~7.5 minutes later the status poll failed with:

```
TOUR_STATUS error: Failed host lookup: 'api.audioura.com'
(No address associated with hostname, errno = 7)
```

The phone had a 1-minute DNS hiccup (network transition / doze mode during the long wait). The old `catch` block immediately cancelled the timer, called `TourStatusService.updateTourStatus(jobId, 'failed')`, and showed an error — even though the server was still generating. One DNS blip = tour marked dead.

---

## What changed — `_pollAndAutoDownload` in `tour_generator_screen.dart`

**Before** (single catch block):
```dart
} catch (error) {
  timer.cancel();
  await TourStatusService.updateTourStatus(jobId, 'failed');
  _showError('Error: $error');
  setState(() { _isGenerating = false; _progress = ''; });
}
```

**After** (three catch clauses):
```dart
} on SocketException catch (e) {
  // Transient network/DNS error — keep polling, don't mark failed
  transientErrors++;
  await DebugLogHelper.addDebugLog('TOUR_POLL: Transient network error ($transientErrors/$maxTransientErrors): $e — continuing to poll');
  if (transientErrors >= maxTransientErrors) {
    timer.cancel();
    await DebugLogHelper.addDebugLog('TOUR_POLL: Too many consecutive network errors — giving up poll for job $jobId (tour may still complete on server)');
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
} on http.ClientException catch (e) {
  // Identical handling to SocketException
  transientErrors++;
  // ... (same logic as above)
} catch (error) {
  // Unexpected error (not a network blip) — abort and mark failed (original behaviour)
  timer.cancel();
  await TourStatusService.updateTourStatus(jobId, 'failed');
  _showError('Error: $error');
  setState(() { _isGenerating = false; _progress = ''; });
}
```

**New fields added to `_pollAndAutoDownload`:**
```dart
const int maxTransientErrors = 3;
int transientErrors = 0;
```

**Successful poll now resets the counter:**
```dart
if (response.statusCode == 200) {
  transientErrors = 0;  // ← added
  Map<String, dynamic> status = jsonDecode(response.body);
  ...
```

**Soft give-up behaviour:**
- No `updateTourStatus(jobId, 'failed')` call
- `tour_id_$jobId` mapping in SharedPreferences is preserved
- Orange snackbar: "Network connection lost. Tour may still be generating — check My Tours shortly."
- Spinner cleared, user not stuck

**Background poll files unchanged** — `background_tour_monitor.dart` and `background_service.dart` already keep the tour in the pending list on any exception (their catch blocks do `updatedPendingTours.add(tourJson)` and continue). No change needed.

---

## What is NOT changed (scope boundary)

- `_pollNewsAndAutoDownload` (news polling) — not in scope, news services are local-only (`:5012`), DNS blips on LAN are not a concern
- Background poll files — already resilient
- All other methods — unchanged

---

## Questions for Claude

**Q1 — `jobTimer` variable declared but never used directly**
`Timer? jobTimer` is declared at the top of `_pollAndAutoDownload` but the `Timer.periodic` return value is assigned to it and then `timer` (the callback parameter) is used for all `cancel()` calls. `jobTimer` is never referenced again. Is this a leak risk, or is it safe because `timer` inside the callback IS the same timer object and cancelling it is sufficient?

**Q2 — `transientErrors` counter resets only on HTTP 200**
If the server returns HTTP 4xx or 5xx (non-200), the code falls through the `if (response.statusCode == 200)` block silently — no `transientErrors` increment, no `attempts` increment, nothing. Is this the right behaviour, or should non-200 responses be counted as transient errors too (or at least logged)?

**Q3 — `maxTransientErrors = 3` at 10-second poll interval**
3 consecutive errors = 30 seconds of network outage before soft give-up. In the log, the DNS hiccup was ~60 seconds. Would 6 be a safer threshold, or is 3 sufficient given that the counter resets on any success?

**Q4 — Duplicate snackbar code in `SocketException` and `http.ClientException` handlers**
Both handlers have identical logic (increment, check threshold, same snackbar, same log). Is there a cleaner way to handle this without introducing a helper method, given the constraints of the `on Type catch` syntax in Dart?

---

## Checklist for reviewer

- [ ] `SocketException` correctly catches DNS lookup failures (`errno = 7` as seen in log)
- [ ] `http.ClientException` correctly catches HTTP client-level errors
- [ ] `transientErrors` counter reset on successful poll
- [ ] Soft give-up: no `failed` status written, `tour_id_$jobId` preserved
- [ ] `mounted` guard before `setState` / `showSnackBar` in both transient handlers
- [ ] General `catch` still marks `failed` for non-network errors (correct)
- [ ] Background poll files correctly assessed as already-resilient (no change needed)
- [ ] `_pollNewsAndAutoDownload` correctly deferred (not in scope)

---

## iOS correlation
Shared Dart — iOS inherits this fix when it builds the same commit. No separate change needed.
