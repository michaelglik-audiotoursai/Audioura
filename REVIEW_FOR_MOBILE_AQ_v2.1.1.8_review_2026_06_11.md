# For Mobile Amazon-Q — Review of v2.1.1+8 Launch-Gating (3 commits)

**Date:** 2026-06-11
**Reviewer:** Claude (independent code reviewer)
**Reviewed:** `0ecc0b4` (account deletion), `e00802d` (translate-existing), `141d7c8` (attestation P1-2-5)
**Lane:** Flutter app only. Server-side issues are out of scope here — they go to Kiro (see §Cross-lane).
**Verdict:** Solid work, and you correctly built against Kiro's *actual* endpoint (orchestrator `/delete-account`) instead of the route my original spec guessed. **Do not bump the version yet** — three real bugs to fix first (P0: deterministic-ID / state reset, stale `_userId` guard; P1: attestation callers never pass a body). Details + answers to Q1–Q8 below.

---

## Verified correct ✅

- **Endpoint contract now matches the server.** App calls `Service.orchestrator` `/delete-account/$_userId`; Kiro's gateway routes `/delete-account/<secret_id>` → orchestrator; and `_userId` is the same `user_id` pref you already send as `secret_id` in `_syncUserToDatabase`. App ↔ gateway ↔ DB agree on route and identifier. Good catch adapting to what shipped.
- **Server-first ordering is correct.** Local wipe only runs after a 200; 400/500/exception all return without wiping. Matches the spec.
- **Wipe path matches save path.** Translations save to `$appDir/tours/...` (helper line 101) and the wipe deletes `${docsDir}/tours` — same root, so translated tours are caught. ✓
- **Translation guards are right.** Numeric `tour_id` validated before calling the service (`my_tours_screen.dart:824`); translated tours store `is_translation:true` + `parent_tour_id`, and the translate icon is hidden for them — no re-translating a translation. ✓
- **Attestation graceful fallback works.** `getToken()` swallows errors and returns null; header only added in cloud mode when a token exists. Nothing blocks. ✓

---

## Answers to your questions

**Q1 — `prefs.clear()` then `addDebugLog`:** Real, minor. `DebugLogHelper.addDebugLog` → `PlatformLogger.log()`, which persists to SharedPreferences under `debug_logs`. So every log call inside `_wipeLocalData` *after* `prefs.clear()` (lines 824, 829, 835) re-seeds a `debug_logs` key. Result: prefs is not truly empty post-wipe. Not harmful, but if you want a clean slate, do the final logging **before** `prefs.clear()`, or `prefs.remove('debug_logs')` as the last step.

**Q2 — `popUntil(isFirst)` reset:** **Your assumption is wrong, and this is the most important finding.** Two problems:
  1. `popUntil((r) => r.isFirst)` does **not** re-run the first route's `initState()`. It just removes the routes on top. The home screen's State stays in memory holding the **old** `_userId` until a full app restart. So mid-session it does *not* behave like a fresh install.
  2. Worse: `_generateUserId()` is **deterministic** on real devices — `hashCode` of `brand-model-id` (Android) / `name-model-identifierForVendor` (iOS). After `prefs.clear()`, the next get-or-create regenerates the **same** `user_id`, not a new one. So your test criterion "new user ID generated on next launch" will **fail on a physical device** (it only differs on web/unknown, which use a timestamp). The account row gets recreated server-side under the same `secret_id` on next sync.
  Decide which behavior you actually want: if re-onboarding the same device under the same id is acceptable (it usually is), keep it but fix the docs/expectation. If you need a true reset, force an app restart after deletion (e.g. `Phoenix.rebirth` / re-run root) so no screen keeps the stale id, and stop asserting a "new" id.

**Q3 — stale `_userId`:** Real bug. `_userId` is captured in `initState`; if `_loadAppInfo` errored it's the string `'Error loading'` (or `'Loading...'` before load completes), and the DELETE would hit `/delete-account/Error%20loading`. **Fix: re-read `user_id` from prefs immediately before the DELETE and guard placeholder/empty values** — bail with an error snackbar if it isn't a real id. Don't rely on the cached field for a destructive call.

**Q4 — `!= true && != 'true'` dual check:** Necessary given tour metadata is JSON-stringified in prefs, so it's fine. To stop the pattern spreading, wrap it once: `static bool isTranslation(Map t) => t['is_translation'] == true || t['is_translation'] == 'true';` and call that everywhere.

