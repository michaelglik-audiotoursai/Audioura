# Review for Mobile Amazon-Q — Android M1 Final (commit `9265ac6`)

**Date:** 2026-06-03
**Scope:** Flutter/Dart app code only.
**Verdict:** ✅ **The code is correct and will now build** — compile blocker and runtime crash are both genuinely fixed, and the URL migration is complete and verified. Version is `2.1.1+2` — consistent with `pubspec.yaml`. Build when ready.

---

## Verified in code ✅

- **Compile fix (`_processAdditionalLanguages`):** `final prefs = await SharedPreferences.getInstance();` is back (line 411) and is passed to `_saveTourToMyToursTranslated` (line 426). The undefined-`prefs` error is gone. ✅
- **Runtime crash fix (`background_tour_monitor.dart`):** no `apiBaseUrl` reference remains, so the `tour['apiBaseUrl'] as String` cast that would throw on every backgrounded tour is removed. The remaining `as String` casts there (`startTime`, `jobId`, `location`, lines 31/32/74/75) are on keys that **are** stored in the pending-tour JSON, so they're safe. ✅
- **Migration complete:** a search of `tour_generator_screen.dart` shows **no `:5002` and no `:5005`** left (the only `as String?` hit is an unrelated, safe nullable cast on a saved tour path). `_downloadBackgroundTour` → `Service.orchestrator`, `_processAdditionalLanguages` → `Service.mapDelivery`, both background services → `Service.orchestrator`. ✅
- **`print()` → `DebugLogHelper`:** consistent with the changes shown; no concern.

So the substance of M1 is done correctly and the two blockers from the prior review are resolved.

## ✅ Version confirmed
Version is `2.1.1+2` in `pubspec.yaml` — `versionCode` incremented from `+1` to `+2`, `versionName` is `2.1.1`. This is the accepted version for this build cycle. No version change needed before building.

## Answers to your questions
- **Q1 (`prefs` as parameter vs obtained inside `_saveTourToMyToursTranslated`):** Style only — both are safe since `SharedPreferences` is a cached singleton. Passing it in is fine; obtaining it internally would slightly reduce coupling but isn't worth a change. No action needed.
- **Q2 (defer news `:5012` / newsletter `:5017`):** Correct to defer. Those services aren't on Cloud Run yet (Kiro's K6 pending), so migrating now would have no cloud target. Migrate them to `Endpoints(Service.news / Service.newsletter)` when K6 deploys and you want cloud news/newsletters. Confirmed.

## Smoke tests — good plan, proceed to build
Your three priority tests are exactly the right coverage (foreground regression, multi-language cloud, backgrounded cloud). The multi-language test exercises the `_processAdditionalLanguages` → `mapDelivery` fix; the backgrounded test exercises both `_downloadBackgroundTour` and the `background_tour_monitor` crash fix.

## iOS correlation (hand to iOS Amazon-Q)
Shared Dart — iOS rebuilds the **same commit** (after the version bump), no Dart edits, no Info.plist/ATS change, `pod install`, version in lockstep, and runs the same parity tests (multi-language + backgrounded cloud generation).

## M2 reminder (later)
When Kiro hands over the tour-status contract, the status-write switch keys on **`tour_id`** (the `tour_xxx` request id), not `request_string`. Don't start M2 until you have that contract document.

## Bottom line
Code is correct and buildable — compile and crash bugs fixed, migration complete and verified. **Only fix the `pubspec.yaml` version** (it's still `2.1.1+2`, not the `2.1.2+1` the doc claims; bump to `2.1.3+1`), then build and run the three smoke tests. Q1/Q2 need no code changes.
