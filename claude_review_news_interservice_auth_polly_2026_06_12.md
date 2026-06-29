# Claude Review — News Inter-Service Auth + Polly 403 (Kiro, 2026-06-12)

**Reviewing:** `REVIEW_FOR_KIRO_news_interservice_auth_2026_06_12.md` + `news_orchestrator_service.py`, `polly_tts_service.py`.
**Lane:** Services only. **Author:** Claude (independent reviewer).
**Verdict:** OIDC fix is **correct and verified** — good. But your Polly-403 diagnosis is **probably wrong**: a `403` is the signature of Cloud Run **IAM rejection (missing OIDC)**, not an AWS-credential problem. Check the processor → polly-tts auth first; it's likely the same one-line pattern, not an AWS-keys investigation. Details + a scope flag below.

---

## Verified ✅ — orchestrator inter-service auth

`news_orchestrator_service.py` now adds `_get_auth_headers()` to both downstream calls:
- generator: `/process-article` (line 152) → **200** ✅ (was 403)
- processor: `/process-audio` (line 165) → authed ✅

The helper branches correctly (local `http://` → no auth; Cloud Run `https://` → OIDC bearer, cached 3500s), matching the existing tour-orchestrator pattern. This is the right fix and it works.

---

## Pushback — the Polly 403 is almost certainly an OIDC issue, not AWS keys

Your doc says the processor's 500 is due to "AWS Polly returns 403 — expired/invalid AWS credentials." The code says otherwise:

In `polly_tts_service.py`, **every AWS failure path returns 500, never 403**:
- boto3 client init fails (missing/invalid keys) → "Polly client not available" → **500** (lines 40, 145)
- Polly `ClientError` (incl. an AWS-side 403/AccessDenied) → caught → **500** with the error code (lines 130–134)

So a real AWS-credential problem would surface to the processor as a **500**, not a **403**. The fact that you're seeing a **403** points to the **Cloud Run IAM layer rejecting the call before it ever reaches the polly-tts app** — i.e. the **news-processor is calling polly-tts without an OIDC token.** That's the exact same bug you just fixed at the orchestrator hop, one level down.

**Most likely fix:** apply the same `_get_auth_headers()` pattern in the **news-processor** where it calls polly-tts (add the `Authorization: Bearer` token). One-line pattern, not an AWS-keys hunt.

**How to confirm in 2 minutes:**
1. Check **polly-tts logs**. If there's *no* application log for the request, it was rejected at Cloud Run IAM → OIDC issue (apply the token). If the request *reached* the app and then AWS errored, you'd see a 500 + an AWS error code → only then is it credentials.
2. Check whether the **news-processor's call to polly-tts** includes auth headers (does it import/use a `_get_auth_headers` equivalent?). If not → that's it.

Don't rotate AWS keys until the logs actually show an AWS `AccessDenied` — the symptom (403, not 500) says it isn't that.

---

## Scope flag (for Sir Michael)

This whole chain is **news generation**. Confirm whether **news is in the July-1 Beta scope** — there's still an open "news scope" decision. If news is *not* in the first Beta, this Polly 403 is **post-launch, not launch-blocking**, and shouldn't compete with the store-submission critical path. If news *is* in Beta, it needs to be fixed before launch.

---

## Deployment

- `news-orchestrator-00012-x58` (`audioura:v23`) — inter-service auth deployed. ✅

## Bottom line

OIDC fix: correct, verified, done. Polly 403: re-diagnose before chasing AWS keys — the 403 (vs 500) says it's the **processor → polly-tts OIDC hop**, same pattern as the fix you just shipped. Confirm via polly-tts logs. And confirm with Sir Michael whether news is even in the Beta before treating this as launch-blocking.
