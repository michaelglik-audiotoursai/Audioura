# SUBMISSION — LOCAL-693 / D660

**Every download of a paid tour is paid; a failed download never consumes it; warnings; Terms corrected.**

- **Branch:** `LOCAL-693-paid-per-download` (off `subscribed` = `10db345b`)
- **Decision:** D660 (Michael, 2026-10-14) — "For paid tours every download no matter what language needs to be paid. The tour downloaded into the Listen page can be listened to as many times as the listener wants for free: he bought it; it's his." This OVERRULES the earlier buy-once / free-re-download model (LOCAL-677B).
- **Base check:** `git merge-base --is-ancestor 10db345b HEAD` → exit 0 (correct base).

---

## What changed

### 1. Schema — migration 031 (additive)
`migration/sql/031_tour_unlock_consumption.sql`:
- `tour_unlocks.consumed_at TIMESTAMPTZ NULL` — when a successful download spent the purchase. NULL = unconsumed (an active entitlement to one download).
- `tour_unlocks.consumed_by_download_id VARCHAR(255) NULL` — the download id that spent it (audit).
- Replaces the full `UNIQUE(user_id, tour_id)` with a **partial unique index** `uq_tour_unlocks_active ON (user_id, tour_id) WHERE consumed_at IS NULL`, plus `idx_tour_unlocks_unconsumed`.
  - **Why:** D660 requires a buyer to purchase the same language row **again** after a download consumed the previous unlock. The old full UNIQUE made the second purchase a silent no-op (`ON CONFLICT DO NOTHING`). The partial index keeps the same guarantee where it still matters (at most one *active* unlock per user+row — a replayed purchase of an unspent unlock is still a no-op) while allowing a fresh unlock once the previous one is consumed.
- Fully idempotent (`ADD COLUMN / CREATE INDEX IF NOT EXISTS`, guarded constraint drop). Applied twice = identical. No `DROP`/`DELETE` of data, no column retype.

Existing already-bought rows default to `consumed_at = NULL` (unconsumed): a generous, non-breaking default — a listener who bought before D660 and has not downloaded still gets their one download.

### 2. Server — map-delivery (`map_delivery/app.py`)
- `_user_has_unlock` now requires an **UNCONSUMED** unlock (`consumed_at IS NULL`). A consumed unlock no longer authorises a download → `/download-tour` returns **402** (buy again). Pre-031 DBs fall back to presence (never wrongly refuse a paid tour on an old DB).
- The download itself does **NOT** consume. **Decision: app-confirm, not server-mark** — the server streams the zip through a generator and cannot see whether the client received the whole file (a mid-stream disconnect looks like a normal generator finish server-side). So a failed/cut-off download must not reach the consume step. `/download-tour` instead mints a `download_id`, returns it in the `X-Download-Id` header (empty for free / curator / grandfathered / already-owned-free), and the app confirms.
- **New endpoint `POST /tour/<id>/download-complete`** — called by the app AFTER it has written a complete, valid zip. It stamps the oldest unconsumed unlock `consumed_at = NOW()`. Idempotent / defensive (a double-confirm or a free download is a harmless no-op; never 500s the app).
- Grandfathered (LOCAL-677C) and curator-own downloads are unchanged and never consume.
- Self-healing DDL (`_ensure_unlock_consumption_columns`) so the gate works whether or not migration 031 has run.

### 3. Server — unlock-state + purchase writes
- `tour_pricing_service.preview_state` (`GET /tour/<id>/unlock-state`): `unlocked` now means **has an unconsumed purchase**; added `downloads_bought` and `downloads_used`.
- `is_unlocked_cur` is unconsumed-only (pre-031 fallback); added `download_counts_cur`.
- All `tour_unlocks` `INSERT ... ON CONFLICT (user_id, tour_id)` updated to `ON CONFLICT (user_id, tour_id) WHERE consumed_at IS NULL` (targets the partial index; a bare conflict target now errors). Sites: `tour_pricing_service.record_unlock` + 4 in `entitlements_api._verify_tour_purchase`, which also self-heals the consumption schema before inserting.
- **Store idempotency is unchanged and still primary:** `purchases.transaction_id` is UNIQUE, so a replayed transaction is caught (409 `already_verified`) before any unlock insert — the LOCAL-677 replay test stays green.

