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
| `METER_ROLE_TOKEN_FILE=/…/token` bind-mount | Host file bind-mount | BOTH are required (the code compares them): `METER_ROLE_TOKEN` env from secret `meter-role-token`, AND the same secret mounted as a file `--update-secrets /opt/meter/role_token=meter-role-token:latest` with `METER_ROLE_TOKEN_FILE=/opt/meter/role_token`. Without both, no row is 'listener' and DAILY_PAID_LIMIT_USD counts nothing. Table `paid_api_calls` comes from migration 053. |
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
| `APP_BUNDLE_ID` | `com.glikfamily.audioura` | iOS bundle (attestation). |
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
| `STORIED_MODE` | `false` | Subscribed is not the storied flag. |
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
| `APPLE_BUNDLE_ID` | `com.glikfamily.audioura` | StoreKit 2 JWS `bundleId` pin. |
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
| `BLOB_STORAGE_TYPE` | `r2` | Tour ZIPs live in Cloudflare R2 (S3-compatible), NOT GCS (see §12). |
| `R2_BUCKET` / `R2_ENDPOINT` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | bucket name + secrets `r2-access-key-id`, `r2-secret-access-key` | Read path for stored tours. |
| `DB_PASSWORD` | secret `db-password` | — |

---

## 5. translation-subscribed (private) — image `translation-service/` Dockerfile, port 5030

Reads: `DB_* OPENAI_API_KEY PORT TOUR_TRACK TRANSLATION_ENGINE TRANSLATION_LLM_MODEL TRANSLATION_PROSE_MODEL TRANSLATION_NAMES_MODEL TRANSLATION_LLM_TIMEOUT TRANSLATION_GUIDEBOOK`.

| Env var | GCloud value / secret | Notes |
|---|---|---|
| `TOUR_TRACK` | `subscribed` | track stamp on translated tours |
| `OPENAI_API_KEY` | secret `openai-api-key` | shared with storied (see §12) |
| `TTS_ENGINE` | `polly` | **No Kokoro on GCloud** (§8). |
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
| `TTS_ENGINE` | `polly` | **Polly only on GCloud.** `polly_tts_service.py` defaults to `polly`; `kokoro` requires the Kokoro model and is not deployed to Cloud Run. |
| AWS Polly + Comprehend | secrets `aws-access-key-id`, `aws-secret-access-key` | region us-east-1; save routes do TTS (cost-bearing). |
| `BLOB_STORAGE_TYPE` | `r2` | R2 read/persist (§12). |
| `R2_*` | as §4 | — |
| `POLLY_TTS_URL` | internal polly-tts URL (if split) or inline | — |
| `LOCAL_IDENTITY_TOKEN` / `LOCAL_LANGUAGE_STUB_URL` | **leave UNSET in prod** | local-dev stubs only. |
| `DB_PASSWORD` | secret `db-password` | — |

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
| tour-generator-subscribed | 5000 | `Dockerfile.generator` | `DATABASE_URL`/`DB_*` (+ `DB_PASSWORD` secret), `OPENAI_API_KEY` (secret `openai-api-key`), `GEMINI_API_KEY` (secret `GEMINI_API_KEY` — **UPPERCASE name**, note), `SERP_API_KEY` (secret `serp-api-key`) + `SERP_PROVIDER=serper`, `STORIED_MODE=false`, `GATEWAY_API_KEY` (secret). Hosts `/tour/share`. Only the generator reads SERP/Gemini. |
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
