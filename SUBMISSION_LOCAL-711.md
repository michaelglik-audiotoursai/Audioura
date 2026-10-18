# SUBMISSION — LOCAL-711: Server-written short tour titles + translation line (D673)

**Branch:** `LOCAL-711-short-titles` (from `subscribed` = `57294733`)
**Agent:** Mac Mini Kiro
**App version:** `2.4.27+65` → `2.4.28+66` (patch +1, build +1)

## What this delivers (D673)

Tour names are often whole sentences the curator typed. D672 already shortened
them in the app with `shortTourTitle()`. D673 asks the **server** to write a
short, faithful title once, store it on the tour, translate it like the name,
and surface it so the share email uses it (title + subject). It also adds a
line to every share email and community invite advertising translation.

Two additive, fail-open changes:

1. **`audio_tours.short_title`** (migration 040): a 2–6 word subject plus the
   type, e.g. "Massachusetts Politics — Walking Tour". Written once at tour
   creation by one cheap `gpt-4o-mini` call; `--backfill` fills existing
   originals; translations carry the translated value. NULL on any failure →
   the app falls back to its own `shortTourTitle()`. The user's `tour_name` is
   never changed.
2. **The translation offer line** in every share email + community invite,
   right after "Hands-free audio: press play and walk." (after the explanation
   sentence in the invite):
   > Prefer another language? Audioura plays it in yours: just pick your language and listen.

The exact generated emails are in **`SHARE_EMAIL_SAMPLES_LOCAL-711.md`**.

## 1. Migration — `migration/sql/040_short_title.sql`

`ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS short_title TEXT`. Additive,
idempotent. **LEAD applies it** (and runs the backfill — see §7).

## 2. The module — `tour_short_title.py` (repo root)

Modelled on `tour_editor_score.py`.

- **`make_short_title(tour_name, request_string, tour_type) -> (title|None, usage)`**:
  one chat call at `temperature 0` to the cheapest model the repo uses
  (`SHORT_TITLE_MODEL` → `CHECK_LLM_MODEL` → `gpt-4o-mini`). The prompt enforces
  "`<Subject> — <Type> Tour`", 2–6 words, no invented facts, no place unless it
  IS the subject, no quotes; an empty type gives "` — Tour`". The output is
  re-sanitised (strips quotes/label/trailing punctuation) and **validated**:
  non-empty and ≤ 60 chars, else `None`.
- **`make_short_title_only(...)`**: a thin wrapper that NEVER raises and returns
  the title or `None` — the contract the orchestrator / translation callers use.
- **`--backfill`**: originals (`original_tour_id IS NULL`, not test) with
  `short_title IS NULL`, in commit batches, **idempotent** (a re-run picks up
  only what is left), writes **ONLY `short_title`** (never `tour_name`, never a
  DELETE), logs the per-run token cost, and prints the NULL-original count
  **before → after**. `--dry-run` writes nothing.

Self-contained (no `llm_models` import) so it drops cleanly into the three
service images.

## 3. Write at creation — `tour_orchestrator_service.py`

`store_audio_tour`'s new-insert path now adds `RETURNING id` to all three INSERT
branches, captures the id, and **after the tour is committed** calls
`make_short_title_only(tour_name, request_string, <type from the name>)` and
UPDATEs `short_title`. It is strictly **non-blocking**: wrapped in try/except
with a rollback, skipped for test rows, and any failure only logs — the stored
tour is never affected.

## 4. Translation — `translation-service/translation_service.py`

Both translation paths (the main `tour_content` path and the ZIP fallback
`_translate_tour_from_zip`) now:
- SELECT the source tour's `short_title` (guarded: `NULL::text` on an older
  schema, so the service never 500s pre-migration);
- translate it with `translate_text` **only when the original has one**;
- append `short_title` to the INSERT column/value lists, guarded by the column
  check AND a non-empty translated value — exactly where `tour_name` is
  translated. Orthogonal to the existing `track` / `source_version` branches.

## 5. Expose it — `map_delivery/app.py`

Added `_has_short_title_column(cur)` + `_short_title_select(cur)` (mirroring
`_source_version_select`). `short_title` is now SELECTed and returned on the
three payloads that already carry `tour_name`:
- `/tour-by-code/<code>` (share-resolve),
- `/tours-near/<lat>/<lng>`,
- `/tour-info/<id>`.

