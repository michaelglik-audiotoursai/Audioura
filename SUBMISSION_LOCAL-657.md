# SUBMISSION — LOCAL-657: show a tour's version in the app ("v2 · updated Oct 9")

**Branch:** `LOCAL-657-tour-version-label`
**Base:** `subscribed` @ `8e12c846` (verified ancestor of HEAD)
**Agent:** Mac Mini Kiro

## Problem (Michael 2026-10-09)

LOCAL-606 replaces a regenerated tour **in place** — same `id`, same share code —
and archives each superseded version into `audio_tour_versions(tour_id,
version_no, replaced_at)`. But the app shows nothing to distinguish the fresh
content from the old one. Tour **557** (share code `q9oSUebU`), regenerated
today, looks identical to the version it replaced. Michael: *"We should have
some distinction between tours with the same requested string, I thought we used
to place a version number?"*

## What was delivered

### 1. Server — map-delivery (`map_delivery/app.py`)

Both list endpoints the app's tour dialogs read now carry two new fields on
every tour element:

- **`version`** = `COALESCE(MAX(version_no), 0) + 1` for that tour's own id.
  A never-replaced tour has no archive rows → version **1**. Each replacement
  archives the old `version_no` (1, 2, 3…), so N archived rows mean the live row
  is version **N+1**.
- **`updated_at`** = the newest `replaced_at` if the tour was ever replaced,
  else the row's `created_at`, as an ISO date (`YYYY-MM-DD`).

Both are computed with **one `LEFT JOIN` over a single grouped pass** of
`audio_tour_versions` (`MAX(version_no)`, `MAX(replaced_at)` grouped by
`tour_id`) — **not a query per tour**. A shared helper `_version_fields()`
derives the pair from `(max_version_no, last_replaced_at, created_at)`.

Endpoints changed:
- `GET /tours-near/<lat>/<lng>` — the location-based home list.
- `GET /tour-by-code/<code>` — share-code resolution (the second way in).

**Translations:** `/tour-by-code` can resolve to a translation row
(`original_tour_id` set) as well as an original. Either way the join is on the
**resolved row's own id**, so a translation carries **its own** version — the
version of the exact tour the listener downloads, per the ticket.
(`/tours-near` only lists originals, so translations never appear there.)

### 2. App (`audio_tour_app/lib/screens/home_screen.dart`)

A new helper `_tourVersionLabel(tour)` builds `"v{version} · updated {Mon D}"`
and is rendered next to **Downloads** in both dialogs that `_presentFoundTours`
drives (they share code as of today):

- the **single-tour** dialog (`_onTourMarkerTapped`), and
- the **multiple-tour** dialog (`_showMultipleTourDialog`).

The label appears **only when `version >= 2`**. For v1 it shows nothing new.
Every field read is **defensive**: a missing `version` (an old map-delivery that
does not send the field), an unparseable value, or a missing/unparseable
`updated_at` yields `null` and simply renders nothing — **it never crashes**.

### 3. Local stack (`docker-compose.subscribed-local.yml`)

`map-delivery` was **not** in the subscribed-local override. Added it the same
way as the other subscribed-local services, with build context
`/Users/micha/audioura-subscribed-local/map_delivery`:

```yaml
  map-delivery:                           # LOCAL-657 version/updated_at on /tours-near + /tour-by-code
    build: {context: /Users/micha/audioura-subscribed-local/map_delivery}
```

`docker compose -f docker-compose-master.yml -f docker-compose.subscribed-local.yml config`
merges cleanly and the merged `map-delivery` build context resolves to the
subscribed-local path. **LEAD rebuilds the shared container** — this task did
**not** rebuild or replace `audioura-map-delivery-1`.

## Tests

### Server unit tests — `tests/test_local657_version_label.py` (6 tests)

Hermetic: a tiny scripted fake DB cursor replaces `get_db_connection`, so the
tests **write no database rows** and run with no services up, while driving the
**real** endpoint code (SELECT column order, `_version_fields` derivation, JSON
shape the app consumes).

- `/tours-near`: version **1** when there are no archive rows; version **3**
  after two replacements, with `updated_at` = newest `replaced_at` (not
  `created_at`).
- `/tour-by-code`: version **≥ 2** for a replaced tour (the `q9oSUebU`/557
  shape); version **1** for a fresh tour; a **translation** row carries its own
  version.
- `_version_fields()` directly: `datetime`, plain `date`, and no-timestamp cases.

```
$ python3 -m unittest tests.test_local657_version_label   → Ran 6 tests OK
$ python3 -m pytest tests/test_local657_version_label.py -q → 6 passed
```

### Flutter

- `flutter analyze lib/screens/home_screen.dart` — **no new errors or
  warnings**. The diff against the pre-change baseline is only line-number
  shifts plus **one** `prefer_const_constructors` *info* on a new `Text` whose
  content is a runtime value (`_tourVersionLabel(...)!`, `Colors.blue.shade700`)
  and therefore cannot be `const` — consistent with every other `Text` in these
  dialogs.
- `flutter build ios --no-codesign` — **succeeds**:
  `✓ Built build/ios/iphoneos/Runner.app (37.3MB)`.

The app was **not** installed to the phone (LEAD does that with Michael).

## Live check — own container, read-only, no paid APIs

Built the image from this branch and ran it as **my own** container on spare
port **5055**, attached to the shared network `development_default` so the
hardcoded host `postgres-2` resolves to the shared Postgres
(`development-postgres-2-1`). Only SELECT-only endpoints were hit; container
logs show **no** UPDATE/INSERT/DELETE. **No `docker compose -p audioura`; no
rename or replacement of any `audioura-*` container; no database rows written.**

```bash
docker build -t local657-map:test --build-arg GIT_SHA=$(git rev-parse --short HEAD) map_delivery
docker run -d --rm --name local657-map --network development_default -p 5055:5005 local657-map:test
curl -s http://localhost:5055/tour-by-code/q9oSUebU
docker stop local657-map        # --rm cleans up; image removed afterwards
```

Result (abridged) — tour **557**, **version 3**, **updated 2026-10-09**:

```json
{
  "count": 1,
  "tours": [{
    "id": 557,
    "name": "Walking tour in Boston dedicated to Massachusetts politics and current affairs, Boston, MA - walking Tour",
    "via_share_code": "q9oSUebU",
    "distance_km": null,
    "version": 3,
    "updated_at": "2026-10-09"
  }]
}
```

`version >= 2` for tour 557 ✓. The shared `audioura-map-delivery-1` and
`development-postgres-2-1` containers were left running and untouched; my
container and test image were removed.

## Compatibility

- **Old app against new server:** the new JSON fields are additive; an app that
  does not read them is unaffected.
- **New app against old server:** `version`/`updated_at` are absent →
  `_tourVersionLabel` returns `null` → no label, no crash.

## Files changed

- `map_delivery/app.py` — `_version_fields()` helper; `version`/`updated_at` via
  one grouped `LEFT JOIN` on `/tours-near` and `/tour-by-code`.
- `audio_tour_app/lib/screens/home_screen.dart` — `_tourVersionLabel()` helper;
  conditional label in the single- and multiple-tour dialogs.
- `docker-compose.subscribed-local.yml` — add `map-delivery`.
- `tests/test_local657_version_label.py` — 6 hermetic server unit tests.
