# Claude Code Review — Graceful Error Handling + Diagnostic Email (commit `1846ba4`)

**Date:** 2026-06-25
**Branch:** `services-migration`
**Commit:** `1846ba4`
**ClickUp task:** wdvrdaw21e

---

## What was done

### New file: `lib/services/error_handler_service.dart`

Central error handler with three functions:

**1. `friendlyMessage(int statusCode)`** — translates HTTP codes to user-friendly text:
- 401 → "Audioura couldn't connect securely. Please make sure you have the latest version of the app, then try again."
- 402 → server message or "This content requires a subscription."
- 429 → "Daily limit reached. Please try again tomorrow."
- 500/502/503 → "Our servers are temporarily unavailable."
- Default → "Something went wrong. Please try again."

**2. `showError(BuildContext, statusCode, endpoint)`** — shows snackbar with friendly message + "Report" action button.

**3. `_reportProblem(context, statusCode, endpoint)`** — opens prefilled `mailto:support@audioura.com` with diagnostics:
- Timestamp (local + UTC)
- Failed endpoint
- HTTP status
- App version + build number
- Platform + OS version
- Server mode (cloud/local)
- Device ID
- Last 20 debug log lines
- User sees everything before sending (consent-based)

**4. `connectionErrorWidget(onRetry)`** — widget showing "Couldn't connect to Audioura" + retry button (replaces false "no tours" state).

### Modified: `lib/screens/home_screen.dart`

- Added `_connectionError` state field
- On 401/error from `/tours-near`: shows `ErrorHandlerService.showError()` and sets `_connectionError = true` (instead of silently showing empty map)
- Import added: `error_handler_service.dart`

### Modified: `lib/screens/tour_generator_screen.dart`

- On 401 from `/generate-complete-tour`: uses `ErrorHandlerService.friendlyMessage(401)` instead of raw "unauthorized" or "Server error: 401"
- Other errors still parse server messages when available
- Import added: `error_handler_service.dart`

---

## Files changed

| File | Action |
|------|--------|
| `lib/services/error_handler_service.dart` | NEW — central error handler |
| `lib/screens/home_screen.dart` | Added error state + ErrorHandlerService on 401 |
| `lib/screens/tour_generator_screen.dart` | Uses friendly message for 401 |

---

## What's NOT yet done (follow-up scope)

- Newsletter/subscription screens still have scattered `'Server error: ${response.statusCode}'` snackbars — can be migrated to `ErrorHandlerService.showError()` in a follow-up pass
- The `connectionErrorWidget` is defined but not yet wired into the map view (would need to conditionally show it when `_connectionError == true` instead of the map — layout change that needs visual review)

---

## Test criteria

- [ ] Trigger a 401 (build with wrong key) → friendly message appears, no raw "401"
- [ ] "Report this problem" action on snackbar → opens Gmail with prefilled diagnostics
- [ ] User can review email content before sending (timestamp, version, device ID, log excerpt visible)
- [ ] If no email client: shows fallback message with support address
- [ ] Pending device test: full E2E

---

## Verdict requested

Approve — Part A (unified friendly messages) and Part B (diagnostic email) are implemented. Tour generation and home screen are covered. Newsletter/subscription can be migrated in a follow-up pass.
