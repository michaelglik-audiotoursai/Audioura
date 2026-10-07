# SUBMISSION — LOCAL-604: Plan page changes (names, queue/code entry, Curator, hidden levels, level codes, invitations)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-604-plan-page-michael`
**Base:** `subscribed` @ `21b9eba` (verified: `git merge-base --is-ancestor 21b9eba HEAD` → exit 0)
**App version:** `2.4.4+30`
**Design of record:** SUBSCRIPTION_LEVELS.md (D613) + LEAD ruling D619.

---

## What Michael asked for (2026-10-06) and where it lives

1. **Install level is "Introduction".** → `plans.display_name` (migration 016); the app renders the name.
2. **Free plan: queue OR code, with explanation.** → Free card on the plan page: "Join the queue" (asks for an email) + a single "I have a code" box; the explanation says the code arrives by email, is valid 10 minutes once the queue reaches you, or comes as an invitation from a friend on a paid plan.
3. **$25 Round is "Curator"; its headline feature is selling.** → `plans.display_name = 'Curator'`; Curator's first bullet is "Create tours for sale."
4. **Tester and Administrator never shown.** → `plans.hidden = true` for `tester`/`admin`; `/entitlements/me` returns a visible-only `levels` list; the app renders only that list.
5. **Michael switches his device between any level by entering a code.** → level codes (table `level_codes`, sha256 hashes only) claimed through the same single code box; a match sets the level, including tester and admin.
6. **$10 Pack and Curator show they can send free-subscription invitations.** → "Send free-subscription invitations (3 lifetime / 5 per month)" bullet on Pack and Curator.

---

## Deliverables

### 1. Migration 016 (additive, idempotent) — `migration/sql/016_plan_display_level_codes.sql`
- `plans.display_name` + `plans.hidden`; sets l1 "Introduction", l2 "Free", l3 "$10 Pack", l4 "Curator" (visible); tester "Tester", admin "Administrator" (hidden).
- `level_codes(code_hash CHAR(64) PK, level FK→plans, created_at, revoked_at, uses)` — **hashes only, no plaintext column**.
- `l2_queue.email` (nullable).
- `l2_settings.offer_ttl_minutes` default **10** (the old `offer_expiry_hours` column is retained; the seat core now reads the minutes column).
- Verified: applies cleanly on `audiotours_test`, re-runs with no change (idempotent).

### 2. Server (`user-tracking/`)
- **`entitlements_api.py`**
  - `/entitlements/me` now returns `display_name` (current level) and `levels` (visible-only, in plan order, each with `display_name`, `price_usd`, `can_sell`, `referrals_allowed`, `referral_period`, `max_stops`).
  - `/l2/queue/join` accepts an optional `email`.
  - `/l2/claim` is a **single box that routes three code kinds**, in order: (1) level code → `claim_level_code`; a revoked level code is refused `403 level_code_revoked`; (2) queue-offer code → `l2_seats.claim_seat`; (3) friend invitation (referral) code → inline cursor-based redemption mirroring `referral_engine`'s checks. The response carries `claim_kind` and (for level codes) `granted_level`.
- **`level_codes.py`** (new, framework-free module **+ CLI**): `generate_code()` → `AUD-XXXX-XXXX` Crockford base32 via `secrets`; `hash_code()` → sha256 of the normalised code; `claim_level_code()` sets any level and starts a **test pack** for l3/l4 (`pack_started_at=now`, `anniversary=+1 month`, a `purchases` row `store='level_code'`); `revoke_code_hash()`. CLI: `python3 level_codes.py create <level>` prints the plaintext **once to stdout** and the hash to stderr — the plaintext is never committed, logged or written to a file by the task; `python3 level_codes.py revoke <hash>`.
- **`email_sender.py`** (new, framework-free): `send_offer_email()` behind `EMAIL_MODE` — `log` (default; writes the code to the log) and `smtp` (`SMTP_HOST/PORT/USER/PASS/FROM`; **not configured by this task**, fails soft if half-configured). Never raises; redacts the address in logs.
- **`l2_seats.py`**: `get_settings` reads `offer_ttl_minutes`; `join_queue(cur, user_id, email=None)` stores the email; `leave_queue`, `claim_seat` and `expire_offers` **null the email**; `offer_free_seats` uses the 10-minute TTL and emails the stored address best-effort. The app still shows the pending offer in-app, so nothing depends on email being wired up.
- **Mirror kept in sync**: `l2_seats.py`, `level_codes.py` and `email_sender.py` are byte-identical in the repo root and `user-tracking/` (the user-api build context cannot import repo-root modules). `tests/test_local596_mirror_in_sync.py` → **PASS**.

