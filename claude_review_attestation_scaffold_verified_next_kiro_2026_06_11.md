# Claude Review — Attestation Scaffold Fixes Verified + What's Next (2026-06-11)

**Reviewing:** Kiro's header + stateless-nonce fixes in `api-gateway/main.py`.
**Lane:** Services only. **Author:** Claude (independent reviewer).
**Verdict:** Both contract fixes are **correctly implemented** — the gateway now matches the app, and the nonce is multi-instance safe. The scaffold is sound for log-only. **Three things to lock before any enforcement**, and a clear pivot for what's next (attestation enforcement is *not* on the launch-critical path — spend backstop is).

---

## Verified ✅

- **Single header.** `_verify_attestation()` reads `X-App-Attestation` (+ optional `X-App-Platform`) — matches what the app sends (`main.py:75-76`). The old `X-Integrity-Token`/`X-App-Attest` mismatch is gone.
- **Stateless HMAC nonce.** `_issue_nonce()` → `<ts_hex>.<rand>.<hmac>`; `_verify_nonce()` recomputes the HMAC and checks TTL (`:100-129`). Any Cloud Run instance can issue and verify with the shared secret — the multi-instance flake risk I raised is solved correctly.
- **Log-only behavior + `/attest-nonce`** (API-key-gated) are wired; `/health` reports the mode. Good.

---

## Lock these before enforcement is ever flipped on

These don't matter in log-only, but they're the difference between "logging shell" and "real security gate." Capture them now so they're not forgotten.

1. **The gate currently verifies nothing — by design, but be clear about it.** `_verify_attestation()` logs token presence and returns pass (`:95-97`, "always passes in scaffold"). It does **not** yet (a) call the Play Integrity API / verify the App Attest signature, nor (b) extract the embedded nonce and call `_verify_nonce()`. That's the real work remaining before enforcement — and it's substantial (Google/Apple verification, nonce extraction, verdict checks). Today "attestation" is a log line, not a check. Fine for now; just don't mistake the scaffold for a working gate.

2. **Set `ATTESTATION_NONCE_SECRET` in prod.** The HMAC key defaults to `'default-nonce-hmac-key-change-in-prod'` (`:48`). If that env var isn't set on the deployed service, the signing key is a public known value → anyone can forge valid nonces. Put a real secret in Secret Manager and wire it before enforcement. (Harmless in log-only.)

3. **Stateless = fresh, but not single-use (replay window).** Because there's no record of spent nonces, a captured `(nonce, token)` pair can be **replayed for up to the 300s TTL**. That's the inherent trade for going stateless. Acceptable for v1 because per-user **quota (entitlements, fail-closed) is the real spend cap** and attestation is anti-mimicry — but make it a conscious decision. Mitigations, cheapest first: shorten `NONCE_TTL_SECONDS` to ~120s; bind the request body into the token's `clientDataHash` (so a replay can only repeat the *same* request, not pivot to a costlier one); add a small used-nonce cache (Memorystore) only if replay proves to be a real problem.

---

## What's next — sequencing (this is the important part)

**Attestation enforcement is a post-launch rollout** (log-only → enforce). The contract is now locked and the gateway is live in log-only, so the remaining attestation work — real token verification here, and Mobile's Phase 3/4 — **does not block first store submission.** Park it. Don't enforce before launch.

That frees the lane. Priorities to July 1:

**Kiro (services), in order:**
1. Capture the three lock-items above (5-minute note + set the secret when prod is configured). Then **stop** further attestation work — it's parked.
2. **Kill-switch Cloud Function** — the moment Sir Michael gives you the Pub/Sub topic name, write + deploy the function that sets cost services to `--max-instances=0` on the budget-exceeded message. This is the real spend protection and is higher priority than attestation right now.
3. **Blob / privacy-policy alignment** — close the open item against `PRIVACY_POLICY.html`.
4. **News cloud paths** — *only if news is in v1 scope* (deploy news-orchestrator + newsletter to Cloud Run, add gateway routes). Confirm scope with Sir Michael first.
5. **Execute the DB-down test** (or a unit test that forces the DB call to throw → assert 503) so T4 has one real run, not inspection-only.

**Sir Michael (you):**
1. **Create the GCP budget + Pub/Sub topic** (per `OWNER_ACTIONS_budget_and_credentials_2026_06_11.md`, ~$300) — this is the single highest-leverage thing on your plate; it unblocks Kiro's kill-switch and protects you the moment you have real installs.
2. **Decide encrypt-at-rest direction** (KMS now vs session-token later) — needed before real users connect news logins.
3. **Decide whether news is in v1 scope** — it gates items 3-4 above for both Kiro and Mobile.
4. Host `PRIVACY_POLICY.html` at an HTTPS URL + finish the Play/Apple org registration.

**Mobile:** nothing urgent. The attestation contract doc is ready for Phase 3/4 **after** launch. Don't start it now.

---

## Bottom line

The scaffold fixes are correct and the app↔gateway contract is locked — good. Note the three pre-enforcement lock-items, then treat attestation as **parked until after first submission**. The live critical path is the **spend backstop** (your budget/Pub-Sub → Kiro's kill-switch) and the **news-scope decision**, not attestation.
