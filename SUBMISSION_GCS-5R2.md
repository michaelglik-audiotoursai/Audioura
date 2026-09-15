# SUBMISSION — GCS-5R2

**Agent:** Services Kiro
**Branch:** `kiro/gcs-5r2`
**Base:** `storied` = `59a2323` (verified `git merge-base --is-ancestor 59a2323 HEAD` → exit 0; HEAD == 59a2323)
**ClickUp:** `wdvrdaycwj`
**Follow-up to:** GCS-5R (`kiro/gcs-5r` @ `d4e1e07`, merged into local `storied` as `59a2323`)

The editing service and the app change from GCS-5R are final. This task fixes only
the **deploy** (the gateway image was built from the wrong tree) plus one small
`update-stop` validation regression. No deploy was executed; no app change was made.

---

## 1. The defect and the fix (gateway image must be v35's code + the 4 routes)

### Root cause (confirmed against the repo)
`deploy_gcs5_tour_editing.sh` step 3 built the new gateway image from the **storied
working tree**:

```bash
docker build -f "${GATEWAY_DOCKERFILE}" -t "${GATEWAY_IMAGE}" api-gateway
```

and its only pre-build proof was a **YAML-only** `route_diff.py`. But storied's
`api-gateway/main.py` has diverged from the running `services/api-gateway:v35`
image. Verified locally:

```
git diff origin/main:api-gateway/main.py  HEAD:api-gateway/main.py
  → 53 insertions(+), 28 deletions(-)   (origin/main == v35 per LEAD)
```

The divergence is exactly the attestation-handling change LEAD flagged:
`import sys` + `sys.path.insert(0,'/app')`, `from storied_version_constants import …`,
`ATTESTATION_MODE`, `PLAY_INTEGRITY_API_KEY`, `APP_PACKAGE_NAME`, `APP_BUNDLE_ID`,
`_verify_attestation` rewritten to import `attestation_verifier` and call Play
Integrity / App Attest, and extra `/health` fields (`version`, `mode`).

So "v35 + exactly 4 routes" was true for the **YAML** and **false for the code**.
Shipping the storied-tree build would change attestation on every cost-bearing
route — on Preview now and on Stable (the Beta control) later.

`api-gateway/Dockerfile` and `api-gateway/gateway_routes.yaml`:
```
git diff origin/main:api-gateway/Dockerfile  HEAD:api-gateway/Dockerfile          → (no diff)
git diff origin/main:api-gateway/gateway_routes.yaml HEAD:api-gateway/gateway_routes.yaml
  → +tour-editing backend, +4 editing routes only
```

### Fix (in `deploy_gcs5_tour_editing.sh`, step 3 only)
Stage a clean build context in a temp dir and build **from it**, not from the
storied tree:

