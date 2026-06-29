# remind_kiro.md — Resume Context for Kiro Amazon-Q (Cloud Services)

**Purpose:** Restore context for a fresh Kiro (Services/GCloud) session. Treat the **repo + GCP console as ground truth**; this file is the decision/status memory. Last synthesized: **2026-06-17**.

**Your lane:** cloud services + GCloud only. NOT the Flutter app (that's Mobile Amazon-Q) and NOT the iOS build (iOS Amazon-Q). Don't edit `audio_tour_app/`.

---

## 1. Production architecture (live)
```
Mobile app → https://api.audioura.com
  → Cloudflare (proxy ON, Full-strict TLS, DDoS/CDN)
  → GCP External Application Load Balancer (static IP 34.36.147.30, Google-managed cert)
  → api-gateway (YAML-driven auth-proxy, PUBLIC; loads gateway_routes.yaml at startup)
        • mints Google OIDC tokens per backend (metadata server)
        • X-API-Key required on cost endpoints (fail-closed 503 if key unset)
        • Attestation scaffold (log-only): X-App-Attestation header, /attest-nonce (stateless HMAC), ATTESTATION_ENFORCED=false
        • 20 routes loaded from gateway_routes.yaml (no hand-coded Python routes)
  → backends: ALL --no-allow-unauthenticated (IAM-locked, return 403 without an OIDC token)
```
- **GCP project:** `audiotours-migration`, region `us-central1`.
- **Cloud SQL:** `audioura-db` (PostgreSQL 15). Services connect via unix-socket Cloud SQL connector.
- **Blobs:** Cloudflare R2 holds tour/news ZIPs; map_delivery dual-reads R2 else BYTEA.
- **Current monolithic image:** `audioura:v28` (latest deployed). Translation-service has its own Dockerfile in `development/translation-service/`.
- **Max-instances set:** orchestrator=10, generator/news/translation/processor=5 each.

## 2. Gateway (YAML-driven)
- `api-gateway/main.py` — generic loader, reads `gateway_routes.yaml`
- `api-gateway/gateway_routes.yaml` — single source of truth for all cloud-exposed endpoints (20 routes)
- Attestation: `/attest-nonce` (stateless HMAC nonce, API-key-gated), `_verify_attestation()` logs but never blocks (log-only mode)
- Nonce contract for Mobile: `GET /attest-nonce` → `{"nonce":"<ts>.<rand>.<hmac>", "ttl_seconds":300}`. App binds nonce into Play Integrity / App Attest token, sends in `X-App-Attestation` header.

## 3. Entitlements & Quotas (deployed, tested)
- `plans` table: `free`(1 tour/day, 10 news/week), `tester`(100/day), `paid`(10/day)
- Fail-closed: missing user→401; DB connection error→**503**; over quota→429.
- **DB connection errors raise** (propagate to orchestrator → 503). Query errors return 9999 (429 backstop).
- Single authoritative writer: `source='orchestrator'` on `tour_requests`. Column default `'tracking'`.
- Rollback on generation failure: both thread + cloud_tasks (worker) paths.
- `news_max_minutes` enforced via word-budget truncation.
- Test devices: `USER-281301397` (Android), `USER-974226925` (iPhone) → `tester` plan.

## 4. Translation service
- Single source of truth: `development/translation-service/translation_service.py`
- Handles primary (tour_content) + fallback (ZIP extraction with `audio_N.txt`)
- Coordinates preserved via `_restore_metadata_labels`; manifest.json updated in BOTH paths
- Korean (`ko`/Seoyeon) supported; `name` field in translation API response

## 5. Tour generation
- Phase 3C skipped for walking tours; GEO-CHECK handles proximity
- User-explicit stops protected from Phase 3C AND GEO-CHECK
- Multi-building coordinates: distinct coords → all stops get coords
- `_MULTI_BUILDING_INSTITUTION_RE` is **plural-only** (libraries/churches/buildings)

## 6. Account Deletion — VERIFIED ✅
- `DELETE /delete-account/<secret_id>` — 12 tables in FK order, idempotent, fail-closed
- End-to-end tested: credentials + DH keys confirmed purged

## 7. News Pipeline (end-to-end working on cloud)
- All inter-service calls use OIDC auth (`_get_auth_headers`)
- Chain: gateway → news-orchestrator → news-generator (OIDC✅) → news-processor (OIDC✅) → polly-tts (OIDC✅)
- Live-tested: `200 success` end-to-end
- Gateway routes: `/generate-news`, `/news-status/<id>`, `/news-articles`, `/news-download/<id>`
- **Newsletter quota design:** one newsletter = one quota unit (batch check upfront); individual articles use `source='newsletter'` to skip per-article check
- Sibling processors (subscription_article_processor, background_article_processor) now use env-var URLs + OIDC auth

## 8. Privacy Policy — UPDATED
- Tours are shared/public content, retained anonymized after deletion
- Policy amended (sections 1, 4, 6); label fixed to "About → Delete My Account"

## 9. ClickUp MCP Integration
- Config at `~/.kiro/settings/mcp.json` using `mcp-remote` bridge to `https://mcp.clickup.com/mcp`
- OAuth completed successfully. Node.js v22.17.0 installed.
- **Queue workflow:** "check ClickUp for new tasks and execute them" → read queue → execute → update status
- ClickUp list for Backend Agent: `🟦 Backend Agent (Kiro) — queue` (id 901327587897)
- After completion, move tasks to `⏳ Waiting for Claude Review` (id 901327587900)

---

## IMMEDIATE NEXT (in progress)

1. **Kill-switch test — RESUME HERE:**
   - Function: `billing-killswitch` (Gen2, `killswitch-sa@...`)
   - Pub/Sub topic: `projects/audiotours-migration/topics/billing-killswitch`
   - IAM: all permissions granted (run.developer + artifactregistry.reader + iam.serviceAccountUser on compute SA)
   - **Action:** Publish test message, confirm 8/8 disabled, then RESTORE:
     ```powershell
     $msg = '{"costAmount":350,"budgetAmount":300,"alertThresholdExceeded":1.0}'
     gcloud pubsub topics publish billing-killswitch --project=audiotours-migration --message=$msg
     ```
   - Wait ~90s, check logs for "8/8 services disabled"
   - Verify: `gcloud run services describe tour-orchestrator --region=us-central1 --project=audiotours-migration --format="value(spec.template.metadata.annotations['autoscaling.knative.dev/maxScale'])"`
   - RESTORE after confirming:
     ```powershell
     gcloud run services update tour-orchestrator --max-instances=10 --region=us-central1 --project=audiotours-migration --quiet
     # others: --max-instances=5
     $svcs = @("tour-generator","news-orchestrator","news-generator","news-processor","translation-service","polly-tts","tour-worker")
     foreach ($s in $svcs) { gcloud run services update $s --max-instances=5 --region=us-central1 --project=audiotours-migration --quiet }
     ```

## OUTSTANDING (prioritized)

1. **Kill-switch test completion** — publish message, confirm disable, restore (see IMMEDIATE NEXT above)
2. **News parsing guardrail** — DEPLOYED (v25/v26, newsletter-processor-00004-7zp). Economist→402 verified. MailChimp regression passed.
3. **`/key_exchange` route** — DEPLOYED (v26, gateway 21 routes). Verified live: returns 404 "No server key" (correct for test).
4. **Cloud Tasks deploy** — queue not created yet (API not enabled). Commands in `migration/setup_cloud_tasks_queue.sh`.
5. **Attestation enforcement** — scaffold deployed (log-only). Flip after Mobile sends tokens.
6. **Encrypt-at-rest** — owner decision pending.
7. **Profile portability** — deferred to next-version.

## Mobile-AQ Issues (documented, not my lane)
- News/newsletter calling local ports in cloud mode → `REVIEW_FOR_MOBILE_AQ_news_cloud_routing_2026_06_17.md`

## 10. Where the detail lives
- Review trail: `REVIEW_FOR_KIRO_*.md` (my work), `claude_review_*.md` (Claude feedback)
- Owner decisions: `OWNER_DECISIONS_*.md`
- Test scripts: `test_news_quota_integration.py`, `test_t4_db_down_unit.py`, `test_newsletter_cloud.py`
- Privacy policy: `PRIVACY_POLICY.html`

**When you finish a chunk, update THIS file** so the next stateless session can resume.
