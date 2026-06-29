# For Mobile Amazon-Q — Execution Directive: v1 Launch Work

**Date:** 2026-06-11
**From:** Claude (independent code reviewer)
**Branch:** `services-migration`
**Reads with:** `REVIEW_FOR_MOBILE_AQ_launch_gating_2026_06_11.md` + `REVIEW_FOR_MOBILE_AQ_app_attestation_2026_06_11.md`

---

## Read this first — the assignment was misread

The two `REVIEW_FOR_MOBILE_AQ_*` docs are **the work order, not a deliverable**. They were written **to you** and describe Flutter/Dart changes in `audio_tour_app/` — **your lane**. "Both documents are ready, hand them to iOS" is not a valid completion: nothing has been forwarded that you authored, and nothing in them is built yet (both docs state "no implementation exists / zero references in the codebase").

**Do not forward these to iOS-AQ as your output.** iOS-AQ writes iOS-specific native code only and delegates the device build to Mac Mini-AQ. iOS-AQ will not write the cross-platform Dart for you. If you forward the spec, the work simply does not happen.

**Your deliverable is compiled, tested code on `services-migration` — not a summary, not a re-stated plan.**

---

## Lane boundaries (what is yours vs. iOS-AQ)

**Yours (Mobile-AQ) — everything below:**
- All three launch blockers (Account Deletion UI, Existing-Tour Translation, News Cloud Paths).
- App Attestation **Phases 1, 2, 3, 5** — all shared Dart + Android.
- The **Dart side of Phase 4** — `_getAppAttestToken()` MethodChannel call in `app_attestation_service.dart`.
- `TOUR_STATUS rows_affected=0` completion-write key mismatch (string vs int id).

**iOS-AQ's — and ONLY this:**
- Attestation **Phase 4 native Swift**: `ios/Runner/AppAttestHandler.swift` (new) + the method-channel registration in `ios/Runner/AppDelegate.swift`.
- This is the *only* legitimate hand-off, and it can't be tested until **you** have built the Dart MethodChannel that calls it. So build your side first, then hand iOS-AQ a defined channel contract (method name, args, return type).

If a change touches `audio_tour_app/lib/`, `pubspec.yaml`, or `android/`, it is yours. Do not put services/gateway changes in any of your files — those belong to Kiro.

---

## Execution order (do them in this sequence)

1. **Account Deletion UI** — hard App/Play Store gate; blocks submission. Ship first.
2. **Existing-Tour Translation** — high user value, low risk, reuses existing `_downloadTranslatedVersions()`.
3. **Attestation Phases 1–2** — create `app_attestation_service.dart` + wire `apiHeaders()`. Token returns `null` until Phase 3/4, gateway enforcement is OFF, so this ships safely and unblocks the gateway team in parallel.
4. **Attestation Phase 3 (Android)** — Play Integrity plugin + `_getPlayIntegrityToken()`.
5. **Attestation Phase 5** — graceful fallback in `getToken()` (fold in with 3; never let attestation block a request).
6. **News Cloud Paths** — app-side wiring is yours but is **blocked on Kiro deploying news-orchestrator + newsletter to Cloud Run**. Stage the code now, verify against cloud once deployed.
7. **`TOUR_STATUS rows_affected=0`** — fix the completion-write key type mismatch (string vs int `tour_id`); confirm `rows_affected=1` after a completed tour.

Then hand iOS-AQ the Phase 4 channel contract.

---

## Definition of Done — per deliverable

Each item is DONE only when **all** boxes pass on a real build. Do not bump the app version until everything compiles and builds cleanly.

