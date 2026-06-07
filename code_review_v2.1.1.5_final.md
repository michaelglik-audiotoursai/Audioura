# Code Review — v2.1.1+5 Poll Hardening (Final State)
**Date:** 2026-06-08
**Commits:** `5853b62` + `14f11eb` on `services-migration`
**File:** `lib/screens/tour_generator_screen.dart`
**Scope:** Flutter/Dart only — no services changes.

---

## Context

This is the final state of `_pollAndAutoDownload` after two rounds of fixes (v2.1.1+4 poll resilience + v2.1.1+5 hardening). Please review the **complete current implementation** below and answer the 3 questions at the end.

---

## Complete Current Implementation of `_pollAndAutoDownload`

```dart
// State field (line ~42):
Timer? _pollTimer;

Future<void> _pollAndAutoDownload(String jobId, String location, [List<String>? languages]) async {
  const int maxAttempts = 90; // 15 minutes timeout
  const int maxTransientErrors = 6; // tolerate up to 6 consecutive blips (~60s)
  int attempts = 0;
  int transientErrors = 0;

  _pollTimer?.cancel();
  _pollTimer = Timer.periodic(const Duration(seconds: 10), (timer) async {

    // Closure: handle transient network/DNS blips without marking failed
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

    try {
      final response = await http.get(
        await Endpoints.url(Service.orchestrator, '/status/$jobId'),
      );
      if (!mounted) { timer.cancel(); return; }  // screen left while awaiting — stop safely

      if (response.statusCode == 200) {
        // Successful poll — reset transient error counter
        transientErrors = 0;
        Map<String, dynamic> status = jsonDecode(response.body);

        setState(() {
          _progress = status['progress'] ?? 'Processing...';
        });

        if (status['status'] == 'completed') {
          timer.cancel();
          setState(() {
            _progress = 'Downloading and extracting tour...';
          });

          // Auto-download, extract, and play
          final nonEnglish = (languages ?? []).where((l) => l != 'en').toList();
          final wantsEnglish = languages == null || languages.isEmpty || languages.contains('en');
          final finalTourId = await _autoDownloadAndPlay(jobId, location, languages, wantsEnglish);

          // Process additional languages if requested
          if (finalTourId != null && nonEnglish.isNotEmpty) {
            final translatedPath = await _processAdditionalLanguages(finalTourId, languages!);
            if (!wantsEnglish && translatedPath != null) {
              await _removeTourFromSavedTours(finalTourId);
              if (mounted) {
                setState(() { _isGenerating = false; _progress = ''; });
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => TourPlayerScreen(
                      tourPath: translatedPath,
                      tourTitle: location,
                    ),
                  ),
                );
              }
            }
            else if (!wantsEnglish && translatedPath == null) {
              if (mounted) setState(() { _isGenerating = false; _progress = ''; });
            }
          }

          await TourStatusService.updateTourStatus(jobId, 'completed');

        } else if (status['status'] == 'error' || status['status'] == 'failed') {
          timer.cancel();
          await TourStatusService.updateTourStatus(jobId, 'failed');

          String errorMessage = 'Tour generation failed';
          String userFriendlyMessage = 'Unable to generate tour. Please try again.';
          List<String> suggestions = [];

          if (status['error'] != null) {
            errorMessage = status['error'].toString();
          }

          if (status['user_error'] != null) {
            final userError = status['user_error'];
            if (userError['message'] != null) {
              userFriendlyMessage = userError['message'].toString();
            }
            if (userError['suggestions'] != null && userError['suggestions'] is List) {
              suggestions = List<String>.from(userError['suggestions']);
            }
          } else if (status['user_message'] != null) {
            userFriendlyMessage = status['user_message'].toString();
          } else if (status['error_type'] != null) {
            switch (status['error_type']) {
              case 'knowledge_validation_failed':
              case 'ai_knowledge_insufficient':
                userFriendlyMessage = 'Unable to find sufficient information about this location. Please try a more specific or well-known location.';
                break;
              case 'location_not_found':
                userFriendlyMessage = 'Location not found. Please check the spelling and try a more specific address.';
                break;
              case 'insufficient_content':
                userFriendlyMessage = 'Not enough information available to create a tour for this location. Please try a different location.';
                break;
              case 'service_unavailable':
                userFriendlyMessage = 'Tour generation service is temporarily unavailable. Please try again in a few minutes.';
                break;
              default:
                userFriendlyMessage = status['error_type'].toString().replaceAll('_', ' ');
            }
          }

          await DebugLogHelper.addDebugLog('TOUR_ERROR: Services returned error - Type: ${status['error_type']}, Message: $errorMessage');
          await DebugLogHelper.addDebugLog('TOUR_ERROR: Full status response: ${jsonEncode(status)}');

          setState(() {
            _isGenerating = false;
            _progress = '';
          });

          _showServicesErrorDialog(userFriendlyMessage, suggestions);
          return;

        } else if (attempts >= maxAttempts) {
          timer.cancel();
          await TourStatusService.updateTourStatus(jobId, 'timeout');
          _showTimeoutError();
          setState(() {
            _isGenerating = false;
            _progress = '';
          });
          return;
        }

        attempts++;

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
        // Other 4xx — likely a permanent client error; log, stop, tell the user
        timer.cancel();
        await DebugLogHelper.addDebugLog('TOUR_POLL: unexpected ${response.statusCode} for job $jobId: ${response.body}');
        if (mounted) {
          setState(() { _isGenerating = false; _progress = ''; });
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Tour generation unavailable right now — please try again.'),
              backgroundColor: Colors.red,
              duration: Duration(seconds: 8),
            ),
          );
        }
      }

    } on SocketException catch (e) { await handleTransient(e); }
      on http.ClientException catch (e) { await handleTransient(e); }
      catch (error) {
      // Unexpected error (not a network blip) — abort and mark failed
      timer.cancel();
      await TourStatusService.updateTourStatus(jobId, 'failed');
      _showError('Error: $error');
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
    }
  });
}

// dispose():
@override
void dispose() {
  _pollTimer?.cancel();
  _tourRequestController.dispose();
  _stopCountController.dispose();
  super.dispose();
}
```

