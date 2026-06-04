# Spec — Getting Audioura to Full Cloud Functionality (Tours + Newsletters)

**Date:** 2026-06-03
**Audience:** Sir Michael (owner actions) + Kiro Amazon-Q (code/deploy)
**Format:** each deliverable = (1) what it's called · (2) how it's done · (3) billing · (4) exact steps you do

> Division of labor: **You** do account-level things — GCP Console, domain/DNS, billing decisions, secrets, approvals. **Kiro** does code and `gcloud` deploys. Each deliverable marks which steps are yours.

Deliverables are in dependency order. **A and B are the critical path** — without them the phone cannot drive a multi-service cloud flow no matter what else is deployed.

---

## Deliverable A — Tour-Status REST Endpoint  ⭐ critical path

**(1) What it's called:** "Orchestrator status endpoint" — replacing the client-side raw-SQL status update (`DirectDbUpdate` → `:5003`).

**(2) How it's done:** Kiro adds an authenticated `POST /tour-status` (and `GET /tour-status/<job_id>`) route to `tour_orchestrator_service.py` that updates the tour row via the existing DB connection. The mobile app's `TourStatusService` is changed to call `Endpoints.url(Service.orchestrator, '/tour-status')` instead of `DirectDbUpdate`. The six near-duplicate raw-SQL updaters (`direct_db_update`, `direct_jdbc_update`, `direct_postgres_connection`, `direct_update_api`, `postgres_direct`, `server_api`) are deleted. This removes raw SQL from the client entirely.

**(3) Billing:** **None.** Pure code change; no new infrastructure.

**(4) Exact steps you do:**
- Ask Kiro to implement A and confirm `:5003`/`execute_sql` is never deployed publicly.
- After Kiro's mobile build, smoke-test on local WiFi that tour generation still reports progress/completion (regression check) before relying on it in cloud.
- Nothing in the GCP Console.

---

## Deliverable B — Single-Domain API Gateway  ⭐ critical path (the big unlock)

**(1) What it's called:** "API gateway" — implemented as a **GCP External Application Load Balancer** (HTTPS) with **Serverless Network Endpoint Groups (NEGs)** and a **URL map** that path-routes to each Cloud Run service. (This is what lets one `cloud_base_url` reach all services and is exactly what the app's "gateway path routing" checkbox was built for.)

**(2) How it's done:** A Serverless NEG is created per Cloud Run service (map-delivery, orchestrator, translation, newsletter, …). A URL map routes `/map-delivery/*` → map-delivery NEG, `/orchestrator/*` → orchestrator NEG, etc., **with a path rewrite that strips the prefix** so each service still sees its own root routes. A Google-managed SSL certificate secures `api.audioura.com`. In the app you then set `cloud_base_url = https://api.audioura.com` and turn the **"Use gateway path routing" checkbox ON** — no rebuild.

**(3) Billing: Yes.** A global external Application Load Balancer charges **$0.025/hour for up to 5 forwarding rules (~$18/month)**, plus a small per-GB data-processing fee on traffic. The **Google-managed SSL certificate is free.** Serverless NEGs add no separate charge. (Cheaper interim alternative in the note below.)

**(4) Exact steps you do (GCP Console):**
1. **Own the domain.** Have `audioura.com` registered and its DNS manageable (you mentioned setting this up). Decide the gateway hostname, e.g. `api.audioura.com`.
2. **Network services → Load balancing → Create load balancer →** "Application Load Balancer (HTTP/S)", Internet-facing, Global.
3. **Backends:** for each Cloud Run service, "Create a Serverless NEG" in `us-central1` pointing at that service. Add one backend service per NEG.
4. **Routing rules (URL map):** add host `api.audioura.com`; path rules `/map-delivery/*` → map-delivery backend, `/orchestrator/*` → orchestrator backend, `/translation/*`, `/newsletter/*`, `/news/*`, `/tour-id/*`, `/custom-audio/*`, `/user/*` → matching backends. **Enable URL rewrite to strip the path prefix** on each rule (so `/map-delivery/download-tour/42` reaches the service as `/download-tour/42`). *(Ask Kiro to confirm each prefix matches the `_cloudPaths` map in `endpoints.dart`.)*
5. **Frontend:** HTTPS, create a **Google-managed certificate** for `api.audioura.com`, reserve a static IP (the console offers this in the flow).
6. **DNS:** in your domain registrar, add an **A record** for `api.audioura.com` → the load balancer's static IP. Wait for the managed cert to go "ACTIVE" (can take ~15-60 min after DNS resolves).
7. **In the app (About):** set `cloud_base_url = https://api.audioura.com`, tick **"Use gateway path routing"**, switch to Cloud. Now every service is reachable through the one domain.

> **Cheaper interim alternative (optional):** instead of the LB, Kiro can deploy a tiny **nginx reverse-proxy as its own Cloud Run service** that path-routes to the others. Billing is then near-zero (Cloud Run scales to zero, pay-per-request), and you point `cloud_base_url` at the proxy's `*.run.app` URL (free TLS) until `audioura.com` is ready. Trade-off: you manage an nginx config instead of a console URL map, and custom-domain TLS still eventually wants the LB or Cloud Run domain mapping. **Recommendation:** use the nginx-proxy now to start testing cheaply; move to the LB when you put it behind `audioura.com` for real use.

