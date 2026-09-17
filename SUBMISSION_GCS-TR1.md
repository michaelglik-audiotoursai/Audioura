# SUBMISSION — GCS-TR1

**Agent:** Services Kiro
**Branch:** `kiro/gcs-tr1` (from `main` = `912cdd1`; `git merge-base --is-ancestor 912cdd1 HEAD` → 0)
**ClickUp:** `wdvrdaydr1`
**Scope:** `translation-service` only. No deploy performed. One production write only (the 424/425/426 hide).

---

## 1. What was broken (confirmed, not re-derived)

Reproduced the exact Cloud Run failure on the deployed **v35** baseline (see §6 RED proof):

```
INFO Using stored tour content: 106 characters
INFO Translated stop 1/.. ; Generated audio for stop 1/..
ERROR Error creating mobile-compatible ZIP: a bytes-like object is required, not 'NoneType'
  File ".../translation_service.py", line 1227, in _create_mobile_compatible_zip
    f.write(original_zip_data)
INFO Created translated tour <id> in ru ...        <- artifact-less row inserted anyway
```

Root causes (v35 == commit `73d8eb5`, verified byte-identical modulo line endings — v35 ships CRLF):
1. The source ZIP is only fetched from R2 **inside** `if not tour_content:`. R2-migrated tours
   with `tour_content` (107/120/284) skip it, so `original_zip_data` stays `None`.
2. `_create_mobile_compatible_zip` swallows the exception and returns `original_zip_data`
   (`None`); the INSERT then stores `audio_tour = NULL` with no `tour_blob_uri`.
   `map_delivery_service.py` only serves rows with `(audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)` → 404.
3. The cache check returned any existing `(original_tour_id, content_language)` row without
   requiring an artifact, so re-requesting Russian for tour 107 kept returning the broken 424.
4. `track` was never written, so translations defaulted to `beta`.

---

## 2. The fix (build from the `73d8eb5`/v35 copy of `translation_service.py`)

All changes are in `translation-service/translation_service.py` (nothing else in the image changes).

- **Source ZIP fetch moved above the branch.** Whenever `audio_tour` is NULL and
  `tour_blob_uri` is set — regardless of `tour_content` — the ZIP is downloaded from R2 via the
  existing `R2BlobStorage`. Applied to both the main path and (via `zip_data_override`) the
  ZIP-fallback path.
- **Never insert an artifact-less row.** New `TranslationArtifactError` (`error_code =
  "TRANSLATION_ARTIFACT_FAILED"`) is raised when the source ZIP can't be obtained, when the main
  path has `tour_content` but no source ZIP, or when `_create_mobile_compatible_zip` /
  `translate_zip_audio` returns `None`/empty. The transaction is rolled back; no INSERT happens.
  The `_create_mobile_compatible_zip` `except` was changed from
  `return original_zip_data  # Return original on error` to `return None` (signal failure).
- **Cache check requires an artifact.** Added
  `AND (audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)` to the tour cache query so
  artifact-less rows are ignored and regenerated.
- **Track inheritance.** The translation inherits the source tour's `track`. `track` is selected
  from the source row and written on INSERT, guarded by the same `information_schema.columns`
  check the orchestrator uses, so the INSERT still works on a DB without the column. Both the
  main and the ZIP-fallback INSERTs were updated (two INSERT variants: with/without `track`).
- **Endpoint contract.** `/translate-with-audio` now catches `TranslationArtifactError` and
  returns **HTTP 502** with `error_code: TRANSLATION_ARTIFACT_FAILED` (top-level and per-language)
  instead of the old always-200. Success responses are unchanged.
- **Storage stays BYTEA** (`audio_tour`); no R2 write added, per LEAD.

Final `translation_service.py` SHA256 (the exact file shipped in the overlay):
`3cf0c6179941fd143f9eb27c2b032414680d14c089bb8e011d285015807b4cf2`

---

## 3. Overlay image (built and verified locally; NOT pushed)

`translation-service/Dockerfile.tr1`:
```dockerfile
FROM us-central1-docker.pkg.dev/audiotours-migration/services/translation-service:v35
COPY translation_service.py /app/
```

