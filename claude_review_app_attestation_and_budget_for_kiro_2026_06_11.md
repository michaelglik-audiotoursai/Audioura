# FOR KIRO (Amazon-Q) — Anti-Mimicry: Attestation Verification + Hard Budget Cap (2026-06-11)

**Lane:** Cloud services (gateway / backend / GCP billing) — services only. **Author:** Claude.
**Launch gate (v1):** an illicit client must not be able to use the extracted `X-API-Key` to drive Audioura's
cost-bearing services. Two parts: **(1)** verify app-attestation tokens server-side on cost-bearing endpoints;
**(2)** a **hard GCP spend cap** as the always-on backstop. Companion app doc:
`REVIEW_FOR_MOBILE_AQ_app_attestation_2026_06_11.md`.

> Context: `X-API-Key` is extractable from the APK, so it is not a real boundary. Per-user quotas help but can be
> multiplied by minting new `secret_id`s. Attestation closes the mimicry hole; the budget cap bounds worst-case spend.

---

## Part 1 (MUST for the launched platform) — Verify attestation server-side

Gate the **cost-bearing** endpoints behind attestation verification, in addition to the existing API key:
- `/generate-complete-tour`, `/generate-news`, and the translate/with-audio endpoints. (Read-only/status routes can stay key-only.)

**The app will send a platform attestation token** (header, e.g. `X-Integrity-Token` for Android Play Integrity,
`X-App-Attest` for iOS App Attest — final header names per the Mobile doc). The backend must:

1. **Android — Play Integrity:** verify the integrity token via the Play Integrity API (server-to-server). Check the
   verdict: app recognized + licensed, device integrity (MEETS_DEVICE_INTEGRITY), and that the token's **nonce**
   matches one you issued recently (anti-replay). Reject emulators/tampered/unrecognized.
2. **iOS — App Attest:** on first use, register the device's attestation public key (`attest`); on each request,
   verify the **assertion** signature against that key and a server nonce/counter (anti-replay). Reject if invalid.
3. On missing/invalid/expired/replayed token → **403** `{"error":"attestation_failed"}`; serve nothing.
4. **Nonce issuance:** add a small `GET /attest-nonce` (key-auth) that returns a short-lived random nonce the app
   binds into its token, so tokens can't be captured and replayed.
5. **Rollout flag:** gate enforcement behind an env (e.g. `ATTESTATION_ENFORCED=true`) so you can deploy in
   "log-only" mode first (verify + log failures but still serve), confirm genuine traffic passes, then flip to enforce.

Keep the `X-API-Key` check too (defense in depth). Follow the current official Play Integrity / App Attest server
verification docs for exact calls — don't hand-roll crypto.

**Tests (Part 1).**
- Genuine app (real device, current build) → token verifies → 200.
- Missing token / random token / token with stale or wrong nonce → **403 attestation_failed**, nothing generated.
- Replay a previously valid token → rejected (nonce/counter freshness).
- Emulator / re-signed APK (Android) → fails device/app integrity → 403.
- `ATTESTATION_ENFORCED=false` (log-only) → failures logged but served; `=true` → failures blocked.
- New gateway routes present in `gateway_routes.yaml` (e.g. `/attest-nonce`), reachable on cloud.

---

## Part 2 (MUST, ships regardless) — Hard GCP spend cap + alerts

**Important:** a GCP **Billing budget alone does NOT stop spending** — it only emails alerts. For a real cap you
need both of:

1. **Bound throughput:** set **Cloud Run `--max-instances`** to a sane ceiling on each cost-bearing service
   (tour-orchestrator, tour-worker, news-orchestrator, news-generator, translation, polly-tts). This caps
   concurrency → caps OpenAI/Polly/compute burn rate even under attack.
2. **Budget + automated kill-switch:**
   - Create a **Billing budget** on project `audiotours-migration` with alert thresholds (e.g. 50/90/100% of a
     monthly ceiling you choose), notifying Sir Michael's email.
   - Wire the budget's **Pub/Sub** notification to a **Cloud Function** that, at 100%, caps damage — e.g. sets the
     cost-bearing Cloud Run services to `--max-instances=0` (or disables the billing account). This is the only way
     to get a true hard stop.

**Tests (Part 2).**
- Confirm each cost-bearing service has a max-instances ceiling (`gcloud run services describe …`).
- Trigger the budget threshold in a test (or lower the ceiling temporarily) → alert email fires; the kill-switch
  function scales the services to 0 / disables billing.
- Confirm alerts reach Sir Michael.

---

## Definition of done
- [ ] Attestation verified server-side on cost-bearing endpoints; genuine app passes, forged/missing/replayed → 403.
- [ ] `/attest-nonce` issued + bound; rollout flag works (log-only → enforce).
- [ ] Cloud Run max-instances set on all cost-bearing services.
- [ ] Billing budget + alert thresholds + automated kill-switch at 100%; alerts to Sir Michael.

## Scope / timeline note
Services-only. The app must generate the tokens (Mobile-AQ doc). Realistically this is a few days across both
lanes; if the date is tight, **Part 2 (budget cap + max-instances) must ship no matter what** — it's the backstop —
and Part 1 ships for whichever store you launch first. Deploy Part 1 in log-only mode first to avoid blocking
genuine users on day one.
