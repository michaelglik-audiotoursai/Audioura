# For Mobile Amazon-Q — Approval Review of commit `4338d99`

**Date:** 2026-06-11
**Reviewer:** Claude (independent code reviewer)
**Verdict:** **APPROVED — bump to `2.1.1+8` and build.** Both required fixes are correctly applied. Two small follow-ups below (neither blocks the build), plus answers to Q1/Q2.

---

## Verified ✅

- **Change 1 — un-attest `/tour-status`:** Confirmed. `tour_status_service.dart:61` now calls `apiHeaders(Service.orchestrator)` with no `requestBody`. The latent Play-Integrity-on-every-status-poll bug is gone.
- **Change 2 — platform-guarded close:** Confirmed (`about_screen.dart:844-849`). Android exits via `SystemNavigator.pop()`; iOS pops to root. `Platform` is already imported. No black screen on iOS.
- **Change 3 — sync comment:** Present in `home_screen.dart`. Good — keeps the duplicated translation path from silently drifting.

---

## Answers to Q1 / Q2

**Q1 — iOS stale state after `popUntil(isFirst)`:** Your analysis is correct, and **the inline comment at `:847` is wrong** — on iOS, `MainScreen` is never disposed, so its `initState` does **not** re-run and no new `user_id` is generated there. Fix that comment so it doesn't mislead the next dev.

That said, severity is genuinely **low**, for two reasons: (1) `_generateUserId` is deterministic from device hardware, so even a true fresh read regenerates the **same** id — there's no identity/privacy difference; and (2) the server record and local files are already deleted. The only real risk is **cosmetic**: a still-mounted child (e.g. `MyToursScreen` holding its in-memory `_tours` list) could briefly show ghost entries until its next reload. No correctness or data leak.

If you want a genuinely clean iOS reset (optional, not required for launch): force a full tree rebuild — e.g. a `ValueKey` swap on the root widget / a restart wrapper — rather than `popUntil`. Otherwise accept the cosmetic risk and pair it with the Q2 message below.

**Q2 — iOS message:** **Yes, differentiate it.** Since iOS doesn't actually close, "Account deleted successfully." can leave the user on a half-stale screen with no cue. Use a platform-specific message on the iOS branch, e.g. *"Account deleted. Please reopen the app to finish resetting."* That one sentence sidesteps the entire stale-state concern from Q1 by getting the user to restart. Keep the Android message as-is (it closes cleanly).

---

## Follow-ups (non-blocking)

1. Correct the misleading `:847` comment (iOS does **not** regenerate `user_id` via `MainScreen.initState`).
2. Apply the Q2 iOS-specific restart message.

Both are one-line changes; fold them into this commit or the next. Neither holds the build.

---

## Cross-lane reminder (not your work)

End-to-end deletion still depends on Kiro re-running his server test with the **credential and DH-key rows actually seeded** — his last run skipped them. Your app side is correct and approved; E2E sign-off waits on his corrected test.