`translation-service/tests_tr1/verify_overlay.sh` proves:
- **(a)** the deployed v35 `/app/translation_service.py` is **identical to commit `73d8eb5`**
  modulo line endings (v35 ships CRLF): after `tr -d '\r'` both hash
  `27a53f0fb9ead2947b420e9a2d713690a1625137f262802ab5342594d48c3d2f`.
- **(b)** the `/app` SHA256 manifest diff between v35 and `v35-tr1` lists **only**
  `./translation_service.py`:
  ```
  Changed paths:
  ./translation_service.py
  RESULT: PASS — only translation_service.py differs
  ```
Tagged locally `translation-service:v35-tr1`. Not pushed.

---

## 4. Acceptance criteria — results

Harness: `translation-service/tests_tr1/` — local Postgres + MinIO (as R2) via
`docker-compose.test.yml`; AWS Translate/Polly patched at method level (no spend).
Run: `bash tests_tr1/run_tests_tr1.sh` → **6 passed**.

| AC | Test | Result |
|----|------|--------|
| 1. red→green, R2-migrated source (tour_content set, audio_tour NULL, tour_blob_uri→ZIP in MinIO): row has an artifact; ZIP valid with translated `audio_N.txt` | `test_ac1_r2_migrated_source_produces_valid_artifact` | PASS |
| 2. failure path (missing R2 key): endpoint non-200, **no row inserted** (count unchanged) | `test_ac2_missing_r2_key_fails_and_inserts_no_row` | PASS |
| 3. cache trap: artifact-less row for same `(tour, lang)` is ignored; a working row is created | `test_ac3_cache_trap_ignores_artifactless_row` | PASS |
| 4. track: `storied` source → `storied`; `beta` source → `beta` | `test_ac4_track_inherited_from_source[storied|beta]` | PASS |
| 5. regression guard (D242): inserting a row without an artifact must fail the test | `test_ac5_no_row_without_artifact_when_zip_build_fails` | PASS |

The translated ZIP is asserted to be a valid ZIP whose `audio_1.txt` contains translated
(non-ASCII) text.

---

## 5. RED proof against v35 (D242 — break it, see red)

`translation-service/tests_tr1/prove_red.sh` loads the v35 baseline (extracted from `73d8eb5`)
and runs the same scenarios on the **same** Postgres + MinIO stack. Output:

```
RED CONFIRMED (AC1/AC5): v35 created tour <id> with NO artifact (audio_tour NULL, tour_blob_uri NULL) -> map-delivery 404
RED CONFIRMED (AC3): v35 returned artifact-less cached row <id> as a hit
RED PROOF: 2 historic failure(s) reproduced on v35
```
The v35 run logs the identical crash: `line 1227, in _create_mobile_compatible_zip` /
`f.write(original_zip_data)` / `TypeError: a bytes-like object is required, not 'NoneType'`,
then "Created translated tour …" — matching the Cloud Run log.

---

## 6. Orphan report (READ-ONLY) — all translation orphans, not just 424–426

Via the Cloud SQL Auth Proxy to `audiotours-migration:us-central1:audioura-db`
(db `audiotours`, user `admin`; password read from Secret Manager `db-password`, never printed;
proxy binary and all secret/token files deleted afterward).

`SELECT count(*) FROM audio_tours;` → **336** (before any change).

`SELECT id, original_tour_id, content_language, track, lat, lng, created_at FROM audio_tours
 WHERE original_tour_id IS NOT NULL AND audio_tour IS NULL AND tour_blob_uri IS NULL ORDER BY id;`

| id | original_tour_id | content_language | track | lat | lng | created_at |
|----|------|------|------|------|------|------|
| 368 | 144 | de | beta | 10.7731 | 106.6983 | 2026-06-09 15:38:08.409894 |
| 378 | 207 | zh | beta | 43.6957 | 7.2694 | 2026-06-25 14:52:39.196864 |
| 424 | 107 | ru | beta | 42.3256 | -71.2305 | 2026-09-17 01:48:57.971239 |
| 425 | 120 | ru | beta | 42.3224 | -71.1647 | 2026-09-17 01:49:42.253021 |
| 426 | 284 | ru | beta | 42.2433 | -71.1778 | 2026-09-17 01:50:33.785737 |