A **translation** returns its OWN translated `short_title` (like `t.tour_name`,
not the original's). It is placed just before the original-language pair so the
trailing content-rating columns (`_row_with_rating`) stay last; absent column →
`NULL` (fails open to today's behaviour).

## 6. App — `audio_tour_app/`

- **`lib/utils/share_code.dart`**: new `const kTranslationOfferLine` (the exact
  D673 wording). Inserted into `buildShareMessage` right after the hands-free
  line, and into `buildCommunityInvite` right after the explanation sentence.
- **`lib/widgets/share_tour_sheet.dart`**: `buildShareTourDetails` gains
  `serverShortTitle` — the title is the non-empty server value, else
  `shortTourTitle(rawName)`; `shareTour()` passes a `shortTitle` through.
- **`lib/services/downloaded_tour_meta.dart`**: `DownloadedTourMeta` stores
  `short_title` (so the player shares it offline).
- **`lib/services/communities_models.dart`**: `CommunityInviteTourOption` parses
  `short_title`; the invite's tour line prefers it.
- Call sites (`my_tours_screen`, `tour_player_screen`, `communities_about_screen`)
  pass the server value when they hold it.
- **`pubspec.yaml`**: `2.4.27+65` → `2.4.28+66`.

Dockerfile COPY lines added for the new module: `Dockerfile.orchestrator` and
`translation-service/Dockerfile` (a copy of `tour_short_title.py` lives in
`translation-service/` because its build context is that directory).
`Dockerfile.generator` already `COPY *.py`, so it needs no change.

## 7. Live test (read-only — NO backfill on the shared DB)

`make_short_title` run for real (one `gpt-4o-mini` call each, ~**$0.0005**
total) on tours 365, 557 and the 8 newest originals. The tour names were read
**read-only** from the shared `development-postgres-2-1`; **nothing was written
to the DB** (LEAD runs the backfill after applying migration 040).

| id  | short_title |
|-----|-------------|
| 365 | Faneuil Hall Marketplace — Walking Tour |
| 368 | Buttermilk & Bourbon — Tour |
| 370 | Restaurant Tour — Tour |
| 372 | Chart House Restaurant Tour — Tour |
| 388 | Crystal Lake to Paul Revere Park — Biking Tour |
| 397 | WNDR Museum — Tour |
| 399 | McMullen Museum of Art — Museum Tour |
| 400 | Harvard Art Museums — Museum Tour |
| 402 | Vietnam National Fine Arts Museum — Museum Tour |
| 557 | Massachusetts Politics — Walking Tour |

All ≤ 60 chars. 365 and 557 match the values in the regenerated samples.
`SHARE_EMAIL_SAMPLES_LOCAL-711.md` was regenerated from the real code.

## 8. Tests

- **Python** `tests/test_local711_short_title.py` (16 pass): `make_short_title`
  with a stub model (good / >60 / empty / exception → None); `make_short_title_only`
  never raises; `validate` / `_sanitise` / `_tour_type_from_name`; the backfill
  selects ONLY NULL originals (not translations, test rows, or already-set) and
  UPDATEs ONLY `short_title` (a DELETE raises in the fake cursor), is idempotent,
  and writes nothing on `--dry-run`; the translation copy condition; and the REAL
  `/tour-by-code` + `/tours-near` endpoints carry `short_title`.
- Sibling map-delivery fixtures updated for the new SELECT column
  (`test_local687_content_rating.py`, `test_local701_community_tours.py`). The
  map-delivery suite set is at the **same** pass-rate as the base
  (`subscribed`): **no new breakage** (the remaining pre-existing reds are stale
  fixtures in 666/657/88 that were already red before this task).
- **Dart**: `share_code_test.dart` goldens updated with the translation line +
  a new "D673 translation offer line" group; new
  `share_tour_details_short_title_test.dart` proves the server short_title is
  used verbatim else the fallback. Full **`flutter test`: 602 passed, 6 failed**
  — the 6 are all `local109_swipe_e2e_test.dart` (needs a live backend), the
  known baseline failures.

## Notes

- Everything is additive and fails open: an absent column or a failed title
  leaves `short_title` NULL and the app behaves exactly as under D672.
- The user-typed `tour_name` is never modified anywhere.
- Did not edit DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE / .continuous_dev.
