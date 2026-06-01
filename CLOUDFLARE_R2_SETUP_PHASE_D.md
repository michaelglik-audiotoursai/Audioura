# Cloudflare R2 Object Storage Setup — Phase D Data Migration

**Created:** May 29, 2026  
**Status:** R2 bucket provisioned; credentials generated; ready for Kiro implementation  
**Migration Phase:** D (Data migration: DB blobs → Cloudflare R2)  
**Context:** See `AUDIOURA_SERVICES_MAP_POI_HISTORY.md` §3 (BlobStorage abstraction) and §4 (Phase D plan)

---

## 1. R2 Bucket Details (Public — safe for GitHub)

| Field | Value |
|---|---|
| **Bucket Name** | `v1-audiotours-r2-bucket` |
| **Account ID** | `4b4aa47cda0cc65f20b20ac0b363ac7` |
| **S3 Endpoint** | `https://4b4aa47cda0cc65f20b20ac0b363ac7.r2.cloudflarestorage.com/v1-audiotours` |
| **Region** | Eastern North America (ENAM) |
| **Storage Class** | Standard |
| **Public Access** | Disabled (bucket is private) |
| **Created** | May 29, 2026 |

---

## 2. Authentication Credentials (References Only — NO actual secrets here)

R2 API credentials have been generated and stored **outside** this repository.

### Credential References

```python
# These values must be injected at runtime, not committed to Git

R2_ACCESS_KEY_ID = os.getenv('R2_ACCESS_KEY_ID')
# Example format: ad2cc36d85c739a97e9b8e5da3cf8613
# Stored in: .env (local dev) or Google Cloud Secret Manager (production)

R2_SECRET_ACCESS_KEY = os.getenv('R2_SECRET_ACCESS_KEY')
# Example format: 50c4b79ffbf048b016227daad2968865276b3e0815ad2790d7d265677d4e48a
# Stored in: .env (local dev) or Google Cloud Secret Manager (production)

R2_ENDPOINT = 'https://4b4aa47cda0cc65f20b20ac0b363ac7.r2.cloudflarestorage.com'
R2_BUCKET = 'v1-audiotours-r2-bucket'
```

### Storage Locations for Real Values

#### Local Development (`.env` file)
```bash
# .env (add to .gitignore)
R2_ACCESS_KEY_ID=<actual_access_key_from_cloudflare>
R2_SECRET_ACCESS_KEY=<actual_secret_key_from_cloudflare>
R2_ENDPOINT=https://4b4aa47cda0cc65f20b20ac0b363ac7.r2.cloudflarestorage.com
R2_BUCKET=v1-audiotours-r2-bucket
```

#### Production (Google Cloud Secret Manager)
```bash
# Create secrets in GCP
gcloud secrets create r2-access-key --data="<actual_access_key>"
gcloud secrets create r2-secret-key --data="<actual_secret_key>"

# Cloud Run service retrieves via Secret Manager:
# Services bind to these secrets as env vars at deploy time
```

---

## 3. BlobStorage Abstraction Layer (Phase B → Phase D handoff)

From `AUDIOURA_SERVICES_MAP_POI_HISTORY.md` §2:

> **2.7 GB of ZIP files in PostgreSQL BYTEA.** Expensive backups, slow restores. Solution: abstraction layer in Phase B (with `BlobStorage` interface, MinIO-backed local test); flip to R2 in Phase D.

### Implementation Pattern

```python
# blobstorage.py (abstraction interface)

class BlobStorage:
    """Abstract interface for tour ZIP storage."""
    
    async def upload(self, tour_id: str, zip_bytes: bytes) -> str:
        """Upload ZIP; return object URI."""
        pass
    
    async def download(self, tour_id: str) -> bytes:
        """Download ZIP by tour ID."""
        pass
    
    async def delete(self, tour_id: str) -> None:
        """Delete ZIP by tour ID."""
        pass


# r2_storage.py (R2 implementation)

class R2BlobStorage(BlobStorage):
    """S3-compatible R2 backend."""
    
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str):
        self.s3_client = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name='auto'
        )
        self.bucket = bucket
    
    async def upload(self, tour_id: str, zip_bytes: bytes) -> str:
        key = f"tours/{tour_id}.zip"
        self.s3_client.put_object(Bucket=self.bucket, Key=key, Body=zip_bytes)
        return f"{self.bucket}/{key}"
```

---

## 4. Services Affected (Phase D Implementation)

Per `AUDIOURA_SERVICES_MAP_POI_HISTORY.md` §6 (Service topology):

| Service | Current Behavior | Phase D Change |
|---|---|---|
| `tour-orchestrator` | Stores final ZIP in DB BYTEA | Upload ZIP to R2; store URI in `audio_tours.tour_blob_uri` |
| `map-delivery` | Reads ZIP from DB BYTEA | Read ZIP from R2 via S3 API |
| `tour-generation-modernized` | Writes ZIP to `/app/tours/` (shared volume) | Stream ZIP to R2 directly (or return to orchestrator for upload) |
| `tour-editing-phase2` | Reads/writes in `/app/tours/` + DB | Migrate to HTTP-based content passing + R2 for final ZIP |

---

## 5. Migration Smoke Tests (Phase D verification)

Before declaring Phase D done, verify:

1. **Upload tour ZIP to R2.** Generate a tour; confirm final ZIP appears in R2 bucket (not in DB BYTEA).
2. **Download from R2 via map-delivery.** Request a tour ZIP via the `/tour/<id>` endpoint; confirm it's served from R2.
3. **Multi-region resilience.** Test from different regions (if applicable); confirm no latency issues.
4. **Cleanup old DB blobs.** Once all new tours use R2, migrate existing BYTEAs to R2 (separate script).

---

## 6. Kiro Implementation Checklist

- [ ] **Phase B refactor (prerequisite):** BlobStorage abstraction layer with MinIO local test
- [ ] **Phase D implementation:**
  - [ ] Update `tour_editing_phase2.py` to use R2BlobStorage
  - [ ] Update `map-delivery` to serve from R2
  - [ ] Add `tour_blob_uri` column to `audio_tours` table
  - [ ] Inject R2 credentials via environment variables (Cloud Run Secret Manager in production)
  - [ ] Update docker-compose.yml to inject .env on local dev
- [ ] **Data migration script:** Backfill existing tour ZIPs from DB BYTEA to R2
- [ ] **Smoke tests:** Run verification checklist (§5)

---

## 7. Secrets Management Summary

| Secret | Local Storage | Production Storage | Injected As |
|---|---|---|---|
| `R2_ACCESS_KEY_ID` | `.env` | GCP Secret Manager | `os.getenv('R2_ACCESS_KEY_ID')` |
| `R2_SECRET_ACCESS_KEY` | `.env` | GCP Secret Manager | `os.getenv('R2_SECRET_ACCESS_KEY')` |

**GitHub rule:** `.env` is in `.gitignore`; production secrets never committed.

---

## 8. Document Trail

- **Phase B design:** `migration/m02_phase_b_design_for_claude_review.md`
- **Phase B Claude review:** `migration/claude_response_m02_phase_b_design.md`
- **Phase D plan (this file):** `CLOUDFLARE_R2_SETUP_PHASE_D.md`
- **Overall migration plan:** `AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md`

---

**Status:** Ready for Kiro + Amazon Q implementation. No secrets in this file; all credentials external.
