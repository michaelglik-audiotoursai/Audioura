# SUBMISSION — LOCAL-733: pack carry-over (D703)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-733-pack-carryover` (from `subscribed` @ `6416a986`)
**code_sha:** `d4ac1cc4` (the commit on this branch; see `git log -1`)

A pack bought while a pack is still active now ADDS to what is left (same level)
or converts the remainder 1:1 into the new level's units (different level). No
paid tour is lost. Members are shown what is left on the plan screen, near the
Generate button, and in the post-purchase message.

---

## Rules as implemented (D703)

All logic lives in the purchase grant of `user-tracking/entitlements_api.py`
(`POST /purchases/verify`), in the new helper `_carry_over_used(old_state,
old_plan, new_level, new_plan, now)` (with `_pack_units_left`). The grant reads
the device's current state/plan BEFORE writing, computes the new counters, and
UPSERTs them; the anniversary still becomes `now + 1 calendar month`.

1. **Same level while the current pack is active** (`now < anniversary_at`): the
   new pack ADDS. Implemented by LOWERING the used counters by the new pack's
   per-pack allowance, so a NEGATIVE "used" is the carried extra and
   `max(0, per_pack - used) = per_pack + extra`.
   - Chosen approach: **negative `*_used`**, NOT a new `*_bonus` column.
     `device_entitlement.fresh_used/edits_used/ops_used` are `INTEGER NOT NULL`
     with **no CHECK constraint** (verified: the only constraints are the PK and
     the `level` FK), so negatives are allowed and every `*_left` computation
     (`_allowances_left`, which the app reads) keeps working unchanged.
   - Example: $10 Pack with 3 fresh + 1 edit left → buy $10 Pack → **8 fresh,
     6 edits**.
