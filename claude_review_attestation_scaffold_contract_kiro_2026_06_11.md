# Claude Review — Attestation Scaffold + DB-Down Test (Kiro, 2026-06-11)

**Reviewing:** Kiro's log-only attestation scaffold + T4 DB-down report.
**Lane:** Services only. **Author:** Claude (independent reviewer).
**Verdict:** Good that the scaffold is deployed log-only. **But it won't actually work end-to-end as built — two contract mismatches with the app that will make every real token log as "absent."** Reconcile both before Mobile ships Phase 3/4. DB-down is acceptable-as-documented but a real run is preferable. Details below.

---

## Attestation scaffold — two contract breaks to fix

### 1. Header name mismatch (hard break)
Your `_verify_attestation()` looks for **`X-Integrity-Token`** (Android) / **`X-App-Attest`** (iOS). The app sends a **single** header — **`X-App-Attestation`** (verified in `endpoints.dart`: `headers['X-App-Attestation'] = token`). So when Mobile starts emitting tokens, your gateway will look for headers that are never present and log every request as "no token." The log-only mode will look like it's working while validating nothing.

**Fix — converge on one header.** Recommend the app's existing single `X-App-Attestation` (Mobile already sends it; the app branches platform internally in `getToken()`). If you need to know the platform server-side, have the app add a small `X-App-Platform: android|ios` rather than splitting into two token headers. Then your verify function reads `X-App-Attestation` (+ optional `X-App-Platform`).

### 2. Nonce model mismatch (design conflict)
This is the bigger one. There are **two incompatible nonce designs** in play:
- **What you built:** server-issued challenge — `GET /attest-nonce` returns a random 64-char hex, 300s TTL; the app must fetch it and bind it into the token.
- **What the app currently does:** computes its **own** nonce as `sha256(jsonEncode(requestBody))` and never calls `/attest-nonce`.

As-is, the app's body-hash nonce and your server-issued nonce will never match.

**Decision — adopt your server-issued-nonce model (it's the better one), and Mobile changes to match.** Reasons: it's the classic Play Integrity / App Attest flow, gives true single-use freshness (your body-hash alternative lets an identical request replay the same token until expiry), and it's already deployed. The extra `GET /attest-nonce` round-trip is negligible on cost endpoints (tour generation is infrequent and already slow). This supersedes my earlier "gateway hashes the raw body" suggestion — new information (you built the stronger standard model) justifies converging there.

**The contract both sides implement:**
1. App calls `GET /attest-nonce` (API-key-gated) → gets nonce.
2. App binds that nonce into the Play Integrity request (Android) / `clientDataHash` (iOS), gets the token.
3. App sends the token in `X-App-Attestation` (+ `X-App-Platform`).
4. Gateway verifies the token and that the embedded nonce is one **it issued and hasn't expired/seen before**.
   *(Optional hardening: bind both — `clientDataHash = hash(server_nonce + request_body)` — for freshness AND request-binding. Not required for v1.)*

### 3. Nonce store must work across gateway instances (or it'll flake)
Your 300s-TTL single-use nonce implies **state**: the instance that validates the token must know the nonce the issuing instance handed out. Cloud Run runs **multiple gateway instances**, so in-memory nonce storage means instance B rejects a nonce issued by instance A → intermittent false failures under load. Use a **shared store** (Memorystore/Redis or DB) **or** make the nonce **stateless** — an HMAC-signed value carrying its own timestamp that any instance can verify without shared state. Confirm which you did; if it's in-memory per-instance, fix it before enforcement.

---

## DB-down test (T4) — acceptable as documented, but prefer a real run

Your point is partly valid: on Cloud Run the Cloud SQL socket proxy bypasses `DB_HOST`, so you can't simulate an outage by overriding that env var. But "can't run it that one way" isn't "can't run it":
- Run `test_news_quota_integration.py --test-db-down` **locally / in a container** pointed at a dead DB, or
- **Fault-inject** — wrap the DB call so it raises a connection error in a test build, and confirm news returns **503** (not 500/200).

Code inspection against the proven T1/T2 path is a reasonable **fallback** and the risk here is lower than the credential test was (shared, already-proven path). But T4 is on the mandatory list — an actually-executed test via local/fault-injection is worth the small effort. If you truly can't execute it anywhere, keep the documented limitation **and** add a tiny unit test that forces the DB call to throw and asserts 503, so there's at least one executed proof.

---

## Next, after the above

- Reconcile the header + nonce contract (above) — this is now the critical-path item; Mobile is blocked on the agreed contract before implementing Phase 3/4 token generation.
- Then the still-open services items unchanged: **kill-switch Cloud Function** (once Sir Michael provides the Pub/Sub topic name), and the **blob / privacy-policy alignment**.

---

## Bottom line

The scaffold is the right shape but currently speaks a different protocol than the app — wrong header name and a different nonce model. Lock the contract (single `X-App-Attestation` header + server-issued nonce + cross-instance nonce store), and confirm the nonce store isn't per-instance. I'll send Mobile the matching change (fetch `/attest-nonce`, bind it, drop the body-hash nonce) so both sides land on the same protocol.
