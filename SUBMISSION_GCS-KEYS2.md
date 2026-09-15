# SUBMISSION — GCS-KEYS2

**Agent:** Services Kiro
**Task:** Give the Storied generator (`tour-generator-storied`) its Gemini key.
**ClickUp:** `wdvrdaxxm9`
**Authorised by:** Michael, 2026-09-15 (secret created in Console; wire in + grant secretAccessor).
**Project:** `audiotours-migration`  **Region:** `us-central1`
**Base:** storied = `016ad35`. `git merge-base --is-ancestor 016ad35 HEAD` → exit 0 (verified).

The secret value was never accessed or printed. `gcloud secrets versions access`
was never run. Everything below is metadata / config only.

---

## Result summary

- ✅ Per-secret `roles/secretmanager.secretAccessor` grant added for the compute SA (additive).
- ✅ `GEMINI_API_KEY=GEMINI_API_KEY:latest` wired into **`tour-generator-storied` only**, via `--update-secrets`.
- ✅ New revision **`tour-generator-storied-00003-2gf`** is Ready and serving 100% traffic.
- ✅ `GET /health` returns **HTTP 200** (`status: healthy`).
- ✅ Storied env differs from before **only** by the added `GEMINI_API_KEY`; all other secrets/env preserved.
- ✅ Beta `tour-generator` **untouched**: revision `00023-nrv`, 5 env entries, no Gemini.

---

## 0. Preconditions (metadata only)

`gcloud secrets versions list GEMINI_API_KEY --format="value(name,state)"`

```
1	enabled
```

Before-state snapshots captured to `/tmp/gen_storied_before.json` and `/tmp/gen_beta_before.json`.

---

## 1. Per-secret accessor grant (STEP 1)

```
gcloud secrets add-iam-policy-binding GEMINI_API_KEY \
  --project audiotours-migration \
  --member="serviceAccount:60899077572-compute@developer.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor
```

Output:

```
Updated IAM policy for secret [GEMINI_API_KEY].
bindings:
- members:
  - serviceAccount:60899077572-compute@developer.gserviceaccount.com
  role: roles/secretmanager.secretAccessor
etag: BwZbjDXccfM=
version: 1
```

---

## 2. Wire into the Storied generator ONLY (STEP 2)

```
gcloud run services update tour-generator-storied \
  --region us-central1 --project audiotours-migration \
  --update-secrets GEMINI_API_KEY=GEMINI_API_KEY:latest
```

Output:

```
Deploying...
Creating Revision.....done
Routing traffic...done
Done.
Service [tour-generator-storied] revision [tour-generator-storied-00003-2gf] has been deployed and is serving 100 percent of traffic.
Service URL: https://tour-generator-storied-60899077572.us-central1.run.app
```

`--update-secrets` (not `--set-secrets`) was used so the existing secret list was preserved.

---

## 3. IAM policy after the grant

`gcloud secrets get-iam-policy GEMINI_API_KEY --format=json`

```json
{
  "bindings": [
    {
      "members": [
        "serviceAccount:60899077572-compute@developer.gserviceaccount.com"
      ],
      "role": "roles/secretmanager.secretAccessor"
    }
  ],
  "etag": "BwZbjDXccfM=",
  "version": 1
}
```

---

## 4. New revision Ready + health check

- Revision: `tour-generator-storied-00003-2gf`, `Ready: True`, 100% traffic.
- Health: `GET https://tour-generator-storied-ixkp5nkrlq-uc.a.run.app/health`
  with `gcloud auth print-identity-token`.

```
HTTP_STATUS=200
{"build_time":"no_manifest","code_sha":"no_manifest",
 "cost_ceiling":{"hard_limit_aborts":0,"last_abort_cost":null,"last_abort_job_id":null,"target_warnings":0},
 "drift_files":["<manifest_missing>"],"manifest_ok":false,"mode":"true",
 "service":"tour_text_generator","status":"healthy","version":"2.2.0.1"}
```

---

## 5. Before / after — `tour-generator-storied`

**BEFORE — revision `tour-generator-storied-00002-xql`**
image: `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v1`

```
STORIED_MODE = true
TOUR_STORAGE_MODE = cloud
PYTHONUNBUFFERED = 1
TOUR_TRACK = storied
DB_HOST = /cloudsql/audiotours-migration:us-central1:audioura-db
DB_NAME = audiotours
DB_USER = admin
DB_PORT = 5432
DATABASE_URL = postgresql://admin@/audiotours?host=/cloudsql/audiotours-migration:us-central1:audioura-db
VENUE_CACHE_DB_URL = postgresql://admin@/audiotours?host=/cloudsql/audiotours-migration:us-central1:audioura-db
OPENAI_API_KEY -> secret:openai-api-key:latest
DB_PASSWORD -> secret:db-password:latest
PGPASSWORD -> secret:db-password:latest
SERP_PROVIDER = serper
SERP_API_KEY -> secret:serp-api-key:latest
```

**AFTER — revision `tour-generator-storied-00003-2gf` (Ready: True)**
image: `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v1` (unchanged)

```
STORIED_MODE = true
TOUR_STORAGE_MODE = cloud
PYTHONUNBUFFERED = 1
TOUR_TRACK = storied
DB_HOST = /cloudsql/audiotours-migration:us-central1:audioura-db
DB_NAME = audiotours
DB_USER = admin
DB_PORT = 5432
DATABASE_URL = postgresql://admin@/audiotours?host=/cloudsql/audiotours-migration:us-central1:audioura-db
VENUE_CACHE_DB_URL = postgresql://admin@/audiotours?host=/cloudsql/audiotours-migration:us-central1:audioura-db
OPENAI_API_KEY -> secret:openai-api-key:latest
DB_PASSWORD -> secret:db-password:latest
PGPASSWORD -> secret:db-password:latest
SERP_PROVIDER = serper
SERP_API_KEY -> secret:serp-api-key:latest
GEMINI_API_KEY -> secret:GEMINI_API_KEY:latest      <-- ONLY change
```

**Diff:** exactly one addition — `GEMINI_API_KEY -> GEMINI_API_KEY:latest` — plus the new revision.
`OPENAI_API_KEY`, `DB_PASSWORD`, `PGPASSWORD`, `SERP_API_KEY`, `SERP_PROVIDER`,
`TOUR_TRACK=storied`, `STORIED_MODE=true` all still present. Image unchanged.

---

## 6. Before / after — Beta `tour-generator` (control, must be unchanged)

**BEFORE — revision `tour-generator-00023-nrv`**
image: `us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v36-local474`

```
TOUR_STORAGE_MODE = cloud
OPENAI_API_KEY -> secret:openai-api-key:latest
PYTHONUNBUFFERED = 1
KEY_FIX = v3
OAIFIX = done
```

**AFTER — revision `tour-generator-00023-nrv` (Ready: True)** — identical

```
TOUR_STORAGE_MODE = cloud
OPENAI_API_KEY -> secret:openai-api-key:latest
PYTHONUNBUFFERED = 1
KEY_FIX = v3
OAIFIX = done
```

**Diff:** none. Same revision `00023-nrv`, same image, 5 env entries, no Gemini. Control intact.

---

## Compliance with rules

- Never accessed/printed the secret value; never ran `gcloud secrets versions access`.
- Used `--update-secrets` (never `--set-secrets`).
- Only `tour-generator-storied` was modified; `tour-modernized-storied`,
  `tour-orchestrator-storied`, and Beta `tour-generator` were not touched.
- No tour generation, no SQL, no other secret, no other service.
- Branch created from HEAD (`016ad35`); base ancestry verified (exit 0).
