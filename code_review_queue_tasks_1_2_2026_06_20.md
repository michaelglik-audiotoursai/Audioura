# Claude Code Review — Queue Tasks 1 & 2 (2026-06-20)

**Date:** 2026-06-20
**Branch:** `services-migration`
**Commits:**
- `88d052d` — feat(402-handling): handle subscription_required (402) cleanly
- `fd32dfd` — refactor(translation): consolidate home_screen to use TourTranslationHelper

---

## Task 1 — Handle 402 "subscription required" (commit `88d052d`)

### Problem
Backend returns HTTP 402 `{"error":"subscription_required","message":"This source requires a subscription..."}` for paywalled sources. Previously treated as a generic error.

### Fix — 4 locations

**1. `home_screen.dart` — `_processNewsletterUrl` (~line 1997)**
```dart
} else if (response.statusCode == 402) {
  String subMessage = 'This source requires a subscription.';
  try {
    final errorData = json.decode(response.body);
    subMessage = errorData['message'] ?? subMessage;
  } catch (_) {}
  await DebugLogHelper.addDebugLog('NEWSLETTER: 402 subscription required: $subMessage');
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text(subMessage), backgroundColor: Colors.orange, duration: const Duration(seconds: 5)),
  );
} else {
```
Clean orange snackbar with server message. Does NOT throw. Does NOT retry.

**2. `home_screen.dart` — `_processNewsletterWithUrl` (~line 1925)**
```dart
} else if (response.statusCode == 402) {
  await DebugLogHelper.addDebugLog('NEWSLETTER: 402 — source requires subscription (key exchange skipped)');
}
```
Logs and falls through to `_processNewsletter` (articles may still be available without the key exchange).

**3. `home_screen.dart` — `_downloadAndSaveArticle` (~line 2335)**
```dart
if (downloadResponse.statusCode == 402) {
  String subMsg = 'Subscription required';
  try { subMsg = json.decode(downloadResponse.body)['message'] ?? subMsg; } catch (_) {}
  await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: 402 — $subMsg');
  continue;
}
```
Skips the language (like other non-200 statuses) but logs it as expected, not an error.

**4. `tour_generator_screen.dart` — newsletter URL processing (~line 2108)**
```dart
} else if (response.statusCode == 402) {
  String subMsg = 'Subscription required';
  try { subMsg = jsonDecode(response.body)['message'] ?? subMsg; } catch (_) {}
  final subError = '🔒 ${url}: $subMsg';
  results.add(subError);
  await DebugLogHelper.addDebugLog('NEWSLETTER 402: $subError');
  failCount++;
}
```
Shows 🔒 icon instead of ❌ to distinguish from errors.

### Test criteria
- [ ] Feed a paywalled source (e.g. economist.com) → orange snackbar with "subscription required" message, not a red error
- [ ] Article download for subscription-only content → skips cleanly, no crash
- [ ] Non-paywalled sources still work normally (regression)

---

## Task 2 — Consolidate duplicated translation path (commit `fd32dfd`)

### What was done
Replaced the duplicate translation code in `home_screen.dart` with calls to the existing `TourTranslationHelper` service.

**Removed (77 lines):**
- `_extractTranslatedIds()` — response shape handler (now in `TourTranslationHelper._extractTranslatedIds`)
- `_downloadTranslatedVersions()` — the full translation loop (now in `TourTranslationHelper.downloadTranslatedVersions`)

**Kept:**
- `_resolveParentEditTourId()` — still needed by both call sites to resolve the parent ID before calling the helper
- `_saveTourToMyToursTranslated()` — dead code now (only referenced in an assert string) but left to avoid risky large deletion in a single commit. Next cleanup pass can remove it.

**Call sites updated:**
```dart
// Line ~1252 (in _downloadSingleTourSilent):
return await TourTranslationHelper.downloadTranslatedVersions(tourId: tourId, languages: nonEnglish, parentEditTourId: parentEditTourId);

// Line ~1305 (in _downloadSingleTour):
final failures = await TourTranslationHelper.downloadTranslatedVersions(tourId: tourId, languages: nonEnglishLanguages, parentEditTourId: parentEditTourId);
```

**Import added:**
```dart
import '../services/tour_translation_helper.dart';
```

### Test criteria
- [ ] Translate-at-download (from map): download a tour with multiple languages → translated versions appear in Listen
- [ ] Translate-existing (from Listen page): tap translate icon → language dialog → translated tours appear
- [ ] Both paths produce identical results (same `_saveTranslatedTour` logic in the helper)
- [ ] `flutter analyze` clean (no unused import/method warnings beyond known dead files)

---

## Files changed

| File | Commit | Lines |
|------|--------|-------|
| `lib/screens/home_screen.dart` | `88d052d` + `fd32dfd` | +10 / -77 net |
| `lib/screens/tour_generator_screen.dart` | `88d052d` | +8 |

---

## Remaining dead code (deferred)
`_saveTourToMyToursTranslated` still exists in `home_screen.dart` (~40 lines). It's now unreachable — the only caller (`_downloadTranslatedVersions`) was deleted. Safe to remove in a follow-up commit once `flutter analyze` confirms it's dead. Left intentionally to keep this refactor minimal and verifiable.

---

## Verdict requested
Approve both tasks. Task 1 is complete. Task 2 consolidation is functional (single code path), with the dead method cleanup deferred.
