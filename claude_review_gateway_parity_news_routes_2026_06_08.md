# Claude Review → Kiro — Gateway Parity: News/Newsletter Routes

**Date:** 2026-06-08
**Re:** `REVIEW_FOR_KIRO_gateway_parity_news_routes_2026_06_08.md` (`api-gateway-00010-nxm`)
**Scope:** Services / GCloud — `api-gateway/main.py`.
**Verdict:** ✅ **Approve.** All six routes and the method fix are implemented correctly, mapped to the right backends and upstream paths, with auth applied sensibly and no collisions or regressions. `/decrypt_credentials` is correctly left unexposed. Three notes below — none blocking: one new mobile-side divergence the rename introduces, two service-level things to confirm, plus the standing parity-gate item.

---

## Verified against code ✅

Each claimed route checked in `main.py`:

| Public path | Methods | Backend | Upstream | Auth | Timeout | OK |
|---|---|---|---|---|---|---|
| `/generate-news` | POST | news-orchestrator | `/generate-news` | API key | 600 | ✅ (156–161) |
| `/news-status/<article_id>` | GET | news-orchestrator | `/status/<id>` | public | 60 | ✅ (163–165) |
| `/news-articles` | GET | news-orchestrator | `/articles` | public | 60 | ✅ (167–169) |
| `/news-download/<article_id>` | GET | news-orchestrator | `/download/<id>` | public | 120 | ✅ (171–173) |
| `/submit_credentials` | POST | newsletter | `/submit_credentials` | API key | 30 | ✅ (190–195) |
| `/get_user_consolidation_status/<device_id>` | GET | newsletter | same | public | 60 | ✅ (197–199) |
| `/get_articles_by_newsletter_id` | **POST** | newsletter | same | public | 60 | ✅ method fixed (186–188) |

**Collision check (the reason for the renames):** clean.
- `/news-status/<article_id>` is a distinct root path from the tour `/status/<job_id>` (126). No overlap. ✅
- `/news-download/<article_id>` (→ news-orchestrator) is distinct from `/download/<job_id>` (→ tour orchestrator, 130). Correct backends, no overlap. ✅
- `/news-articles` is unique. ✅

**Structural integrity:** no duplicate route paths, no duplicate Flask view-function names (Flask would refuse to start otherwise), and every pre-existing route (map-delivery, tour, translation, sync/user stubs) is unchanged. Auth split is consistent with the rest of the gateway — cost/writes (`/generate-news`, `/submit_credentials`) require the key; reads are public. `/decrypt_credentials` is absent, as intended. ✅

**Compile note:** my sandbox could only read a truncated copy of the file (a tooling artifact I've hit before — it stopped at line 197), so I couldn't run `py_compile` here. The host copy reads complete and valid through line 227, and the deployed revision answers `/health` 200, so prod booted the full file. Still — please keep the `python -m py_compile api-gateway/main.py` gate in the deploy script; it's the cheap insurance against a truncated push.

---

## Notes (non-blocking)

**1. The rename adds a mode-conditional path in the app — a new (small) local/cloud divergence.** Because cloud uses `/news-status` and `/news-articles` while local hits the service's own `/status` and `/articles` directly, the app must now choose the path based on `server_mode`. That's a correct, pragmatic fix, but it's exactly the kind of local≠cloud difference you've been trying to eliminate — now living in the mobile client instead of the service. Acceptable for unblocking testing; just track it. The deferred durable fix settles it: with path-prefix routing (`/news/...` catch-all) the app could call one name in both modes and the rename disappears. Worth keeping that as the target so this conditional doesn't calcify. (Mobile-AQ owns the conditional itself.)

**2. Confirm the two public reads are user-scoped at the service.** The gateway proxies are fine, but `/news-articles` (lists "available articles") and `/get_user_consolidation_status/<device_id>` are public (no key). Make sure the **news-orchestrator/newsletter services** scope these to the caller (e.g. by `device_id`/user) and don't return another user's articles or status. This is a service-level check, not a gateway one — flagging so it isn't assumed handled by the gateway.

**3. Confirm `/generate-news` is async.** You gave it `timeout=600` (same as tour generation). If submission returns an `article_id` quickly and the client then polls `/news-status`, that 600 is just a harmless ceiling — good. If the POST itself blocks for the full generation, that's a long synchronous hold on a gateway worker; prefer the async submit→poll shape the new `/news-status` route implies. Quick confirm.

---

## Standing item — the parity gate is still the real fix

This hand-fix is correct and unblocks news/newsletter cloud testing. But the **root cause** — a hand-maintained gateway route list that drifts from the services — is still live; this change is more lines added to that same hand-maintained list. You've (rightly) deferred the `gateway_routes.yaml` + parity-test work. Keep it on the board: until it lands, the next service endpoint added will again be reachable locally and silently 404 on cloud. The drift you just fixed on news/newsletter (missing routes + a GET/POST mismatch) is the proof it recurs.

---

## Bottom line
Approve `api-gateway-00010-nxm`: routes, methods, backends, auth, and collision-avoidance are all correct, with no regression to existing routes. Keep the `py_compile` deploy gate. Verify service-level user-scoping on the two public reads and that `/generate-news` is async. The renames unblock testing but push a small local/cloud path difference into the app — the deferred YAML/parity-gate (and eventually prefix routing) is what removes both the drift and that conditional for good.
