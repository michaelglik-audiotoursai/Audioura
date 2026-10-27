# SUBSCRIBED_GCLOUD_ENV.md — Subscribed track GCloud environment manifest

**Task:** LOCAL-764 · **Branch:** LOCAL-764-subscribed-cloud-readiness · **Base:** subscribed @ 1e740b0a
**Rulings:** D712, D708 (track `subscribed`), D594/D604 (local stack)

Everything the GCloud_Storied (Windows) session needs to stand up the Subscribed
track on Cloud Run **without guessing**: per service, the image source, the port,
and **every environment variable the service reads**, with the GCloud value or
the **Secret Manager secret NAME** (never a secret value).

> **No GCloud action is taken by this task.** This is a manifest only — no
> `gcloud` command is run, nothing is deployed. The secret names here reference
> the existing storied secrets (see `GCLOUD_STORIED_START_HERE.md`, which this
> task does NOT edit); the Subscribed services reuse the same model-provider /
> AWS / storage secrets unless noted.

---

## 0. Conventions & cross-cutting rules

- **Never `--set-secrets` / `--set-env-vars` on a live service** — they replace
  the whole list and would delete other secrets while `/health` still passes
  (GCLOUD_STORIED_START_HERE.md). Use, in one command:
  `--remove-env-vars X --update-secrets X=secret:latest` or
  `--update-env-vars ...` to change one var.
- **Secrets are referenced by NAME only here.** Grant each service's runtime SA
  `roles/secretmanager.secretAccessor` on exactly the secrets it reads.
- **Backends are private** (`--no-allow-unauthenticated`); only the gateway is
  public. Service-to-service calls carry a Google OIDC identity token (the
  gateway already does this). The `*_URL` values below are the private Cloud Run
  URLs of the `-subscribed` services and are injected into the gateway via the
  `${…_URL}` placeholders in `api-gateway/gateway_routes.subscribed.yaml`.
- **Track:** every Subscribed service that stamps/reads provenance sets the track
  to `subscribed`. The var name differs by service (below): orchestrator/
  translation read `TOUR_TRACK`; map-delivery reads `DELIVERY_TRACK_FILTER`.
- **DB:** Cloud SQL is SHARED across Beta/Storied/Subscribed (D708); rows are
  separated by the `track` column, NOT by database. Subscribed services connect
  with the same `DB_*` / `DATABASE_URL` + `--add-cloudsql-instances` as storied.
  `DB_PASSWORD` is a secret (`db-password` or the storied equivalent).

### Mac-only settings GCloud must NOT copy (and what replaces them)

| Mac (local compose) value | Why it is Mac-only | GCloud replacement |
|---|---|---|
| `DB_HOST=postgres-2`, `DB_PASSWORD=password123` (compose default) | Docker-network host + throwaway dev password | Cloud SQL via `--add-cloudsql-instances`; `DB_PASSWORD` from Secret Manager |
| `*_URL=http://subscribed-…-204:50xx` / `http://host.docker.internal:…` | Docker-network / host-loopback names | Private Cloud Run `https://…-subscribed-<proj>.run.app` URLs |
| `PAID_API_LOG=/meterlogs/paid_api_calls.jsonl` (`_meter/paid_api_meter.py:10`) | `/meterlogs` is a host bind-mount | Leave unset → the meter logs to the default path in the container's ephemeral FS, or point at a mounted volume; the DB ledger is the source of truth, not this file |
| `METER_ROLE_TOKEN_FILE=/…/token` bind-mount | Host file bind-mount | BOTH are required (the code compares them): `METER_ROLE_TOKEN` env from secret `meter-role-token`, AND the same secret mounted as a file `--update-secrets /run/meter-secret/role_token=meter-role-token:latest` with `METER_ROLE_TOKEN_FILE=/run/meter-secret/role_token` (never under /opt/meter: a secret volume there hides the baked meter). Without both, no row is 'listener' and DAILY_PAID_LIMIT_USD counts nothing. Table `paid_api_calls` comes from migration 053. Services that need it: orchestrator, generator, modernized, translation, and polly-tts-subscribed (LOCAL-768). |
| `ATTESTATION_NONCE_SECRET=default-nonce-hmac-key-change-in-prod` (gateway default) | Dev placeholder | MUST be a real secret in prod (`attestation-nonce-secret`) |
| `GATEWAY_API_KEY=test-api-key` (compose default) | Dev placeholder | Secret `gateway-api-key` |
| `AWS_ACCESS_KEY_ID=test` / `…=test` (compose) | Fake AWS creds for local Polly stub | Real AWS creds from secrets (Polly/Comprehend) |

---

## 1. api-gateway (PUBLIC) — image `api-gateway`, Dockerfile `api-gateway/Dockerfile`, port 8080

The ONE public service. Reads (main.py):

