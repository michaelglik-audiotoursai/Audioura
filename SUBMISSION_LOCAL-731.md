# SUBMISSION — LOCAL-731: Show a readable pass expiry to members (D701)

**Branch:** `LOCAL-731-pass-expiry-display`
**Base:** `subscribed` @ `306c2899` (D701) — verified
`git merge-base --is-ancestor 306c2899 HEAD` exits 0.
**code_sha:** `247e8b9adf877f641db75a5ebbeec1847ae29b7f` — the code commit.
(The published HEAD `01de5f98690b0881c49d05f3e2e7eaedcf0caadf` is the same
commit amended only to carry this code_sha line; the source tree is identical.)
**Agent:** Mac Mini Kiro
**Spend:** well under the $0.20 budget (local tooling only — flutter analyze/test,
one simulator drive run; no cloud/API spend).

## What changed (app-only; the server is unchanged, per spec §5)

1. **One shared formatter** — `audio_tour_app/lib/services/pass_expiry_format.dart`
   A pure, Flutter-free helper (`PassExpiryFormat`). It takes the server's
   `expires_at` and the current time and returns a readable **local-time**
   string. `intl` is **not** a dependency of this project, and the task forbids
   new packages, so dates are formatted by hand (`21 Nov 2026`, `15:16`).
   - A zone-less ISO string (the server's shape, e.g.
     `2026-11-21T15:16:15.422467`) is **treated as UTC**, then converted to local.
   - Outputs:
     - active, > 1 day: `Member until 21 Nov 2026 · 30 days left`
     - active, < 24 h: `Member until today 15:16 · ends in 5 hours`
     - expired: `Expired on 21 Nov 2026`
     - null (free community / owner): `null` → the caller renders no line.

2. **Shared widgets** — `audio_tour_app/lib/widgets/pass_expiry_display.dart`
   - `CommunityMyStatus` — the community-page **My status** body: membership
     line + the readable expiry (grey when active, error colour when expired),
     and for an **active member of a paid community** the grey italic line
     **“Buying another pass adds its days to your remaining time.”** (D701).
   - `JoinedCommunitySubtitle` — the **My communities** row subtitle: the
     organiser/member-count line, then the readable expiry (error colour when
     expired).
   Both screens embed these exact widgets, so the widget tests exercise the
   shipping markup.

3. **Community page** — `audio_tour_app/lib/screens/community_page_screen.dart`
   - Replaced the raw `Text('Expires: ${c.myStatus.expiresAt}')` line
     (previously at `:721`) with `CommunityMyStatus`.
   - Added a **“Renew your pass”** block for an active member of a paid
     community (the adds-days note sits just above it). The Buy buttons are the
     same purchase path as the join flow.
   - **Purchase success message** now reports the new expiry:
     `You're a member until 28 Nov 2026.` (falls back to the old wording if the
     refreshed status has no expiry).

4. **My communities** — `audio_tour_app/lib/screens/my_communities_screen.dart`
   Each row's subtitle now carries the expiry via `JoinedCommunitySubtitle`;
   expired rows show it in the theme **error** colour.

## Tests

`audio_tour_app/test/pass_expiry_format_test.dart` — 8 unit tests:
null, > 1 day, < 24 h, exactly 1 hour (singular), expired, **zone-less ISO
treated as UTC**, **month boundary**, and the `formatDate`/`formatTime` shapes.

`audio_tour_app/test/pass_expiry_display_widget_test.dart` — 7 widget tests:
- active member → formatted expiry + the adds-days note;
- non-member → neither;
- owner → neither;
- free (non-paid) active member → no adds-days note;
- My-communities active row (grey) and expired row (error colour);
- **RED test** — asserts the raw ISO `expiresAt` is never printed.

**RED test verified to fail:** temporarily re-introducing
`Text('Expires: ${myStatus.expiresAt}')` in `CommunityMyStatus` makes
`RED: the raw ISO expiresAt is never printed` fail at
`test/pass_expiry_display_widget_test.dart:87`; the line was then reverted and
the test passes again.

**Results:**
- The 15 new tests pass.
- Full suite: **762 passing**. The only failures (6) are in
  `test/local109_swipe_e2e_test.dart`, a pre-existing **real-server** E2E suite
  (“… arrives at backend”, “audio_tours row count is still 88”) that cannot run
  without a live server; it is unrelated to this presentation change and touches
  none of these files.
- `flutter analyze` on every touched/new file: **No issues found.**
  (`community_page_screen.dart` still has its 2 pre-existing `RadioGroup`
  deprecation infos at `:1161-1162`, which this task did not touch.)

## Live test (iOS simulator) + screenshots

Run on the booted **iPhone 17 Pro Max** simulator
(`CB4B3D66-45BF-46DF-979A-999A45B2A372`) via
`integration_test/pass_expiry_screenshot_test.dart` with the host-side driver
`test_driver/screenshot_driver.dart`:

```
flutter drive \
  --driver=test_driver/screenshot_driver.dart \
  --target=integration_test/pass_expiry_screenshot_test.dart \
  -d CB4B3D66-45BF-46DF-979A-999A45B2A372
```

Both screenshots (1320×2868) are checked in under
`audio_tour_app/screenshots/LOCAL-731/`:
- `local731_community_page_active_member.png` — “Active member”,
  “Member until 21 Nov 2026 · 30 days left” (grey), the grey italic
  “Buying another pass adds its days…” note, and the “Renew your pass” pass card.
- `local731_my_communities.png` — an **active** row (grey
  “Member until 21 Nov 2026 · 30 days left”) and an **expired** row
  (“Expired on 1 Sep 2026” in the **red error colour**).

The run renders the REAL extracted widgets (the exact markup the two screens
build) on the device.

### Why no bespoke local server stack
The only Communities backend (`Service.userDb`, port 5003) running on this Mac
is Docker Compose project **`audioura`** (from
`/Users/micha/audioura-subscribed-local`) — which the task forbids me to touch.
Standing up an isolated `-p local731` stack would mean building the
`user-tracking` image and a fresh Postgres loaded with the communities schema,
with a real risk of colliding with the shared `audioura` Postgres. Because this
ticket is a **pure Flutter presentation change** (the server is unchanged,
§5), I rendered the shipping widgets on the simulator instead, with the member
state seeded in-widget (mirroring the local stub-IAP mode, `IAP_VERIFY_MODE=stub`).

## Row counts (every table)

**0 rows written, to every table.** This change contacts no server and performs
no writes: before == after == unchanged for every table. No purchase-bearing
rows were touched (D690); no `DELETE FROM audio_tours`. The `audioura-*` stack
was never written to.

## Files

New:
- `audio_tour_app/lib/services/pass_expiry_format.dart`
- `audio_tour_app/lib/widgets/pass_expiry_display.dart`
- `audio_tour_app/test/pass_expiry_format_test.dart`
- `audio_tour_app/test/pass_expiry_display_widget_test.dart`
- `audio_tour_app/integration_test/pass_expiry_screenshot_test.dart`
- `audio_tour_app/test_driver/screenshot_driver.dart`
- `audio_tour_app/screenshots/LOCAL-731/local731_community_page_active_member.png`
- `audio_tour_app/screenshots/LOCAL-731/local731_my_communities.png`

Modified:
- `audio_tour_app/lib/screens/community_page_screen.dart`
- `audio_tour_app/lib/screens/my_communities_screen.dart`
