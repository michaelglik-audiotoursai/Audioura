# Claude → Kiro — Make ALL Functionality Reachable on Cloud (Gateway/Local Parity)

**Date:** 2026-06-08
**Scope:** Services / GCloud — the API gateway and the backend route surface. (Two app-facing path names need Mobile-AQ; flagged, not specified here.)
**Goal:** Guarantee that every endpoint that works locally also works on cloud, with the *same service code*, and make it structurally impossible for them to drift apart again.

---

## 1. Why "works locally, missing on cloud" keeps happening (the actual mechanism)

It is **not** two sets of files and **not** different branches. I verified there is exactly one `news_orchestrator_service.py` (16,581 B), one `newsletter_processor_service.py`, and one `api-gateway/main.py`. The service code is identical for local and cloud.

The difference is the **routing layer**, and only cloud has one:

- **Local** (`endpoints.dart` → `_localPorts`): the app calls each service **directly by port** — `http://<ip>:5012/generate-news`, etc. Every `@app.route` a service defines is automatically reachable. There is no allowlist.
- **Cloud** (`endpoints.dart`, `server_mode='cloud'`, `cloud_use_path_prefixes=false`): the app calls one domain `api.audioura.com`, and **`api-gateway/main.py` is a hand-maintained list of root-path routes**. Only the endpoints someone explicitly added to that file are reachable. Everything else returns the gateway's 404 — *even though the backend service is deployed and healthy*.

So the gateway's route table is a second, manually-curated copy of "what endpoints exist," and it drifts from the services. That drift is the bug class. `/generate-news` is just the instance you noticed.

## 2. The drift is already wider than news (evidence)

I diffed each service's real `@app.route` set against the gateway:

**news-orchestrator** (`news_orchestrator_service.py`):

| Service endpoint | Gateway status |
|---|---|
| `POST /generate-news` | ❌ **missing** — app can't submit articles on cloud |
| `GET /download/<article_id>` | ✅ mapped (as `/news-download/<id>`) |
| `GET /status/<article_id>` | ❌ **missing** — and would *collide* with the tour `GET /status/<job_id>` (gateway line 126) |
| `GET /articles` | ❌ **missing** |

**newsletter-processor** (`newsletter_processor_service.py`):

| Service endpoint | Gateway status |
|---|---|
| `GET /newsletters_v2` | ✅ mapped |
| `POST /get_articles_by_newsletter_id` | ⚠️ **method mismatch** — gateway registered it as **GET** (line 167), service is **POST** |
| `POST /process_newsletter` | ✅ mapped |
| `POST /submit_credentials` | ❌ **missing** |
| `GET /get_user_consolidation_status/<device_id>` | ❌ **missing** |
| `POST /decrypt_credentials` | ❌ missing — **and should stay internal, not public** (credential endpoint) |

Two missing, one method-mismatch, one must-stay-private — from a hand-edited list. This is exactly why a manual gateway can't be the long-term answer.

---

## 3. Immediate fix — unblock news + newsletter testing now

Add/correct these gateway routes (`api-gateway/main.py`), root-path, correct methods, auth as noted. Costs money or writes data ⇒ `require_api_key()`.