### 4. App (Flutter, `audio_tour_app/`)
- **Buy dialog** (`home_screen.dart`): adds the D660 warning under the single-language note for an unbought paid tour — *"Downloads to this phone. Deleting it or changing phones means buying again."*
- **Confirm download** (`home_screen.dart`, `tour_translation_helper.dart`): after a tour (or paid translation) is downloaded AND saved/extracted, the app calls `POST /tour/<id>/download-complete` with the `X-Download-Id`. A failed/cut-off download never reaches this call → the unlock stays unconsumed and the listener retries for free. Fully defensive (a failed confirm never breaks the already-successful download).
- **Delete confirmation** (`my_tours_screen.dart` + new pure helper `widgets/delete_tour_prompt.dart`): a PAID tour deletes behind *"Delete and lose it?"* with the **same** D660 sentence; a free tour keeps the plain confirmation.
- **Buy & Download shows again after a consumed purchase** automatically: `unlock-state` now returns `unlocked:false` once consumed, so the existing dialog logic re-shows the Buy row.
- **Playback unchanged:** downloaded tours play unlimited and offline (D654).
- Build bumped `2.4.15+50` → `2.4.16+51`.

### 5. Terms (`legal/`)
- `TERMS.md` §2 rewritten to D660 (one download per purchase; on-phone forever; delete / new phone / reinstall = buy again; a failed download does not use up the purchase; pay before download).
- `REFUNDS.md` tour-refund section clarified per-download.
- `GUIDE_TERMS.md` + `PRIVACY.md` corrected away from "free re-download".
- Version bumped `draft1` → `draft2 (LOCAL-693 / D660)`. `legal/html/*.html` regenerated via `build_html.py`. Verified: D660 wording present in `terms.html`, zero residual "free re-download" wording anywhere in `legal/`.

### 6. Ratings — verified buyer stays verified
`tour_reviews_service.compute_verified` is unchanged on purpose: it marks a listener Verified if **any** `tour_unlocks` row exists across the language family, with no `consumed_at` filter. D660 only sets `consumed_at` and never deletes a row, so a buyer whose purchase was consumed by a download **stays Verified**. Added an explicit D660 comment; proven by a test.

---

## Tests

| Suite | Result |
|---|---|
| `tests/test_local693_paid_per_download.py` (new, 7 tests) | **7 passed** |
| `tests/test_local677_paid_tours.py` (existing) | **24 passed** |
| `tests/test_local686_price_ladder.py` (existing) | **7 passed** |
| **Python total (677 + 686 + 693)** | **38 passed, 0 failed** |
| `audio_tour_app/test/delete_tour_prompt_test.dart` (new, 6 tests) | **6 passed** |
| `flutter analyze` on changed/new files | **0 errors** (pre-existing info/warn lints only) |

New 693 coverage: buy → download OK → confirm → 2nd download 402 → rebuy → OK; failed/cut-off download does not consume (never confirmed, then retried free); two languages = two independent purchases; grandfathered + curator never consume (and carry no `X-Download-Id`); unlock-state `unlocked`/`locked` + `downloads_bought`/`downloads_used`; verified buyer stays verified after consume.

**Harness note:** the existing 677 suite could not load `map_delivery/app.py` on this host because the file's `import personal_match` (added by LOCAL-689) was unresolved — a pre-existing harness gap (base code: 9 fail + 9 err). Fixed `_load_md()` to add `map_delivery/` to `sys.path` so the real module loads; 677 is now fully green.

---

## Live test (PROCESS)

- **Constraint honoured:** no `-p audioura`, no `audioura-*` container touched. Ran the **real** service modules (`map_delivery/app.py` download + download-complete endpoints, `user-tracking/entitlements_api.py` purchase verify) as in-process Flask clients against the **dev DB** (`localhost:5433/audiotours`), using only `is_test = TRUE` rows, cleaned up afterward.

- **Migration 031 on the dev DB `audiotours` — row counts before/after:**

  | | tour_unlocks rows | consumed_at column | constraint | partial index |
  |---|---|---|---|---|
  | **before** | **2** | absent | `uq_tour_unlocks_user_tour` | — |
  | **after** | **2** | present (both NULL / unconsumed) | dropped | `uq_tour_unlocks_active`, `idx_tour_unlocks_unconsumed` |

  Purely additive: **2 → 2 rows, no data changed**; the 2 pre-existing unlocks remain as unconsumed (one download each still available).