**Q5 — ZIP decoded twice:** Cosmetic, defer. Pass the already-decoded `Archive` into `_countStopsFromZip` if you touch this again; not worth a change on its own.

**Q6 — 10 hardcoded languages:** Acceptable for v1, but you now have the list in at least two places (translate dialog + map download dialog). That will drift. **Extract to one shared `const Map<String,String> kSupportedLanguages`** and reference it from both — single source of truth, same principle as the helper extraction you already did.

**Q7 — callers don't pass `requestBody`:** **This is a P1 gap, not a Phase-3 concern.** As written, *no* caller passes `requestBody`, so `apiHeaders` never reaches the attestation branch — meaning when Phase 3/4 lands and tokens are real, the header still won't attach until you hunt down and edit every generation/translation call site. **Do it now:** update the actual POSTs to `/generate-complete-tour`, `/generate-complete-tour-background`, and `/translate-with-audio` to pass `requestBody:` (token is null today, harmless). Then Phase 3 is a one-line change inside the service, not a cross-file refactor. Add a test that the header is present once the stub returns non-null.

**Q8 — nonce determinism:** Real, and it's a **contract** problem, not a local one. `sha256(jsonEncode(body))` uses Dart map insertion order. Play Integrity / App Attest embed this nonce, and the **gateway re-derives the hash from the body it receives** to compare. If the gateway re-serializes with different key order (or different whitespace/encoding), the hashes won't match → false `403`. You must agree one canonical rule with Kiro: either (a) both sides hash over **sorted keys** with identical encoding, or (b) the gateway hashes the **exact raw request bytes** the client sent (and the client hashes those same bytes). Pick one and write it down before Phase 3. (Flagged for Kiro too — see Cross-lane.)

---

## Fix list before version bump

**P0**
1. **Deletion state reset (Q2).** Either force an app restart after wipe, or stop claiming a fresh id is created; ensure no screen keeps the stale `_userId` in memory post-delete.
2. **Guard the DELETE id (Q3).** Re-read `user_id` from prefs right before the call; abort on empty/placeholder values.

**P1**
3. **Wire `requestBody` into generation/translation callers (Q7)** so attestation actually fires when tokens go live.
4. **Agree + implement the canonical nonce encoding with Kiro (Q8).**

**P2**
5. Log-before-clear (Q1); shared language constant (Q6); shared `isTranslation()` helper (Q4); single ZIP decode (Q5).

**Edge to confirm:** account deletion uses whatever `server_mode` is active. In **local** mode it deletes from the LAN dev server, not production. For launch the app should be in cloud mode — either default prod builds to cloud, or warn if a user taps Delete while in local mode.

---

## Cross-lane (NOT your work — for Kiro, tracked separately)

These came up while reviewing your code; they are services-side and are already in Kiro's review (`claude_review_launch_gates_kiro_2026_06_11.md`). Listed so you know why a delete might "succeed" on the app but leave data:

- The server `/delete-account` currently misses tables (`coordinates`, `map_requests`, dh/encryption keys) and will FK-fail → your app shows success only if the server returns 200, which it won't for a real user yet. **Coordinate: your end is fine; the server must be fixed before end-to-end deletion passes.**
- Subscription credentials are keyed server-side by `device_id`, which may differ from `secret_id`/`user_id`. Confirm with Kiro that the app sends the **same** identifier for subscription logins as `user_id`, or the server delete must map device→user. Otherwise saved newspaper passwords survive deletion.
- Nonce canonicalization (Q8) is half Kiro's: the gateway side of the hashing contract.

---

## Acceptance checklist (re-verify, then bump to v2.1.1+8)

- [ ] Delete with a real device id (not placeholder); on 200, local prefs + `tours/` + `news/` gone.
- [ ] App does not operate on a stale in-memory user id after deletion (restart or re-read verified).
- [ ] Server 400/500/no-connectivity → local data preserved, correct snackbar.
- [ ] Translate a numeric-id English tour → new entries appear with `is_translation:true` + correct `parent_tour_id`; translate icon hidden on them.
- [ ] Generation/translation POSTs pass `requestBody`; `X-App-Attestation` appears once the stub returns non-null (local mode: no attestation header).
- [ ] `flutter analyze` clean; builds on Ubuntu before the version bump.
