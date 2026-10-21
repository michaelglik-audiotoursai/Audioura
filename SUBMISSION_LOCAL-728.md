# SUBMISSION — LOCAL-728

**No user-to-user blocking: members and organisers report to Audioura; only the administrator bars or bans. Notice wording.**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-728-admin-only-moderation`
- **Base (code_sha):** `09564687` (subscribed = LOCAL-726). `git merge-base --is-ancestor 09564687 HEAD` → exit 0 (verified on the correct base, not `origin/*`).
- **Decisions:** D691 (no member↔organiser blocking; only the admin bars/bans; tours are by AI **and curators**), D690 (a bar ends the membership **by expiry**, never DELETE — the row is the purchase record), D658 (a banned user keeps downloaded audio; a ban blocks NEW access only).
- **Spend:** $0.00 — no paid API. All verification used an isolated local Postgres and the Android emulator. (≤ $0.50 budget.)

---

## What was REMOVED (user-level blocking from LOCAL-726)

**App**
- `audio_tour_app/lib/screens/blocked_users_screen.dart` — **deleted** (the Settings "Blocked"/unblock screen).
- `about_screen.dart` — removed the **"Blocked"** OutlinedButton and the `blocked_users_screen` import.
- `community_page_screen.dart` — removed **"Block organiser"** and **"Manage members → Remove & bar"**: deleted `_blockOrganiser()`, `_manageMembers()` and the whole `_ManageMembersSheet` class; replaced the ⋯ PopupMenu (report / block / manage) with a **single "Report to Audioura"** AppBar action.
- `my_communities_screen.dart` — removed `_blockOrganiser()` and the **"Block organiser"** row menu item (kept Origin / Open), and the now-unused `_userId` field.
- `communities_service.dart` — removed `blockUser`, `barMember`, `_block`, `unblockUser`, `members`, `myBlocks`.
- `communities_models.dart` — removed the now-unused `CommunityMember` and `CommunityBlock` classes (`Community.ownerUserId` kept; harmless).

**Server (`user-tracking/communities_api.py`)**
- Removed the user-facing endpoints `POST /communities/<id>/block`, `POST /communities/<id>/unblock`, `GET /communities/blocks`, `GET /communities/<id>/members` (they 404 now).
- `blocked_owner_ids_for()` is neutralised (returns an empty set): the member's `mine` / `map` / `new-tours` views no longer hide anyone (D691 removed user blocking). Any legacy `member_block`/`organiser_bar` rows (should be 0) are left as history and no longer filter anything.

## What was ADDED / CHANGED

**App — one report for everything, to Audioura**
- `community_page_screen.dart`: the ⋯ bar now has ONE action, **Report to Audioura** (flag icon). It opens `_ReportToAudiouraSheet` — a reason radio (`spam` / `offensive` / `inaccurate` / `inappropriate` / `other`) + an optional free-text field — and POSTs `{user_id, reason, detail}`. Confirmation: **"Thanks — Audioura will review this."** Keys for tests: `report_reason_*`, `report_detail`, `report_submit`.
- Tours keep their own Report (`map_delivery /report-tour`) — untouched.
- `communities_service.report(id, {userId, reason, detail})` sends reason + optional detail.

**App — first-run notice wording**
- `informational_notice_screen.dart`: first point is now **"Audioura tours are created with AI and by guides and curators. They can contain mistakes — enjoy them as stories, not as official guidance."** The other points are kept.
- **Ack key bumped `info_notice_ack_v1` → `info_notice_ack_v2`.** Chosen because the wording change is **material** (AI alone → AI **and curators**), so already-acknowledged v1 installs see the corrected notice once after this update.

**Server — report to Audioura**
- `report_community` writes ONE `community_reports` row with `reason` (code) + `detail` (optional text) + `status 'open'`, and returns `{reported:true, report_id}` — **no owner leak** (it used to return `owner_user_id`). Falls back to a reason-only insert on an un-migrated DB.

**Server — admin-only moderation (separate admin key)**
- `_require_admin_key()` checks a **distinct** secret `ADMIN_API_KEY` via the `X-API-Key` header (constant-time), **fail-closed** (503 `admin_not_configured` when unset). The app sends only the gateway key, so no app user can reach the admin surface.
- New admin endpoints (all require the admin key):
  - `GET  /communities/admin/reports?status=open|reviewed|dismissed|all` — open community + tour reports.
  - `POST /communities/<id>/admin/bar` — bar a user from one community (ends membership by expiry, records `admin_bar`, ledger).
  - `POST /communities/<id>/admin/unbar` — lift the bar (deletes the bar row only; ledger).
  - `POST /communities/admin/ban` — ban a user from the service (ledger).
  - `POST /communities/admin/unban` — lift the ban (sets `lifted_at`, keeps the row; ledger).
  - `POST /communities/<id>/admin/disable` (`{enable:true}` to re-enable) — the per-community off switch (ledger).
  - `GET  /communities/admin/actions` — read the ledger.
- Ban gate: `is_user_service_banned()` is checked in `verify_community_pass` and `create_community` → **403 `banned`** (no purchase, no generation/creation). Downloaded audio is never touched (no membership/purchase row is ever deleted).
- Bar gate: `is_user_barred()` now honours `organiser_bar` (legacy) **and** `admin_bar`.

**Admin CLI — `moderation.py`** (next to `review_queue.py`)
- `reports` / `bar` / `unbar` / `ban` / `unban` / `disable` / `enable` / `log`. `--actor` labels the ledger (default `moderation.py`). Never DELETEs a membership/purchase row; an `unbar` deletes only a `community_blocks` bar row. Default `DATABASE_URL` port 5433 (mirrors `review_queue.py`).

**Legal (drafts; not published — LEAD re-posts for Michael)**
- `TERMS.md` §5: block sentence replaced with the report-to-Audioura wording ("You can report any tour, community or organiser to us…").
- `TERMS.md` §10 first line: "Tours are created with the help of AI **and by guides and curators**…".
- `ORGANISER_TERMS.md` §8: reports go to **Audioura** (which may forward to the organiser); **organisers cannot bar members themselves**.
- `PRIVACY.md` Communities paragraph: reports go to **Audioura (not to the owner)**.
- Rebuilt `legal/html/*.html` with `legal/build_html.py` (terms, privacy, organiser-terms re-rendered; wording verified in the HTML).

## Migrations (additive, idempotent, declared)

- **`migration/sql/045_community_reports_triage.sql`** — `community_reports` gains `detail TEXT` and `status VARCHAR(16) DEFAULT 'open'` (+ CHECK `open|reviewed|dismissed`, + index). No DROP/DELETE/retype.
- **`migration/sql/046_admin_moderation.sql`** —
  - widens `community_blocks.kind` CHECK to the **superset** `('member_block','organiser_bar','admin_bar')` (drops the old `community_blocks_kind_check`, adds `chk_community_blocks_kind`); the allowed set only grows, so no existing row is invalidated;
  - `service_bans` table (active-ban partial unique index on `user_id WHERE lifted_at IS NULL`);
  - `admin_actions` append-only ledger (`action, actor, target_user_id, target_community_id, reason, report_id, created_at`).

**Idempotency / row counts (isolated DB, verified):** re-applying 045 and 046 produced only "already exists, skipping" NOTICEs and **no errors**. Row counts of `community_reports`, `community_blocks`, `service_bans`, `admin_actions` were **unchanged (0 → 0)** across the re-apply — the migrations add columns/tables, never rows.

## Tests

Isolated Postgres only (`docker run --rm --name local728-pg … -p 55728:5432 postgres:15`, db `audiotours_test`, `HOSTNAME` dropped from env). **No `audioura-*` container was touched.** Run with `DB_HOST=localhost DB_PORT=55728 DB_NAME=audiotours_test DB_USER=admin DB_PASSWORD=password123`.

- **`tests/test_local728_admin_moderation.py` — 11 passed**, covering:
  - a report writes ONE `community_reports` row with reason + detail + status `open`; the response does **not** leak the owner;
  - every admin endpoint is **refused without the admin key (401)**, refused with only the **gateway key (401)**, and **closed (503)** when `ADMIN_API_KEY` is unset;
  - the old user block endpoints are **gone (404)**;
  - via the **`moderation.py` CLI** against the isolated DB: `bar` ends the membership **by expiry** (row kept, `transaction_id` present — D690) and records `admin_bar`; the barred member **cannot rejoin by code (403 barred)**; `unbar` lets them return;
  - `ban` writes an active `service_bans` row; a **banned user's purchase AND community creation are refused (403 banned)**; the membership row is **never deleted** (D658); `unban` restores purchasing;
  - **every action writes an `admin_actions` ledger row** (asserted actor/reason/target);
  - `disable`/`enable` toggle `communities.disabled`.
  - **RED test:** with `is_user_service_banned` forced to `False`, the banned user's purchase succeeds → the "refused with 403" assertion fails (`pytest.raises(AssertionError)`), proving the green guarantee is not vacuous.
- **Regression:** `tests/test_local690_communities.py` (report test updated to the D691 Audioura behaviour) + `test_local726_crime_wording.py` → **45 passed** together with the 728 suite. `test_local700/702/703/704/710b/713` → **55 passed** (local702's 23 pass after adding migration 030 to the isolated DB — a bootstrap gap, not a code change).
- **Deleted obsolete tests:** `tests/test_local726_community_blocks.py` (exercised the removed block endpoints) and `audio_tour_app/test/local726_store_musts_test.dart` (referenced removed models + old ack key/wording).
- **Flutter:** `audio_tour_app/test/local728_admin_moderation_test.dart` — **7 passed** (owner id still parses; report is the only moderation surface; notice ack key is **v2**; a v1-acked install is shown the v2 notice once; the notice renders the AI-**and-curators** wording and the old "fact-checked" wording is gone). `flutter analyze` on the changed files is clean apart from a pre-existing `RadioListTile` deprecation info (same pattern already in `about_screen.dart`).

## Emulator screenshots (Android emulator-5554 only — never Michael's phones)

`submission_screens/local728/`:
- `01_community_page_single_report.png` — the community ⋯ bar with the **single Report to Audioura** action (no Block/Manage members).
- `02_report_to_audioura_form.png` — the Report form (reason radios + optional detail + "Send report").
- `03_first_run_notice_v2.png` — the first-run notice with the **AI and by guides and curators** wording.

(Captured by running a throwaway harness entrypoint that imports the real `InformationalNoticeScreen` and reproduces the community-page AppBar + report sheet, pinned to `-d emulator-5554`; the harness file and the installed app were removed afterward. A local `debug.keystore` was generated for the emulator debug build — gitignored, not committed.)

## Safety / process
- Branched from `subscribed` HEAD (`09564687`), ancestor check passes.
- Additive migrations only; no DELETE of purchase-bearing rows; no `DELETE FROM audio_tours`.
- Isolated container `local728-pg` + emulator only; no `audioura-*` resource touched.
- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD. ClickUp status unchanged.
