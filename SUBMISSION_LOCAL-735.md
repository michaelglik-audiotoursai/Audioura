# SUBMISSION — LOCAL-735

**Reorganise "Your plan": current plan → Upgrade your plan (code) → Apply for the Free plan (Introduction only) → rest as is**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-735-plan-screen-order`
- **Base:** `subscribed` @ `157688f7` (verified: `git merge-base --is-ancestor 157688f7 HEAD` → exit 0)
- **code_sha:** HEAD of `LOCAL-735-plan-screen-order` at push (this commit). Previous staged sha before the doc-sha amend: `666da76c`.

---

## What changed

### 1. Plan screen reorder — `audio_tour_app/lib/screens/plan_screen.dart`

New top-to-bottom order, matching Michael (2026-10-22):

1. **Current plan card** — unchanged, including the LOCAL-733 "what's left · until …" line.
2. **"Upgrade your plan"** (`_upgradeCard()`) — shown on **every** level. One short line
   ("Have a code from Audioura, a friend's invitation or the Free-plan queue? Enter it here to
   switch your plan.") + the single code field and **Use code** button (same `/l2/claim` redeem
   call; one box, server decides the code kind).
3. **"Apply for the Free plan"** (`_applyFreeCard()`) — shown **only on Introduction (l1)**
   (`if (_ent.level == 'l1')`). Explains the generation allowance, with the stop count read from
   the **plan data the screen already loads** (`_freePlanAllowanceText()` reads the Free/l2 level's
   `maxStops`, falling back to the stated sentence), plus the existing "Join the queue" /
   "Update my queue email" action and the queue-position / pending-offer text. Hidden on Free,
   paid, tester and admin.
4. **"Buy a pack"**, then **"The plans"** — unchanged.

Removed the old level-aware `_freeCard()` / `_freeCardIntroduction()` / `_codeOnlyCard()` and the
"Get the Free plan" / "Have a code?" / "I have a code" framing. The shared `_codeBox()` no longer
takes a `withHeading` flag. New widget keys for tests: `upgrade_card_title`, `apply_free_card_title`,
`apply_free_allowance_text`.

### 2. Code-switch carry-over (keeps D703 true) — backend

A level code that switches to a **paid** level (l3/l4) while a paid pack is active must **not** wipe
what is left — it carries over with the SAME rules as a purchase (LOCAL-733). A code to
Introduction / Free / tester keeps today's behaviour (fresh pack, no carry).

- `level_codes.py` (**both** repo-root and `user-tracking/` copies, kept **byte-identical** —
  verified with `diff`): `claim_level_code(...)` gains an optional `carry_over=None` callable
  `(cur, user_id, new_level, now) -> (fresh_used, edits_used, ops_used)`. The l3/l4 branch calls it
  **before** the INSERT and writes the returned counters (via `EXCLUDED`) instead of the old hard
  `0/0/0`. When omitted (the CLI path) or when there is no active pack, counters start fresh — the
  pre-LOCAL-735 behaviour. The module stays framework-free; the carry-over logic is **not** copied
  here.
- `user-tracking/entitlements_api.py` `/l2/claim` route: injects a small `_carry_over` adapter that
  reads `_get_device_state` / `_get_plan` and returns `_carry_over_used(...)` — the single LOCAL-733
  implementation, **reused, not copied**.

`l2_seats.py:372` (the line the ticket flagged) is `evict_idle` — it drops an **idle** L2 device
back to L1 (a lapse, not a code switch) and correctly keeps today's 0/0/0 reset; it is untouched.

---

## Tests

### Flutter widget tests — all green, `flutter analyze` clean

```
flutter analyze lib/screens/plan_screen.dart test/plan_screen_level_aware_test.dart \
  test/plan_screen_free_card_test.dart test/plan_screen_buy_buttons_test.dart
  → No issues found!

flutter test test/plan_screen_level_aware_test.dart test/plan_screen_free_card_test.dart \
  test/plan_screen_buy_buttons_test.dart
  → 00:01 +33: All tests passed!
```

Coverage (`test/plan_screen_level_aware_test.dart`, `test/plan_screen_free_card_test.dart`):
- "Upgrade your plan" with the code box present on **every** level (l1, l2, l3, l4, admin);
- "Apply for the Free plan" present on **l1 only**, absent on l2/l3/l4/admin;
- the Apply card's generation allowance reads the day/month counts and the stop count from the
  server payload (`up to 6 stops` when the l2 row says 6);
- section order on Introduction: current → Upgrade → Apply → (below the fold) Buy a pack;
- section order on a paid level: current → Upgrade → Buy a pack, no Apply card;
- buy-button labels unchanged, no user-facing "round"; the LOCAL-610/733 rules text preserved.

**RED test** (`RED: Apply card must not appear on a paid level (l3)`): verified it FAILS when the
Apply card is shown on a paid level. Temporarily making `_applyFreeCard()` render on every level:
```
Actual: _TextWidgetFinder:<Found 1 widget with text "Apply for the Free plan">
FAILED … RED: Apply card must not appear on a paid level (l3)
```
Reverted; the suite is green again.

### pytest — code + carry-over rule — `tests/test_local735_code_carryover.py`

```
python3 -m pytest tests/test_local735_code_carryover.py -q
  → 9 passed

