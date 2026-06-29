# Review for Mobile Amazon-Q — v2.1.1+3 (Blockers A+B fixed), commit `787a7f6`

**Date:** 2026-06-03
**Scope:** Flutter/Dart app code only.
**Verdict:** ✅ **Both cloud blockers are genuinely fixed and verified — this build is worth testing on device, including cloud end-to-end.** It's the first build where cloud generation can actually work from the app. Prerequisite: the gateway API key must be entered in About before the cloud tests.

---

## Verified in code ✅
- **`Endpoints.apiHeaders()`** (endpoints.dart:67) adds `X-API-Key` from `gateway_api_key` **only in cloud mode**; local stays key-free. Correct.
- **Both `/generate-complete-tour` POSTs** use `apiHeaders(Service.orchestrator)` — foreground (line 191) and background (line 1273). ✅
- **`/tour-status`** uses `apiHeaders` (tour_status_service.dart:60). ✅
- **`TranslationService`** now uses `Endpoints.url(Service.translation, '/translate-with-audio')` + `apiHeaders(Service.translation)` (Blocker B) — the LAN-IP hardcode is gone, `config.dart` import removed. ✅
- **About screen** has the obscured `gateway_api_key` field with save/load/dispose wired. ✅
- The only remaining plain `{'Content-Type'}` POSTs in `tour_generator_screen.dart` are the **news (`:5012`, line 1589)** and **newsletter (`:5017`, line 1995)** calls — correctly deferred (those services aren't deployed and aren't in scope). No gap for the current cloud test.

So every in-scope cost-bearing endpoint now sends the key in cloud, and translation routes through the gateway. The migration is complete.

## Is it worth testing on device? **Yes — both local and cloud.**
- **Local WiFi (test 1):** full regression, including `rows_affected: 1` (LAN `/user` works).
- **Cloud foreground (test 2):** generation + download should now **succeed** (key is sent). `rows_affected: 0` is **expected** (Kiro's `/user` route isn't deployed) — not a failure.
- **Cloud multi-language (test 3):** exercises the Blocker-B translation fix.
- **Cloud backgrounded (test 4):** exercises the background-download path.

**Prerequisite for the cloud tests:** Sir Michael must paste the `gateway-api-key` value (from Secret Manager) into About → cloud → API key field, and set `cloud_base_url = https://api.audioura.com` with path-routing OFF. Without the key, cloud generation returns 401 (see Q1).

## Answers to your questions
**Q1 — `apiHeaders()` silently omits the key when empty (→ 401). Throw or log?** **Log, don't throw.** Throwing would break the generation flow with an ugly exception. Better: (a) in `apiHeaders()`, when `mode == 'cloud'` and the key is empty, write a clear `DebugLogHelper` warning — e.g. *"Cloud mode but gateway_api_key not set — request will 401; set it in About"*; and (b) when a cost-endpoint response is **401**, surface a user-facing message ("Set your API key in About settings"). This is **worth doing** precisely because it's the most likely cloud test snag (forgetting the key), and a silent 401 is confusing. Medium priority — not a blocker for testing (just set the key), but it'll save you debugging time.

**Q2 — SharedPreferences `tour_id_$jobId` / `request_$jobId` cleanup.** Low priority; acceptable as-is. Add cleanup after a terminal status when convenient (prevents slow unbounded growth). Not needed for this cycle.

## Version note
Keeping `2.1.1+3` is functionally fine — the `versionCode` (`+3`) is unchanged, so reinstalling over the prior `2.1.1+3` works. Just be aware you can't tell this build from the earlier (untested) `2.1.1+3` by version alone; if you want certainty about which APK is on the phone, check a debug log line / build timestamp after install. Non-blocking.

## iOS correlation (hand to iOS Amazon-Q)
Shared Dart — iOS rebuilds the same commit, enters the API key in its own About settings, runs the same four tests.

---

## Bottom line
Blockers A + B are fixed and verified; news/newsletter deferrals are correct. **Worth testing now** — run the local regression and the three cloud tests after setting the API key + cloud URL in About. Expect `rows_affected: 0` in cloud (services `/user` dependency) — generation, multi-language, and download should all succeed. Recommend doing Q1's log/401-message improvement so a missing key is obvious during testing.