- **Live end-to-end D660 flow (real endpoints, dev DB, `is_test` row):**
  1. download before buy → **402**
  2. buy → **200**
  3. download after buy → **200**, `X-Download-Id` set, counts (bought/used) = (1, 0)
  4. `POST /download-complete` → `consumed: true, remaining_unconsumed: 0`, counts (1, 1)
  5. second download → **402** (purchase spent)
  6. rebuy → **200**
  7. download after rebuy → **200**, counts (2, 1)

  All assertions matched; `is_test` rows cleaned up.

---

## Commits (per step, on `LOCAL-693-paid-per-download`)
1. migration 031 — `consumed_at` + partial active-unlock unique index
2. map-delivery gate requires UNCONSUMED unlock; `POST /tour/<id>/download-complete`
3. unlock-state `unlocked`=unconsumed + counts; `ON CONFLICT` → partial index; self-heal; 677 harness path fix
4. app — Buy warning line; paid-tour delete confirmation; confirm download-complete; build bump
5. Terms — D660 wording; regenerate `legal/html`
6. ratings — document verified stays verified (no logic change)
7. tests — D660 lifecycle + Dart `DeleteTourPrompt`

## Not done / out of scope
- Full Docker-container live run was deliberately **not** performed: `map_delivery/app.py` hard-codes `host="postgres-2"` (the shared container network), and the ticket forbids touching the `audioura-*` project/containers. The in-process run exercises the identical service code and the real dev Postgres, which is the faithful, safe equivalent.
- Real Apple/Google store verification stays in stub mode locally (unchanged, D652).

---

# 693B — D660 addendum: calm wording; server-side consumption; test isolation

**Decision:** D660 addendum (Michael, 2026-10-14): *a bought tour is like a bought bag — no warning at purchase.* Plus a LEAD review of 693: *consumption must be decided by the SERVER, not the app.*

## What changed and why

### 1. No warning at purchase time
Removed the Buy-dialog line *"Downloads to this phone. Deleting it or changing phones means buying again."* from `home_screen.dart`. There is no longer any purchase-time warning (grepped the app for the sentence and the only live use was this one; the rest was in `DeleteTourPrompt`, handled below).

### 2. Delete confirmation moved to a calm voice (paid only)
`DeleteTourPrompt` now returns the exact D660-addendum copy for a **paid** tour:
- title **"Delete paid tour?"**
- body **"Are you sure you want to delete this paid tour? Downloading it again will require another purchase."**
- buttons **"Cancel"** (default, listed first) and **"Delete"**.

The withdrawn LEAD wording ("Delete and lose it?", "changing phones") is gone. **Free** tours are unchanged: plain "Delete Tour", no warning. `my_tours_screen.dart` renders the dialog from the model's `cancelLabel`/`confirmLabel`.

### 3. Legal drafts — calm, plus the recovery code
Grepped the whole `legal/` folder for `re-?download` / alarm wording and fixed every hit:
- **TERMS §2** rewritten to state the one-download rule plainly, once, without alarm, and adds: *"If you lose or replace your phone, you can restore your Listen page … with your recovery code, without paying again."* (recovery code = LOCAL-695.)
- **REFUNDS** — adds the same recovery-code sentence to "What a purchase gives you".
- **GUIDE_TERMS §1** — softened ("Downloading the tour again later is a new purchase." replaces "buys again if they delete it or move to a new phone").
- **PRIVACY** — already factual; version bumped with the set.

All four bumped to `2026-10-14-draft3 (LOCAL-693B / D660 addendum)`; `legal/html` regenerated via `legal/build_html.py` (recovery-code wording verified present in `terms.html` and `refunds.html`).

### 4. Server-side consumption (LEAD review) — the core fix
**Problem (693):** a purchase was consumed only when the app called `POST /tour/<id>/download-complete`. A modified app, or a direct API call (the gateway key ships inside the app), could simply never call it and download forever.