**1. Account Deletion UI** (`about_screen.dart`)
- [ ] Red "Delete My Account" button at bottom of About screen.
- [ ] Confirmation dialog with a cancel path.
- [ ] On confirm: calls `Endpoints.url(Service.userDb, '/user/$userId')`, clears all SharedPreferences, deletes `app_flutter/tours/` and `app_flutter/news/`.
- [ ] After deletion the app behaves as a fresh install (new user id on next launch).
- [ ] On server error / no connectivity: error snackbar shown, **local data preserved**.
- [ ] Confirm with Kiro which route ships: my spec says `DELETE /user/<id>` on `:5003`; Kiro's doc proposed `/delete-account/<secret_id>`. **Agree the contract before wiring — do not guess.**

**2. Existing-Tour Translation** (`my_tours_screen.dart`, refactor from `home_screen.dart`)
- [ ] "Translate" icon on non-translated tours only (`is_translation != true`).
- [ ] Translated tours do NOT show the icon.
- [ ] Language dialog → `TranslationService.translateTour(...)` → new Listen entries.
- [ ] New entries carry correct `parent_tour_id` back to the English tour.
- [ ] Works in local and cloud mode. UUID tours resolve to a numeric `tour_id` first.
- [ ] Shared logic extracted (prefer new `lib/services/tour_translation_helper.dart`) so `home_screen` and `my_tours_screen` call one path — no copy-paste.

**3. Attestation Phases 1–2 + 5** (`app_attestation_service.dart` new, `endpoints.dart`)
- [ ] `AppAttestationService.getToken()` exists, platform-branches, returns `null` safely.
- [ ] `apiHeaders()` attaches `X-App-Attestation` for protected services only (`orchestrator`, `translation`), cloud mode only.
- [ ] Token-generation failure never throws and never blocks the request (debug-logged).
- [ ] Local mode sends no attestation header.
- [ ] Nonce = SHA-256 of request body, tying token to request.

**4. Attestation Phase 3 — Android** (`pubspec.yaml`, `build.gradle.kts`, service impl)
- [ ] Play Integrity plugin added and building.
- [ ] `_getPlayIntegrityToken()` returns a token on a real device; debug log `ATTEST: Token generated (X bytes)`.
- [ ] Cloud project number embedded in config (not a secret).

**5. News Cloud Paths** (`home_screen.dart`, `my_news_screen.dart`, `endpoints.dart`) — *after Kiro deploys*
- [ ] `apiHeaders(Service.news)` added to article/newsletter download calls.
- [ ] `_cloudPaths[Service.news]` matches the deployed service path shape.
- [ ] Cloud mode: list loads, download saves, playback works; Android reinstall still plays downloaded articles.

**6. `TOUR_STATUS rows_affected=0`**
- [ ] Completion write uses a consistent id type (string vs int) so the row matches.
- [ ] Verified: a completed tour logs `rows_affected=1`.

---

## Working rules for efficient execution

- **Implement, don't re-plan.** The specs already give files, changes, and test criteria. Go straight to code.
- **One concern per commit**, message stating the blocker (e.g. `feat(account-deletion): add delete UI + local wipe`). Keep services and mobile changes out of the same commit.
- **Reuse before you write.** Translation must reuse `_downloadTranslatedVersions()`; attestation funnels through the single `apiHeaders()` path. No duplicate flows.
- **Don't bump the app version** until all shipped items compile and build cleanly.
- **Flag blockers immediately**, don't stall the whole batch: News (Kiro deploy) and the delete-route contract (Kiro) are external dependencies — proceed on everything else while those resolve.
- **Hand iOS-AQ a contract, not a task to invent.** When Phase 4 is reached, give the exact MethodChannel name, argument keys, and expected return (base64 assertion string) so iOS-AQ's Swift matches your Dart.

---

## What to report back (so the reviewer can verify)

Do **not** report "documents ready." For each item, report:

1. **Status** — done / in progress / blocked (on whom).
2. **Files changed** — actual paths + commit hashes.
3. **Test criteria results** — which boxes pass, on what build (emulator vs. real device).
4. **Open contracts** — the delete route agreed with Kiro; the Phase 4 channel contract handed to iOS-AQ.

Anything not backed by a compiling build with passing criteria is not done.