| Env var | GCloud value / secret NAME | Notes |
|---|---|---|
| `GATEWAY_ROUTES_FILE` | `gateway_routes.subscribed.yaml` | **NEW (LOCAL-764).** Selects the Subscribed manifest. Unset = Beta/Storied manifest (unchanged default). Relative path resolved beside `main.py`; absolute allowed. |
| `GATEWAY_API_KEY` | secret `gateway-api-key` | Fail-closed: if unset, every `api_key` route returns 503/401. The app's baked-in `--dart-define=GATEWAY_API_KEY` must equal this. |
| `PORT` | `8080` | Cloud Run default. |
| `ATTESTATION_MODE` | `log_only` (or `off`) | `enforce` not implemented. |
| `ATTESTATION_ENFORCED` | `false` | — |
| `ATTESTATION_NONCE_SECRET` | secret `attestation-nonce-secret` | **Must be a real secret in prod** — the dev default is a placeholder. |
| `PLAY_INTEGRITY_API_KEY` | secret `play-integrity-api-key` (optional) | Only used when attestation verifies Android. |
| `APP_PACKAGE_NAME` | `com.audioura.audiotours` | Android package. |
| `APP_BUNDLE_ID` | `com.audioura.audiotours` | iOS bundle (attestation). |
| Backend URLs | `MAP_DELIVERY_URL`, `ORCHESTRATOR_URL`, `USER_API_URL`, `TRANSLATION_URL`, `NEWS_ORCHESTRATOR_URL`, `NEWSLETTER_URL`, `TREATS_URL`, `TOUR_EDITING_URL`, `TOUR_ID_RESOLUTION_URL`, `GENERATOR_URL`, `VOICE_URL`, `CUSTOM_AUDIO_URL` | Private Cloud Run URLs of the 12 `-subscribed` backends. Each has a `${VAR:-default}` placeholder in the subscribed manifest; set the real URL as an env var. |

Gateway host: Subscribed app points at `https://subscribed-api.audioura.com`
(LOCAL-764, `endpoints.dart` `_subscribedCloudBaseUrl`). Same Cloudflare → GCP LB
path as Beta/Storied; only the hostname differs.

---

## 2. tour-orchestrator-subscribed (private) — image from `Dockerfile.orchestrator`, port 5002

Reads (`tour_orchestrator_service.py`): `DB_HOST DB_NAME DB_PASSWORD DB_PORT
DB_USER GCP_PROJECT_ID PORT`, plus:

| Env var | GCloud value / secret | Notes |
|---|---|---|
| `TOUR_TRACK` | `subscribed` | **Required.** Stamps every tour row with the subscribed track (D708). Default `beta` — MUST be overridden. |
| `STORIED_MODE` | **`true`** | **D717 (2026-10-26):** this flag is the story pipeline (spine, fact sheets, story types, museum features, I-CON evaluation), not a track label. The local Subscribed stack Michael reviewed runs `true` (docker-compose-master.yml); `false` on GCloud made Preview tours skip it. |
| `DB_PASSWORD` | secret `db-password` | — |
| `TOUR_GENERATOR_URL` | `https://tour-generator-subscribed-<proj>.run.app` | internal |
| `MODERNIZED_URL` | modernizer URL if used | optional |
| `TRANSLATION_URL` | `https://translation-subscribed-<proj>.run.app` | internal |
| `USER_API_URL` | `https://user-api-subscribed-<proj>.run.app` | internal |
| `TOUR_UPDATE_URL` / `TOUR_WORKER_URL` | internal URLs | if worker split is used |
| `COORDINATES_URL` | internal URL | optional |
| `JOB_STORE_MODE` | `database` (cloud; job_store.py accepts only 'database'/'memory') | not in-memory on Cloud Run |
| `GENERATION_MODE` | as storied | — |
| `CLOUD_TASKS_QUEUE` / `CLOUD_TASKS_LOCATION` / `WORKER_SERVICE_ACCOUNT` | if Cloud Tasks worker split enabled | optional |
| **`L2_SEAT_JOB_ENABLED`** | `true` | **Required for L2 seats.** Enables the in-process L2 seat offer loop (`l2_seat_job.py`). When off, seats are never offered. |
| `L2_SEAT_JOB_INTERVAL_SECONDS` | e.g. `300` | loop cadence |
| `RECOVERY_CODE_PEPPER` | **secret `recovery-code-pepper`** | **Required** — recovery-code routes are DISABLED (503) if unset (`recovery_code_service.py:784`). 32+ random bytes, server-held, never leaves the server. |
| `DAILY_PAID_LIMIT_USD` | e.g. `50` (or unset) | Daily paid-API spend ceiling (`_meter/paid_api_meter.py`). **OFF when unset** — a tour is never blocked by a missing limit, but set it for cost safety. |
| `METER_ROLE` / `METER_ROLE_TOKEN` / `METER_ROLE_TOKEN_FILE` | `listener` + secret `meter-role-token` (listener-facing services only) | Marks metered rows as listener vs creator. Token via secret, not a host file (see Mac-only table). |