**Fix (693B):**
- **map-delivery decides consumption.** `download_tour`'s streaming generator stamps the oldest unconsumed unlock `consumed_at = NOW()` **only after yielding the LAST byte** of the zip (`_consume_unlock_after_stream`, own short-lived connection). A client disconnect raises `GeneratorExit` inside the generator *before* that point, which is caught and re-raised **without** consuming — a cut-off download never spends the purchase (D660), decided by the server, not the app.
- **`POST /tour/<id>/download-complete` is replaced by `POST /tour/<id>/download-failed`.** The app no longer confirms success; it reports **failure** (bytes received, but save/validate failed). `_restore_unlock` restores the just-consumed purchase **exactly once** (`restored_at`), **only within 24h** of consumption:
  - restore → **200** `{restored:true, remaining_unconsumed}`;
  - second report for the same purchase (already restored) → **409** `already_restored`;
  - report past 24h → **409** `window_expired`;
  - nothing consumed → **409** `not_consumed`.
- **Migration 032** (`032_tour_unlock_restore.sql`) adds `tour_unlocks.restored_at` (additive, idempotent); the service self-heals the column via `_ensure_unlock_consumption_columns`.
- **App:** `_confirmDownloadComplete` → `_reportDownloadFailed(tourId, consumesHeader, reason)`, wired at all four download call sites (main, silent, single-English, translation) to fire **only** when the bytes arrived (HTTP 200) but the zip could not be saved/validated, keyed off the `X-Download-Consumes-Unlock` response header. Build bumped `2.4.17+52`.

### 5. Test isolation
**Problem:** `test_local693` passed alone but 5 tests 401'd under `pytest tests -k "677 or 686 or 690 or 691 or 693"`. Root cause: `test_local595_api` / `604` / `596` set `GATEWAY_API_KEY` (and `IAP_VERIFY_MODE`) **unconditionally at import time** and never restore them; the entitlements / document-acceptance modules cache `API_KEY = os.getenv('GATEWAY_API_KEY')` at import, so the `setdefault`-based 677/690/691/693 inherited a non-empty key → auth required → 401.

**Fix:** each of 677 / 690 / 691 / 693 now **owns and restores its own env** via an autouse module-scoped fixture `_isolate_entitlements_env` (saves, forces `GATEWAY_API_KEY=''`, `IAP_VERIFY_MODE='stub'`, `ALLOW_UNAUTHENTICATED_ENTITLEMENTS='true'`, restores on teardown). Each module's loader also pins the cached `API_KEY=''` / `IAP_VERIFY_MODE='stub'` on the freshly-imported module. No change to the offending 595/604/596 modules (out of scope).

## Tests (all green)
- **Combined** `pytest tests -k "677 or 686 or 690 or 691 or 693"` → **80 passed, 0 failed, 18 skipped** (was 37 failed before isolation fix).
- **`test_local693` alone** → **10 passed**, including the LEAD cases:
  - full stream **consumes** (buy → download → second 402 → rebuy);
  - **cut-off stream** (generator closed before last byte) → **does NOT consume**, retries free, then a full download consumes;
  - **download-failed** restores once (200) → second report **409** → past-24h **409** → no-consumption **409**;
  - two languages consumed independently; grandfathered + curator never consume; unlock-state counts; verified stays verified.
  - `_make_tour_zip` uses `ZIP_STORED` with enlarged payloads so the zip spans multiple 8KB chunks and the cut-off genuinely exercises the `GeneratorExit` path.
- **Dart** `flutter test test/delete_tour_prompt_test.dart` → **6 passed**: paid exact title/body/buttons, free skips the warning, `isPaidTour` detection.
- `python3 -m py_compile map_delivery/app.py` OK; `flutter analyze` on the 4 changed Dart files → **0 errors** (only pre-existing lint info/warnings outside the changed lines).

## Commits (693B, on `LOCAL-693-paid-per-download`)
1. app — remove Buy-dialog warning; delete confirmation to exact D660-addendum copy; build bump
2. legal — calm wording + recovery-code sentence (TERMS/REFUNDS/GUIDE_TERMS/PRIVACY → draft3); regenerate `legal/html`
3. server — migration 032 `restored_at`; map-delivery consumes server-side at last byte; replace `download-complete` with `download-failed` (restore-once / 24h / 409); app reports failure
4. tests — rewrite 693 for server-side consumption + cut-off + restore; env isolation across 677/690/691/693

## Not done / out of scope
- Same as 693: no full Docker-container live run (`map_delivery/app.py` hard-codes `host="postgres-2"`; the ticket forbids touching `audioura-*` containers). The in-process clients exercise the identical service code against the real dev Postgres.
- The recovery-code restore flow itself (entering a code on a new phone) is **LOCAL-695**; 693B only adds the Terms/Refunds sentence that promises it.
