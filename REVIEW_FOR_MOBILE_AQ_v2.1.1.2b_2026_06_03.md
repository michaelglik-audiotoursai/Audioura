# Review for Mobile Amazon-Q — Android v2.1.1+2 (M1 completion)

**Date:** 2026-06-03
**Scope:** Flutter/Dart app code only.
**Verdict:** ⚠️ **The three missed sites are correctly migrated — but this build will NOT compile as-is.** Your Q1 instinct is right: `_processAdditionalLanguages` still passes `prefs` after you removed its declaration. Fix that one line before building. There's also a version-number regression to correct.

---

## Verified migrated ✅
A search for hardcoded LAN URLs in `tour_generator_screen.dart` now shows **no `:5002` and no `:5005`** left — so:
- `_downloadBackgroundTour` status + download → migrated to `Endpoints.url(Service.orchestrator, …)`, `serverIp`/`.217` removed. ✅
- `_processAdditionalLanguages` translated download → migrated to `Endpoints.url(Service.mapDelivery, …)`. ✅
- `background_service.dart` dead `apiBaseUrl` / `serverIp` reads removed (Q2/Q3). ✅

The only remaining hardcoded URLs are news (`:5012`, lines 1587/1624/1688) and newsletter (`:5017`, line 1993) — correctly deferred until those services deploy (K6). Fine.

## 🔴 BLOCKER — Q1: `_processAdditionalLanguages` won't compile
You removed the `final prefs = …` local from `_processAdditionalLanguages`, but line **425** still passes `prefs`:
```dart
await _saveTourToMyToursTranslated(translatedId, resp.bodyBytes, appDir.path, prefs, lang);
```
I confirmed: there is **no** `final prefs` declared anywhere between the method signature (line 381) and line 425, and `_processAdditionalLanguages(int finalTourId, List<String> languages)` has no `prefs` parameter or field. So `prefs` at line 425 is an **undefined name → compile error.** That's almost certainly why "no tests yet" — `build_flutter_clean.sh` would fail.

**Fix (minimal):** re-obtain `prefs` in the method before the loop — it's cheap (the instance is cached after first load):
```dart
Future<String?> _processAdditionalLanguages(int finalTourId, List<String> languages) async {
  final prefs = await SharedPreferences.getInstance();   // ← add back
  final appDir = await getApplicationDocumentsDirectory();
  ...
  await _saveTourToMyToursTranslated(translatedId, resp.bodyBytes, appDir.path, prefs, lang);
}
```
(Alternatively, drop the `prefs` parameter from `_saveTourToMyToursTranslated` and have it call `SharedPreferences.getInstance()` itself — more churn. The one-line re-add is simplest and keeps the signature.)

This is the only thing blocking the build. Everything else is correct.

## 🟡 Version regression
`pubspec.yaml` is now `2.1.1+2`, but the previous M1 build was `2.1.2+1`. So `versionName` went **backwards** (`2.1.2` → `2.1.1`). The Android `versionCode` (the `+N`) did increase (1 → 2), so it's not Play-Store-blocking, but a non-monotonic `versionName` is confusing and will bite later. Bump forward — e.g., **`2.1.3+1`** (or `2.1.2+2`) — and keep `versionName` monotonic from here.

## Smoke test plan — good, but fix the compile error first
Your priority tests are exactly right (multi-language cloud, backgrounded completion, foreground regression, manual background download). Just note: they can't run until the Q1 fix lands and the APK actually builds. Once it builds:
- **Multi-language cloud** exercises the `_processAdditionalLanguages` fix (Service.mapDelivery translated download).
- **Backgrounded completion cloud** exercises the `_downloadBackgroundTour` fix (Service.orchestrator status+download).
- Confirm both translated and English versions land in My Tours over cellular.

## M2 reminder (later, not now)
When Kiro hands over `CONTRACT_TOUR_STATUS_FOR_MOBILE_AQ.md`, the status-write switch from `DirectDbUpdate` to `POST /tour-status` keys on **`tour_id`** (the `tour_xxx` request id), not `request_string` — send the right id or it updates 0 rows. Don't start M2 until you have that contract.

## iOS correlation (hand to iOS Amazon-Q)
Shared Dart — iOS rebuilds the **same commit** (after the Q1 fix), no Dart edits, no Info.plist/ATS change, `pod install`, version in lockstep, and runs the same parity tests (multi-language + backgrounded cloud generation).

## Bottom line
Migration content is correct and complete for M1. **Add the one `prefs` line in `_processAdditionalLanguages` so it compiles**, bump the version forward, then run the multi-language and backgrounded cloud tests. Nothing here needs Kiro or the services.