> **L2 seat cap = 100.** This is NOT an env var — it is `plans.l2.seat_cap` in
> the `plans` table (`l2_seat_job.py:15`, `subscription_levels.py`). It is set by
> migration/seed data (see the migration runbook), not by Cloud Run config.

---

## 3. user-api-subscribed (private) — image from the user-tracking service, port 5000

Hosts communities, entitlements, L2 claim/queue, purchases/IAP verify, legal,
user registration, support-id. Reads (`user-tracking/communities_api.py`,
`entitlements_api.py`): `DATABASE_URL`/`DB_*`, plus:

| Env var | GCloud value / secret | Notes |
|---|---|---|
| `DB_PASSWORD` / `DATABASE_URL` | secret `db-password` (in the URL or as its own secret) | shared Cloud SQL |
| `ADMIN_API_KEY` | **secret `admin-api-key`** | Distinct from `GATEWAY_API_KEY`; guards `/communities/admin/*`. **Fail-closed:** unset ⇒ admin surface returns 503 (unreachable). The app never carries it; the subscribed gateway does NOT expose admin routes (`internal_only`). |
| `IAP_VERIFY_MODE` | `apple` or `per_store` | `per_store` = Apple on iOS + Google on Android. `stub` only for tests. |
| `IAP_ALLOW_STUB_STORE` | **unset** (⇒ false) | **Fail-closed.** `entitlements_api.py:59` treats unset/anything-not-true as false, so a `store: "stub"` purchase is REFUSED in prod. Only ON for the Android TEST PURCHASE path in dev. |
| `ALLOW_UNAUTHENTICATED_ENTITLEMENTS` | **unset** (⇒ false) | **Fail-closed.** `entitlements_api.py:292` returns false unless explicitly `true/1/yes`; unset means an unauthenticated entitlement request is rejected. Leave unset in prod. |
| `APPLE_BUNDLE_ID` | `com.audioura.audiotours` | StoreKit 2 JWS `bundleId` pin. |
| **`APPLE_IAP_ENVIRONMENT`** | **`Production,Sandbox`** | **Production-with-Sandbox fallback (LOCAL-764).** TestFlight purchases are signed `Sandbox` even against Production, so a Production-only pin would REJECT every TestFlight buy. The verifier now accepts a comma-separated list (`apple_jws_verifier.py` + both callers). Set `Production,Sandbox` for the TestFlight launch; narrow to `Production` only after TestFlight ends. Unset = check disabled (not recommended in prod). |
| `GOOGLE_PLAY_SA_JSON` | **secret file** `google-play-sa-json` mounted at a path; set the var to that path | Google Play service account for Android IAP verify. Absent ⇒ Google verify unconfigured (returns a handled "unconfigured", not a crash). |
| `GOOGLE_PACKAGE_NAME` | `com.audioura.audiotours` | Play package. |
| `GOOGLE_API_BASE` | default | override only for testing. |
| `EMAIL_MODE` / `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM` | SMTP creds as secrets if email is enabled | optional (community/renewal mail). |
| `ORGANISER_TERMS_VERSION`, `COMMUNITY_*`, `PASS_REMINDER_BEFORE_DAYS`, `RENEWAL_WARN_DAYS` | business defaults | tune as needed; safe defaults exist in code. |
| `GATEWAY_API_KEY` | secret `gateway-api-key` | if the service itself checks inter-service key. |

**Apple verify = Production with Sandbox fallback — VERIFIED FIXED (LOCAL-764).**
The StoreKit 2 JWS verifier pinned the `environment` to a single value, so a
Production deployment would reject TestFlight (Sandbox) transactions. Fixed:
`verify_signed_transaction(expected_environment=…)` now accepts a single string
(strict pin, unchanged) OR an iterable (`Production`, `Sandbox`); the HTTP layer
parses a comma-separated `APPLE_IAP_ENVIRONMENT`. Proven by
`user-tracking/test_local764_apple_env_fallback.py` (5/5) with the LOCAL-598
suite still green (17/17).

---

## 4. map-delivery-subscribed (private) — image `map_delivery/` (its own Dockerfile → `app.py`), port 5005

> Build from `map_delivery/` (NOT the root `map_delivery_service.py`) — the
> GCloud image is `app.py`, which hosts `/tour-by-code/<code>` and the route set
> the app uses (same decisive fix as the storied stack, D358).

Reads: `DB_HOST DB_NAME DB_PASSWORD DB_PORT DB_USER PORT BLOB_STORAGE_TYPE`, plus:

