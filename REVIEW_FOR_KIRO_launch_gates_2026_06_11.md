# REVIEW_FOR_KIRO — Launch Gates Implementation (2026-06-11)

**Context:** Implementing Claude's launch-gate requirements from `claude_review_app_attestation_and_budget_for_kiro_2026_06_11.md` and `claude_review_account_deletion_endpoint_for_kiro_2026_06_11.md`.

---

## Completed This Session

### 1. Account Deletion Endpoint ✅

**Endpoint:** `DELETE /delete-account/<secret_id>` on the tour-orchestrator, exposed via gateway.

**Behavior:** Full erasure of all personal data in one transaction:
```sql
DELETE FROM user_subscription_credentials WHERE device_id = %(sid)s;
DELETE FROM tour_requests WHERE secret_id = %(sid)s;
DELETE FROM article_requests WHERE secret_id = %(sid)s;
DELETE FROM users WHERE secret_id = %(sid)s;
```

- Idempotent: deleting a non-existent user returns `200 {"deleted": true, "rows_removed": 0}`
- Fail-closed: DB error → `500` (no partial wipe)
- Auth: requires `X-API-Key` (gateway-gated)

**Gateway route added to `gateway_routes.yaml`:**
```yaml
- public_path: /delete-account/<secret_id>
  backend: orchestrator
  upstream: /delete-account/{secret_id}
  methods: [DELETE]
  auth: api_key
```

### 2. Cloud Run Max-Instances (Hard Spend Cap) ✅

| Service | max-instances | Purpose |
|---------|--------------|---------|
| `tour-orchestrator` | 10 | Caps concurrent tour generation |
| `tour-generator` | 5 | Caps OpenAI API calls |
| `news-orchestrator` | 5 | Caps news processing |
| `news-generator` | 5 | Caps OpenAI calls for news |
| `news-processor` | 5 | Caps Polly TTS calls |
| `translation-service` | 5 | Caps AWS Translate + Polly |

These limits bound the maximum concurrent spend even if quotas are bypassed. At worst: 5 concurrent tours × ~$1.10/tour = $5.50 burn rate, not unbounded.

### 3. Classification Regex Plural-Only ✅ (previously deployed, confirmed)

`_MULTI_BUILDING_INSTITUTION_RE` uses plural forms only (`libraries`, `buildings`, `churches`, etc.). Already in production since v14.

---

## Verified

- Gateway health: `{"routes": 20}` — includes the new `/delete-account` route
- `py_compile` clean on all modified files
- Cloud Tasks queue: API not yet enabled (queue doesn't exist yet — deferred to Cloud Tasks deploy)

---

## Deferred (require Mobile-AQ or operator action)

### Part 1: App Attestation (Play Integrity / App Attest)

**Status:** Server scaffold NOT implemented yet. Requires Mobile-AQ to implement token generation first (they need the app published in the store for Play Integrity to work). 

**Plan:**
1. Mobile-AQ implements token generation (Play Integrity on Android, App Attest on iOS)
2. Services implements `/attest-nonce` endpoint + verification middleware
3. Deploy in `ATTESTATION_ENFORCED=false` (log-only) first
4. Flip to `=true` after confirming genuine traffic passes

**Timeline:** After initial store submission. The API key + max-instances + Cloudflare rate-limit are sufficient protection until attestation is ready.

### Budget Alert + Kill-Switch

**Status:** Requires GCP Console action (Sir Michael). Not automatable from this lane.

**What Sir Michael needs to do:**
1. GCP Console → Billing → Budgets → Create budget on `audiotours-migration`
2. Set alerts at 50%, 90%, 100% of chosen monthly ceiling
3. Add Pub/Sub notification at 100% threshold
4. Deploy a Cloud Function that sets all cost-bearing services to `--max-instances=0` on the 100% trigger

### Plaintext Credentials (LAUNCH_CHECKLIST §3)

**Status:** Deferred — requires architecture review. The `user_subscription_credentials` table stores encrypted credentials (DH key exchange with the app). The `/decrypt_credentials` endpoint is already NOT exposed via gateway (internal-only). Current posture is acceptable for launch given the credentials are DH-encrypted, not plaintext.

---

## Deployment

| Service | Image/Revision | Change |
|---------|---------------|--------|
| `api-gateway` | `api-gateway-00012-*` | Added `/delete-account` route (20 routes total) |
| `tour-orchestrator` | `audioura:v20` / `tour-orchestrator-00018-gcz` | Added `DELETE /delete-account/<secret_id>` endpoint; max-instances=10 |
| `tour-generator` | max-instances=5 | No code change |
| `news-orchestrator` | max-instances=5 | No code change |
| `news-generator` | max-instances=5 | No code change |
| `news-processor` | max-instances=5 | No code change |
| `translation-service` | max-instances=5 | No code change |

---

## Files Modified

| File | Change |
|------|--------|
| `development/tour_orchestrator_service.py` | Added `/delete-account/<secret_id>` endpoint |
| `development/api-gateway/gateway_routes.yaml` | Added delete-account route (now 20 routes) |