---

## Deliverable C — Deploy the Remaining Backend Services

**(1) What it's called:** "Backend service deployment" — translation-service, coordinates, news-orchestrator, news-generator, news-processor, newsletter-processor (and tour-editing for custom tours).

**(2) How it's done:** Kiro builds each into the existing universal image and `gcloud run deploy`s it (one Cloud Run service each), wires the inter-service env URLs (`TRANSLATION_URL`, `COORDINATES_URL`, `NEWS_*_URL`) on the orchestrators, binds the same Secret Manager secrets, and pins any that use the in-memory job store to `max-instances=1`.

**(3) Billing: Yes, but usage-based and small.** Each is a Cloud Run service that **scales to zero** — you pay only per request and CPU-time while handling traffic. For test-level volume this is cents/month per service. No fixed monthly fee.

**(4) Exact steps you do:**
- Confirm the relevant secrets exist in Secret Manager (OpenAI, AWS for Polly, R2 — already done; translation uses OpenAI).
- Approve Kiro deploying these (it adds Cloud Run services to the project).
- After Deliverable B exists, add a routing rule + Serverless NEG for each newly deployed service in the load balancer (same as B step 4).

---

## Deliverable D — Finish the Cloud SQL Data Import

**(1) What it's called:** "Cloud SQL data import" — load the remaining tables (`article_requests`, `news_audios`, `custom_tours`, and the small lookup tables) into Cloud SQL.

**(2) How it's done:** Kiro imports the remaining tables, resolving the circular FK between `article_requests` and `news_audios` by **dropping the FK constraint, loading both tables, then re-adding it** (Cloud SQL doesn't grant the superuser needed for `--disable-triggers`). Also create the `custom_tours` table (empty is fine) for schema parity.

**(3) Billing:** **Negligible.** Storage for these rows is tiny (metadata only; blobs are in R2). No new service.

**(4) Exact steps you do:**
- None directly — this is Kiro's import work. Just confirm Cloud SQL is reachable for the import (see Deliverable E for how it connects).

---

## Deliverable E — Lock Down Cloud SQL (remove public `0.0.0.0/0`)

**(1) What it's called:** "Cloud SQL private connectivity." Recommended method: the **native Cloud Run ↔ Cloud SQL connector** (`--add-cloudsql-instances`), not a VPC connector.

**(2) How it's done:** Each Cloud Run service is deployed with `--add-cloudsql-instances=audiotours-migration:us-central1:audioura-db`; the service connects over Google's secure Cloud SQL socket (`/cloudsql/...`) using IAM, so the database **no longer needs a public IP or any authorized network**. You then remove the `0.0.0.0/0` rule. (Code change: point `DB_HOST` at the unix socket path for those services — small, Kiro does it.)

**(3) Billing:** **No extra charge** for the native Cloud SQL connector — you keep paying only for the Cloud SQL instance itself. *(Contrast: a Serverless **VPC Access connector** is the other option but it bills for backing Compute instances on an ongoing hourly basis — avoid it here since the native connector is free and simpler. Check current VPC pricing if you ever need it for other reasons.)*

**(4) Exact steps you do (GCP Console):**
1. Confirm with Kiro that all services are redeployed with `--add-cloudsql-instances` and connect via the socket.
2. **SQL → audioura-db → Connections → Networking →** remove the `0.0.0.0/0` authorized network (and you can keep your own dev IP temporarily if you still need direct admin access).
3. Optionally **stop the instance** between test sessions to save cost (db-f1-micro is ~$0 stopped).
4. Rotate the DB password one more time after the import if any tooling touched it (you already have the no-newline procedure).

---

## Sequence & "when full functionality is testable"

1. **Now:** Kiro forces a map-delivery revision → you test existing-tour download over cellular (R2 is fixed).
2. **A (status endpoint)** + **C (deploy translation + coordinates)** → cloud tour *generation* pipeline can run.
3. **B (gateway)** → the phone can finally reach all services through one domain → **end-to-end cloud tour generation becomes testable.**
4. **D (data import)** + **C (news/newsletter services)** behind the gateway → **cloud newsletter generation becomes testable.**
5. **E (lock down DB)** → before any broad/unattended use.

So: **cloud tour generation** is testable after A + B + the translation/coordinates deploys; **cloud newsletter generation** after the news/newsletter services + data import are also behind the gateway. Until then, keep doing full generation/newsletter testing on **local WiFi** (already fully working) and use cloud for the existing-tour download path.

If you want, I'll have the exact `gcloud`/URL-map commands written out for Kiro for Deliverable B (both the LB and the nginx-proxy variants), and the orchestrator `POST /tour-status` route for Deliverable A.

---

**Sources (GCP pricing):**
- [Cloud Load Balancing pricing](https://cloud.google.com/load-balancing/pricing) — $0.025/hour for up to 5 forwarding rules + data processing
- [Serverless VPC Access / VPC pricing](https://cloud.google.com/vpc/pricing)
- [Cloud Run pricing](https://cloud.google.com/run/pricing) — scales to zero, pay-per-use