| Env var | GCloud value / secret | Notes |
|---|---|---|
| `DELIVERY_TRACK_FILTER` | `subscribed` | **Required.** `app.py:548` filters served tours to this track so Subscribed shows only subscribed tours. |
| `SUBSCRIBED_STABLE_MIN_SCORE` | `7.2` (or **unset**) | **NEW (LOCAL-770, Michael 2026-10-26).** When set AND `DELIVERY_TRACK_FILTER=subscribed`, Subscribed's list endpoints (`/tours-near`, `/search-tours`) ADDITIONALLY surface an ORIGINAL Stable (`track IN ('beta','storied')` or NULL) tour whose `editor_score >= this value`, plus that original's translations (a translation follows its original's score via `COALESCE(orig.editor_score, t.editor_score)`). **A listing filter, never a copy** — no row is copied, moved or deleted (`app.py` `_track_filter_clause`). **Unset = feature OFF = today's subscribed-only behaviour.** Paid Stable rows are excluded (free only). All other gates still apply (content rating / review_status, community visibility, Free/Paid filter). Stable is unaffected — its map-delivery never reads `editor_score`. Requires the one-time scoring step below so Stable originals HAVE a score. Only `/tours-near` and `/search-tours` apply the track filter; the by-id serving paths (`/download-tour`, `/tour-info`, `/tour-by-code`) are track-agnostic, so a listed Stable tour is already downloadable. |
| `BLOB_STORAGE_TYPE` | `r2` | Tour ZIPs live in Cloudflare R2 (S3-compatible), NOT GCS (see §12). |
| `R2_BUCKET` / `R2_ENDPOINT` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | bucket name + secrets `r2-access-key-id`, `r2-secret-access-key` | Read path for stored tours. |
| `DB_PASSWORD` | secret `db-password` | — |

### One-time scoring step for `SUBSCRIBED_STABLE_MIN_SCORE` (LOCAL-770)

`SUBSCRIBED_STABLE_MIN_SCORE` gates on `editor_score`, so a Stable original with
**no score is never surfaced**. Give every visible Stable original a score ONCE
against Cloud SQL with `tour_editor_score.py` (migration 025 must be applied):

```bash
# 1. DRY-RUN COUNT FIRST (read-only, no model call, no write): how many Stable
#    originals already qualify at >= 7.2, and how many are still unscored.
python3 tour_editor_score.py --count-min-score 7.2 --track beta,storied
#   → "[count-min-score track=beta,storied] visible originals: N; scored >= 7.2: M; still unscored: U (read-only, nothing written)"

# 2. BACKFILL the unscored ones (scores ONLY rows with no score; --track limits
#    scope to the Stable tracks a Subscribed listing would surface).
python3 tour_editor_score.py --backfill --track beta,storied
#   add --dry-run to print the scores + total cost without writing.
```

- **Scope:** `--backfill` already scores only visible ORIGINALS with no score
  (`original_tour_id IS NULL AND is_test IS NOT TRUE AND lat IS NOT NULL AND
  length(tour_content) > 200 AND editor_score IS NULL`); `--track beta,storied`
  (LOCAL-770) further limits it to the Stable tracks via
  `COALESCE(track,'beta') IN (...)` so Subscribed rows are left alone.
- **Writes ONLY `editor_score*`:** `editor_score`, `editor_score_detail`,
  `editor_scored_at` (migration 025). No other column, and never a tour's text,
  audio, price or track — it cannot change what a tour IS, only its starting
  score. Translations are never scored (they show their original's score).
- **Cost (measured, gpt-4.1, 3 runs/tour — SUBMISSION_LOCAL-688.md):** tour 557
  = 7,821 in + 943 out tokens = **~$0.0232 per tour**. For **~300 originals**
  that is **~$6.96** total (≈300 × $0.0232; cheaper if many are already scored —
  the dry-run count in step 1 tells you how many actually need it). A smaller
  model via `EDITOR_SCORE_MODEL=gpt-4o-mini` is ~40× cheaper if cost matters.
- **Safe to re-run:** without `--rescore`, a second backfill scores only rows
  that are still unscored, so interrupting and resuming is harmless.

---

## 5. translation-subscribed (private) — image `translation-service/` Dockerfile, port 5030

Reads: `DB_* OPENAI_API_KEY PORT TOUR_TRACK TRANSLATION_ENGINE TRANSLATION_LLM_MODEL TRANSLATION_PROSE_MODEL TRANSLATION_NAMES_MODEL TRANSLATION_LLM_TIMEOUT TRANSLATION_GUIDEBOOK`.

| Env var | GCloud value / secret | Notes |
|---|---|---|
| `TOUR_TRACK` | `subscribed` | track stamp on translated tours |
| `OPENAI_API_KEY` | secret `openai-api-key` | shared with storied (see §12) |
| `TTS_ENGINE` | `polly` | Inline default for this service only; translation does not HTTP-call the voice service for tour audio. The English voice a listener hears is Kokoro via `polly-tts-subscribed` (§8b). |
| AWS (Polly/Translate) | secrets `aws-access-key-id`, `aws-secret-access-key` | region us-east-1 |
| `DB_PASSWORD` | secret `db-password` | — |

---

## 6. news-orchestrator-subscribed (private) — image `Dockerfile.news-orchestrator`, port 5012

Reads: `DB_* INTERNAL_SERVICE_SECRET NEWS_GENERATOR_URL NEWS_PROCESSOR_URL PORT TRANSLATION_URL`.

| Env var | GCloud value / secret | Notes |
|---|---|---|
| `INTERNAL_SERVICE_SECRET` | secret `internal-service-secret` | inter-service auth to newsletter |
| `NEWS_GENERATOR_URL` / `NEWS_PROCESSOR_URL` / `TRANSLATION_URL` | internal `-subscribed` URLs | — |
| `DB_PASSWORD` | secret `db-password` | — |

App cloud paths `/news-status/<id>` and `/news-download/<id>` proxy to this
service's `/status/<id>` and `/download/<id>` (subscribed manifest).

---

## 7. newsletter-subscribed (private) — image `Dockerfile.newsletter-processor`, port 5017

Reads: `CREDENTIAL_ENCRYPTION_ENABLED DB_* INTERNAL_SERVICE_SECRET NEWS_ORCHESTRATOR_URL PORT`.

| Env var | GCloud value / secret | Notes |
|---|---|---|
| `CREDENTIAL_ENCRYPTION_ENABLED` | `true` | encrypts stored newsletter credentials |
| `INTERNAL_SERVICE_SECRET` | secret `internal-service-secret` | — |
| `DB_PASSWORD` | secret `db-password` | — |

`/decrypt_credentials` is internal-only (handles raw credentials) — NOT exposed
by the gateway (`internal_only` in the subscribed manifest).

---

## 8. tour-editing-subscribed (private) — image `Dockerfile.cloudrun` (CMD `tour_editing_phase2.py`), port 5022

Reads: `DB_* BLOB_STORAGE_TYPE CUSTOM_AUDIO_MAX_SIZE_MB LOCAL_IDENTITY_TOKEN LOCAL_LANGUAGE_STUB_URL POLLY_TTS_URL PORT TOUR_STORAGE_MODE`.

| Env var | GCloud value / secret | Notes |
|---|---|---|
| `TTS_ENGINE` | `polly` | Inline default for this service only (tour-editing's own save-path TTS). The Subscribed English voice is Kokoro via `polly-tts-subscribed` (§8b), reached over `POLLY_TTS_URL` below — not this inline engine. |
| AWS Polly + Comprehend | secrets `aws-access-key-id`, `aws-secret-access-key` | region us-east-1; save routes do TTS (cost-bearing). |
| `BLOB_STORAGE_TYPE` | `r2` | R2 read/persist (§12). |
| `R2_*` | as §4 | — |
| `POLLY_TTS_URL` | `https://polly-tts-subscribed-<proj>.run.app` (§8b) | **Re-point at `polly-tts-subscribed`** (Kokoro), NOT Beta's `polly-tts`. Raise this service's TTS HTTP read timeout to ≥ 300 s (a Kokoro render takes ~150 s). |
| `LOCAL_IDENTITY_TOKEN` / `LOCAL_LANGUAGE_STUB_URL` | **leave UNSET in prod** | local-dev stubs only. |
| `DB_PASSWORD` | secret `db-password` | — |

---

## 8b. polly-tts-subscribed (private) — image `Dockerfile.polly-tts-kokoro` (CMD `polly_tts_service.py`), port 5018

**NEW (LOCAL-768, D667).** The voice (TTS) service with **Kokoro-82M baked in for
IN-PROCESS English rendering**. D667: Michael rated Kokoro better than Polly
neural, and it is cheaper per stop on Cloud Run (see the cost note below). LEAD
ruling: **NO separate Kokoro service** — Kokoro runs in-process inside
`polly_tts_service` (the r1 mode the code already has), so this is the SAME
service/port/endpoints as the plain Polly image, only with the model + engine
deps added and the weights/voice packs baked into the image layer (no cold-start
download).

> **The plain Polly image `Dockerfile.polly-tts` is UNCHANGED and stays
> Polly-only** — it is used by **Beta**, which must keep speaking with Polly.
> Subscribed currently reuses Beta's `polly-tts` read-only; **only Subscribed's
> consumers are re-pointed at `polly-tts-subscribed`** (table at the end of this
> section). Beta's `POLLY_TTS_URL` must NOT change.

Reads (`polly_tts_service.py`): `TTS_ENGINE KOKORO_URL PORT AWS_* PAID_API_LOG`
(+ the `_meter/` role vars when listener-scoped).

| Env var | GCloud value / secret | Notes |
|---|---|---|
| `TTS_ENGINE` | `kokoro` | **Required.** Turns on the Kokoro path. English Polly voices (Joanna/Matthew/Amy/Brian/…) render with Kokoro (`af_heart` female / `am_michael` male); every non-English voice (Tatyana, …) stays Polly. |
| `KOKORO_URL` | **empty string** (`''`) | **Required — must be empty.** Empty ⇒ IN-PROCESS render (the baked model). A non-empty value means "call a host Kokoro service" (the Mac's `:5181`), which does not exist on Cloud Run — leaving it set would make every English request fail the host call and fall back to Polly. Set it explicitly empty (don't just unset, to be unambiguous). |
| AWS (Polly) | secrets `aws-access-key-id`, `aws-secret-access-key` | region us-east-1. Still needed: non-English voices and any Kokoro failure fall back to Polly so a tour never loses audio. |
| `PORT` | `5018` (or Cloud Run's injected `$PORT`) | same port as the plain image. |
| `METER_ROLE` / `METER_ROLE_TOKEN` / `METER_ROLE_TOKEN_FILE` | `listener` + secret `meter-role-token` | listener-facing (same as the other listener services); Kokoro renders meter at $0, Polly fallbacks at the Polly rate. |
| `DAILY_PAID_LIMIT_USD` | e.g. `50` (or unset) | only Polly fallbacks are billed; Kokoro is free. |

**Cloud Run resources (measured — see SUBMISSION_LOCAL-768.md):**

| Setting | Value | Why |
|---|---|---|
| CPU | **4 vCPU / 4 GiB — REQUIRED (LEAD 2026-10-26)**. 2 vCPU is NOT allowed: callers time out at `tts_timeout.synthesize_timeout` = 30 + 0.05×chars s (145 s for a 2,300-char stop), and 2 vCPU needs ~147 s, so stops would be lost to the timeout and fall back to Polly. | Kokoro is CPU torch on Cloud Run (no GPU). Measured warm 2,300-char stop: **2 vCPU ≈ 147 s, 4 vCPU ≈ 70 s, 8 vCPU ≈ 45 s** (native-arch proxy). Cost/stop is ~flat across these (more vCPU finishes proportionally faster), so **4 vCPU is both the cheapest and ~2× faster than 2** — prefer it. 2 vCPU is the floor that keeps Cloud Run's 2 vCPU : 4 GiB minimum ratio. |
| Memory | **4 GiB** | torch + the 82M model + ffmpeg buffers. 4 GiB is the minimum stable; the model baked + warmed sits comfortably under it. |
| `--concurrency` | **1** | A render pins the CPU for the whole ~150 s; a second concurrent request would double the time for both and risk the request timeout. One request per instance, scale out with instances. |
| Request timeout | **≥ 300 s** (set 300) | A single 2,300-char stop takes ~150 s on 2 vCPU (cold ~160 s); a longer stop needs more. 300 s gives headroom; the default 60 s / 120 s would kill every real render. |
| `--min-instances` | **0** | Scale to zero when idle (cost). Cold start to `/health` ready is **~5 s** (weights are baked — no download), so a cold hit adds only ~5 s before the ~150 s render. If p50 latency matters, set `--min-instances 1` to keep one warm (the model loads at start). |
| `--max-instances` | **10** to start (a tour's stops render in parallel; each instance = one render) | each instance = one in-flight render (concurrency 1). |

**Cost per stop (Cloud Run Tier-1 request-based pricing, 2 vCPU + 4 GiB):**
at the measured ~155 s/stop, cpu `2 × $0.000024 × 155 = $0.00744` + mem
`4 × $0.0000025 × 155 = $0.00155` + request `~$0` ≈ **$0.0090/stop**, vs Polly
**neural** for the same 2,300 chars `2300 × $16/1M = $0.0368/stop`. In-process
Kokoro is **~4× cheaper per stop** than Polly neural (and stays cheaper until a
render exceeds ~630 s). The real trade-off is **latency** (~150 s vs sub-second),
hence `--concurrency 1`, timeout ≥ 300 s, and warm-instance options above.

**`/health`** reports `tts_engine`, `kokoro_mode` (`in_process` here),
`model_loaded`, and `ffmpeg_present` — so "healthy" means "this instance can
actually render Kokoro MP3", not merely "Polly reachable". Treat
`model_loaded == true && ffmpeg_present == true` as the readiness gate.

### Subscribed services that must point at `polly-tts-subscribed` (not Beta's `polly-tts`)

Every Subscribed service that calls the voice service reads **`POLLY_TTS_URL`**
(default `http://polly-tts-1:5018`, `tts_timeout.py` sizes the read timeout to
text length). On GCloud, set `POLLY_TTS_URL` on each of these to the private
`polly-tts-subscribed` URL — and raise their TTS HTTP read timeout to ≥ 300 s
because a Kokoro render takes ~150 s (a 60–120 s client timeout would abort it):

| Subscribed service | Var to set | Set to |
|---|---|---|
| tour-editing-subscribed (§8) | `POLLY_TTS_URL` | `https://polly-tts-subscribed-<proj>.run.app` |
| tour-generator-subscribed (§11, via `tour_generation_modernized.py`) | `POLLY_TTS_URL` | same |
| custom-audio-subscribed (§11) | `POLLY_TTS_URL` | same |
| news-processor-subscribed (`news_processor_service.py`) | `POLLY_TTS_URL` | same (if the subscribed news path is stood up) |

> These are the services whose **own `TTS_ENGINE` env is irrelevant** — they do
> not run `polly_tts_service` inline, they HTTP-call it. The engine choice
> (Kokoro vs Polly) lives entirely in `polly-tts-subscribed`'s env above. The
> `TTS_ENGINE=polly` rows in §5 and §8 describe only each service's own inline
> default; the English voice actually heard by a Subscribed listener is decided
> by `polly-tts-subscribed`.

---

## 9. tour-id-resolution-subscribed (private) — image for `tour_id_resolution_service.py`, port 5025

Reads: `DB_HOST DB_NAME DB_PASSWORD DB_PORT DB_USER`. Only the DB + `DB_PASSWORD`
secret. Resolves `/tour/<id>/resolve` (deep-link id → tour).

---

## 10. treats-subscribed (private) — image for `treats_service.py`, port 5007

Reads: `DB_* PORT`. `DB_PASSWORD` secret. Serves `/treats-near/*` and
`/treats-near-places`.

---

## 11. tour-generator-subscribed, voice-subscribed, custom-audio-subscribed (private)

| Service | Port | Image | Required env |
|---|---|---|---|
| tour-generator-subscribed | 5000 | `Dockerfile.generator` | `DATABASE_URL`/`DB_*` (+ `DB_PASSWORD` secret), `OPENAI_API_KEY` (secret `openai-api-key`), `GEMINI_API_KEY` (secret `GEMINI_API_KEY` — **UPPERCASE name**, note), `SERP_API_KEY` (secret `serp-api-key`) + `SERP_PROVIDER=serper`, `STORIED_MODE=true` (D717), `GATEWAY_API_KEY` (secret). Hosts `/tour/share`. Only the generator reads SERP/Gemini. |
| voice-subscribed | 5008 | voice image (`voice_control/app.py`) | `OPENAI_API_KEY` (secret). Hosts `/parse_voice_search`, `/process-voice-command`. |
| custom-audio-subscribed | 5023 | custom-audio image | `DB_*` (+ `DB_PASSWORD` secret), `BLOB_STORAGE_TYPE=r2` + `R2_*`, AWS Polly secrets. Hosts `/tour/<id>/stop/<n>/custom-audio`, `/audio-versions`, `/audio-metadata`. |

> If a `-subscribed` build of generator/voice/custom-audio is not stood up at
> launch, those app features degrade to the Preview-only / empty state
> (storied-compat helpers) — they will not crash the app, but the gateway will
> return the backend's own error since the route exists in the manifest.

---

## 12. Shared secrets (reused from the storied deployment — names only)

Per `GCLOUD_STORIED_START_HERE.md` (read-only reference; not edited here):

| Purpose | Secret NAME | Used by |
|---|---|---|
| OpenAI | `openai-api-key` | generator, translation, voice |
| Gemini | `GEMINI_API_KEY` (UPPERCASE) | generator only |
| Serper (SERP) | `serp-api-key` (+ `SERP_PROVIDER=serper`) | generator only |
| AWS Polly/Comprehend/Translate | `aws-access-key-id`, `aws-secret-access-key` | translation, tour-editing, custom-audio |
| DB password | `db-password` | all DB services |
| Gateway key | `gateway-api-key` | gateway + inter-service |
| Admin key | `admin-api-key` | user-api (admin surface) |
| Recovery pepper | `recovery-code-pepper` | orchestrator (recovery) |
| Attestation nonce | `attestation-nonce-secret` | gateway |
| Internal service | `internal-service-secret` | news-orchestrator, newsletter |
| Google Play SA | `google-play-sa-json` (file mount) | user-api (Android IAP) |
| Cloudflare R2 | `r2-access-key-id`, `r2-secret-access-key` | map-delivery, tour-editing, custom-audio |

### Tour storage on GCloud

Tour ZIPs are stored in **Cloudflare R2** (S3-compatible object store) via
`BLOB_STORAGE_TYPE=r2` + `R2_BUCKET`/`R2_ENDPOINT`/`R2_ACCESS_KEY_ID`/
`R2_SECRET_ACCESS_KEY` (`blobstorage.py`), NOT Google Cloud Storage. Storied
reads/writes the same R2 bucket. **Subscribed can safely share the same R2
bucket** because object keys are tour-id scoped and the DB `track` column keeps
subscribed rows distinct — the same key is never written by two tracks for
different content. If isolation is preferred, set a distinct `R2_BUCKET` (or key
prefix) for Subscribed; functionally the shared bucket is safe.

---

## 13. Fail-closed summary (what happens when a security var is UNSET)

| Var | Unset behaviour | Deploy action |
|---|---|---|
| `GATEWAY_API_KEY` | gateway rejects every api_key route (503/401) | set secret |
| `ADMIN_API_KEY` | admin surface unreachable (503) | set secret |
| `RECOVERY_CODE_PEPPER` | recovery routes DISABLED (503) | set secret |
| `IAP_ALLOW_STUB_STORE` | false ⇒ stub purchases refused | **leave unset in prod** |
| `ALLOW_UNAUTHENTICATED_ENTITLEMENTS` | false ⇒ unauthenticated entitlement refused | **leave unset in prod** |
| `APPLE_IAP_ENVIRONMENT` | env check disabled (any environment accepted) | set `Production,Sandbox` for TestFlight launch |
| `DAILY_PAID_LIMIT_USD` | no spend ceiling (tours never blocked) | set a ceiling for cost safety |
| `GOOGLE_PLAY_SA_JSON` | Google verify unconfigured (handled, not a crash) | mount secret file for Android IAP |


---

## 14. failure_events recorder (LOCAL-785 / D723)

Every server failure and every app failure is recorded to one Cloud SQL table,
`failure_events` (migration **054**), by the shared recorder `failure_log.py`.
`failure_report.py --since 24h|7d` reads it for LEAD. Nothing new to deploy
beyond **applying migration 054** and **one gateway route** — the recorder
writes to the DB each service ALREADY connects to.

### What each service needs

The recorder reuses each service's existing DB connection, so **no new env var
is required**. It reads `DATABASE_URL` if set, else the same
`DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/DB_PORT` the service already uses — exactly
the vars listed per service above. If the DB is unreachable the recorder falls
back to a `FAILURE_EVENT {json}` line on stdout (visible in Cloud Logging), so a
failure is never lost even during a DB outage.

| Service | Records via | DB env it already has |
|---|---|---|
| tour-orchestrator-subscribed (§2) | `failure_log` + `@errorhandler` + job-failure/refusal sites (Generate Now + worker) | `DB_*` (§2) — already present |
| tour-generator-subscribed (§11) | clean-fail evidence (existence-gate / PHASE 3C / thin_evidence / no_matching_places) + `@errorhandler` | `DATABASE_URL`/`DB_*` (§11) — already present |
| translation-subscribed (§5) | `@errorhandler(Exception)` | `DB_*` (§5) — already present |
| tour-id-resolution-subscribed (§9) | 404 (tour/edit-id not found) + 5xx + `@errorhandler` | `DB_*` (§9) — already present |
| map-delivery-subscribed (§4) | download 5xx + `@errorhandler` (a NORMAL 402 purchase gate is NOT recorded) | `DB_*` (§4) — already present |
| user-api-subscribed (§3) | hosts **POST `/client-failure`** (the app's sink) + `@errorhandler` | `DATABASE_URL`/`DB_*` (§3) — already present |

> `failure_log.py` is COPY'd into the user-api image (it lives beside `app.py`
> in `user-tracking/`) and sits at the repo root for every other image's
> `COPY . .`. No extra build step.

Optional tunable (all services): **`FAILURE_LOG_DB_TIMEOUT`** — the recorder's
connect+statement timeout in seconds (default **1**). Leave at the default; the
point is that a slow/down DB never stalls a request.

Test-only (orchestrator): **`FAILURE_LOG_TEST_HOOK=1`** turns on a request hook
that raises on `X-Force-Failure: 1` (or `?force_failure=1`) so a live test can
prove the recorder writes a row without a real failure or any spend. **Leave
UNSET in production.**

### The one new gateway route (subscribed manifest only)

`api-gateway/gateway_routes.subscribed.yaml` gains:

```yaml
  - public_path: /client-failure
    backend: user-api
    upstream: /client-failure
    methods: [POST]
    auth: api_key
```

The app's `FailureReporter` POSTs here (via `Endpoints.post(Service.userDb,
'/client-failure', …)`); user-api rate-limits it to 20/hour per user and caps
the body at 8 KB before storing. It is NOT added to the Beta/Storied manifest
(`gateway_routes.yaml`): that stack routes `/user` to news-orchestrator and has
no user-api backend, so there is nothing there to receive it. Subscribed is the
authoritative stack for this feature (D708).

### Auto-triage (seeded; LEAD overrides with `failure_report.py --mark`)

`failure_log.auto_triage()` seeds `triage` (`triage_source='auto'`); the first
matching rule wins:

| Rule | → triage |
|---|---|
| error_code ∈ {venue_no_verifiable_content, venue_misread, stops_not_colocated, request_unclassifiable, no_matching_places_in_area, content_quality_insufficient, factual_integrity, venue_closed, exhibition_closed} | `ux` |
| error_code ∈ {exhibition_not_found, by_reference_no_material} | `absence` |
| error_code == generation_failed (or purchase_required_for_creator) | `our_bug` |
| else http_status is 5xx | `our_bug` |
| else exception_type is network/timeout-ish (timeout, connection*, socket, ssl, clientexception, oserror, …) | `external` |
| else any other exception_type (a real crash) | `our_bug` |
| else | `unknown` |

Severity for the priority score: our_bug=3 (blocking), external/absence=2
(degraded), ux/unknown=1 (cosmetic). Score = distinct_users × severity ×
recency_weight (≤1d 1.0, ≤7d 0.6, else 0.3).

### 90-day retention

OUT of scope for LOCAL-785 (D723). This feature only writes and reads the table;
a retention/cleanup job is a separate ticket.
