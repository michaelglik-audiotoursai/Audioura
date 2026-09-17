# SUBMISSION — GCS-HIDE2

**Task:** Hide the two older translation orphans (ids 368 and 378) via one reversible DB write
(set `lat` and `lng` to NULL). No deploy; no Cloud Run change.

**ClickUp:** `wdvrdaydr1`
**Agent:** Services Kiro
**Authorised by:** Michael, 2026-09-17 ~11:05 — "I am okay to lose them" (hide orphans 368 and 378).
**Executed:** 2026-09-17, ET.

---

## Base / branch verification

- `git rev-parse HEAD` → `912cdd1cfa5083d3932a502f699b7950612901c8` (== main = 912cdd1).
- `git merge-base --is-ancestor 912cdd1 HEAD` → exit 0 (correct base).
- Branch created from HEAD: `gcs-hide2`. Not branched from origin.

## Connection method

Cloud SQL Auth Proxy v2.14.1 (Windows, x64) to
`audiotours-migration:us-central1:audioura-db`, listening on `127.0.0.1:5432`.
Proxy authorised with an OAuth2 access token from `gcloud auth print-access-token`
(user `michael.glik@gmail.com`; ADC was not present).
DB `audiotours`, user `admin`. Password read from Secret Manager secret `db-password`
into an environment variable at run time and **never printed**. Client: Python `psycopg2`.
Same access path as GCS-TR1 used for 424–426.

---

## Step 1 — count before

```sql
SELECT count(*) FROM audio_tours;
```
Result: **337**

## Step 2 — precondition + backup

```sql
SELECT id, original_tour_id, content_language, lat, lng,
       audio_tour IS NULL AS no_bytea, tour_blob_uri
FROM audio_tours WHERE id IN (368,378) ORDER BY id;
```

Result (2 rows — both exist, both `audio_tour` NULL and `tour_blob_uri` NULL):

| id  | original_tour_id | content_language | lat      | lng       | no_bytea | tour_blob_uri |
|-----|------------------|------------------|----------|-----------|----------|---------------|
| 368 | 144              | de               | 10.7731  | 106.6983  | true     | NULL          |
| 378 | 207              | zh               | 43.6957  | 7.2694    | true     | NULL          |

Matches expected exactly (368 = 10.7731 / 106.6983, de, from 144; 378 = 43.6957 / 7.2694, zh, from 207).

**BACKUP (for reversal):**
- id 368 → lat = `10.7731`, lng = `106.6983`
- id 378 → lat = `43.6957`, lng = `7.2694`

To reverse:
```sql
UPDATE audio_tours SET lat = 10.7731, lng = 106.6983 WHERE id = 368;
UPDATE audio_tours SET lat = 43.6957, lng = 7.2694   WHERE id = 378;
```

## Step 3 — the single production write

```sql
UPDATE audio_tours SET lat = NULL, lng = NULL
WHERE id IN (368,378) AND audio_tour IS NULL AND tour_blob_uri IS NULL;
```
Run inside an explicit transaction; committed only because rows affected == 2.

**Rows affected: 2** → COMMITTED.

## Step 4 — re-select + re-count (verification)

```sql
SELECT id, original_tour_id, content_language, lat, lng,
       audio_tour IS NULL AS no_bytea, tour_blob_uri
FROM audio_tours WHERE id IN (368,378) ORDER BY id;
SELECT count(*) FROM audio_tours;
```

Result:

| id  | original_tour_id | content_language | lat  | lng  | no_bytea | tour_blob_uri |
|-----|------------------|------------------|------|------|----------|---------------|
| 368 | 144              | de               | NULL | NULL | true     | NULL          |
| 378 | 207              | zh               | NULL | NULL | true     | NULL          |

count after: **337** (unchanged).

---

## Rules compliance

1. Only one production write executed: the single guarded `UPDATE` above. No DELETE, INSERT,
   DDL, no other row, no other table.
2. No Cloud Run service state read, compared, or changed. No deploy.
3. Cleanup: proxy binary, proxy logs, pid file, and all query scripts were deleted after the
   run and are not committed. Password never written to disk or printed. `git status` clean
   apart from this submission file.
4. Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, .continuous_dev/STATUS.md,
   GCLOUD_STORIED_START_HERE.md, or BUILD_NUMBERS.md.
5. No blocking questions — task completed as specified.

## Outcome

Both orphans 368 and 378 are hidden (lat/lng nulled). Row count unchanged (337 → 337).
Change is fully reversible using the backup lat/lng values recorded above.
