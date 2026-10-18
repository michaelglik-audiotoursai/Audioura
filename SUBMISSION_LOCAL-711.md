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


---

# 711B — infer a blank type, never "… Tour — Tour" (LEAD review of 711)

**Branch:** `LOCAL-711-short-titles` (continued from `ad62b358`, base `subscribed` = `57294733`)
**App version:** `2.4.28+66` → `2.4.28+67` (build +1)

## Why

LEAD's 711 review found that every tour whose stored type is blank (`… -  Tour`)
got a weak title: the type was dropped to a bare " — Tour" and the subject often
repeated the category words. The four failing rows:

| id | stored name | 711 short title | required |
|----|-------------|-----------------|----------|
| 368 | restaurant tour of Buttermilk & Bourbon - Back Bay, Boston, Ma -  Tour | Buttermilk & Bourbon — Tour | Buttermilk & Bourbon — Restaurant Tour |
| 370 | restaurant tour, Boston, MA -  Tour | Restaurant Tour — Tour | Boston — Restaurant Tour |
| 372 | chart house restaurant tour, Boston, MA -  Tour | Chart House Restaurant Tour — Tour | Chart House — Restaurant Tour |
| 397 | WNDR museum, Boston, MA -  Tour | WNDR Museum — Tour | WNDR Museum — Museum Tour |

## What changed (all in `tour_short_title.py`, deterministic, pure)

1. **Infer the type when the suffix is blank.** `infer_tour_type(name, request,
   stored_type)`: a non-empty stored suffix type always wins (Title-Cased). When
   it is blank, a word-boundary keyword map (`TYPE_KEYWORDS`: restaurant, museum,
   walking, cycling/biking, food, art, history, boat…) reads the type from the
   name then the request. Nothing found → `''` → the plain " — Tour" (711's
   typeless contract). This runs **before** the LLM and the fixed type is passed
   to the prompt, so the model never invents one.
2. **The subject never carries the type words.** The prompt now asks for the
   **SUBJECT only**; the caller appends " — <Type> Tour" via `compose_title`, so
   the type can never be doubled. `_strip_type_words` then removes any type word
   the model still echoed — keeping "Museum" when it is part of a proper name
   ("WNDR Museum", "McMullen Museum of Art") but dropping a bare leading "Museum".
3. **Place-as-subject for a generic subject.** When the stripped subject is only
   category words (`_is_generic_subject`), `_place_from_name` supplies the place
   (first non-generic comma chunk of the name, state codes like "MA" dropped):
   "restaurant tour, Boston" → **Boston — Restaurant Tour**.
4. **Validator hardened.** `validate` now rejects any title whose subject ends in
   "Tour" (the 711 weakness: "Chart House Restaurant Tour — Tour") and any
   "Tour — Tour" anywhere, in addition to the empty / > 60-char checks.

The user's `tour_name` is still never modified; the module stays self-contained;
the orchestrator / translation / backfill callers are unchanged (they already
pass the name-derived type, which `infer_tour_type` now upgrades).

## Live test (read-only — NO backfill on the shared DB)

`make_short_title` re-run for real (one `gpt-4o-mini` call each) on the same 10
ids. The tour names were read **read-only** from the shared
`development-postgres-2-1` (localhost:5433); the connection was closed and
**nothing was written**. Tokens in 3933, out 41, ~**$0.0006**. All ≤ 60 chars.

| id  | stored type | short_title |
|-----|-------------|-------------|
| 365 | walking     | Faneuil Hall Marketplace — Walking Tour |
| 368 | *(blank)*   | Buttermilk & Bourbon — Restaurant Tour |
| 370 | *(blank)*   | Boston — Restaurant Tour |
| 372 | *(blank)*   | Chart House — Restaurant Tour |
| 388 | biking      | Crystal Lake to Paul Revere Park — Biking Tour |
| 397 | *(blank)*   | WNDR Museum — Museum Tour |
| 399 | museum      | McMullen Museum of Art — Museum Tour |
| 400 | museum      | Harvard Art Museums — Museum Tour |
| 402 | museum      | Vietnam National Fine Arts Museum — Museum Tour |
| 557 | walking     | Massachusetts Politics — Walking Tour |

The four blank-type rows now match the required column exactly. 388 keeps
"Biking" because its stored suffix type is non-blank (the keyword map only fires
on a blank type).

## Tests

`tests/test_local711_short_title.py` — **33 pass** (was 16). Added, all with a
stub LLM that echoes the SUBJECT it is given:

- `infer_tour_type` — stored type wins and is Title-Cased; map reads the type
  from the name when blank; biking → Cycling; nothing → `''`.
- `_strip_type_words` — strips the category word and an echoed full suffix,
  keeps proper-name "Museum", drops a bare "Museum".
- `_is_generic_subject`, `_place_from_name` (state code "MA" dropped),
  `compose_title`.
- A parametrized row per id (`_B_ROWS`: the 4 failing + the 6 good from 711),
  each asserting the required output, ≤ 60 chars, and no doubled "Tour".
- `validate` rejects "Restaurant Tour — Tour", "Chart House Restaurant Tour —
  Tour", "WNDR Museum Tour — Museum Tour", "X Tour — Tour"; accepts the clean
  forms.

The original 711 cases stay green (`_strip_type_words` reduces an echoed full
title back to its subject); `test_empty_reply_rejected` now uses an empty
name+request so it still returns `None` under the new place-as-subject rescue.
Sibling map-delivery fixtures (`test_local687`, `test_local701`) unchanged and
still pass.

## Process

Continued the existing `LOCAL-711-short-titles` branch. Did not edit DECISIONS /
CLAUDE / BACKLOG / WORK_QUEUE / .continuous_dev. Own containers only — the shared
`audioura-*` stack was never started, renamed, or written to.
