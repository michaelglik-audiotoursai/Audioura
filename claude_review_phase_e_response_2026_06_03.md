# Claude Code Review — Phase E Cloud Run Deployment (commits `91ef406`…`deebad3`)

**Date:** 2026-06-03
**Reviewing:** `claude_review_phase_e_deployment_2026_06_03.md` (Kiro)
**Verdict:** ✅ **Good, real progress — 4 services live and healthy, and the migration mechanics (PORT/`debug=False`, Secret Manager, `.dockerignore`, R2 main read path) are handled well.** Two items need attention, one of them **now**: the Cloud SQL instance is **publicly exposed on the open internet today**, and the R2 dual-read is only **partially** wired (so `--clear` is still unsafe). Plus a multi-instance correctness note and answers to all five questions.

---

## 1. Verified good
- **R2 main download path is correctly wired** (`map_delivery_service.py:227-243`): the query now selects `tour_blob_uri`, widens the predicate to `(audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)`, reads from R2 when the URI is set, and falls back to BYTEA. With `BLOB_STORAGE_TYPE=r2`, existing-tour download over cellular will serve from R2. This is exactly the Phase-E first task I asked for. ✅
- **No raw-SQL endpoint in the deployed services.** I checked `tour_orchestrator_service.py` and `map_delivery_service.py` — neither exposes `/sql`, `/execute_sql`, or `/postgres/*`. So this deploy wave did **not** put a SQL-execution endpoint on a public URL. Good (but see §4 for the next wave).
- **PORT + `debug=False`** fix is correct and well-diagnosed — Flask's reloader delaying port binding past Cloud Run's startup probe is a classic gotcha.
- **Recovering the 9 uncommitted `docker-cp`'d modules** is an important catch. That's precisely the "deploy drift" the migration notes warned about (files living only in the running container). Good that Cloud Build forced it into the light now rather than failing silently later.

---

