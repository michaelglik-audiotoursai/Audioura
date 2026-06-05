# Review for Kiro Amazon-Q — Services K1–K9

**Date:** 2026-06-03
**Branch:** `services-migration`
**Scope:** Services/GCloud only.
**Verdict:** ✅ Solid. Gateway hardening, the status endpoint, secrets, DB lockdown, and data import are done and verified. One production risk remains (K3, acknowledged) and one test gap to close.

---

## Verified in code
- **K2 gateway** (`api-gateway/nginx.conf`): explicit routes for all needed paths; `/download/` and `/tour-status` added; **catch-all now `return 404`** (no longer proxies unknown paths to the orchestrator); `proxy_read_timeout 600` on generation. Correct.
- **K1 status endpoint:** `@app.route('/tour-status', methods=['POST'])` exists (`tour_orchestrator_service.py:1004`).
- **K7/K8:** the DB-querying smoke tests pass (tours-near returns 191 tours) **with `0.0.0.0/0` cleared**, which proves the unix-socket Cloud SQL connector works — K8 is verified by the fact that DB reads still succeed without the public IP.

## Two things to address

### 1. K1 was not actually verified to update a row
Smoke Test 6 returned `{"rows_affected": 0}` — the endpoint returned 200 but matched **no** row. So you've proven it's wired, not that it works. Please:
- Re-test with a **real** `tour_id` that exists in `tour_requests` and confirm `rows_affected: 1`.
- **Publish the exact contract for the mobile team** (so I can pass it to Mobile Amazon-Q in their own document): the endpoint keys on `tour_id` updating `tour_requests`, whereas the old client path matched on `request_string`. Confirm which id the app must send (the `tour_xxx` request id), so they don't repeat the `rows_affected: 0` no-op.

### 2. K3 (backend auth) — the main outstanding production risk
All backends are `--allow-unauthenticated`, so anyone on the internet can POST `tour-orchestrator/generate-complete-tour` and burn your OpenAI/Polly budget. The "nginx can't do OIDC" rationale is an over-simplification — it's *awkward*, not impossible (njs/lua fetching a token from the metadata server), but the cleaner path is a tiny auth proxy that mints ID tokens, or the GCP LB with IAM. **Acceptable for a short, attended test; lock down before broad/unattended use:** keep the gateway the only public surface and set backends `--no-allow-unauthenticated`.

## Done / Remaining
- ✅ K4 (secrets → Secret Manager), K5 (deleted dead `tour-id-resolution`), K7 (import incl. `custom_tours`), K8 (DB locked via unix socket).
- ⏳ K6 (news/newsletter deploy) and K9 (DNS — Sir Michael's action) remain as planned.

## Bottom line
Approved. Re-test `/tour-status` against a real row (expect `rows_affected: 1`) and publish the contract; lock down backends (K3) before broad use. Nothing here requires mobile-app changes — that review is in a separate document for Mobile Amazon-Q.