---

## What Changed Since v2.1.1+4 (summary for context)

| Item | Change |
|------|--------|
| `jobTimer` local → `_pollTimer` State field | Timer now reachable from `dispose()` — leak closed |
| `_pollTimer?.cancel()` in `dispose()` | Timer cancelled when user leaves screen |
| `_pollTimer?.cancel()` before re-arming | Prevents double-timer if `_generateTour` called twice |
| `if (!mounted) { timer.cancel(); return; }` after `await http.get` | Stops the callback cleanly if screen was disposed while request was in flight |
| 429 branch | Stop + "Daily tour limit reached" deep-orange snackbar |
| 5xx branch | Routes through `handleTransient()` — counts toward 6-blip tolerance |
| Other 4xx branch | Log + stop + red "Tour generation unavailable" snackbar (was: silent spinner clear) |
| `maxTransientErrors` 3 → 6 | ~60s tolerance (matches observed DNS outage) |
| `handleTransient` closure | Both `on SocketException` and `on http.ClientException` are now one-liners; 5xx also uses it |

---

## Questions for Claude

### Q1 — `_pollTimer` re-arm guard: is `_pollTimer?.cancel()` before the new `Timer.periodic` sufficient?
If `_generateTour` is called a second time while a poll is already running (e.g. user taps Generate twice quickly), the old timer is cancelled and a new one starts. The old timer's currently-awaiting callback can still complete — but after it returns, `timer.cancel()` inside it cancels the **old** timer (already cancelled — idempotent, safe). And `_pollTimer` now points to the new timer. Is there any race condition here that could leave two timers running simultaneously, or is the cancel-before-arm pattern sufficient?

### Q2 — After `timer.cancel()` in the 200/completed branch, the code continues with `await _autoDownloadAndPlay(...)` and `await _processAdditionalLanguages(...)` — these are long async operations. Is there a `mounted` check missing before `TourStatusService.updateTourStatus(jobId, 'completed')` at the end of the completed branch?
The branch has `if (mounted)` guards around the Navigator push and setState calls, but `TourStatusService.updateTourStatus` (a SharedPreferences write) is called unconditionally after all the awaits. Is that safe, or should it also be inside a `mounted` check, or does it not matter for a non-UI operation?

### Q3 — Overall assessment of the complete poll method
Now that all the pieces are in place (timer field, dispose cancel, mounted guard, non-200 branching, transient closure, 6-blip tolerance, 15-min overall cap), is there anything structurally wrong or missing from this implementation? Any edge cases not covered?

---

## Scope Boundaries (not changed, confirmed correct)
- `_pollNewsAndAutoDownload` — news is LAN-only (`:5012` hardcoded), cloud hardening deferred
- `background_tour_monitor.dart` — already resilient (re-queues on any exception)
- `background_service.dart` — already resilient (same pattern)
- `pubspec.yaml` — version `2.1.1+5`

---

## Reviewer Checklist
- [ ] Q1 — double-timer race condition risk?
- [ ] Q2 — `TourStatusService.updateTourStatus` after long awaits — needs `mounted` check?
- [ ] Q3 — anything structurally missing from the full implementation?