2. **Different level while active** ($10 Pack ↔ Curator): what is left converts
   ONE FOR ONE into the new level's units, then the new pack is added.
   - **l3 → l4:** `(fresh_left + edits_left)` become extra Curator ops →
     `ops_used = -(fresh_left + edits_left)`.
   - **l4 → l3:** `ops_left` become extra fresh tours → `fresh_used = -ops_left`;
     edits start fresh.
   - `max_stops` / `can_sell` follow the NEW level (they come from the new
     level's `plans` row, unchanged).
3. **Expired pack** (`now >= anniversary_at`) **or first purchase / no prior
   pack window:** starts fresh from zero (unchanged behaviour).
4. The new month starts at the purchase (anniversary = `now + 1 calendar
   month`); the carried units live in that new month.
5. **Idempotency unchanged:** an already-processed `transaction_id` still
   returns `409 already_verified` and never grants (or adds) twice.
6. `/entitlements/lapse` and the anniversary expiry are untouched.

### Showing what's left (app)

- **Plan screen current-plan card** (`lib/screens/plan_screen.dart`): a new
  keyed line (`Key('plan_left_line')`) under the title, e.g.
  `"$10 Pack · 8 new tours and 6 stop-adding edits left · until 22 Nov 2026"`.
  The date reuses `PassExpiryFormat.formatDate` (LOCAL-731). Introduction shows
  nothing extra; Free shows `"N new tours left today"` (falls back to
  `"… this month"`).
- **Rules text** replaced: _"Buying early starts a new month and replaces what's
  left."_ → **"Buying another pack adds it to what's left and starts a new
  month."**
- **After a successful pack purchase:** the screen refreshes first, then the
  snackbar says what is now left, e.g. _"You now have 8 new tours and 6 edits
  until 22 Nov 2026."_
- **Generate Tour screen** (`lib/screens/tour_generator_screen.dart`): one short
  grey line (`Key('generate_tours_left_line')`) just above the Generate button,
  e.g. `"3 new tours left in your pack"` (paid) / `"1 new tour left today"`
  (Free). Hidden on Introduction (cannot generate) and on hidden/admin plans.
- The phrasing is centralised in a new Flutter-free helper
  `lib/utils/plan_left_summary.dart` (`cardLine` / `generateLine` /
  `purchaseMessage`), so the three surfaces read identically and are unit-
  tested directly.

---

## Tests

### Server — `tests/test_local733_pack_carryover.py` (pytest, audiotours_test only)

Uses the LOCAL-595 `IsolatedSchema` harness (private throwaway schema cloning
`plans`, `device_entitlement`, `purchases`; proves public row counts unchanged
in teardown). **8 tests, all pass:**

- `test_same_level_pack_adds_to_what_is_left` — 3 fresh + 1 edit left, buy $10
  Pack → **8 / 6**.
- `test_me_reports_the_new_left_after_carry_over` — `/entitlements/me` reports
  the new `fresh_left`/`edits_left` (8 / 6).
- `test_full_pack_bought_again_doubles` — 5 + 5 → 10 / 10.
- `test_expired_pack_does_not_carry_over` — anniversary pushed to the past →
  back to 5 / 5 (fresh).
- `test_l3_to_l4_converts_one_for_one_into_ops` — 3 fresh + 1 edit → **29 ops**
  (25 + 4).
- `test_l4_to_l3_converts_ops_into_fresh` — 6 ops left → **11 fresh** (5 + 6),
  edits fresh.
- `test_replayed_transaction_does_not_add_twice` — replay → `409`, still 8 / 6.
- **RED test** `test_carry_over_beats_the_old_hard_reset` — asserts the result
  is NOT 5 (the old hard reset) and IS 8 / 6.

**Red-test proof:** with the OLD grant restored (`fresh_used=0, edits_used=0`),
the red test FAILS with `AssertionError: 5 == 5 : old hard reset would give 5 —
carry-over must add`. With the carry-over it PASSES. (Reproduced by
`git stash` of `entitlements_api.py`, run, restore.)

Run: `python3 -m pytest tests/test_local733_pack_carryover.py -q` → `8 passed`.

### App — widget + unit tests (`flutter test`)

- `test/plan_left_summary_test.dart` — unit tests of the phrasing helper
  (cardLine / generateLine / purchaseMessage) for pack / Curator / Free /
  Introduction, singular/plural.
- `test/plan_pack_carryover_test.dart` — widget tests:
  - plan card line for $10 Pack, Curator, Free; Introduction shows no line;
  - the new rules sentence is present and the old "replaces what's left" is
    gone;
  - the Generate-screen grey line for pack and Free; hidden on Introduction.
  - (dates computed via `PassExpiryFormat.formatDate` so the assertions are
    timezone-independent).
- `test/plan_screen_level_aware_test.dart` — the existing LOCAL-610 rule
  assertion updated to the new sentence.

All pass (`flutter test test/plan_left_summary_test.dart
test/plan_pack_carryover_test.dart test/plan_screen_level_aware_test.dart` →
`All tests passed!`, 32 tests), and the sibling `plan_screen_*` tests still
pass.

### `flutter analyze` (touched files)

- `lib/utils/plan_left_summary.dart`, `test/plan_left_summary_test.dart`,
  `test/plan_pack_carryover_test.dart`: **No issues found.**
- `lib/screens/plan_screen.dart`: no new issues.
- `lib/screens/tour_generator_screen.dart`: **47 issues before = 47 after**
  (all pre-existing; measured by analyzing the base vs changed file). Zero new.

---

## Live test

Own container only — **never** `-p audioura`, **never** touched `audioura-*`
(all 13 `audioura-*` containers remained up throughout).

- Container: `docker run --rm --name local733-user-api --network
  development_default -p 5099:5000`, `IAP_VERIFY_MODE=stub`, `GATEWAY_API_KEY=""`,
  `DATABASE_URL=…@172.18.0.2:5432/audiotours_test`. Env set explicitly (HOSTNAME
  not copied). Container + image removed after the test.
- Store mode: `GET /purchases/mode` → `{mode: stub, stub: true}`.
- Stub purchases on TEST users only (`LIVE733-*`); no real device, no emulator
  needed for the server proof.

**Results** (TEST user `LIVE733-…`):

| step | action | result |
|------|--------|--------|
| buy #1 | `l3_pack_10` | granted l3, 5 fresh / 5 edits, anniversary 22 Nov 2026 |
| consume | `UPDATE device_entitlement … fresh_used=2, edits_used=4` (TEST user only) | 3 fresh / 1 edit left |
| buy #2 | `l3_pack_10` | **8 fresh / 6 edits — carry-over proven live** |
| replay #2 | same `transaction_id` | **HTTP 409**, still 8 / 6 (idempotent) |
| convert | `l4_round_25` | **39 ops** (8 + 6 carried + 25) |

**Plan-card screenshot** (TEST user `LIVE733SHOT-…`, driven to 8 / 6):
`audio_tour_app/screenshots/plan_card_local733.png`. The rendered card line is

> `$10 Pack · 8 new tours and 6 stop-adding edits left · until 22 Nov 2026`

— matching the task example exactly (verified against the live `/entitlements/me`
payload and the widget tests). Generate line: `8 new tours left in your pack`;
success message: `You now have 8 new tours and 6 edits until 22 Nov 2026.`
_Note:_ the PNG is captured in `flutter test`, whose placeholder (Ahem) font
renders glyphs as filled boxes; the card LAYOUT is correct and the exact text is
proven by the widget tests and the live payload above.

### Row counts (audiotours_test, every table written)

| table | before | after | delta | notes |
|-------|--------|-------|-------|-------|
| `purchases` | 1 | 6 | +5 | LIVETX1/2/3 + SHOT1/2, all `LIVE733*`. Replay 409 NOT recorded. |
| `device_entitlement` | 15 | 17 | +2 | the two `LIVE733*` TEST users only. |

All added rows belong to my `LIVE733*` TEST users; nothing else was written.
**No deletes** — purchase-bearing rows kept (D690); no `DELETE FROM audio_tours`.

### Budget

**$0.00** — stub purchases only, no AI generation, local container. Well under
the $0.30 cap.

---

## Files changed

- `user-tracking/entitlements_api.py` — `_pack_units_left`, `_carry_over_used`;
  purchase grant rewired (carry-over instead of hard reset).
- `audio_tour_app/lib/utils/plan_left_summary.dart` — new phrasing helper.
- `audio_tour_app/lib/screens/plan_screen.dart` — card line, rules sentence,
  success message.
- `audio_tour_app/lib/screens/tour_generator_screen.dart` — grey tours-left
  line + entitlement load (with a test seam).
- `tests/test_local733_pack_carryover.py` — server tests incl. red test.
- `audio_tour_app/test/plan_left_summary_test.dart` — unit tests.
- `audio_tour_app/test/plan_pack_carryover_test.dart` — widget tests.
- `audio_tour_app/test/plan_screen_level_aware_test.dart` — updated rule
  assertion.
- `audio_tour_app/screenshots/plan_card_local733.png` — plan-card screenshot.

Not edited: DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`. ClickUp status unchanged.
