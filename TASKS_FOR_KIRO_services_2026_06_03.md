# Tasks for Kiro Amazon-Q (Services → Google Cloud)

**Date:** 2026-06-03
**Scope:** Services/GCloud only. (Mobile-app code is **not** your purview — that's Mobile Amazon-Q.)
**Source:** derived from the Phase E gateway review + the cloud-functionality spec.

> Where a task defines a contract the mobile app depends on (e.g., the status endpoint), implement the **server side** and publish the exact request/response shape so Mobile Amazon-Q can call it. Do not edit the Flutter app.

---

## K1 — Orchestrator REST status endpoint (replaces client-side raw SQL)  ⭐ critical
**What:** Add an authenticated status API to `tour_orchestrator_service.py` so the mobile app no longer issues raw SQL to update/read tour status.
**Do:**
- `POST /tour-status` — body `{ "job_id": "...", "request_string": "...", "status": "completed|failed|...", "tour_id": <optional> }` → updates the tour row via the existing DB connection; returns `{ "ok": true }`.
- Confirm `GET /status/<job_id>` already returns progress/completion (it's routed in the gateway) and document its response shape.
- **Publish both contracts** (paths, fields, responses) in your reply so Mobile AQ can wire to them.
**Note:** the `:5003` `execute_sql` / `/sql` / `/postgres/direct` endpoints must **never** be deployed with public ingress. This REST endpoint is what lets us retire them.
**Billing:** none.

## K2 — Gateway hardening (`api-gateway/nginx.conf`)
- **Catch-all → 404 + explicit routes.** Replace the `location /` catch-all (currently → orchestrator) with explicit routes the app actually needs, and make the default `return 404`. Keep these explicit: `/download/` → orchestrator (job ZIP download), plus the existing `/generate-complete-tour`, `/status/`, `/jobs`.
- **Confirm generation is async** (POST returns a `job_id` quickly, client polls `/status`). If any leg is synchronous, raise `proxy_read_timeout`, the **api-gateway** Cloud Run `--timeout`, **and** the **orchestrator** `--timeout` together (to 600). Prefer keeping it async.
**Billing:** none (config).

## K3 — Backend authentication (before anything beyond a short attended test)
Today the gateway and all backends are `--allow-unauthenticated`, so anyone can POST to `tour-orchestrator/generate-complete-tour` and run up the OpenAI/Polly bill.
**Do:** set backends to `--no-allow-unauthenticated` and have the **gateway** attach a Google-signed identity token for each backend's audience (or, as a lightweight interim, a shared-secret header the backends verify). Keep the gateway as the only public surface.
**Billing:** none.

## K4 — Move translation + coordinates secrets to Secret Manager
They're currently plain env vars (OpenAI key visible to Cloud Run viewers + in revision history). Re-store via the no-newline workflow (`[IO.File]::WriteAllText` → `--data-file`) and bind them as Secret Manager references.
**Billing:** none.

## K5 — Delete the failed `tour-id-resolution` Cloud Run service
Redundant (resolve now lives in map-delivery) and never deployed cleanly. Remove it.
**Billing:** removing it slightly reduces surface; no charge.

## K6 — Deploy the news/newsletter pipeline (Deliverable C)
Deploy `news-orchestrator`, `news-generator`, `news-processor`, `newsletter-processor`; wire their inter-service URLs; **add gateway routes** for the app's paths (`/newsletters_v2`, `/process_newsletter`, `/get_articles_by_newsletter_id`, `/download/<articleId>` for news). Pin any in-memory-job-store services to `max-instances=1`.
**Billing:** Cloud Run, scales to zero — cents/month at test volume.

## K7 — Finish Cloud SQL data import (Deliverable D)
Import remaining tables (`article_requests`, `news_audios`, small lookups) and **create `custom_tours`** (empty is fine, for schema parity). Resolve the `article_requests`↔`news_audios` circular FK by **dropping the FK, loading both, re-adding it** (Cloud SQL doesn't grant the superuser needed for `--disable-triggers`).
**Billing:** negligible (metadata only; blobs in R2).

## K8 — Lock down Cloud SQL (Deliverable E)
Use the **native Cloud Run ↔ Cloud SQL connector**: redeploy services with `--add-cloudsql-instances=audiotours-migration:us-central1:audioura-db` and connect via the `/cloudsql/...` socket, so the DB needs no public IP. Then tell Sir Michael it's safe to remove `0.0.0.0/0`.
**Billing:** no extra charge (native connector). Do **not** use a Serverless VPC connector here (it bills hourly).

## K9 — Production gateway domain (coordinate with Sir Michael)
When `api.audioura.com` is ready, the gateway needs to answer on it. Two options — pick with Sir Michael:
- **(cheap) Keep the nginx-on-Cloud-Run gateway**, fronted by Cloudflare DNS/proxy (free TLS), or Cloud Run **domain mapping** (free managed cert). You provide the Cloud Run service; he points DNS.
- **(production) GCP External Application Load Balancer** (~$18/mo) with Serverless NEGs + path routing.
Your part is the gateway/service config; **DNS and the domain are Sir Michael's** (see his doc). When this lands, the mobile app sets `cloud_base_url=https://api.audioura.com` (still prefixes OFF — your nginx routes by root path, so the app's "gateway path routing" checkbox stays unchecked).
**Billing:** $0 (Cloudflare/Cloud Run domain mapping) or ~$18/mo (GCP LB).

---

### Dependency order
K1 + K2/K3 → enables clean cloud tour generation. K6 + K7 → enables cloud newsletters. K8 → before broad use. K9 → when the domain is live. K4/K5 are cleanup, do anytime.

**Hand-off:** publish the K1 status-endpoint contract and confirm K2 route names so Mobile Amazon-Q can wire the app to them.
