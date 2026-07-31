# Storied Feature Flags — Master Reference

All environment variables controlling Storied behavior. This document is the single source of truth for what each flag does, its default, and where it's consumed.

---

## Flags

| Variable | Default | Service | Purpose |
|----------|---------|---------|---------|
| `STORIED_MODE` | `false` | tour-generator | Master switch. When `true`: enables spine generation, fact sheets, story-type assignment, persona injection, de-repetition rewrite, tour hook intro, improved directions. When `false`: pipeline runs identically to Beta. |
| `ATTESTATION_MODE` | `off` | api-gateway | Controls attestation verification. `off`: skip entirely. `log_only`: verify tokens, log results, always allow. `enforce`: block invalid tokens (NOT for Aug 1). |
| `ATTESTATION_ENFORCED` | `false` | api-gateway | Legacy flag. Prefer `ATTESTATION_MODE`. When `true` + `ATTESTATION_MODE=enforce`: rejects missing/invalid tokens with 403. |
| `BASE_URL` | `https://audioura.io` | tour-generator | Base URL for share links returned by `POST /tour/share`. |
| `REFERRAL_BASE_URL` | `https://audioura.io` | tour-generator | Base URL for referral links returned by `POST /referral/create`. |
| `DATABASE_URL` | `postgresql://admin:admin@localhost:5433/audiotours` | tour-generator | Postgres connection URL for persona store, tour cache, shared tours, referrals. |
| `OPENAI_API_KEY` | (required) | tour-generator | OpenAI API key for all generation calls. |
| `GATEWAY_API_KEY` | (required) | api-gateway, tour-generator | Shared secret for API key authentication on cost-bearing endpoints. |
| `PLAY_INTEGRITY_API_KEY` | (empty) | api-gateway | Google Cloud API key for Play Integrity verification. Only needed when `ATTESTATION_MODE=log_only` or `enforce`. |
| `APP_PACKAGE_NAME` | `com.audioura.audiotours` | api-gateway | Android package name for Play Integrity API calls. |
| `APP_BUNDLE_ID` | `com.glikfamily.audioura` | api-gateway | iOS bundle ID for App Attest verification. |

---

## Flag Interactions

- `STORIED_MODE=false` → entire Storied pipeline disabled. No spine, no facts, no persona, no rewrite, no hook. Tour output identical to Beta.
- `ATTESTATION_MODE=off` → no attestation logging or verification occurs. Headers ignored.
- `ATTESTATION_MODE=log_only` → tokens parsed and logged but NEVER block a request.
- `DATABASE_URL` absent → persona, cache, sharing, referrals silently skip (graceful degradation).

---

## Where Each Flag is Consumed

| Flag | Files |
|------|-------|
| `STORIED_MODE` | `generate_tour_text.py`, `Dockerfile.generator`, `docker-compose-master.yml` |
| `ATTESTATION_MODE` | `api-gateway/main.py`, `attestation_enforce_gate.py`, `docker-compose-master.yml` |
| `BASE_URL` | `sharing_endpoints.py`, `docker-compose-master.yml` |
| `REFERRAL_BASE_URL` | `referral_endpoints.py`, `docker-compose-master.yml` |
| `DATABASE_URL` | `persona_preference_store.py`, `persona_endpoints.py`, `sharing_endpoints.py`, `referral_endpoints.py`, `tour_cache_layer1.py`, `run_storied_db_migration.py` |

---

## Release Timeline

| Date | Flag State | Reason |
|------|-----------|--------|
| Pre-Aug 1 (development) | `STORIED_MODE=false`, `ATTESTATION_MODE=off` | Pipeline untouched during development |
| Aug 1 (tester build) | `STORIED_MODE=true`, `ATTESTATION_MODE=log_only` | Storied active, attestation logging |
| Post-testing (TBD) | `STORIED_MODE=true`, `ATTESTATION_MODE=enforce` | Full enforcement after log data reviewed |
