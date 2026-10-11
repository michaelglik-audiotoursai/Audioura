# SUBMISSION — LOCAL-671: tour dialogs show the ORIGINAL language ("Original: English"), not a list of languages (D648)

**Branch:** `LOCAL-671-original-language`
**Base:** `subscribed` @ `70a0bf83` (contains LOCAL-670B; verified ancestor of HEAD)
**Agent:** Mac Mini Kiro

## Why (Michael, 2026-10-10)

> "Display: no languages. User should choose and we should translate. But it is a good idea to indicate the original language."

The tour dialogs must not list available translations. The listener still picks
any target language with the existing selector and we translate. The one thing
worth surfacing is the language the tour was **originally written in** —
"Original: English".

## What was delivered

### 1. map-delivery — every tour element carries `original_language`

`map_delivery/app.py`, across **all four** endpoints the app's tour dialogs read
(`/tour-by-code`, `/tours-near`, `/tour-info`, `/search-tours`):

- New pure helper **`_resolved_original_language(own_content_language,
  original_tour_id, source_content_language)`**:
  - **ORIGINAL** row (`original_tour_id` NULL) → its **own** `content_language`
    (the language it was written in).
  - **TRANSLATION** row (`original_tour_id` set) → the **ORIGINAL** tour's
    `content_language`. A translation's own language (`ru`, `fr`, …) is **not**
    the original language and is ignored.
  - Unknown on either side → defaults to **`'en'`**, so the dialog never shows a
    blank "Original:".
- The ORIGINAL's language is reached by a self-join: `_ORIGINAL_LANGUAGE_JOIN`
  (`LEFT JOIN audio_tours orig ON orig.id = t.original_tour_id`), inert for an
  original row (no match → NULL). The two columns `t.content_language AS
  own_content_language` and `orig.content_language AS source_content_language`
  are **appended as the final two SELECTed columns** on every endpoint
  (`_ORIGINAL_LANGUAGE_SELECT`), mirroring exactly how LOCAL-670 appended its
  rating columns — so existing column positions, and therefore every sibling
  test fixture, stay stable except for two new trailing values.
- Each endpoint's row unpacking takes the two trailing values and sets
  `original_language` on the JSON element.

**Read-only. No schema change** — `content_language` already exists (and
`original_tour_id` from the translation feature). Purely additive to the JSON.

### 2. App — the dialogs show "Original: <Language name>", no translation list

`audio_tour_app/lib/screens/home_screen.dart`:

- New `_originalLanguageLabel(tour)` returns `"Original: <Language name>"` from
  the tour's `original_language` code, mapped to a display name via the existing
  `_getLanguageName` (en→English, es→Spanish, fr→French, de→German, ru→Russian,
  zh→Chinese, else the uppercased code). It is **null-safe**: a missing or blank
  field (an older map-delivery that does not send it) returns `null`, so the
  label simply does not appear rather than reading "Original: ".
- Rendered beside the version and rating badges in **both** dialogs on the shared
  `_presentFoundTours` path:
  - **single-tour** dialog (`_onTourMarkerTapped`), under the rating badge and
    `_tourVersionLabel`.
  - **multi-tour** dialog (`_showMultipleTourDialog`), in each tour's subtitle
    `Column`, after the version block and before the language row.
- **No list of available translations** was added. The existing
  `LanguageSelector` in both dialogs still lets the listener choose any language
  to translate into — unchanged.

**Compatibility:** additive. An old app ignores `original_language`; a new app
against an old server (no field) shows no "Original:" label and never crashes.

## Tests

### Server unit tests — hermetic (scripted fake cursor, no DB, no services, zero rows written)

`tests/test_local671_original_language.py` drives the **real** map-delivery
endpoint code:

