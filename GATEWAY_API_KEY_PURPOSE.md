# Gateway API Key — Purpose, Current & Future Role (2026-06-24)

Summary of the design decision and reasoning for the **`GATEWAY_API_KEY`** (`X-API-Key`). **Decision: we keep this key permanently — it stays as a layer even after app attestation is enabled.**

## What it is
- A **static shared secret** that the **`api-gateway`** Cloud Run service checks via the `X-API-Key` header (`_require_api_key`, constant-time compare, fail-closed).
- Baked into the mobile app **at build time** via `--dart-define=GATEWAY_API_KEY=…` (sourced from a gitignored `build_secrets.env`). The same value is configured on the gateway as its `API_KEY` env / Secret Manager secret. They must match exactly or the app gets 401.
- The **same value ships in every install** (all users carry the same key).

## What it is NOT (important)
- It is **NOT a Google Cloud / AWS credential.** It cannot access GCloud, GCP project resources, Secret Manager, AWS, or the database. The ONLY thing that recognizes it is our own gateway.
- It **cannot bypass our services.** There is no "GCloud" that accepts this key — it is only meaningful as the password our gateway checks. Cloud access uses OAuth/service-account (OIDC) tokens that live **server-side only** (never in the app).

## Honest security properties
- **Encrypted in transit** (TLS/HTTPS), but **not a secret at rest in the client** — a static key compiled into the app can be extracted by decompiling the APK or proxying the app's HTTPS traffic on a controlled device. You **cannot hide a secret in a client app.**
- Therefore it does **NOT** prove a request came from the genuine, unmodified app. It is a **coarse gate**, not an identity proof. Conceptually it is like a **"publishable" key** (Google Maps / Firebase / Stripe publishable keys are shipped in clients on purpose) — an identifier + gate, protected by *other* mechanisms.
- **Worst case if leaked:** an attacker calls our **public gateway endpoints** directly (tour/news generation) → **cost abuse** (OpenAI/Polly spend). It does NOT expose cloud secrets. This risk is **bounded by per-user quota + server-side rate limiting** (already enforced).

## Current purpose (Beta)
1. **Coarse gate** — blocks random internet/bot traffic from hitting the gateway.
2. **Revocation / rotation handle** — on abuse, rotate the key (update gateway `API_KEY` + `build_secrets.env`, ship an app update) to cut off old/leaked clients.
3. **Interim client gate** — until attestation is implemented, this is the *only* client-side gate, so it must stay.

## Future role — KEPT even after attestation (Play Integrity / App Attest)
We will add **app attestation** (the real "genuine, unmodified app" boundary) post-Beta. The API key is **not removed** — it becomes a complementary layer:
- **First-line cheap pre-filter** — reject obviously-bad traffic with a fast header check *before* doing the heavier attestation verification (saves cost/latency, mitigates trivial DoS/bot floods).
- **Kill-switch / rotation handle** — still the fastest way to cut off all clients of a given build.
- **Defense in depth** — layered with attestation (strong identity) + per-user quota (abuse cap) + cert pinning + short-lived tokens. No single layer is the whole defense.

**Rule going forward:** the gateway API key is a permanent, low-cost outer gate. Attestation is the strong inner boundary that proves app authenticity. We keep both.

## Operational notes
- **Rotate** by updating the gateway's `API_KEY` (Cloud Run env / Secret Manager) **and** `build_secrets.env`, then shipping an app build. Old clients 401 until updated.
- **Backup:** the canonical value lives on the gateway (Secret Manager / Cloud Run env); also keep it in a password manager. `build_secrets.env` is gitignored — never commit it or paste the value into ClickUp/commits/logs.
- Recommended key strength if ever regenerated: ≥32 random bytes (e.g. `openssl rand -hex 32`).