5 orphans total. **Only 424/425/426 were acted on** (LEAD instruction). 368 and 378 are
reported for LEAD; no action taken.

---

## 7. Narrow, reversible hide of 424/425/426 (the only production write)

Preconditions checked: all three exist and are artifact-less (`audio_tour` NULL, `tour_blob_uri`
NULL). **Backup (lat/lng) recorded before the update:**

| id | lat (backup) | lng (backup) |
|----|------|------|
| 424 | 42.3256 | -71.2305 |
| 425 | 42.3224 | -71.1647 |
| 426 | 42.2433 | -71.1778 |

```sql
UPDATE audio_tours SET lat = NULL, lng = NULL
WHERE id IN (424,425,426) AND audio_tour IS NULL AND tour_blob_uri IS NULL;
```
- **Rows affected: 3** (asserted).
- `count(*)` **before = 336**, **after = 336** (unchanged).
- Re-select after: 424/425/426 now have `lat = NULL, lng = NULL`, still artifact-less.
- **No DELETE.** Reversible: restore the lat/lng values in the table above.

---

## 8. Staged deploy (dry-run default — NOT executed)

`deploy_translation_tr1.sh` (repo root). Default is `--dry-run`; pass `--apply` to execute.
It names only `translation-service`. Dry-run output:

```
==============================================================
 GCS-TR1 deploy — service: translation-service (and no other)
 base image : us-central1-docker.pkg.dev/audiotours-migration/services/translation-service:v35
 new image  : us-central1-docker.pkg.dev/audiotours-migration/services/translation-service:v35-tr1
 dockerfile : .../translation-service/Dockerfile.tr1   (overlay: COPY translation_service.py /app/)
 context    : .../translation-service
 mode       : DRY-RUN
==============================================================

Build:
  docker build -f .../translation-service/Dockerfile.tr1 -t .../translation-service:v35-tr1 .../translation-service
Push:
  docker push .../translation-service:v35-tr1
Deploy (image only — no other flags, no other service):
  gcloud run services update translation-service --region us-central1 --image .../translation-service:v35-tr1

Rollback (manual):
  gcloud run services update translation-service --region us-central1 --image .../translation-service:v35

DRY-RUN: no build, no push, no deploy performed. Re-run with --apply to execute.
```

Rollback is to `:v35`, image only.

---

## 9. Files in this submission

- `translation-service/translation_service.py` — the fix (built from the v35/`73d8eb5` copy).
- `translation-service/Dockerfile.tr1` — overlay.
- `deploy_translation_tr1.sh` — staged deploy, dry-run default, `translation-service` only.
- `translation-service/tests_tr1/`
  - `docker-compose.test.yml` — Postgres + MinIO test stack.
  - `test_translation_tr1.py` — AC1–AC5 (green).
  - `run_tests_tr1.sh` — bring up stack, run pytest, tear down.
  - `prove_red_v35.py` + `prove_red.sh` — RED proof against v35.
  - `verify_overlay.sh` — (a) v35≡`73d8eb5`; (b) `/app` manifest diff = only `translation_service.py`.

Not committed / cleaned up: Cloud SQL Auth Proxy binary, access-token and db-password temp
files (deleted), one-off DB report/hide scripts (run then removed), pytest caches.

---

## 10. PROCESS compliance

- **Deployed nothing.** No `docker push`, no `gcloud run update`. Overlay built locally only.
- **Only production write:** the single `UPDATE … WHERE id IN (424,425,426)`. No DELETE, no
  INSERT, no DDL, no other row.
- Did not touch `storied`'s `translation_service.py`, the gateway, the app, or any other service.
- Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  `GCLOUD_STORIED_START_HERE.md`, `BUILD_NUMBERS.md`.
- Windows: all file I/O uses `encoding="utf-8"`; bash scripts run in Git Bash; proxy binary and
  secret/token files cleaned up; DB password never printed.

## 11. Blocking questions
None. The `track` column was present in the cloud DB (all 5 orphans carry `track='beta'`), and the
guarded INSERT also works if it is absent.
