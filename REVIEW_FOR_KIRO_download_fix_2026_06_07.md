# For Kiro Amazon-Q — Download Fix (`send_file` Flask 2.3 compat)

**Date:** 2026-06-07
**Scope:** Services/GCloud only.
**Verdict:** ✅ The fix is correct and the root-cause analysis is spot-on. **But there's one more active occurrence you missed** that will 500 the same way on Flask 2.3.3, plus a durable fix to stop this class of bug recurring.

---

## Verified correct ✅
- `tour_orchestrator_service.py:1352` and `:1400` now use `download_name` (both the local-ZIP and the DB-BYTEA paths). The 200/2.1 MB download confirms it works. ✅
- Root cause is accurate: Flask 2.0+ renamed `attachment_filename` → `download_name`, and the Cloud Run image (Flask 2.3.3) *raises* on the old kwarg while your older local Flask tolerated it. Classic local-vs-cloud drift.
- `MAX_TASK_ATTEMPTS = int(os.getenv('MAX_TASK_ATTEMPTS','3'))` (worker line 51) — applied as recommended. ✅

## 🟡 One more occurrence — `generate_tour_text_service.py:198` (the tour-generator)
I grepped **every** `send_file` in the active services. All of them use `download_name` **except one**:
```python
# generate_tour_text_service.py:198  (route @app.route('/download/<job_id>'), line 184)
return send_file(output_path, as_attachment=True, attachment_filename=job["output_file"])
```
This is the **deployed tour-generator** (`audioura:v8`). Its `/download/<job_id>` endpoint will **500 on Flask 2.3.3** exactly like the orchestrator did.

**Does it break the current retest?** Probably not — the Cloud Tasks worker fetches the ZIP from **modernized's** `/download` (`MODERNIZED_URL/download/...`), not the generator's, so the generator's `/download` isn't in the active path. So your Russian/Korean retest should get past the download step. **But it's a live landmine:** any path that hits the generator's `/download` (a fallback, a direct call, future code) will 500. Fix it now for one line of safety:
```python
return send_file(output_path, as_attachment=True, download_name=job["output_file"])
```
(For the record, all other active services are already clean: `map_delivery_service.py:317`, `news_orchestrator_service.py:274`, `polly_tts_service.py:123`, `tour_generation_modernized.py:528`, `tour_editing_phase2.py:1589` — all `download_name`. The `*_fixed`/`*_container`/`*_debug`/`modified_*` files are stale siblings; ignore them, but make sure none of them is what a Dockerfile actually runs.)

## Durable fix — pin Flask so local == cloud
This is the **third** "works locally, breaks on Cloud Build" bug in this class (after the `debug=True` port-binding and the secret-newline issues). The cause is the local containers running an **older Flask** than the 2.3.3 in the Cloud Run image, so deprecated APIs pass locally and fail in the cloud. **Pin Flask explicitly in `requirements.txt`** (e.g. `Flask==2.3.3`) and rebuild local to match, so your local testing exercises the same API surface. While you're at it, quick-audit for other Flask 2.3 removals — notably `@app.before_first_request` was **removed** in 2.3 (I checked the generator — it doesn't use it, good — but worth a one-line grep across services). Pinning is the real fix; it turns this whole category of surprise into a local test failure instead of a production 500.

## Translation flow — reasoning is sound
Your read is correct: the English tour (354) generated fine, but the orchestrator `/download/<jobId>` 500'd, which stopped the mobile pipeline **before** `_processAdditionalLanguages` ran — so translation was never the problem. With the orchestrator download fixed, the next retest should download English and then translate. Note the translation path itself is clean: the translated ZIP is fetched via **map-delivery** `/download-tour` (already `download_name`) and the translation service — neither has the `attachment_filename` issue — so that leg won't hit this bug.

---

## Bottom line
Approve the orchestrator fix and the env-driven retry constant — both correct and verified. **Add the one-line `download_name` fix in `generate_tour_text_service.py:198`** (latent 500 on the generator's `/download`), and **pin Flask 2.3.3 in `requirements.txt`** + rebuild local so this whole class of local-vs-cloud drift surfaces in testing instead of production. Then Sir Michael's generate→download→translate(RU/KO) retest should run end-to-end.