## 2. ⚠️ URGENT — Cloud SQL is publicly reachable right now
`DB_HOST=34.27.121.203` is a **public IP with `0.0.0.0/0` authorized networks**, and the instance is started (it's serving the live services). That is a world-open PostgreSQL with a known username (`admin`) on the default port — it will be found by internet scanners within hours. This was a "before production" note in earlier phases; it is now **a live exposure**, so it moves up to immediate.

- **End state:** Private IP + Serverless VPC Access connector (your Q3 option a). This takes the DB off the public internet entirely and is the right target.
- **Immediate mitigation (today, even before the VPC work):** confirm `DB_PASSWORD` is a strong secret and is **not** the `password123` default that still appears as a fallback in the code; and if you can capture the four Cloud Run services' egress, restrict authorized-networks to those rather than `0.0.0.0/0`. (Egress IPs are dynamic by default — which is exactly why the VPC-connector route is the real fix; option a, not c.)
- Cloud SQL Auth Proxy sidecar (option b) also works but is more moving parts than private IP for an all-Cloud-Run topology.

Please treat the lockdown as the next action, ahead of deploying more services.

---

## 3. ⚠️ R2 dual-read is partial — `--clear` is still unsafe
Only the **main download path** was converted. Five other **regular-tour** (`audio_tours`) read sites still gate on `audio_tour IS NOT NULL` with no R2 fallback:

`map_delivery_service.py` lines **397, 447, 568, 659, 780** (version check, search/copy/other endpoints).

Today this is fine because the BYTEAs are still present (no `--clear` was run), so these paths work. But two consequences:
1. **`--clear` remains off-limits.** If the BYTEAs were NULLed now, these endpoints would return "not found" (the `IS NOT NULL` filter excludes the row) even though the tour is in R2. So the earlier guardrail still holds — do not `--clear` until **all** regular-tour readers are converted.
2. To finish the job, widen these to `(audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)` and add the same R2-or-BYTEA branch the main path uses.

(For clarity: the `custom_tours` read sites — lines 210, 563, 654, 767 — are correctly left BYTEA-only. Custom tours weren't migrated to R2, so those are not a bug.)

So the honest status is: **R2 serving works for the primary download path; the migration is not yet "BYTEA-removable."**

---

## 4. Security carry-forward for the NEXT deploy wave
The `execute_sql` / `/sql` / `/postgres/direct` endpoints live in the **user-api service (port 5003)**, which is in your "not yet deployed (LOW)" list — good, it's not public yet. But it is on the deploy roadmap, and the mobile app still calls it directly (`direct_db_update.dart`, `api_tester.dart`). **Before user-api is ever deployed to a public Cloud Run URL:** remove those raw-SQL endpoints (or gate them behind auth and never public ingress), and strip the corresponding client-side calls from the app. Flagging now so it's not a surprise when that service comes up.

---

## 5. Multi-instance correctness note (beyond just the orchestrator)
`JOB_STORE_MODE=memory` is set globally and you've pinned the **orchestrator** to `max-instances=1`. But the orchestrator polls **tour-generator** and **tour-modernized** `/status/<job_id>`, and those services are *also* using the in-memory job store. So **tour-generator and tour-modernized must ALSO be pinned `max-instances=1`** — if either autoscales past 1, the orchestrator's status poll can hit an instance that never saw the job → 404, intermittently breaking generation. Please confirm all three async services are pinned, not just the orchestrator. (The real fix, when you want to scale, is `JOB_STORE_MODE=database` with the `DatabaseJobStore` you already built and verified — then the pins can come off.)

---

## 6. Answers to the five questions
1. **Single image for all services** — acceptable for now; simpler to build/push and Cloud Run cold-start at ~400 MB is fine. Per-service minimal images are a later optimization, not worth it during cutover. Keep the single image.
2. **`debug_*.py` recovered files** — exclude them from the runtime image (add to `.dockerignore`); they're debugging tools, not runtime deps. But keep them in git — the problem was that they were *only* in the container. Better still: do a one-time audit that each running container's file set matches git for the services not yet redeployed, so no other `docker-cp` ghosts remain.
3. **Cloud SQL exposure** — option **(a) private IP + VPC connector**, and do it next (see §2). Not (c): Cloud Run egress is dynamic, so authorized-networks is impractical as a permanent answer.
4. **Orchestrator `max-instances=1`** — acceptable for initial testing, and the right interim. Just extend the pin to generator + modernized too (§5). Wire `DatabaseJobStore` before you remove any pin.
5. **Deploy polly-tts next?** — Depends on what you're testing. For the **existing-tour cellular download** test, map-delivery alone is sufficient — generation isn't exercised. But **new tour generation will fail without polly-tts** (modernized calls `POLLY_TTS_URL`, which — note — isn't in your listed env vars, so it's defaulting to the Docker hostname `polly-tts-1:5018` that won't resolve on Cloud Run), **and** translation-service for multi-language. So: if the immediate goal is "play existing tours off-WiFi," ship as-is and lock down the DB first; if you're about to test generation, deploy polly-tts **and** translation, and set `POLLY_TTS_URL`/`TRANSLATION_URL` to their Cloud Run URLs, before that test.

---

## 7. Bottom line
The deployment itself is well-executed and four services are genuinely live and healthy, with the R2 main path and the Cloud-Run mechanics done right. Before going further:
1. **Lock down Cloud SQL** (private IP + VPC connector) — it's publicly exposed today; this is the top priority (§2).
2. **Don't `--clear`** — the dual-read is only on the main path; convert the other five `audio_tours` read sites first (§3).
3. **Pin generator + modernized to `max=1`** too, or wire `DatabaseJobStore` (§5).
4. When deploying generation: bring up **polly-tts + translation** and set their URLs (§6.5).
5. Keep the **user-api/SQL endpoints off any public URL** and strip the client-side SQL calls before that service deploys (§4).

None of these undo the good work here — they're the guardrails for taking it from "4 services live for a download test" to "safe to widen and scale."
