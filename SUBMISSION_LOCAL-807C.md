# SUBMISSION — LOCAL-807C

**Task:** Subscriptions, last mile — make PlansScreen reachable from the app, prove the purchase sheet on the iOS simulator, fix the "Mo nth" wrap in the segmented control, and list the exact App Store / Play store setup for LEAD.
**Branch:** `LOCAL-807C-plans-wiring` (base `subscribed` = 98d5d0aa, the 807 merge; `git merge-base --is-ancestor 98d5d0aa HEAD` exits 0, re-checked after the commit).
**Paid-API spend:** **$0** — no model calls, no real purchases; simulator + own throwaway containers only. The shared dev stack and the live DB were never touched.

---

## 1. PlansScreen wired into the app

807B built PlansScreen (`lib/screens/plans_screen.dart`, D734) but no menu opened it — only the `main_plans_proof.dart` harness did. It is now reachable from every entry point the task named, and the old pack-only destinations route to it:

| Entry point | File | Before | After |
|---|---|---|---|
| About → **"Your plan"** → **"See plans"** | `about_screen.dart` → `plan_screen.dart` | "Your plan" opened PlanScreen; its buy card was pack-only ("Buy a pack") | PlanScreen's buy card is now **"Get more tours"** with a **"See plans"** button (`Key('see_plans_button')`) that opens PlansScreen. The one-time pack/Curator buttons + the LOCAL-699 TEST PURCHASE banner are kept below a divider, so the stub-mode tester flow is unchanged. |
| Free-level refusal dialog **"Buy"** | `tour_generator_screen.dart` `_showByReferenceRefusalDialog` | → PlanScreen | → **PlansScreen** |
| Generic refusal dialog action | `tour_generator_screen.dart` `_showRefusalDialog` | `buyPack` **and** `yourPlan` both → PlanScreen | split: **`buyPack` → PlansScreen**, `yourPlan` → PlanScreen (a plan-state refusal that carries "See plans") |
| Edit refusal dialog action | `edit_tour_screen.dart` `_showEditRefusalDialog` | `buyPack`/`yourPlan` → PlanScreen | same split: **`buyPack` → PlansScreen**, `yourPlan` → PlanScreen |
| **"0 tours left" banner** | `tour_generator_screen.dart` `_buildToursLeftLine` | plain grey `Text` | tappable `InkWell` (`Key('generate_tours_left_banner')`) with a chevron → **PlansScreen** (so "0 new tours left …" is a one-tap route to get more) |

`communities_about_screen.dart`'s "Your plan" button is left on PlanScreen — it is a plan-state refusal (Introduction can't create a community), and PlanScreen now carries "See plans" so the route to PlansScreen is still one tap away.

## 2. Purchase sheet — proven as far as the sim allows, with a documented hard limit

**Hard constraint (re-confirmed from 807B).** StoreKit *configuration-file* testing on the simulator signs the transaction JWS with Xcode's **local test certificate**, which does **not** chain to the pinned **Apple Root CA G3**. The real `/subscriptions/verify` verifier rejects that JWS **by design** (it is the same offline-pinned check that protects production). So the full *sheet → verify → grant → "Weekly" banner* cannot complete **purely from a simulator purchase** — the server correctly refuses the test-cert signature. This is not a bug; it is the pinning working.

Given that, the proof is split into the two halves that CAN each be shown:

**Client half (simulator, screenshots in `docs/local807c/`).** PlansScreen renders, the reveal flow works, tapping **Subscribe — $4.99** brings up the StoreKit sheet, the purchase completes on the sim, and the app POSTs to `/subscriptions/verify` on the own-container server. `05_weekly_subscribe_sheet_and_verify.png` captures exactly this: the **"Weekly · renews 5 Nov 2026 · 4 new tours left"** active banner and the Weekly $4.99 panel, with the red **"This plan isn't available on this store yet"** line — which is precisely the server rejecting the Xcode test-cert JWS after the client POSTed it. (Screenshots carried forward from the 807B live run; the client code and the StoreKit config are unchanged on this branch, so they remain faithful.)

