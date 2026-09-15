# SUBMISSION — GCS-KEYS1

Give the Storied generator its SERP key.

- **Agent:** Services Kiro
- **Base:** storied (`4976943`)
- **Branch:** `gcs-keys1-serp` (created from HEAD)
- **ClickUp:** `wdvrdaxxm9`
- **Authorised by:** Michael, 2026-09-15 16:43 — "Approved: push storied, and add the SERP and Gemini keys"
- **Project:** `audiotours-migration` / region `us-central1`
- **Result:** COMPLETE. No secret value appears anywhere in this file.

---

## Base verification

```
git rev-parse HEAD             -> 49769431c4c25a7170818ecd25c035a639e57248
git merge-base --is-ancestor 4976943 HEAD  -> exit 0 (BASE_OK)
```

HEAD is `4976943`; the required base is an ancestor of HEAD.

---

## Step-by-step command outputs (lengths only, never the value)

### 1. Read `SERP_API_KEY` from `.env` (value never printed)
File: `C:\Users\micha\eclipse-workspace\AudioTours\development\.env` (CRLF; CR stripped, quotes/whitespace trimmed).

```
length=40
```
40 chars — matches the expected key length. Not a placeholder.

### 2. Pre-existence check
`gcloud secrets describe serp-api-key` returned non-zero (secret did not exist), so creation proceeded. The secret was **not** pre-existing; no version was added to an existing secret.

### 3. Create secret from stdin, no trailing newline
```
Created version [1] of the secret [serp-api-key].
```
Command: `printf '%s' "$SERP_VAL" | gcloud secrets create serp-api-key --project audiotours-migration --replication-policy=automatic --data-file=-`
`unset SERP_VAL` was run immediately after.

### 4. Byte-length verification of stored value (value never printed)
```
accessed_bytes=40
```
Stored secret is exactly 40 bytes — confirms no trailing newline.

### 5. Wire into the Storied generator ONLY (`--update-*` only)
```
gcloud run services update tour-generator-storied --region us-central1 --project audiotours-migration \
  --update-secrets SERP_API_KEY=serp-api-key:latest \
  --update-env-vars SERP_PROVIDER=serper
```
Output:
```
Service [tour-generator-storied] revision [tour-generator-storied-00002-xql]
has been deployed and is serving 100 percent of traffic.
Service URL: https://tour-generator-storied-60899077572.us-central1.run.app
```

---

## Secret

| Field | Value |
|---|---|
| Secret name | `serp-api-key` |
| Version | `1` |
| Replication policy | automatic |
| Stored byte length | 40 |
| Project-level access | compute SA `60899077572-compute@developer.gserviceaccount.com` already holds `roles/secretmanager.secretAccessor` at project level — no per-secret grant needed |

---

## New Storied revision

- **New revision:** `tour-generator-storied-00002-xql`
- **Ready:** `Ready = True`
- **Serving:** 100% of traffic

---

## Before / After — `tour-generator-storied` (Storied — receives the key)

| | Before | After |
|---|---|---|
| Revision | `tour-generator-storied-00001-6kn` | `tour-generator-storied-00002-xql` |
| Image | `.../services/audioura-storied:v1` | `.../services/audioura-storied:v1` (unchanged) |
| Env — plain | STORIED_MODE=true; TOUR_STORAGE_MODE=cloud; PYTHONUNBUFFERED=1; TOUR_TRACK=storied; DB_HOST=/cloudsql/audiotours-migration:us-central1:audioura-db; DB_NAME=audiotours; DB_USER=admin; DB_PORT=5432; DATABASE_URL=postgresql://admin@/audiotours?host=/cloudsql/...:audioura-db; VENUE_CACHE_DB_URL=postgresql://admin@/audiotours?host=/cloudsql/...:audioura-db | **same, plus** SERP_PROVIDER=serper |
| Env — secret refs | OPENAI_API_KEY→openai-api-key:latest; DB_PASSWORD→db-password:latest; PGPASSWORD→db-password:latest | **same, plus** SERP_API_KEY→serp-api-key:latest |

**Diff:** exactly `SERP_PROVIDER=serper` (env) + `SERP_API_KEY` as secret ref `serp-api-key:latest`, plus the new revision. Nothing else changed.

---

## Before / After — `tour-generator` (Beta — CONTROL, must be untouched)

| | Before | After |
|---|---|---|
| Revision | `tour-generator-00023-nrv` | `tour-generator-00023-nrv` (unchanged) |
| Image | `.../services/audioura:v36-local474` | `.../services/audioura:v36-local474` (unchanged) |
| Env — plain | TOUR_STORAGE_MODE=cloud; PYTHONUNBUFFERED=1; KEY_FIX=v3; OAIFIX=done | identical |
| Env — secret refs | OPENAI_API_KEY→openai-api-key:latest | identical |

**Diff:** none. Beta control was not touched — no SERP key, no new revision.

---

## Startup-log SERP scan (redacted to key names only)

Scanned logs for the new revision `tour-generator-storied-00002-xql` (textPayload and jsonPayload.message, case-insensitive `serp`):

```
(no SERP lines found)
```

No SERP-related log lines at startup. `work_story_searcher` only emits SERP activity when a web-story search runs (not at boot), so there is nothing to report/redact from startup. No tour generation was performed.

---

## Rules compliance
1. Ran straight through with no failures; no retries or workarounds needed.
2. Secret value never printed, logged, echoed, committed, or written to any file; lengths only. `unset SERP_VAL` was executed.
3. Before/after recorded for both generator services (above).
4. New Storied revision confirmed `Ready = True`; startup logs scanned for SERP (none found).
5. No tour generation, no SQL. Only `serp-api-key` and `tour-generator-storied` were touched.
6. None of the protected docs were edited.
7. No blocking questions.

## Files changed on this branch
- `SUBMISSION_GCS-KEYS1.md` (this file). Temporary helper scripts used during execution were deleted and are not committed.