### 3. App (`audio_tour_app`, 2.4.4+30)
- `entitlements_service.dart`: new `PlanLevel` model; `Entitlements` gains `displayName`, `levels`, `queuePosition`, `pendingOfferCode` (all parsed defensively); `EntitlementsService.joinQueue(email)` and `claim(code)` (returns `ClaimResult`).
- `plan_screen.dart`: current-plan header uses the server display name; the plans table renders only the **visible server levels** by display name (Curator's first bullet is "Create tours for sale."; Pack/Curator show the invitations line); the **Free card** has "Join the queue" (email dialog, validated) with a pending-offer banner / queue position, and a **single** "I have a code" box with the explanation text; after a successful code the app refreshes `/entitlements/me` and shows the new level.
- `flutter analyze` on the changed files → **No issues found** (the project's 1388 pre-existing analyzer errors are all in untouched legacy files — `audio_handler.dart`, `tour_service.dart`, `map_page.dart`). `flutter build ios --no-codesign` → **Built build/ios/iphoneos/Runner.app (37.3MB)**.

### 4. Tests
- `tests/test_local604_plan.py` — **21 passed**: hidden levels absent from `/me`; display names correct; email stored on join and **nulled on claim/leave/expiry**; **10-minute** offer TTL; **three-kind** claim routing (level code / offer / referral); a level code switches to **every** level incl. tester/admin; l3/l4 start a test pack; a **revoked** code → 403; **hashes only** (asserts no plaintext column; hash is sha256, len 64).
- `audio_tour_app/test/plan_screen_free_card_test.dart` — **6 passed**: display-name + visible-levels parsing (hidden absent, older payload empty, malformed skipped, pending-offer/queue parse); the Free card shows "Join the queue", a single code box, and the explanation; empty code prompts rather than crashing.
- **Regression re-run of `test_local59[5-8]*` (all PASS):**

  | file | result |
  |---|---|
  | tests/test_local595_anniversary.py | 18 passed |
  | tests/test_local595_api.py | 10 passed |
  | tests/test_local595_edit_gate.py | 8 passed |
  | tests/test_local595_enforcement.py | 31 passed |
  | tests/test_local596_api.py | 11 passed |
  | tests/test_local596_mirror_in_sync.py | PASS (run as script, exit 0; pytest reports "no tests ran" / exit 5 because the file has no test functions — it is a plain-assert script) |
  | tests/test_local596_referral.py | 9 passed |
  | tests/test_local596_seats.py | 12 passed |
  | tests/test_local597_by_reference.py | 9 passed |
  | tests/test_local597_guard.py | 13 passed |
  | user-tracking/test_local598_apple_jws.py | 17 passed |
  | user-tracking/test_local598b_entitlements_auth.py | 5 passed |

### 5. Live verification (own stub container only — no `audioura-*` touched, no GCloud)
- Built `local604-userapi:latest` from `user-tracking/`; ran `docker run --rm --name local604-userapi --network development_default -e DATABASE_URL=postgresql://admin:password123@development-postgres-2-1:5432/audiotours_test -e GATEWAY_API_KEY= -e ALLOW_UNAUTHENTICATED_ENTITLEMENTS=true -e EMAIL_MODE=log -e IAP_VERIFY_MODE=stub -p 5604:5000`. All 13 `audioura-*` containers confirmed still running, untouched, after the run.
- CLI created one level code per level (plaintext to stdout, sha256 to stderr).
- Device `LOCAL604-DEVICE-01` claimed each level live via `POST /l2/claim`; `/entitlements/me` after each switch showed: **l1 Introduction, l2 Free, l3 $10 Pack (anniversary set), l4 Curator (anniversary set), tester Tester, admin Administrator**; `claim_kind=level_code`, `granted_level` correct; the `levels` list was always `['l1','l2','l3','l4']` only (hidden levels never shown).
- Revoked the l4 code via the CLI → claim returned **HTTP 403 `level_code_revoked`**.
- **Cleanup by exact id/hash, with counts:** purchases=2, l2_offers=0, l2_queue=0, device_entitlement=1, level_codes=6 deleted; afterwards 0 `LOCAL604-` device rows and 0 of my level codes remained.
- **Michael's device row unchanged:** `('USER-1073427300','admin',None,None)` before == after → **True**.

---

## Process
- Committed after each step (migration → server → app → tests → this doc).
- No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, SUBSCRIPTION_LEVELS.md or .continuous_dev/STATUS.md.
- **LEAD creates Michael's real codes after merge** (`python3 level_codes.py create <level>`); the task commits none.