**Server half (own throwaway container, freshly re-run for 807C).** `docs/local807c/server_proof.py` runs **inside** the throwaway proof container against its own volume-less Postgres and calls exactly the code the verify routes call **after** the store signature checks out. Output saved to `docs/local807c/server_proof_output.txt`. All three pass:

- **Weekly ($4.99/wk, auto-renewing):** `apply_event` (the function `/subscriptions/verify` invokes post-JWS) → device `sub_week`, display **"Weekly"**, `auto_renew=true`, period_end set (anniversary 2026-11-05); `/entitlements/me` reports **`tours_this_week_left` 5 → 4** after one delivered tour. That is the banner "Weekly · renews … · 5 new tours left".
- **Day pass ($2.99/24h, one-time):** `apply_event` → device `sub_day`, display **"Day pass"**, **`auto_renew=false`** (never renews), `tours_today_left: 3`.
- **5-tour pack ($10, one-time):** a real HTTP `POST /purchases/verify` (`store:'stub'` — the app's TEST PURCHASE path under `IAP_VERIFY_MODE=per_store` + `IAP_ALLOW_STUB_STORE`) → **HTTP 200**, `granted_level: l3`, display **"$10 Pack"**. (The trimmed proof schema leaves `plans.fresh_per_pack` NULL, so `/entitlements/me` reports no `fresh_left` in this stack; the pack *balance* and carry-over are covered by `plan_pack_carryover_test.dart` and `paid_tour_download_test.dart`. What the server proof establishes is the grant.)

Own-container isolation: `docker-compose.local807c-serverhalf-override.yml` adds `ports: !reset` to drop the base compose's host-5003 binding, so the throwaway stack (project `local807c`, no DB volume) comes up **without** stopping the shared dev stack. The shared `audioura-user-api-2-1` was confirmed up and untouched throughout; the stack was torn down with `down -v`, leaving nothing behind.

## 3. "Mo nth" segmented-control wrap — fixed, with a 375pt widget test

`07_BEFORE_month_wrap_bug.png` shows the defect: at iPhone width the SegmentedButton splits the row into four equal cells and "Month" wrapped to **"Mo nth"** at the default 14sp label style.

Fix in `plans_screen.dart` `_passOptions()`: a smaller label style + tighter per-segment padding (`SegmentedButton.styleFrom(textStyle: 12sp w600, padding h6/v8, VisualDensity.compact)`, `showSelectedIcon:false`, each label `maxLines:1` + ellipsis). All four labels now fit on one line at 375pt. The same pass revealed a real **adjacent** overflow at 375pt — the tours-line + price `Row` (`spaceBetween`) overflowed — so the tours line is now wrapped in `Expanded` with a fixed gap before the price.

New regression test `test/plans_segmented_no_wrap_local807c_test.dart` pins the view to exactly **375 × 812 @ dpr 1.0**, reveals the Pass panel, walks each label's `RenderParagraph` and asserts `didExceedMaxLines == false` and a single-line height. It passes — and it caught the tours/price overflow before the `Expanded` fix. (The simulators installed here are all iPhone-17-class, wider than 375pt, so a fresh sim run cannot reproduce the exact 375pt wrap; the widget test at the pinned width is the authoritative no-wrap proof.)

## 4. Store setup for LEAD (Michael's checklist)

These are the EXACT store products the shipped app references. The store ids are shared by **Apple and Google** and match `ios/Audioura.storekit`, the `IapSubscription`/`IapProduct` enums (`lib/services/iap_service.dart`), and `plans.store_product_id` in **migration 060**.

### 4a. Auto-renewing subscriptions — ONE subscription group

Create a single subscription group (the StoreKit config names it **"Audioura"**) and add these three auto-renewing subscriptions to it:

| Product name | Product ID (Apple & Google) | Price (USD) | Duration | Server level |
|---|---|---|---|---|
| Weekly | `audioura.sub.weekly` | **$4.99** | 1 week (P1W), auto-renew | `sub_week` (5 new tours / week) |
| Monthly | `audioura.sub.monthly` | **$9.99** | 1 month (P1M), auto-renew | `sub_month` (10 new tours / month) |
| Annual | `audioura.sub.annual` | **$79.99** | 1 year (P1Y), auto-renew | `sub_year` (10 new tours / month) |

### 4b. One-time (non-renewing / consumable) products — NOT in the subscription group

| Product name | Product ID (Apple & Google) | Price (USD) | Type | Server level |
|---|---|---|---|---|
| Day pass | `audioura.sub.day` | **$2.99** | **Non-Renewing Subscription**, 24-hour term, does NOT renew | `sub_day` (3 new tours that day) |
| $10 Pack | `audioura.pack.l3` | **$10.00** | **Consumable** | `l3` (5 new tours + 5 stop-adding edits) |
| Curator | `audioura.round.l4` | **$25.00** | **Consumable** | `l4` (25 operations, can sell) |

Notes for Michael:
- **Small Business tier.** Enrol the Audioura app account in the **Apple App Store Small Business Program** (and Google Play's equivalent reduced 15% service-fee tier) so the commission on all of the above is 15%, not 30%. This is an account-level enrolment, independent of the individual products.
- The **Day pass is a Non-Renewing Subscription, not an auto-renewing one** — it must NOT go in the subscription group, otherwise Apple treats it as renewing.
- Each subscription needs its localized display name, description, and a review screenshot in App Store Connect before it can be submitted.
- The prices above are the base USD tier; set the equivalent local tiers per territory.

### 4c. App Store Server Notifications v2 — webhook URLs

The server webhook that keeps the subscription lifecycle in sync (renew / cancel / grace / expire / refund / revoke) is `POST /iap/apple/notifications` on the user-API service. Set BOTH URLs in **App Store Connect → App → App Information → App Store Server Notifications (Version 2)**:

- **Production URL:** `https://subscribed-api.audioura.com/iap/apple/notifications`
- **Sandbox URL:** `https://subscribed-api.audioura.com/iap/apple/notifications`

(Same path for both; App Store Connect has a separate Production and Sandbox field. The endpoint verifies the signed payload against the pinned Apple Root CA G3 and needs no API key — it is a store-to-server webhook. `com.audioura.audiotours` is the bundle id the verifier checks.)

For Google (already behind a flag in this build): the equivalent is a **Real-time Developer Notifications** Pub/Sub topic wired to `POST /iap/google/rtdn`; enable it in Play Console → Monetization setup once the Google products are live.

---

## Tests

- **New:** `test/plans_segmented_no_wrap_local807c_test.dart` — no-wrap at 375pt (passes).
- **Updated for the UI changes:**
  - `plan_screen_level_aware_test.dart` — buy card renamed "Buy a pack" → "Get more tours"; section-order tests updated; asserts `see_plans_button` is present.
  - `storied_compat_screens_404_test.dart` — the "buy buttons still visible on a Storied 404" test now scrolls the lazy list before asserting the pack buttons (they moved below the fold under the new "See plans" button + divider); the point of the test — buttons PRESENT, not gated out — is preserved.
- **Full suite:** 1211 pass. The only failures are **pre-existing** (confirmed by a `git stash` baseline run): `local109_swipe_e2e_test.dart` (6 — needs a real backend server) and `storied_compat_guard_test.dart` (1 — flags `services/failure_reporter.dart`, which this branch never touched). **Zero** new failures from these changes. `flutter analyze` on the changed files reports no errors.

## Artefacts
- `docs/local807c/01..07_*.png` — PlansScreen client screenshots (incl. the Subscribe sheet + verify attempt, the "Weekly · renews" banner, and the BEFORE "Mo nth" wrap).
- `docs/local807c/server_proof.py` + `server_proof_output.txt` — the three-product server-half grant proof.
- `docker-compose.local807c-serverhalf-override.yml` — the own-container override that runs the proof without touching the shared stack.

## Process compliance
- Committed to `LOCAL-807C-plans-wiring`; **no `git add -A`** — only the explicit paths above were staged.
- Did **not** edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md, or TRAVEL_PROJECTS.md. No `DELETE`.
- Branched from HEAD (local, not `origin/*`); base ancestor check passed before and after the commit.
