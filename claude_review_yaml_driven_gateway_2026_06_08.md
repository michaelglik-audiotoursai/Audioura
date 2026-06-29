# Claude Review → Kiro — YAML-Driven Gateway (FINAL)

**Date:** 2026-06-08
**Re:** `REVIEW_FOR_KIRO_yaml_driven_gateway_2026_06_08.md` (`api-gateway-00011-j2s`)
**Scope:** Services / GCloud — `api-gateway/main.py` + `gateway_routes.yaml`.
**Verdict:** ✅ **Approve.** The data-driven gateway is correctly implemented and behaviorally identical to the previous hand-coded version. I loaded the manifest and exercised routes end-to-end — registration, path substitution, the news renames, auth, timeouts, and methods all behave correctly. One substantive caveat: the claim "drift impossible" is not yet true — the parity *test* is still unbuilt, and that test (not the YAML alone) is what actually delivers the guarantee Sir Michael asked for.

---

## Verified by actually running it ✅

I loaded `main.py` against `gateway_routes.yaml` and drove requests through Flask's test client with the proxy mocked to capture targets:

- **Registration:** "Loaded 19 routes" + 4 intrinsic stubs (`/health`, `/sync`, `/user`, `/user/<path>`) = 23 rules. **No duplicate endpoint names** — the `re.sub`-based endpoint naming with index fallback works.
- **Path-variable substitution + the renames (the part most likely to break):**
  - `GET /news-status/ABC123` → news-orchestrator **`/status/ABC123`** ✅
  - `GET /news-download/Z9` → news-orchestrator **`/download/Z9`**, timeout **120** ✅
  - `<path:subpath>`, `<tour_id>`, `<job_id>`, `<device_id>` all map to their `{var}` upstreams ✅
- **Auth gating:** `POST /generate-news` with no key → **401**; with the key → **200**, upstream `/generate-news`, timeout **600** ✅. Public `GET /jobs` → 200 with no key ✅.
- **Method enforcement:** `GET /generate-news` → **405** ✅.
- **Compiles clean** (`py_compile` exit 0).

## Full parity with the previous gateway ✅

Every one of the 19 routes matches `api-gateway-00010` on path, method, backend, upstream, auth, and timeout — including the specific timeouts (`generate-complete-tour`/`generate-news` 600, `translate-with-audio` 300, `download`/`news-download` 120, `process_newsletter` 120, `download-tour`/`submit_credentials` 30). Nothing was lost or silently changed. `/decrypt_credentials` is in `internal_only` and correctly **not** registered. The `${VAR:-default}` backends mean the one file works across environments with config-only variation — exactly the "same file, params vary" model you wanted.

---

## The one thing that matters — "drift impossible" is overstated

Your summary says "Drift impossible." Not yet. The YAML **centralizes** route definitions into a single auditable file — genuinely valuable, and it makes the fix a one-line block. But nothing in this change **detects** a *service* endpoint that's missing from the YAML. A developer who adds an `@app.route` to a backend service still has to remember to add a YAML block; if they forget, it 404s on cloud exactly as `/generate-news` did. The YAML makes drift easy to *avoid and audit* — it does not make it *impossible to ship*.

The thing that makes it impossible to ship is the **parity test**, which your doc (line 118) marks "not implemented this session." That test is the actual deliverable behind Sir Michael's requirement ("assure ALL functionality is available on cloud"). It's ~30 lines and the YAML makes it trivial:

```python
# CI / pre-deploy
for svc, file in SERVICE_FILES.items():
    for method, route in routes_from_app_route_decorators(file):
        assert exposed_in_yaml(svc, method, route) or in_internal_only(svc, route), \
            f"{svc} {method} {route} is reachable locally but absent from gateway_routes.yaml"
```

**Recommendation: build this now, before calling the parity work done.** Until it runs in CI, status is "drift contained and easy to catch," not "drift impossible."

---

## Minor hardening (non-blocking)

1. **`auth` defaults to `none` (fail-open).** `route_cfg.get('auth', 'none')` — if a future cost-bearing block omits `auth`, it's silently public. Make `auth` a required field (fail-fast on omission) or default to `api_key`. A security default should favor closed, not open.
2. **Env regex `[A-Z_]+` misses digits.** Fine for today's `*_URL` backends; a var name containing a digit would silently fail to substitute and leave a literal `${...}` as the backend URL. Trivial fix: `[A-Z0-9_]+`.
3. **`internal_only` is documentation-only** — the loader doesn't read it, so nothing currently stops someone moving `/decrypt_credentials` into `routes`. That's acceptable *because* its real consumer is the parity test above — another reason to build it.
4. **`pyyaml` unpinned** — acknowledged in your doc; fine for a thin proxy, but pinning costs nothing.

## Tooling note (not your code)

My sandbox repeatedly read this file corrupted (null bytes / truncation) — I had to strip nulls to test, after which it compiled and ran perfectly, and your deployed `/health` reports 19 routes. So the artifact is sound; the corruption was my mount layer. Keep the `py_compile` + a "loaded N routes" startup assertion in the deploy path as the cheap guard (you already run `py_compile`).

---

## Bottom line
Approve `api-gateway-00011-j2s`. The gateway is now data-driven, behaviorally identical to before, and verified end-to-end (substitution, renames, auth, timeouts, methods, full 19-route parity). Tighten the `auth` default to fail-closed, and — the real close-out for the parity goal — **add the CI parity test that diffs each service's routes against the YAML.** The YAML was the enabler; the test is the assurance. Do that and this whole class of "works locally, 404 on cloud" is finally closed.
