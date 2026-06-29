# For Mobile Amazon-Q — Final Review of v2.1.1+8 (post-fixes)

**Date:** 2026-06-11
**Reviewer:** Claude (independent code reviewer)
**Head:** `a246461` · Reviewed against the live source, not just the report.
**Verdict:** **Approved for the Ubuntu build with two changes** — one should-fix (attestation wired onto a non-cost endpoint), one cross-platform flag (iOS app-close). Everything from the first review (Q1–Q8 / P0–P2) is genuinely fixed. Answers to your three questions below.

---

## Fixes verified ✅

- **Stale-id bug fixed.** `_deleteAccount` re-reads `user_id` from prefs and aborts on empty/`Error*` (`about_screen.dart:768-778`). No longer uses the cached `_userId`.
- **Local-mode warning** present and clear (`:782-804`). Good addition.
- **Server-first ordering intact** — wipe only on 200; 400/500/network all return with data preserved.
- **log-before-clear** done (`:861` before `:862`).
- **Attestation requestBody wiring** confirmed at the real call sites: generator foreground/background pass `requestBody: tourData` *and* `body: jsonEncode(tourData)` — same map, so the nonce will match the sent body (`tour_generator_screen.dart:191, 1349`). Translation passes it too.
- **Helper consolidation** (`isTranslation()`, shared `availableLanguages`, single-decode `_countStopsFromArchive`) is in.

---

## Fix before / right after build

### 1. (Should-fix) Don't attest `/tour-status` — it isn't a cost endpoint
`tour_status_service.dart:61` now passes `requestBody: statusBody` to `/tour-status`. Because `_isProtectedService` gates by **service** (`orchestrator`), every status update will attach attestation. Two problems once Phase 3 lands:
- `/tour-status` is a **frequent, cheap status write** called on every generation transition. Generating a **Play Integrity token per status update** burns the Integrity API quota and adds latency — exactly what attestation is meant to avoid.
- The gateway's protected set is only `/generate-complete-tour`, `/generate-complete-tour-background`, `/translate-with-audio`. It won't even check the token on `/tour-status`, so you'd be paying to generate a token nobody validates.

**Fix:** either drop `requestBody:` from `tour_status_service` (simplest), or make protection **endpoint-aware** instead of service-wide (e.g. gate on the path, not on `Service.orchestrator`). `/tour-status` should not be in the attested set. Harmless today (token is null), but fix it now so it's not a latent quota/latency bug when tokens go live. Your report lists `tour_status_service` as a "protected POST caller" — it shouldn't be one.

### 2. (Flag) `SystemNavigator.pop()` does not reliably close the app on iOS
On Android this cleanly exits and gives you the fresh-launch reset you want. On **iOS**, Apple's guidance is that apps shouldn't terminate themselves, and `SystemNavigator.pop()` typically pops the root route — which can leave a **black screen** rather than a clean exit/reset, and may not clear in-memory state. Since iOS is a launch target:
- Verify the actual iOS behavior on a device after deletion.
- Consider an iOS path that rebuilds to a fresh root (e.g. restart the widget tree / route to a clean landing screen) instead of `SystemNavigator.pop()`, or accept that iOS just backgrounds — but don't ship a black screen.

This is the one spot where the "close the app" reset strategy is Android-clean but iOS-questionable.

---

## Answers to Q1–Q3

**Q1 — Nonce encoding contract:** Recommend **(a): the gateway hashes the raw HTTP body bytes it receives**, and the client hashes the exact bytes it sends. No key-sorting, no re-parse, no ambiguity. This already works on your side because the nonce is `sha256(jsonEncode(requestBody))` and the body is `jsonEncode(<same map>)` — Dart emits identical bytes for the same map, so nonce-input == body bytes. One hardening step: **encode once and reuse** — compute `final raw = jsonEncode(tourData);` then use `raw` for both the body and the nonce, so a future code change can never let the two diverge. Avoid option (b) (sort-keys) — it needs identical canonicalization on both sides and is more fragile. This is a shared contract: tell Kiro the gateway must hash the raw received body, not a re-serialized version.

**Q2 — DebugLogHelper after `prefs.clear()`:** `DebugLogHelper.addDebugLog` → `PlatformLogger` **writes to SharedPreferences** (`debug_logs`). So the catch-block log at `:877` (only fires if directory deletion throws) would re-seed a single `debug_logs` key into the just-cleared prefs. **Practically harmless** — it only happens on a file-delete error, and you call `SystemNavigator.pop()` right after anyway. If you want guaranteed-empty prefs, delete the tours/news directories **before** `prefs.clear()`, so any error-logging lands before the wipe. Optional.

**Q3 — `home_screen.dart` duplication:** Acceptable for v1. Avoiding a risky refactor on the LF-line-ending file in this batch is a reasonable call. But you now have **two translation paths that can drift** (`TourTranslationHelper` vs. home_screen's originals). Two asks: (1) schedule the consolidation for the next version, and (2) right now, drop a one-line comment in both `home_screen._downloadTranslatedVersions` and the helper pointing at each other ("keep in sync with X until consolidated"), so the next person editing one knows to mirror the other. Not a blocker.

---

## Cross-lane reminders (not your work)

- **Q1 is half Kiro's:** the gateway must hash the raw received body bytes (above). Already noted in his review.
- **End-to-end deletion** still depends on Kiro's server `/delete-account` passing its live test (12-table wipe). Your half is correct; E2E can only be signed off after his test runs.

---

## Bottom line

Ship it after fix #1 (un-attest `/tour-status`) — that's a quick edit and keeps a latent quota bug out of the build. Treat #2 (iOS close behavior) as a must-verify on a real iOS device before App Store submission. Q1's gateway side goes to Kiro. Then bump to `2.1.1+8` and build.
