# SUBMISSION — LOCAL-732: Warn a member once, on opening Audioura, when a community pass ends within 3 days

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-732-pass-expiry-warning`
**Base:** `subscribed` (HEAD `ffd72a28`, LOCAL-731 already merged — its `PassExpiryFormat` is reused)
**code_sha:** `d641822f` (commit on `LOCAL-732-pass-expiry-warning`)

## What the task asked for
Michael (2026-10-22): "warn member that their subscription to a community is about
to expire, maybe 3 days before, and only once upon entry to Audioura." The server
already flags a 3-day reminder (`run_reminders` in `user-tracking/communities_api.py`,
D657/D658) but nothing delivered it. This change delivers it **in the app**, from
data the app already loads. **Nothing on the server changes.**

## What I built (app-only)

| File | Change |
|---|---|
| `audio_tour_app/lib/services/pass_expiry_format.dart` | **Reused LOCAL-731 formatter**, added `formatShort` → `"Fri 24 Oct · in 2 days"` / `"… · in 5 hours"` (+ `formatWeekdayDate`). Returns null for no-expiry / expired. |
| `audio_tour_app/lib/services/pass_expiry_warning.dart` | **New.** `PassExpiryWarning.select` — pure, Flutter-free selector over the `JoinedCommunity` list (active + `0 < time left ≤ 72 h`, skips free/no-expiry and already-expired). `PassWarnedStore` — SharedPreferences once-key store, key `pass_warned_<id>_<expires_at>`, keeps the last 50 keys. |
| `audio_tour_app/lib/widgets/pass_expiry_warning_dialog.dart` | **New.** One dialog for ALL qualifying communities: title "Community pass ending soon", one row per community with a **Renew** link each, the "Renew to keep getting new episodes and tours. Buying another pass adds its days to your remaining time." body, and a single **Later**. No store names. |
| `audio_tour_app/lib/screens/main_screen.dart` | **Wired in.** Cold start (post-frame) + resume after > 1 h in the background (`_lastPausedAt`). Only when Home (tab 0) is visible; MainScreen only mounts AFTER onboarding + the first-run notice, so the dialog can never sit over those. `_maybeWarnPassExpiry`: load My communities → `select` → drop already-warned → show ONE dialog → **then** `markWarned`. Renew opens that community's page; Later closes. |

### Behaviour details
- **When:** cold start, and resume only if away > 1 h (a brief switch-away does not re-check). Home tab only.
- **Which:** active membership ending within 72 h. Free / no-expiry skipped. Already-expired skipped (that is the server's at-expiry case).
- **Owner's own community:** never appears — `/communities/mine` lists `community_memberships` rows, and the owner is not a member of their own community (D665 addendum). Documented in code + covered by a test.
- **Once:** keyed by `community_id + expires_at`. A renewal moves `expires_at` (D701) → new key → warns again. Cap 50 keys.
- **Network failure:** `CommunitiesService.mine` swallows transport errors to `[]` → nothing shown, nothing stored. `markWarned` runs only AFTER the dialog is shown, so a failure can never silently consume a warning.

## Tests

New/updated test files (all green):
- `test/pass_expiry_warning_test.dart` — selection: **2 days → warn; 4 days → no; expired → no; free → no; owner (never in list) → no**; boundary (exactly 72 h → warn); under-24 h → warn; mixed list returns only qualifying. Once-rule: first run shows → second run (same `expires_at`) shows nothing; **renewal (new `expires_at`) warns again**; 50-key cap; key shape `pass_warned_<id>_<expires_at>`.
- `test/pass_expiry_warning_dialog_test.dart` — **dialog lists two communities with a Renew link each**, short-formatted lines, body wording, Later; Renew fires the right id; **RED: a row never prints the raw ISO `expires_at`**.
- `test/pass_expiry_warning_red_test.dart` — **RED (once-key):** second launch with the once-key check suppresses the dialog; the raw selection (no check) would still show it — documents the regression a missing check ships.
- `test/pass_expiry_format_test.dart` — `formatShort` cases (2 days / 5 hours / singular / null-blank-expired / `formatWeekdayDate` shape "Fri 24 Oct").

### Red test — verified failing without the once-key check
I temporarily bypassed `PassWarnedStore.unwarned` (returned all passes). Result: the
RED test and the once-rule tests failed (3 failures, `Expected: empty / Actual:
[Instance of 'ExpiringPass']`). Restored the check → all green. This proves the
once-key check is load-bearing.

### Results
- **30 new tests pass.**
- `flutter test` full suite: **783 pass, 6 fail**. All 6 failures are pre-existing
  `test/local109_swipe_e2e_test.dart` cases that require a live backend at
  `http://localhost:5102` (SocketException: Connection refused) — unrelated to this
  change, which touches no networking.