- **ORIGINAL reports its own language:** `/tours-near` with an English original →
  `original_language "en"`; a non-English original (`fr`) → `"fr"` (proves the
  field is the row's own language, not a hardcoded `"en"`).
- **TRANSLATION reports its SOURCE's language:** `/tour-by-code` and `/tour-info`
  with a Russian (`ru`) translation of English (`en`) 557 → `original_language
  "en"` (NOT `"ru"`); an original on the same endpoints → its own language.
- **/search-tours** carries it for a translation and an original in one result set.
- **NULL source language → `"en"`** fallback (legacy original predating the
  column default).
- Direct `_resolved_original_language` cases (original/translation/NULL).

Sibling fixtures updated for the two appended trailing columns (same pattern
LOCAL-670 used): `tests/test_local657_version_label.py` and
`tests/test_local666_translation_source_version.py` now supply
`own_content_language` + `source_content_language` and additionally assert
`original_language` where a translation/original is exercised.
`tests/test_local670_tour_ratings.py` is DB-backed (reads JSON, not positional
tuples) and is unaffected.

```
$ python3 -m pytest tests/test_local671_original_language.py \
      tests/test_local657_version_label.py \
      tests/test_local666_translation_source_version.py -q
32 passed
```

### Flutter

- `flutter analyze lib/screens/home_screen.dart`: **0 errors**, and the issue
  count is **identical** to the pre-change HEAD baseline — **298 before, 298
  after** (zero net new issues), verified by stashing the change and diffing the
  analyzer output. (The one transient `prefer_const_constructors` info from a new
  `SizedBox` was removed by making it `const`.)
- `flutter build ios --no-codesign` — **succeeds**:
  `✓ Built build/ios/iphoneos/Runner.app (37.3MB)`.

The app was **not** installed to the phone. An incidental `Podfile.lock`
CocoaPods version bump (1.16.2→1.17.0) produced by the local build was reverted —
not part of this ticket.

## Live check — own container, read-only, no paid APIs

Built the image from this branch and ran it as **my own** container on spare port
**5057**, attached to the shared network `development_default` so the hardcoded
host `postgres-2` resolves to the shared Postgres (`development-postgres-2-1`,
network alias `postgres-2`). Only SELECT-only endpoints were hit.

```bash
docker build -t local671-map:test map_delivery
docker run -d --rm --name local671-map --network development_default -p 5057:5005 local671-map:test
curl -s http://localhost:5057/tour-info/615   # RU translation of 557
curl -s http://localhost:5057/tour-info/557   # EN original
curl -s "http://localhost:5057/search-tours?pattern=.*&lat=42.36&lng=-71.06"
docker stop local671-map    # --rm cleans up; image removed afterwards
```

Results — the Russian **615** copy of English **557** reports the ORIGINAL
language, and the English original reports its own:

```json
// /tour-info/615  (is_translation: true, parent_tour_id: 557, language: "ru")
{ "id": 615, "language": "ru", "original_language": "en", ... }

// /tour-info/557  (is_translation: false, language: "en")
{ "id": 557, "language": "en", "original_language": "en", ... }
```

`/search-tours` over the Boston area returned both: translations (ids 650/30 `ru`,
33/31 `fr`) all `original_language: "en"`; originals (29/1 `en`) `original_language:
"en"`. **ACCEPTANCE MET: a translation shows its source language, an original
shows its own.**

Container logs show **no** INSERT/UPDATE/DELETE/ALTER/COMMIT (read-only). My
container was stopped (`--rm` auto-removed) and the test image removed. The shared
`audioura-map-delivery-1` and `development-postgres-2-1` were left running and
untouched. **No `audioura-*` container was replaced; no DELETE; no database rows
written; no paid calls.**

## DB change

**None.** `content_language` and `original_tour_id` already exist; this ticket
only adds a derived field to the JSON responses.

## Files changed

- `map_delivery/app.py` — `_resolved_original_language` + `_ORIGINAL_LANGUAGE_SELECT`
  / `_ORIGINAL_LANGUAGE_JOIN`; `original_language` on `/tour-by-code`, `/tours-near`,
  `/tour-info`, `/search-tours`.
- `audio_tour_app/lib/screens/home_screen.dart` — `_originalLanguageLabel`;
  "Original: <Language>" in the single- and multi-tour dialogs.
- `tests/test_local671_original_language.py` — new hermetic server tests.
- `tests/test_local657_version_label.py`, `tests/test_local666_translation_source_version.py`
  — fixtures updated for the two appended columns; assert `original_language`.
