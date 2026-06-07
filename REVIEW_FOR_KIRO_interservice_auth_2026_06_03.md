# For Kiro Amazon-Q — Inter-Service Auth Fix (403 on generation)

**Date:** 2026-06-06
**Scope:** Services/GCloud only.
**Verdict:** ✅ **Your chosen approach is correct — go ahead, do NOT re-open unauthenticated access.** But **do not deploy v7 as-is until it covers *every* inter-service call edge**, not just orchestrator→generator, or the next step (audio) will 403 again. Plus a correction on the "sync" 404 (it's the `/user` route, not `/sync`).

---

## 1. Diagnosis confirmed (from the log)
- `[22:55:52]` generate POST → **200, job queued** → so the **gateway → orchestrator** call worked (the API key was accepted). Good.
- `[22:56:03]` status → **failed**, and the body contains **`403 Forbidden`** HTML.
So the failure is **downstream of the orchestrator**: the orchestrator accepted the job, then its call to `tour-generator /generate` returned 403 because the orchestrator sent **no identity token** and `tour-generator` is `--no-allow-unauthenticated`. Your read is right.

## 2. Approach: ✅ correct — authenticated inter-service calls, NOT re-opening
You were right to reject re-allowing unauthenticated access on the internal services — that would undo the K3 lockdown you just shipped. The correct pattern is exactly what you did: **mint a Google identity token from the metadata server for each inter-service call** (the same thing the gateway already does), and grant the caller's service account `run.invoker` on each callee. Proceed with that. Do **not** take the shortcut.

## 3. 🔴 Before deploying v7 — cover ALL inter-service edges, not just orchestrator→generator
The orchestrator calls **more than just the generator**, and other services call each other. Every one of these edges hits the same 403 unless it attaches a token:
- orchestrator → **tour-generator** (`/generate`)
- orchestrator → **tour-modernized**
- orchestrator → **translation-service** (for multi-language)
- orchestrator → **coordinates**
- **tour-modernized → polly-tts** (the audio step)
- (when news is live) news-orchestrator → news-generator, newsletter-processor, etc.

If v7 only wrapped the orchestrator's call to the generator, the run will get **past** generation and then **403 at the audio step (modernized → polly-tts)** — a second failed test cycle. **Audit every outbound inter-service HTTP call and route it through `_authenticated_request()` before deploying.** (Your test was a 3-language generation, so it exercises generator → modernized → polly-tts → translation → coordinates — all of them.)

## 4. Two things to verify so the token is actually accepted
1. **Audience = the exact callee base URL.** When minting the token, `audience` must be the target service's root `*.run.app` URL (e.g. `https://tour-generator-…run.app`), not the path and not the gateway URL. A wrong audience still yields 403. (This is how the gateway's `get_identity_token(audience)` already works — mirror it.)
2. **`run.invoker` on each callee for the caller's SA.** If all services run as the **same** default compute SA (`60899077572-compute@…`), granting that SA `run.invoker` on every backend covers all edges in one shot — confirm they all run as that SA. If any service uses a different SA, grant that SA invoker on its callees too.

## 5. Deploying v7 is low-risk — go ahead after §3–§4
This change is **additive**: it only adds tokens to outbound calls; the backends stay IAM-locked, the external posture is unchanged, and you can roll back to the current revision instantly. So once v7 covers all edges (§3) and the audience/IAM checks pass (§4), deploy it and re-run the 3-language generation. Expect generation to now complete server-side.

## 6. Correction — the "user sync 404" is the `/user` route, not `/sync`
The log shows `Sync response: 404 {"error":"endpoint not found","service":"api-gateway"}`. The gateway **does** define `/sync` for both GET and POST, so a `/sync` method mismatch would not return "endpoint not found." That 404 is the **catch-all**, meaning the requested path has **no route** — and that path is **`/user/<id>`** (the app's `trackTourRequest`/user-sync). This is the **known `/user` dependency**: the gateway has no `/user` route and `user-api` isn't deployed. So:
- This is also why `TOUR_TRACK … HTTP 404` and `TOUR_STATUS … rows_affected: 0` appear — the tour_requests row is never created.
- **Fix:** deploy `user-api` and add a `/user/<id>` route to the gateway (proxying to it). That fixes both the user-sync and makes `/tour-status` return `rows_affected: 1`. (This is the same `/user` item already on your list — it's now confirmed live in the log, not hypothetical.)

## 7. (Minor) Tour-content "looks changed"
Sir Michael wasn't sure the downloaded tour's content matched his memory. Cloud serves the **R2/Cloud-SQL migrated copy** (tour 75, "Newton Center"), which should be byte-identical to what was migrated. Can't diagnose from "seems different" — if it recurs, capture the **tour id** and we can compare the R2 object against the local DB copy. Not a blocker; the download itself succeeded.

## 8. Future hardening (not now)
Once this works, consider `--ingress=internal` on the internal-only services (generator, modernized, polly-tts, coordinates) so they're not on the public internet at all — only reachable from within the project. Token auth is sufficient for now; this is a later defense-in-depth step.

---

## Bottom line
**Approve the approach — deploy v7, do not re-open unauthenticated.** Just make sure v7 authenticates **every** inter-service edge (esp. modernized→polly-tts and orchestrator→translation/coordinates), with the correct **audience** and `run.invoker` grants, so the 3-language test doesn't 403 at a later hop. Separately, the user-sync 404 is the `/user` route gap (deploy user-api + add the gateway route), not a `/sync` issue. The deploy is additive and safe to roll back, so once the edge-coverage + audience/IAM checks are done, ship it and re-test.