python3 -m pytest tests/test_local735_code_carryover.py tests/test_local733_pack_carryover.py \
  tests/test_local604_plan.py tests/test_local596_mirror_in_sync.py -q
  → 38 passed
```

- **Headline (the ticket):** $10 Pack (l3) with **3 units left** + a code to **Curator (l4)** →
  **25 + 3 = 28 ops**. ✅
- same paid level by code (l3 with 3 fresh + 1 edit left + l3 code) ADDS → 8 fresh, 6 edits;
- a code to Introduction / Free / tester clears the pack (today's rule);
- an EXPIRED l3 pack + a Curator code starts fresh (25 ops, no carry);
- a no-prior-pack device + a Curator code starts fresh (25 ops);
- **RED test**: verified it FAILS against the old 0/0/0 reset — with the hard reset restored the
  headline case gives `AssertionError: 25 == 25` (old reset would give 25, carry-over gives 28).
  Reverted.

Isolation (`_isolated_db.IsolatedSchema`) proof printed on teardown — **zero** writes to public:
```
public.device_entitlement   before=17  after=17
public.purchases            before=6   after=6
public.level_codes          before=0   after=0
OK — zero shared/production writes.
```

Both `level_codes.py` copies confirmed **byte-identical** after the edit
(`test_local596_mirror_in_sync` green; `diff` on the two files empty).

---

## Live test (iOS simulator, isolated containers)

- **Simulator:** iPhone 17 Pro Max (booted). **Never** a physical phone.
- **Containers:** a minimal **isolated** stack — `docker compose -p local735` (postgres + user-api),
  spare host ports **5442** (postgres) and **5103** (user-api), own volume `pgdata735`,
  `ALLOW_UNAUTHENTICATED_ENTITLEMENTS=true`. **Never** `-p audioura`; the `audioura-*` stack
  (13 containers) was left running and untouched; the local735 stack was torn down with `-v`.
- Applied migrations 010, 012, 013, 014, 015, 016 into the local735 DB (plans seeded: l2
  max_stops=5, l3 5/5 units, l4 25 ops).
- Devices: `LIVE735-intro` = fresh l1; `LIVE735-pack` = active l3 pack seeded (fresh_used=2,
  edits_used=3 → 3 new tours + 2 edits left, anniversary 21 Nov 2026). Both verified live via
  `GET /entitlements/me`.
- Screenshots via `flutter drive` of `integration_test/plan_screen_order_screenshot_test.dart`
  (host driver `test_driver/local735_screenshot_driver.dart`), with
  `--dart-define=DEBUG_SERVER_IP=127.0.0.1` forcing local server mode so the REAL `PlanScreen()`
  fetches the LIVE payload. Both tests passed with live assertions (Introduction: Upgrade + Apply
  cards present; $10 Pack: "Current plan: $10 Pack", Upgrade present, Apply absent, "3 new tours
  and 2 stop-adding edits left · until 21 Nov 2026").

> A single temporary, **uncommitted** edit pointed the app's `Service.userDb` local port at the
> spare container port (5003 → 5103) for the run; reverted afterwards — `git diff` on
> `endpoints.dart` is empty.

**Screenshots** (1320×2868, attached):
- `audio_tour_app/build/local735_screenshots/local735_introduction.png`
- `audio_tour_app/build/local735_screenshots/local735_10_pack.png`

### Row counts (every table written)

| table | before | after | notes |
|---|---|---|---|
| device_entitlement | 1 | 2 | the +1 is `LIVE735-pack`, seeded out-of-band **before** the run; the screenshot run itself (2× `GET /entitlements/me`) wrote nothing |
| purchases | 0 | 0 | — |
| level_codes | 0 | 0 | — |

No deletes of purchase-bearing rows (D690). No `DELETE FROM audio_tours`.

### Budget

**$0.00** — the plan screen needs only `GET /entitlements/me`; no tour generation, no paid APIs.
Well within the ≤ $0.20 cap.

---

## Files changed

Modified:
- `audio_tour_app/lib/screens/plan_screen.dart`
- `audio_tour_app/test/plan_screen_level_aware_test.dart`
- `audio_tour_app/test/plan_screen_free_card_test.dart`
- `level_codes.py`
- `user-tracking/level_codes.py`
- `user-tracking/entitlements_api.py`

Added:
- `tests/test_local735_code_carryover.py`
- `audio_tour_app/integration_test/plan_screen_order_screenshot_test.dart`
- `audio_tour_app/test_driver/local735_screenshot_driver.dart`
- `SUBMISSION_LOCAL-735.md`

Not touched: DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`. ClickUp status unchanged.
