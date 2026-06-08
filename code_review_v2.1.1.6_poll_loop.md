# Code Review — v2.1.1+6 Poll Loop Rewrite + translation_failed
**Date:** 2026-06-08
**Commit:** `1472279` on `services-migration`
**File:** `lib/screens/tour_generator_screen.dart`
**Scope:** Flutter/Dart only — no services changes.

---

## Context

v2.1.1+5 poll was approved. Claude Q3 identified two optional improvements:
1. `Timer.periodic` + async callback can overlap → rare double-download. Fix: self-scheduling `Future.delayed` loop.
2. Read new Kiro field `translation_failed` from `/status` → show UX message when server falls back to English.

Both are implemented in this build.

---

## Change 1 — `Timer.periodic` → `Future.delayed` self-scheduling loop

### Before (v2.1.1+5)
```dart
Timer? _pollTimer;  // State field

_pollTimer?.cancel();
_pollTimer = Timer.periodic(const Duration(seconds: 10), (timer) async {
  // ... handleTransient closure ...
  try {
    final response = await http.get(...);
    if (!mounted) { timer.cancel(); return; }
    if (response.statusCode == 200) {
      // ...
      if (status['status'] == 'completed') {
        timer.cancel();
        // ... download ...
        await TourStatusService.updateTourStatus(jobId, 'completed');
      } else if (...error...) {
        timer.cancel();
        // ...
      } else if (attempts >= maxAttempts) {
        timer.cancel();
        // ...
      }
      attempts++;
    } else if (response.statusCode == 429) {
      timer.cancel();
      // ...
    } else if (response.statusCode >= 500) {
      await handleTransient('HTTP ${response.statusCode}');
    } else {
      timer.cancel();
      // ...
    }
  } on SocketException catch (e) { await handleTransient(e); }
    on http.ClientException catch (e) { await handleTransient(e); }
    catch (error) {
    timer.cancel();
    // ...
  }
});

// dispose():
_pollTimer?.cancel();
```

### After (v2.1.1+6)
```dart
// _pollTimer field REMOVED
// dispose() cancel REMOVED

Future<void> _pollAndAutoDownload(String jobId, String location, [List<String>? languages]) async {
  const int maxAttempts = 90;
  const int maxTransientErrors = 6;
  int attempts = 0;
  int transientErrors = 0;
  bool done = false;

  Future<void> pollLoop() async {
    while (!done && mounted) {

      Future<void> handleTransient(Object e) async {
        transientErrors++;
        await DebugLogHelper.addDebugLog('TOUR_POLL: transient error ($transientErrors/$maxTransientErrors): $e');
        if (transientErrors >= maxTransientErrors) {
          done = true;
          // ... soft give-up snackbar ...
        } else {
          if (mounted) setState(() { _progress = 'Network hiccup — still waiting for tour...'; });
        }
      }

      try {
        final response = await http.get(
          await Endpoints.url(Service.orchestrator, '/status/$jobId'),
        );
        if (!mounted) { done = true; return; }

        if (response.statusCode == 200) {
          transientErrors = 0;
          Map<String, dynamic> status = jsonDecode(response.body);
          setState(() { _progress = status['progress'] ?? 'Processing...'; });

          if (status['status'] == 'completed') {
            done = true;
            // ... translation_failed snackbar (see Change 2) ...
            // ... download + navigate ...
            await TourStatusService.updateTourStatus(jobId, 'completed');
            return;
          } else if (status['status'] == 'error' || status['status'] == 'failed') {
            done = true;
            // ... error dialog ...
            return;
          } else if (attempts >= maxAttempts) {
            done = true;
            // ... timeout ...
            return;
          }
          attempts++;

        } else if (response.statusCode == 429) {
          done = true;
          // ... quota snackbar ...
          return;
        } else if (response.statusCode >= 500) {
          await handleTransient('HTTP ${response.statusCode}');
        } else {
          done = true;
          // ... 4xx snackbar ...
          return;
        }

      } on SocketException catch (e) { await handleTransient(e); }
        on http.ClientException catch (e) { await handleTransient(e); }
        catch (error) {
        done = true;
        await TourStatusService.updateTourStatus(jobId, 'failed');
        if (mounted) { _showError('Error: $error'); setState(() { ... }); }
        return;
      }

      if (!done) await Future.delayed(const Duration(seconds: 10));
    }
  }

  pollLoop();  // fire-and-forget
}
```

**Key structural points:**
- `pollLoop()` is called without `await` — it runs concurrently with `_pollAndAutoDownload` returning
- Loop exits when `done = true` OR `!mounted` (checked at top of every iteration)
- `await Future.delayed(10s)` is at the **bottom** of the loop body — only reached when poll completed without a terminal result
- No `Timer` object anywhere — `_pollTimer` field and its `dispose()` cancel are gone

---

## Change 2 — `translation_failed` snackbar

In the `status == 'completed'` branch, immediately before starting the download:

```dart
if (status['translation_failed'] == true && mounted) {
  ScaffoldMessenger.of(context).showSnackBar(
    const SnackBar(
      content: Text('Translation unavailable — showing English version.'),
      backgroundColor: Colors.orange,
      duration: Duration(seconds: 6),
    ),
  );
}
```

- Only fires when `status['translation_failed'] == true` (explicit bool check)
- Absent field or `false` → no snackbar
- `mounted` guard present
- Does not affect download flow — snackbar is informational only

---

## Questions for Claude

### Q1 — `pollLoop()` called without `await` — is fire-and-forget safe here?
`pollLoop()` is a local async function called without `await`. The outer `_pollAndAutoDownload` returns immediately, leaving `pollLoop` running in the background. The loop accesses `mounted`, `setState`, `context` — all State members. Since Flutter's State lifecycle is tied to the widget tree (not `Future` lifetimes), and the loop checks `mounted` at the top of every iteration AND after `http.get` returns, is this pattern safe? Any risk of memory leak or dangling reference from the unawaited Future?

### Q2 — `done = true` set inside `handleTransient` when `transientErrors >= maxTransientErrors` — but the loop condition checks `!done` only at the top. After `handleTransient` returns (having set `done = true`), execution continues to the `if (!done) await Future.delayed(...)` line at the bottom. That guard catches it. But is there any path where `done = true` is set inside a try/catch sub-call and the loop body still continues executing past an unintended point?

### Q3 — The `pollLoop()` future is never stored or awaited. If an unhandled exception escapes `pollLoop()` (e.g. from inside `handleTransient` itself — though it has no throws), would it be silently swallowed by the Dart runtime, or would it surface as an unhandled Future error? Should `pollLoop()` be wrapped in a `catchError` at the call site?

---

## Scope
- ✅ Changed: `tour_generator_screen.dart` — `_pollAndAutoDownload`, removed `_pollTimer` field + `dispose()` cancel
- ✅ Changed: `pubspec.yaml` — version `2.1.1+6`
- ❌ Not changed: `background_tour_monitor.dart`, `background_service.dart`, `_pollNewsAndAutoDownload`

---

## Reviewer Checklist
- [ ] Q1 — fire-and-forget `pollLoop()` safety / leak risk
- [ ] Q2 — `done = true` inside nested closure, loop body continuation
- [ ] Q3 — unhandled Future from unawaited `pollLoop()` call
- [ ] Overall: any concern with the `while (!done && mounted)` + `Future.delayed` pattern vs Timer.periodic?
