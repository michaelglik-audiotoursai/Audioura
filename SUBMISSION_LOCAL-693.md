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
