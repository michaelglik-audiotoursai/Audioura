# Review for Kiro Amazon-Q — K1–K9 Final (commit `e5ed41a`)

**Date:** 2026-06-03
**Scope:** Services/GCloud only.
**Verdict:** ✅ **Sign-off.** Both items from the prior review are resolved and I verified the status endpoint at the code level, not just from the test output. K3 remains the only open production item (acknowledged). K6/K9 remain as planned.

---

## Verified

### K1 status endpoint — now proven, and the implementation is sound
- `rows_affected: 1` on a real `tour_id` confirms it actually updates. ✅
- I also read the endpoint (`tour_orchestrator_service.py:1004-1058`) and it's well-formed:
  - Requires `tour_id` + `status`, 400s if missing.
  - **Whitelists** status (`started|completed|processing|failed`) — good, no arbitrary values.
  - **Parameterized** SQL (`%s`), so no injection.
  - Sets `finished_at = NOW()` on `completed`.
  - Matches on `tour_id` (the `tour_xxx` request id), consistent with the published contract.
  One minor note (non-blocking): it opens a fresh `psycopg2` connection per call rather than pooling — fine at this volume; revisit only if status updates ever get chatty.

### K2 / K7 / K8 — confirmed previously and still passing
404 catch-all + explicit routes; DB reads succeed with `0.0.0.0/0` cleared (proving the unix-socket connector). ✅

### Contract published
`CONTRACT_TOUR_STATUS_FOR_MOBILE_AQ.md` matches the deployed endpoint (path, body `{tour_id, status}`, response `{status, tour_id, rows_affected}`, and the `tour_id`-not-`request_string` distinction). Good — that's exactly what Mobile needs. (I'll handle the mobile wiring review separately, in their own document.)

---

## Still open

### K3 — backend auth (the one production risk)
Acknowledged and correctly scoped to "before broad/unattended use." Your three options are right; my recommendation order: **(1) tiny custom auth-proxy that mints ID tokens from the metadata server** (≈$0, keeps the current architecture) → set backends `--no-allow-unauthenticated`; **(2) GCP LB with IAM** ($18/mo) if you're already moving to the LB for the domain. The shared-secret header is a weak stopgap. Until then, keep test sessions short and attended — anyone can currently POST `generate-complete-tour` and spend your OpenAI/Polly budget.

### K6 / K9
- **K6** (news/newsletter deploy) — pending, separate session. Tour generation/download is unaffected.
- **K9** (DNS) — Sir Michael's action (CNAME `api` → the gateway). Not yours to do; just hand him the target, which you've done.

---

## Bottom line
K1–K9 approved for the current testing phase. The only thing standing between this and production-grade is **K3** (lock the backends) plus the still-pending **K6** and Sir Michael's **K9** DNS. No further services changes needed for the cloud tour-generation test. The corresponding mobile-app review is in a separate document for Mobile Amazon-Q.