- `main.py`             ← `git show origin/main:api-gateway/main.py`   (v35's exact code)
- `Dockerfile`          ← `git show origin/main:api-gateway/Dockerfile` (v35's exact Dockerfile)
- `gateway_routes.yaml` ← `api-gateway/gateway_routes.yaml` (this branch = v35 YAML + 4 routes)

Before building, prove two things (both run in `--dry-run` and `--apply`; a
read-only `docker pull` + `docker cp` extract of the v35 image, no mutation):

1. **Byte-identity of `main.py`** — extract `/app/main.py` from the v35 image and
   compare SHA256 to the staged `main.py`, normalising **only** CRLF/BOM
   (`api-gateway/main_sha_check.py`). Abort if it differs.
2. **Route delta** — extract `/app/gateway_routes.yaml` from v35 and run
   `route_diff.py` against the staged routes. Abort unless the delta is exactly
   +4 editing routes + the `tour-editing` backend, with nothing removed.
3. (Additive proof) run `test_editing_routes.py` **against the staged context**
   so AC2 is demonstrated by the script itself.

Only `docker build`/`docker push` and the `gcloud` deploy/update/IAM calls remain
gated behind `run()` (dry-run prints, never executes). Build now uses
`docker build -f "${STAGE_DIR}/Dockerfile" -t … "${STAGE_DIR}"`.

I did **not** edit `storied`'s `api-gateway/main.py` — that divergence is real
history for a later decision. This task only makes the deploy ship v35 + the routes.

New helper: **`api-gateway/main_sha_check.py`** — prints each file's
CRLF/BOM-normalised SHA256 and exits non-zero on mismatch.

---

## 2. `update-stop` empty-`new_text` regression (item 2)

GCS-5R removed the old `if not new_text` validation. `POST /tour/<id>/update-stop`
then accepted an empty/whitespace `new_text`, synthesised an empty stop, and
risked a zero-length audio file (Michael's "0 length" audio in the editor).

Restored a fail-closed check in `update_single_stop` (`tour_editing_phase2.py`),
scoped to that handler only (the shared `_bulk_save_core` is untouched):

```python
if not isinstance(new_text, str) or not new_text.strip():
    return jsonify({
        "status": "error", "message": "new_text is required and cannot be empty",
        "error_code": "VALIDATION_FAILED", "recoverable": True,
        "suggested_action": "Provide non-empty new_text and try again"
    }), 400
```

Covers empty, whitespace-only, missing, and non-string `new_text`. The pre-existing
`stop_number` check is unchanged.

---

## Acceptance criteria — evidence

### AC1 — dry-run: staged v35 code, SHA256 match, route diff, Preview-only target
Full `--dry-run` executed locally with `docker`/`gcloud` stubbed (the stub feeds
`origin/main`'s files as the v35 image's `/app` files; deploys nothing). Key output:

```
== Stage gateway build context from origin/main (v35 code) + this branch's routes
  Staged context: /tmp/tmp.XXXX
    main.py            <- git origin/main:api-gateway/main.py
    Dockerfile         <- git origin/main:api-gateway/Dockerfile
    gateway_routes.yaml<- api-gateway/gateway_routes.yaml (this branch)

== PROVE the staged main.py is byte-identical to the running v35 image (read-only)
  sha256 (norm CRLF/BOM) = ef7cf1adc15eef5626d6c53cd8a5ca17109f7cde9d8fd9b871f8d781175fab18   (staged)
  sha256 (norm CRLF/BOM) = ef7cf1adc15eef5626d6c53cd8a5ca17109f7cde9d8fd9b871f8d781175fab18   (v35 image)
  PASS: staged gateway main.py is byte-identical to the v35 image main.py (CRLF/BOM-normalised).

== PROVE the route delta is exactly +4 editing routes +1 backend (read-only)
  Added backends:   tour-editing
  Removed backends: (none)
  Added routes:
    + GET   /tour/<tour_id>/download
    + GET   /tour/<tour_id>/job-status/<job_id>
    + POST  /tour/<tour_id>/update-multiple-stops
    + POST  /tour/<tour_id>/update-stop
  Removed routes: (none)
  PASS: only difference is the 4 tour-editing routes + tour-editing backend.

== Build + push NEW gateway image …/api-gateway:v36 (v35 code + Dockerfile + the 4 routes)
  [dry-run] docker build -f '/tmp/tmp.XXXX/Dockerfile' -t '…/api-gateway:v36' '/tmp/tmp.XXXX'

  Target gateway(s): api-gateway-storied   (Preview default; Stable only with --stable)
DRY RUN COMPLETE — nothing was deployed.
```

Sanity check that the guard actually bites — the same SHA helper on **storied**'s
`main.py` (what the old build shipped) vs v35:
```
staged sha256 = 2b82dafb8a0ea960130d7914a196f3a8f58d352bde750c4931b4aec79292703f  (storied main.py)
image  sha256 = ef7cf1adc15eef5626d6c53cd8a5ca17109f7cde9d8fd9b871f8d781175fab18  (v35)
FAIL: staged main.py differs from the v35 image main.py … Aborting.
```

### AC2 — `test_editing_routes.py` passes against the STAGED `main.py`, not storied's
Run inside the staged context (v35 `main.py` + this branch's routes):
```
[1] Manifest static checks:  OK (4 routes, backend=tour-editing, auth=api_key, save timeouts >=300s, resolve untouched)
[2] Live app auth checks:    [ATTESTATION] Mode: LOG-ONLY   ← v35 code path (storied prints Mode: off)
  OK: POST /tour/<tour_id>/update-multiple-stops  no-key=401 wrong-key=401 good-key!=401
  OK: POST /tour/<tour_id>/update-stop            no-key=401 wrong-key=401 good-key!=401
  OK: GET  /tour/<tour_id>/job-status/<job_id>    no-key=401 wrong-key=401 good-key!=401
  OK: GET  /tour/<tour_id>/download               no-key=401 wrong-key=401 good-key!=401
PASSED: all editing routes registered and fail-closed without X-API-Key
```
(The `Mode: LOG-ONLY` line is v35's scaffold `_verify_attestation`; storied's
rewrite would print `Mode: off`. This confirms it ran against v35's code.)

### AC3 — empty-`new_text` red → green
`python tests/test_gcs5r2_update_stop_empty_text.py`:
```
[RED PROBE] pre-fix handler empty new_text -> 200
  PASS: RED: pre-fix handler does NOT return 400 (guard is meaningful)
[GREEN]
  empty new_text      -> 400 VALIDATION_FAILED   PASS
  whitespace new_text -> 400 VALIDATION_FAILED   PASS
  missing new_text    -> 400 VALIDATION_FAILED   PASS
  valid new_text      -> 200 (reaches stubbed save, NOT 400)   PASS
  missing stop_number -> 400 VALIDATION_FAILED (unchanged)     PASS
Results: 6 passed, 0 failed
```

### AC4 — existing guards still pass
```
python tests/gcs5r_b1_import_guard.py
  RESULT: PASS — B1 red->green verified (naive dup fails, current single-handler imports).

python tests/test_local153_tour_editing_shims_guard.py
  Results: 7 passed, 0 failed
```

---

## PROCESS compliance

- **Deployed nothing.** No `gcloud run deploy/update`, no IAM change, no `docker push`.
  The only container interaction in the proof is a read-only `docker pull` + `docker cp`
  of v35 (allowed). Local dry-run used stubs.
- **Verified by effect** (SHA256, route diff, editing test, red→green, guards).
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
  `.continuous_dev/STATUS.md`, `GCLOUD_STORIED_START_HERE.md`, `BUILD_NUMBERS.md`.
- Did **not** touch `audio_tour_app/` (Michael is building from this line).
- Did **not** edit `storied`'s `api-gateway/main.py`.
- Windows: `encoding="utf-8"` on every file read in the new Python (`main_sha_check.py`,
  the new test); bash reads use utf-8-safe `git show`.
- Branch committed and pushed; **not** merged.

## Files changed
| File | Change |
|------|--------|
| `deploy_gcs5_tour_editing.sh` | Step 3 rebuilt: stage v35 `main.py`+`Dockerfile` from `origin/main` + this branch's routes; prove SHA256 byte-identity + route delta + editing test before build; build from staged context; read-only proof runs in dry-run; `--apply` aborts on any failure. |
| `tour_editing_phase2.py` | `update_single_stop`: restore 400 `VALIDATION_FAILED` for empty/whitespace/non-string `new_text`. |
| `api-gateway/main_sha_check.py` | **new** — CRLF/BOM-normalised SHA256 comparison of two `main.py` files. |
| `tests/test_gcs5r2_update_stop_empty_text.py` | **new** — red→green guard for the empty-`new_text` validation. |
