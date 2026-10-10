# SUBMISSION — LOCAL-666: a translation carries its source tour's version ("v10"), and the downloaded tour shows it too

**Branch:** `LOCAL-666-translation-version`
**Base:** `subscribed` @ `18cdcc89` (verified ancestor of HEAD)
**Agent:** Mac Mini Kiro

## Problem (Michael 2026-10-10)

> "The Russian translation is not delivered with the version in the title: you may want to fix that too."

LOCAL-657 computes a tour's `version` from `audio_tour_versions` for the row's
**own** id. A translation row (`original_tour_id` set — e.g. Russian **615** of
tour **557**) is never replaced in place: LOCAL-606's LEAD fix (c0976635) makes a
**fresh** row whenever its source changes, so a translation has **no archive rows
of its own** and LOCAL-657 always calls it **"v1"** (no label). The listener
expects the Russian copy of v10 to say **v10**.

## What was delivered

### 1. DB — `audio_tours.source_version INTEGER NULL` (additive, declared)

`migration/sql/018_audio_tours_source_version.sql` adds the column explicitly;
the translation service also adds it **self-healingly at runtime** (idempotent
`ADD COLUMN IF NOT EXISTS`), mirroring the existing `translation_stale` /
`audio_tour_versions` pattern. Applying the migration and running the code
produce identical schema; running the code without the migration still works.
**No DROP, no DELETE — purely additive.** NULL on every existing row (originals
and pre-666 translations alike) → map-delivery falls back to the source's live
version, so old data is never wrong.

**Column added: `audio_tours.source_version INTEGER` (nullable).**

### 2. translation-service — pin the source version when creating a translation

`translation-service/translation_service.py`:

- `_source_tour_version(cursor, source_id)` = `COALESCE(MAX(version_no),0)+1`
  over `audio_tour_versions` for the **source** id — exactly the number LOCAL-657
  shows for the original. `_ensure_source_version_column(cursor)` self-heals the
  column (guarded like the existing `track` column).
- Both INSERT paths (`translate_tour_with_audio` main path **and** the
  `_translate_tour_from_zip` fallback) now build their column/value lists so
  `source_version` is appended **only when the column exists** — the two historic
  branches (track present/absent) are preserved and `source_version` is added
  orthogonally, so an older schema still inserts cleanly.

### 3. translation-service — `/translate-with-audio` returns `version` + `updated_at`

For `content_type == 'tour'`, each language's result now carries `version` and
`updated_at` (module helper `_translation_version_fields`): `version` = the
translation's pinned `source_version` (else the source's live version), and
`updated_at` = the translation row's own `created_at`. Additive and best-effort —
a derivation failure simply omits the fields.

### 4. map-delivery — a translation reports its SOURCE version

`map_delivery/app.py`, across **`/tour-by-code`, `/tours-near`, `/search-tours`
and `/tour-info`**:

- New `_resolved_version_fields(...)`: for an **original** (`original_tour_id`
  NULL) it is unchanged LOCAL-657 behaviour (own archive → version;
  `replaced_at` else `created_at` → `updated_at`). For a **translation** it
  reports `source_version` (else the **source's live version** via a second
  grouped `LEFT JOIN` of `audio_tour_versions` on `original_tour_id`), with the
  translation's own `created_at` as `updated_at`.
- A cached one-time probe (`_has_source_version_column`) selects `t.source_version`
  or a `NULL::integer` literal, so on an **older schema (column absent)** a
  translation still falls back to the source's live version.
- `/tour-info` now carries `version`/`updated_at` too (it previously sent none).

So the Russian **615** copy of v10 now reports **v10**, not v1.

### 5. App — show the label on the My Tours list, for English AND translations

`audio_tour_app/`:

