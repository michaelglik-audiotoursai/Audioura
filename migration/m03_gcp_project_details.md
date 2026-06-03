# M03 — GCP Project Details

**Date:** 2026-06-02  
**Status:** Project created, APIs enabled, ready for Phase C/D/E work

---

## GCP Project

| Field | Value |
|---|---|
| **Project ID** | `audiotours-migration` |
| **Billing** | Enabled |
| **Service Account** | `60899077572-compute@developer.gserviceaccount.com` |
| **Region** | us-central1 (planned) |

## APIs Enabled

- Cloud Run (`run.googleapis.com`)
- Cloud SQL (`sqladmin.googleapis.com`)
- Cloud Build (`cloudbuild.googleapis.com`)
- Secret Manager (`secretmanager.googleapis.com`)

## What's Next

| Phase | Task | Prereq |
|---|---|---|
| C | Provision Cloud SQL (db-f1-micro), Artifact Registry, Secret Manager entries | ✅ Ready |
| D | Migrate blobs to R2 (need R2 creds in .env) | R2 bucket ready, creds needed in .env |
| E | Deploy services to Cloud Run | C + D complete |

## Note on Project Structure

The migration doc (`AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md`) originally proposed two projects (`audioura-preprod` + `audioura-prod`). We have one project (`audiotours-migration`). For now this serves as the preprod/development cloud environment. A separate prod project can be created later for the actual production cutover (Phase E).
