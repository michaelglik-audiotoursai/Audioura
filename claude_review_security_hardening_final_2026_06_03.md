# Claude.AI Final Review — Security Hardening (Per `REVIEW_FOR_KIRO_security_fixes_2026_06_03.md`)

**Date:** 2026-06-03  
**Branch:** `services-migration`  
**Commit:** `e871eae`

---

## All Residual Items Addressed

### Residual 1: Fail-closed API key check ✅

**Before:** If `GATEWAY_API_KEY` env var was empty/unset, cost endpoints silently opened.

**After:**
```python
if not API_KEY:
    print("[WARNING] GATEWAY_API_KEY is not set — cost-bearing endpoints will REJECT all requests (fail-closed)")

def require_api_key():
    if not API_KEY:
        return jsonify({"error": "service_misconfigured", "message": "API key not configured on gateway"}), 503
    ...
```

Now: missing key → 503 on all cost endpoints + startup WARNING log. Protection cannot silently vanish.

### Residual 2 (minor): Constant-time compare ✅

**Before:** `client_key != API_KEY` (timing-attackable in theory)

**After:** `hmac.compare_digest(client_key, API_KEY)` — constant-time string comparison.

### IAM backend lock: Empirically verified ✅

Removed `allUsers` invoker binding from ALL 10 backends. Direct curl tests confirm:

```
map-delivery:    HTTP 403 ✅
orchestrator:    HTTP 403 ✅
polly-tts:       HTTP 403 ✅
```

No backend is accessible without a Google identity token.

---

## Remaining Recommendations (Not Code — Sir Michael Actions)

| Item | What | Where |
|------|------|-------|
| Cloudflare rate-limit | WAF rule: max 10 req/min on `/generate-complete-tour` | Cloudflare Dashboard → Security → WAF |
| GCP billing budget | Alert at $50/month + hard cap | GCP Console → Billing → Budgets |
| OpenAI usage cap | Set monthly spend limit | OpenAI Dashboard → Usage Limits |

These are backstops to the extractable shared key. The key stops casual abuse; these stop determined abuse with a leaked key.

---

## Final Verification (Production)

```
Health (open):              ✅ 200 {"auth":"enabled","service":"api-gateway"}
Tours-near (open):          ✅ 200
Generate WITHOUT key:       ✅ 401 {"error":"unauthorized"}
Direct backend access:      ✅ 403 (IAM-locked)
Gateway via api.audioura.com: ✅ All routes working through Cloudflare + LB
```

---

## Security Posture (Final)

| Threat | Mitigation |
|--------|-----------|
| Random internet user hits generate | 401 — needs API key |
| Key leaked from APK | Rate-limit + billing cap (Sir Michael action) |
| Key env var accidentally removed | 503 fail-closed + startup WARNING log |
| Timing attack on key comparison | `hmac.compare_digest` |
| Direct backend bypass | 403 — all 10 backends IAM-locked |
| DDoS | Cloudflare proxy (orange cloud) |
| Man-in-the-middle | Cloudflare → LB: Full (strict) TLS; LB → Cloud Run: HTTPS |
| Database exposure | No public IP; unix socket from Cloud Run only |
