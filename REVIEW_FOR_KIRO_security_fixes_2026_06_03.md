# Review for Kiro Amazon-Q — Security Fixes (commit `26380ab`)

**Date:** 2026-06-03
**Scope:** Services/GCloud only (api-gateway).
**Verdict:** ✅ **Both findings are correctly fixed and verified in `api-gateway/main.py`.** The security posture is materially better. Two residual hardening items remain before treating the public URL as fully exposed, plus one empirical check I can't do from code.

---

## Finding 1 — `/download` collision: ✅ fixed
- `/download/<job_id>` → orchestrator (line 125)
- `/news-download/<article_id>` → news-orchestrator (line 166)

No more shared URL rule, so news article downloads now reach news-orchestrator. Correct. (The mobile app will need to call `/news-download/<id>` — that's a mobile-side change, tracked in the mobile review, not yours.) When news is actually exercised, confirm news-orchestrator exposes `/download/<article_id>` so the rename lands on a real endpoint.

## Finding 2 — API-key budget protection: ✅ fixed, with one fail-open caveat
`require_api_key()` is applied to exactly the right set — the cost-bearing and write endpoints:
- `POST /generate-complete-tour` (line 116), `POST /tour-status` (131), `POST /translate-with-audio` (144), `POST /process_newsletter` (153).
Read-only endpoints (`/tours-near`, `/download-tour`, `/tour/<id>/resolve`, `/status`, `/newsletters_v2`, `/get_articles_by_newsletter_id`, `/news-download`, `/health`) stay open. That's the correct split, and your 401/200 test confirms it works in production.

### ⚠️ Residual 1 — the check is fail-OPEN
```python
def require_api_key():
    if not API_KEY:
        return None  # No key configured = open (dev mode)
```
If `GATEWAY_API_KEY` is ever unset/empty on the deployed gateway, **every cost endpoint silently becomes open** — no error, no log. Your 401 test shows it's currently set, but a future redeploy that forgets the Secret Manager binding would silently remove all budget protection. Recommend:
- Confirm `GATEWAY_API_KEY` is bound on the live `api-gateway` revision (the 401 result implies it is — just make it a checklist item for every redeploy).
- Consider **failing closed in production** (e.g. a `REQUIRE_API_KEY=true` env, or simply: if not set, refuse the cost endpoints) — or at minimum log a startup WARNING when `API_KEY` is empty so a missing binding is visible.

### ⚠️ Residual 2 — a shared key shipped in the app is extractable
The `X-API-Key` is a single shared secret the mobile app must carry. APKs are decompilable, so a determined attacker can extract it. This **materially raises the bar** (stops anyone who merely discovers the URL, and stops casual scripting) — good — but it is not a strong secret. Pair it with cheap defense-in-depth:
- A **Cloudflare rate-limit / WAF rule** on `/generate-complete-tour` and `/translate-with-audio` (caps abuse even with a leaked key).
- A **GCP billing budget + alert** and an **OpenAI usage cap** so worst-case spend is bounded and visible.
These are the real backstops; the key alone shouldn't be the only thing between the public and your OpenAI/Polly bill.

### Minor
- `client_key != API_KEY` is not a constant-time compare; over TLS behind Cloudflare a timing attack is impractical, but `hmac.compare_digest(client_key, API_KEY)` is a free upgrade.

## IAM backend lock — verify empirically
You removed `allUsers` from map-delivery and tour-orchestrator and set `--no-allow-unauthenticated` on all 10 backends. I can't confirm deployed IAM from code — please **`curl` a backend `*.run.app` directly** (e.g. map-delivery) and confirm it returns **403**. That's the one test that proves the lock is actually enforced, not just intended.

## Unchanged minor (from prior review)
`proxy_request` reads `resp.content` (full body in memory) despite `stream=True`. Fine for ≤19 MB ZIPs; just keep the gateway Cloud Run memory adequate at `max-instances=3` under concurrent large downloads. Low priority.

---

## Bottom line
Approve commit `26380ab` — Finding 1 and Finding 2 are correctly implemented and verified. Before treating `https://api.audioura.com` as a fully public production surface, close the two residuals: make the API-key check **fail-closed (or at least startup-warn)** so protection can't silently vanish, and add a **Cloudflare rate-limit + GCP billing budget alert** as backstops to the (extractable) shared key. And run the direct-backend `curl` to confirm the IAM 403. Nothing here concerns the mobile app beyond the `/news-download` path note.