- `POST /generate-news` → news-orchestrator `/generate-news` — **API key**, `timeout=600`.
- `GET /news-status/<article_id>` → news-orchestrator `/status/<article_id>` — public. (Distinct name avoids the tour `/status` collision.)
- `GET /news-articles` → news-orchestrator `/articles` — public.
- Fix `/get_articles_by_newsletter_id` to **POST** (it currently won't match the app's POST).
- `POST /submit_credentials` → newsletter — **API key**.
- `GET /get_user_consolidation_status/<device_id>` → newsletter — public (read).
- **Do NOT** expose `/decrypt_credentials`. Keep it service-internal (it's reachable service-to-service; it must never be public — consistent with the standing rule that credential/raw-SQL endpoints stay private).

**Mobile dependency (coordinate with Mobile-AQ, do not change in this lane):** because the news status/list endpoints are exposed under renamed public paths (`/news-status`, `/news-articles`) to avoid the `/status` collision, the app must call those names in cloud mode. Agree the exact names with Mobile-AQ before they wire polling/listing. `/generate-news` keeps its name, so submission needs no rename.

Redeploy the gateway after the edits.

---

## 4. Durable fix — make the gateway data-driven so it can't drift (this is the real answer)

Per your stated principle — *code identical, parameters in config* — stop hand-coding routes in Python. Drive the gateway from a single declarative manifest the gateway loads at startup.

**`api-gateway/gateway_routes.yaml`** (the one source of truth for cloud routing):

```yaml
backends:
  news-orchestrator: ${NEWS_ORCHESTRATOR_URL}
  newsletter:        ${NEWSLETTER_URL}
  orchestrator:      ${ORCHESTRATOR_URL}
  map-delivery:      ${MAP_DELIVERY_URL}
  translation:       ${TRANSLATION_URL}

routes:
  - public_path: /generate-news
    backend: news-orchestrator
    upstream: /generate-news
    methods: [POST]
    auth: api_key
    timeout: 600
  - public_path: /news-status/<article_id>
    backend: news-orchestrator
    upstream: /status/<article_id>
    methods: [GET]
    auth: none
  - public_path: /news-articles
    backend: news-orchestrator
    upstream: /articles
    methods: [GET]
    auth: none
  # … one line-block per exposed endpoint …

internal_only:        # deliberately NOT exposed — documented, asserted by the parity test
  - { backend: newsletter, path: /decrypt_credentials, reason: "handles credentials; service-to-service only" }
```

`main.py` becomes a small loader: read the YAML, loop the `routes`, register one proxy handler each (the existing `proxy_request` already takes `backend_url`, `upstream path`, `timeout`; just feed it from the manifest, and call `require_api_key()` when `auth: api_key`). Adding an endpoint later = add a YAML block (a parameter), never Python. One code path, config-driven — exactly the model you want.

## 5. The assurance — an automated parity gate (so it fails in CI, not in prod)

Add a test that runs in CI and pre-deploy:

1. Parse every backend service file's `@app.route(...)` decorators (regex or `ast`) → the real endpoint set per service.
2. Load `gateway_routes.yaml` → the exposed set + the `internal_only` set.
3. **Fail** if any service endpoint is in neither list. The failure message names the endpoint, so the fix is "expose it in YAML or justify it in `internal_only`."

Sketch:

```python
def test_gateway_covers_all_service_endpoints():
    for svc, path in SERVICE_FILES.items():
        for method, route in extract_routes(path):          # from @app.route
            assert covered_in_yaml(svc, method, route) or listed_internal(svc, route), \
                f"{svc} {method} {route} is reachable locally but not exposed/declared on cloud"
```

This converts "someone forgot a gateway route" from a production 404 into a red build. It is the single mechanism that *guarantees* the parity you're asking for.

## 6. Decision to make (root-path vs. path-prefix)

- **Keep root-path routing (recommended now):** prefixes stay `false`, the YAML manifest + parity gate fix the drift with no mobile re-architecture. Only cost: each exposed endpoint needs one YAML block and a unique public name (hence `/news-status`).
- **Switch to path-prefixes (bigger, cleaner later):** flip `cloud_use_path_prefixes=true` and give the gateway one catch-all per service (`/news/<path:p>` → news-orchestrator, prefix stripped). Then *every* endpoint, current and future, is automatically reachable and collisions vanish — but it's a coordinated change across the app and all services. Good eventual target; not required to reach parity now.

Do Section 4–5 now; revisit prefixes as a follow-up.

## 7. Security guardrail (parity ≠ expose everything)

Reaching parity means every *intended* endpoint is reachable — not that every route is public. Credential endpoints (`/decrypt_credentials`, `/submit_credentials` behind API key), the userDb raw-SQL service (`:5003`), and any `/sql`/`/postgres/direct` paths must be classified `internal_only` or key-gated in the manifest and asserted by the parity test. The test's `internal_only` list is where these get an explicit, reviewed home — so "not exposed" is a deliberate, documented decision rather than an accident.

---

## 8. Rollout

1. **Now (services):** add the Section 3 routes + method fix, redeploy gateway → news submit/poll/list and newsletter actions reachable. Smoke-test each through `api.audioura.com` with the API key.
2. **Coordinate (Mobile-AQ):** confirm the `/news-status` / `/news-articles` public names; Mobile-AQ points the app at them in cloud mode.
3. **Durable (services):** convert `main.py` to load `gateway_routes.yaml`; add the parity test to CI/pre-deploy.
4. From then on: a service endpoint is "done" only when it's either in the manifest or in `internal_only` — enforced by the gate, verified by a staging smoke test that, because local and cloud now expose the same surface, actually predicts prod.

---

## Bottom line
The services already run the same code local and cloud — the gap is the gateway's hand-maintained route list, which has drifted on **both** news and newsletter (missing routes + a method mismatch). Add the missing routes now to unblock testing, then make the gateway load a single `gateway_routes.yaml` and add a parity test that fails the build when any service endpoint isn't exposed or explicitly marked internal. That manifest-plus-gate is what guarantees "everything available on cloud as locally," with config — not code — as the only thing that varies.