- `flutter analyze` on all 8 of my files: **No issues found.** (The repo-wide
  ~1375 `info` lints are pre-existing style notes across the whole codebase.)

## Live test (iOS simulator — iPhone 17 Pro Max, booted)

A **full end-to-end live test against a real backend + DB was a confirmed hard
blocker** (see below). I instead ran a **safe, non-destructive simulator render**
that drives the **real production pieces** — `PassExpiryWarning.select` +
`PassWarnedStore` (SharedPreferences once-key) + `PassExpiryWarningDialog` — over
two simulated launches from in-memory `JoinedCommunity` rows (mock SharedPreferences,
**no backend, no DB, no `audioura-*` contact**). The temporary harness
(`audio_tour_app/tool/local732_harness.dart`) was deleted afterwards.

Screenshots:
- `local732_shots/local732_first_launch_dialog.png` — first launch: dialog titled
  "Community pass ending soon" with **two** rows — "Harbourside Walks: ends Sat 24
  Oct · in 1 day" + Renew, "Old Town Tales: ends Thu 22 Oct · in 9 hours" + Renew —
  the adds-days body and **Later**. The 4-days-out "Far Away Club" is correctly
  **absent**.
- `local732_shots/local732_second_launch_no_dialog.png` — second launch: "2 pass(es)
  still qualify, but all already warned → NO dialog (once-key)."

### Row counts (before / after)
**Zero rows written to any table.** The render harness used in-memory `JoinedCommunity`
data and a mock SharedPreferences only — it never opened a socket or a database. All
`audioura-*` containers were verified still `Up` and untouched before and after. No
DB table was read or written, so every table's row count is unchanged (Δ = 0),
including `community_memberships` and `audio_tours`. No deletes of anything.

### Why no real-backend end-to-end test (documented blocker)
- The app hardcodes `Service.userDb` to **port 5003** (`lib/config/endpoints.dart`,
  `_localPorts`); there is no port override (only `DEBUG_SERVER_IP`, which keeps the
  fixed port).
- Port 5003 is held by the **protected `audioura-user-api-2-1`** container, which the
  task forbids me to touch (`never touch audioura-*`).
- Standing up an isolated `-p local732` stack from `user-tracking/docker-compose.yml`
  would **collide** on host ports 5003 / 5433, the shared `postgres_data` named
  volume, and the external `development_default` network — all shared with the
  protected stack.
- The only populated DB is the protected `audiotours` DB (behind `postgres-2`), and
  the task forbids editing its `community_memberships` rows.

Given those constraints, the DB-editing live test could not be done without touching
the protected `audioura-*` resources. The simulator render above exercises the exact
production widgets + once-key logic end-to-end at the app layer, and the unit/widget
tests cover the selection, the once rule (incl. renewal), the network-failure path,
and the RED test.

## Budget
Well under $0.20 — local Flutter build/test + simulator render only; no paid API calls.

## Process notes
- Committed to `LOCAL-732-pass-expiry-warning` with explicit file paths (never `git add -A`).
- Did **not** edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD. Did not change ClickUp status.
- Base verified: `git merge-base --is-ancestor ffd72a28 HEAD` → exit 0.