- `my_tours_screen.dart`: new top-level pure `tourVersionLabel(tour)` (same rule
  and format as the found-tour dialogs' `_tourVersionLabel` from LOCAL-657),
  rendered under each tour's subtitle on the Listen/My-Tours list — **only when
  `version >= 2`**; every read is defensive, so an entry saved without the fields
  shows nothing extra and never crashes.
- Version/updated_at are persisted into `saved_tours`:
  - **English:** the found-tour entry (map-delivery already sends the fields on
    `/tours-near`, `/search-tours`, `/tour-by-code`) is threaded through
    `_downloadSingleTour[Silent]` → `_saveTourToMyTours` (new optional
    `sourceItem`) and stored when present.
  - **Translations:** `tour_translation_helper` reads
    `result['translations'][lang]['version'/'updated_at']` from
    `/translate-with-audio` and stores them on the saved translation — so a
    translation shows its **source** version (e.g. v10).
- The found-tour dialogs already render the label (LOCAL-657); nothing regressed.
- `pubspec.yaml` bumped **2.4.6+32 → 2.4.7+34** (next build; `+33` reserved for
  LOCAL-665).

**Compatibility:** every new field is additive. An old app ignores
`version`/`updated_at`; a new app against an old server (no fields) simply shows
no label. The DB column is nullable and self-healed.

## Tests

### Server unit tests — hermetic (scripted fake cursor, no DB, no services, zero rows written)

`tests/test_local666_translation_source_version.py` (15 tests) drives the **real**
map-delivery endpoint code and the translation-service helpers:

- **(a) translation inherits v10:** `/tour-by-code` and `/tour-info` with a
  translation row `source_version=10` → **version 10**, `updated_at` = the
  translation's own `created_at`.
- **(b) translation of an unreplaced source = v1:** no archive + no pin → version
  **1** (two variants: pinned `source_version=1`, and NULL-pin falling back to a
  source with no archive) → the app shows no label.
- **(c) column absent → fallback:** the `information_schema` probe returns no row,
  so the translation takes the **source's live version** from the second grouped
  join (`source_max_version_no=9` ⇒ v10).
- An **original-row regression guard** (LOCAL-657 behaviour unchanged), direct
  `_resolved_version_fields` cases, and the translation-service helpers
  (`_source_tour_version`, `_ensure_source_version_column`,
  `_translation_version_fields`; `boto3` stubbed in `sys.modules`).

`tests/test_local657_version_label.py` was updated to the new 13-column SELECT
contract (its translation case now asserts the pinned source version).

```
$ python3 -m unittest tests.test_local657_version_label tests.test_local666_translation_source_version
Ran 21 tests — OK
$ python3 -m pytest tests/test_local666_translation_source_version.py tests/test_local657_version_label.py -q
21 passed
```

### Flutter

- `flutter analyze` on the three changed Dart files: **0 errors**, and the issue
  set is **identical** to the pre-change HEAD baseline (0 new issues) — verified by
  stashing the changes and diffing the analyzer output.
- `flutter build ios --no-codesign` — **succeeds**:
  `✓ Built build/ios/iphoneos/Runner.app (37.3MB)`.

The app was **not** installed to the phone (LEAD does that with Michael). An
incidental `Podfile.lock` CocoaPods version bump (1.16.2→1.17.0) produced by the
local build was reverted — not part of this ticket.

## Live check — own container, read-only, no paid APIs

Built the image from this branch and ran it as **my own** container on spare port
**5056**, attached to the shared network `development_default` so the hardcoded
host `postgres-2` resolves to the shared Postgres (`development-postgres-2-1`,
network alias `postgres-2`). Only SELECT-only endpoints were hit.

**The live DB does not yet have the `source_version` column**, so this live run
exercised the **"column absent → source's live version"** fallback (case c) — the
realest possible test of that path. Source **557**'s live version is **10**
(9 archived + 1).

```bash
docker build -t local666-map:test --build-arg GIT_SHA=$(git rev-parse --short HEAD) map_delivery
docker run -d --rm --name local666-map --network development_default -p 5056:5005 local666-map:test
curl -s http://localhost:5056/tour-info/615     # RU translation of 557
docker stop local666-map    # --rm cleans up; image removed afterwards
```

Result — Russian **615** → **version 10** (was v1), `updated_at` = the
translation's own date:

```json
{
  "id": 615, "language": "ru", "is_translation": true, "parent_tour_id": 557,
  "version": 10, "updated_at": "2026-10-09"
}
```

`/tour-info/557` (English original) → `version 10`, `updated_at 2026-10-10`
(unchanged LOCAL-657 behaviour); `/tour-by-code/q9oSUebU` → 557 `version 10`.
**ACCEPTANCE MET: Russian 615 → version 10.**

Container logs show **no** INSERT/UPDATE/DELETE/ALTER/COMMIT (read-only). My
container was stopped (`--rm` auto-removed) and the test image removed. The shared
`audioura-map-delivery-1` and `development-postgres-2-1` were left running and
untouched. **No `docker compose -p audioura`; no `audioura-*` container was
replaced; no database rows written; no GCloud; no paid calls.**

## DB change (declared, additive)

- **`audio_tours.source_version INTEGER` (nullable).** Set by the translation
  service at translation time to the source tour's current version. NULL on all
  existing rows → map-delivery falls back to the source's live version.

## Files changed

- `migration/sql/018_audio_tours_source_version.sql` — the additive column.
- `translation-service/translation_service.py` — pin `source_version` on both
  INSERT paths; `/translate-with-audio` returns per-language `version`/`updated_at`.
- `map_delivery/app.py` — `_resolved_version_fields` + source-version join across
  `/tour-by-code`, `/tours-near`, `/search-tours`, `/tour-info`; schema-probe
  fallback.
- `audio_tour_app/lib/screens/my_tours_screen.dart` — `tourVersionLabel` + list label.
- `audio_tour_app/lib/screens/home_screen.dart` — thread the found-tour entry's
  version/updated_at into the saved English tour.
- `audio_tour_app/lib/services/tour_translation_helper.dart` — store the
  translation's version/updated_at from the response.
- `audio_tour_app/pubspec.yaml` — 2.4.6+32 → 2.4.7+34.
- `tests/test_local666_translation_source_version.py` — 15 hermetic server tests.
- `tests/test_local657_version_label.py` — updated to the new SELECT contract.
