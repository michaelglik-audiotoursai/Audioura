##### READY FOR REVIEW

## LOCAL-147 — Newsletter Processor: Fail-Closed Credential Gate (Round 2)

### Commit

```
3469e2f LOCAL-147: fail-closed gate on credential endpoints (D14)
bc0f395 LOCAL-147: restore newsletter processor service (no build)
```

### Per-File Changes

| File | Lines | What |
|------|-------|------|
| `newsletter_processor_service.py` | +17 | Add `CREDENTIAL_ENDPOINTS_ENABLED` env-var gate; guard `/key_exchange` and `/submit_credentials` with 503 refusal |
| `docker-compose-master.yml` | +3 | Security comment documenting that credential endpoints are disabled by default |

### What Was Done

Round 1 restored the newsletter processor service to `docker-compose-master.yml`
using the LOCAL-145 pattern (reuse `audioura-tour-generator:latest` image, no build).

Round 2 adds a fail-closed gate (D14) on the two credential endpoints that were
found to store passwords in plaintext (`decrypted_username`, `decrypted_password`
columns, no KMS encryption active). The gate:

- Reads `CREDENTIAL_ENCRYPTION_ENABLED` env var at startup
- Defaults to **disabled** (empty string ≠ `"true"`)
- Returns HTTP 503 with explicit message when disabled
- Does NOT affect `/health`, `/newsletters_v2`, `/process_newsletter`, or any
  other newsletter processing endpoint
- The compose entry does NOT set this env var → endpoints are gated by default
  even if someone runs `docker compose up -d`

### Verbatim Evidence

**Health (service starts and serves with flag off):**
```
$ curl -s http://localhost:5017/health
{"service":"newsletter_processor","status":"healthy"}
```

**Credential endpoints refuse (503, not 400/404):**
```
$ curl -s -w "\nHTTP %{http_code}\n" -X POST http://localhost:5017/key_exchange -H "Content-Type: application/json" -d '{}'
{"message":"Credential endpoints are disabled. At-rest encryption is not configured.","status":"error"}
HTTP 503

$ curl -s -w "\nHTTP %{http_code}\n" -X POST http://localhost:5017/submit_credentials -H "Content-Type: application/json" -d '{}'
{"message":"Credential endpoints are disabled. At-rest encryption is not configured.","status":"error"}
HTTP 503
```

**Newsletter processing unaffected:**
```
$ curl -s -w "\nHTTP %{http_code}\n" http://localhost:5017/newsletters_v2
{"newsletters":[],"status":"success"}
HTTP 200
```

**Container stopped and removed after verification:**
```
$ docker stop newsletter-processor-1 && docker rm newsletter-processor-1
newsletter-processor-1
newsletter-processor-1

$ docker ps --format "{{.Names}}" | grep newsletter-processor
(no output — container is gone)
```

**Existing containers untouched (diff before/after: no changes):**
```
$ diff /tmp/containers_before.txt /tmp/containers_after.txt
(no output — identical)
```

### Row Counts

| Table | Before | After |
|-------|--------|-------|
| `audio_tours` | 106 | 106 |
| `stop_metrics` | 1011 | 1011 |
| `user_subscription_credentials` | 0 | 0 |

### Rollback

```bash
# Revert the code change (returns to round-1 state with no gate):
git revert 3469e2f --no-edit

# Or revert both commits entirely:
git revert 3469e2f bc0f395 --no-edit
```

The container is already stopped and removed. No runtime rollback needed.

### Limitations

1. **Runtime pip install**: The compose entry does `pip install beautifulsoup4`
   at every start, so the container needs PyPI to boot. This is the same
   fragility noted in LOCAL-145. The image already has the module's other
   dependencies but not beautifulsoup4.

2. **Encryption not implemented**: The gate blocks the endpoints but does not
   implement at-rest encryption. `credential_encryption.py` and
   `migrate_credentials_encrypt.py` exist but require a Google Cloud KMS
   keyring that may not be provisioned. That is Michael's decision.

3. **Container left stopped**: Per round-2 instructions, the service is not
   running. To start it: `docker compose -f docker-compose-master.yml up -d newsletter-processor`.
   Credential endpoints will remain gated unless `CREDENTIAL_ENCRYPTION_ENABLED=true`
   is added to the environment block.
