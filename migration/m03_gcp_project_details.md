# M03 — GCP Project Details

**Date:** 2026-06-02  
**Status:** ✅ COMPLETE — All infrastructure provisioned

---

## GCP Project

| Field | Value |
|---|---|
| **Project ID** | `audiotours-migration` |
| **Billing** | Enabled |
| **Service Account** | `60899077572-compute@developer.gserviceaccount.com` |
| **Region** | us-central1 |
| **Authenticated as** | michael.glik@gmail.com |

## APIs Enabled

- Cloud Run (`run.googleapis.com`)
- Cloud SQL (`sqladmin.googleapis.com`)
- Cloud Build (`cloudbuild.googleapis.com`)
- Secret Manager (`secretmanager.googleapis.com`)
- Artifact Registry (`artifactregistry.googleapis.com`)

## Infrastructure Provisioned

### Artifact Registry
| Field | Value |
|---|---|
| Repository | `services` |
| Format | Docker |
| Location | us-central1 |
| Image path | `us-central1-docker.pkg.dev/audiotours-migration/services/<image>` |

### Cloud SQL (PostgreSQL 15)
| Field | Value |
|---|---|
| Instance name | `audioura-db` |
| Tier | db-f1-micro (~$10/month) |
| Region | us-central1 |
| Public IP | `34.27.121.203` |
| Connection name | `audiotours-migration:us-central1:audioura-db` |
| Database | `audiotours` |
| User | `admin` |
| Password | (in Secret Manager: `db-password`) |
| Storage | 10 GB SSD |
| ⚠️ NOTE | `authorized-networks=0.0.0.0/0` is TEMPORARY for setup. Lock down before production. |

### Secret Manager (6 secrets)
| Secret Name | Content | Status |
|---|---|---|
| `db-password` | Cloud SQL admin password | ✅ Real value |
| `openai-api-key` | OpenAI API key | ⚠️ Placeholder — set real value before deploy |
| `aws-access-key-id` | AWS Polly access key | ⚠️ Placeholder — set real value before deploy |
| `aws-secret-access-key` | AWS Polly secret | ⚠️ Placeholder — set real value before deploy |
| `r2-access-key-id` | Cloudflare R2 access key | ⚠️ Placeholder — set real value before deploy |
| `r2-secret-access-key` | Cloudflare R2 secret | ⚠️ Placeholder — set real value before deploy |

## Before Phase E Deployment

1. Update Secret Manager with real API keys (OpenAI, AWS, R2)
2. Lock down Cloud SQL authorized networks (remove 0.0.0.0/0, allow only Cloud Run)
3. Apply database schema (pg_dump from local → Cloud SQL)
4. Configure Cloud Run services with Secret Manager bindings

## Cost Started

- Cloud SQL db-f1-micro: ~$10/month (billing active from creation)
- Everything else: $0 until services deployed with traffic
