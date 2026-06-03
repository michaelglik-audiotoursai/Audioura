# Claude.AI Code Review — Phase C + D Complete

**Date:** 2026-06-02  
**Branch:** `services-migration`  
**Commits:** `b79cd41` through `a8ea378`  
**Scope:** GCP infrastructure provisioning (Phase C) + blob migration to Cloudflare R2 (Phase D)

---

## Phase C — GCP Infrastructure Provisioned

### What was done:

1. **Artifact Registry** created: `us-central1-docker.pkg.dev/audiotours-migration/services/` (Docker format)
2. **Cloud SQL** provisioned: PostgreSQL 15, `db-f1-micro`, instance name `audioura-db`, public IP `34.27.121.203`
3. **Database + user** created: `audiotours` database, `admin` user
4. **Secret Manager** entries created (6 secrets): `db-password`, `openai-api-key`, `aws-access-key-id`, `aws-secret-access-key`, `r2-access-key-id`, `r2-secret-access-key`
5. **Instance stopped** to save costs until Phase E deployment

### Decisions made:

- Single GCP project (`audiotours-migration`) serves as preprod for now; separate prod project later
- `db-f1-micro` tier ($10/month) — viable because blobs moved to R2 (DB will be ~40 MB)
- Public IP with `authorized-networks=0.0.0.0/0` is **temporary** for setup — must be locked down before production
- Secret Manager has placeholders for API keys — real values to be set before Phase E deploy

### Cost:

- Cloud SQL: **$0/month while stopped** (currently NEVER activation policy)
- Everything else: $0 until traffic

---

## Phase D — Blob Migration to R2

### What was done:

Migrated all binary tour/news ZIPs from PostgreSQL BYTEA columns to Cloudflare R2 object storage.

| Table | Column | Objects Migrated | Failures | Total Size (approx) |
|---|---|---|---|---|
| `audio_tours` | `audio_tour` | 193 | 0 | ~900 MB |
| `news_audios` | `news_article` | 751 | 0 | ~1,700 MB |
| **Total** | | **944** | **0** | **~2.6 GB** |

### R2 Object Key Structure:

```
v1-audiotours-r2-bucket/
├── tours/
│   ├── 82.zip
│   ├── 83.zip
│   ├── ...
│   └── 351.zip
└── news/
    ├── 01122f04-1bcb-42af-8bf0-6f4d62be488b.zip
    ├── ...
    └── fff0b5c7-920f-41f1-b6c3-f4b0f08b8b3e.zip
```

### Safety Net:

BYTEA data is **preserved** in the database (not NULLed). The `tour_blob_uri` and `news_blob_uri` columns are populated with the R2 keys. This allows:
- Rollback: if R2 delivery fails, services fall back to BYTEA
- Verification: compare R2 content against DB content
- Cleanup: once R2 delivery is verified in production, run `--clear` to NULL BYTEAs and reclaim ~2.6 GB

### Code Changes:

**`blobstorage.py` fix:** R2 endpoint URL parsing now strips bucket-path suffix. The `.env` had the endpoint as `https://<account_id>.r2.cloudflarestorage.com/v1-audiotours-r2-bucket` (with bucket appended), but boto3 needs just the base URL. The `R2BlobStorage.__init__` now uses `urlparse` to extract only `scheme://netloc`.

**`migration/migrate_blobs_to_r2.py`:** Migration script that:
- Reads BYTEA from local PostgreSQL
- Uploads to R2 under `tours/{id}.zip` or `news/{article_id}.zip`
- Sets `tour_blob_uri` / `news_blob_uri` in the database
- Skips rows that already have a URI set (idempotent, safe to re-run)
- Has `--clear` flag to NULL BYTEAs after verification
- Has `--tours-only` / `--news-only` flags for partial runs

---

## Questions for Review

1. **Cloud SQL authorized networks:** Currently `0.0.0.0/0` (world-open) for initial setup convenience. Before Phase E, this must be restricted to Cloud Run's egress IPs or switched to private IP with VPC connector. Is there a preference for which approach?

2. **R2 key naming:** Tours use numeric IDs (`tours/82.zip`), news uses UUIDs (`news/01122f04-...zip`). Should we normalize to one pattern? The current scheme matches the primary keys in each table.

3. **Dual-read strategy for map_delivery:** When `BLOB_STORAGE_TYPE=r2`, `map_delivery_service.py` should read from R2 (using `tour_blob_uri`). When `tour_blob_uri` is NULL (shouldn't happen now, but for new tours generated during transition), fall back to BYTEA. Is this the right strategy, or should new tours always write to both R2 + BYTEA until we're confident?

4. **When to NULL the BYTEAs:** The migration doc suggests waiting until "R2 delivery is verified for ~1 week in production." Given that we haven't deployed the R2-reading code to `map_delivery` yet (that's Phase E), should we:
   - (a) Deploy R2-reading code first, verify for a few days, then clear BYTEAs
   - (b) Clear BYTEAs now (since we can always re-upload from R2 back to DB if needed)
   - (c) Keep both indefinitely until db-f1-micro storage fills up

5. **The migration script runs against localhost:5433** (the local Docker Postgres). For Phase E, the Cloud SQL instance needs the same schema + data. The plan is `pg_dump` from local → `pg_restore` to Cloud SQL. But now `audio_tours` has both BYTEA + `tour_blob_uri` — should the pg_dump exclude the BYTEA columns (since R2 has the data) to keep the dump small (~40 MB vs ~2.7 GB)?

---

## Phase Status Summary

| Phase | Status | Key Artifact |
|---|---|---|
| A (Audit) | ✅ | `migration/m01_audit_results.md` |
| B (Cloud-Ready) | ✅ Claude signed off | All services env-var-driven, HTTP content passing, job_store, health endpoints |
| C (GCP Setup) | ✅ | `migration/m03_gcp_project_details.md` |
| D (Blob Migration) | ✅ | `migration/migrate_blobs_to_r2.py` — 944 objects, 0 failures |
| E (Deploy) | Ready to start | Build images → push → deploy to Cloud Run → DNS |
