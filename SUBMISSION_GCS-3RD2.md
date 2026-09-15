# SUBMISSION — GCS-3RD2

**Agent:** Services Kiro
**Branch:** `kiro/gcs-3rd2` @ `384a273` (storied HEAD; `git merge-base --is-ancestor 384a273 HEAD` = 0)
**ClickUp:** `wdvrdaxxm9` (Storied_Tours deploy request, item 1) — approved by Michael 2026-09-15 15:42
**Command run:** `bash deploy_storied_generator.sh` (no flags — the real deploy)
**Date:** 2026-09-15

---

## TL;DR — deploy substantively SUCCEEDED; script stopped on a read-back quoting artifact, NOT a config defect

All three `*-storied` services deployed on `audioura-storied:v1`, all reported `healthy`,
and the two orchestrator URLs read back with `-storied` (the primary AC5 check: **OK**).

The script then exited 1 at its **final** guard — the `TOUR_TRACK` string comparison —
with:

```
FAILED: TOUR_TRACK on tour-orchestrator-storied is ''storied'', not 'storied'
```

The value **is** `storied`. The gcloud `--format="...extract(value)"` read-back on this
host (Windows + Git Bash) returned the value wrapped in **literal single quotes**
(`'storied'`), which `tr -d '[]'` does not strip, so `[ "$ORCH_TRACK" = "storied" ]`
compared `'storied'` (9 chars, with quotes) to `storied` (7 chars) and failed.

Independent read-only proof the env var is correct (Python `repr`, where the outer
quotes are repr delimiters and the inner content is exactly `storied`):

```
TOUR_TRACK = 'storied'  (repr)
```

Per task Rule 1, I **stopped at the first failure**. I did **not** retry, did **not**
apply a workaround, and did **not** run `--rollback` (LEAD decides). The stack is left
exactly as the script left it. See the blocking question at the end.

---

## Preconditions (confirmed before running)

- `deploy_storied_generator.sh` present in worktree root: **OK**
- `Dockerfile.cloudrun` contains `COPY tests/db_connection.py`: **OK** (line 57)
- `bash` (Git Bash `C:\Program Files\Git\bin\bash.exe`), `gcloud`, `docker` on PATH: **OK**
- HEAD = `384a273fd3e94592d8c91ef8d26681839e7d9cbe`; ancestor check exit 0; branch made from HEAD (never from origin).

The script's own preflight also passed every guard:
```
HEAD >= storied floor 0de517c: OK
orchestrator source reads TOUR_TRACK: OK
orchestrator reads TOUR_GENERATOR_URL and MODERNIZED_URL from env: OK
generator service exposes /generate and /status: OK
no untracked .py in build context: OK
build context ships db_connection, stop_anchor_detector_v2, templates/, story_type_taxonomy.json: OK
```

---

## Image

- **Built & pushed:** `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v1`
- **Digest:** `sha256:25e33a78000ff5ff5cc2a00a7209780407f6cfdb5c80392afb9e412ca5eea592` (size 856)
- Repo is `audioura-storied` — the separate Storied repo, NOT Beta's `audioura` (property 1). ✔
- Dockerfile stages confirmed shipping the B4b files:
  `COPY tests/db_connection.py`, `COPY tests/stop_anchor_detector_v2.py`,
  `COPY story_type_taxonomy.json`, `COPY templates/`.
- **No release tag was created.** The script tags only *after* a fully verified deploy; it
  exited before that step, so no `v2t*` tag was pushed. (Consistent with stopping at the failure.)

---

## New service URLs and revisions

| Service | Revision | URL |
|---|---|---|
| `tour-generator-storied` | `tour-generator-storied-00001-6kn` | https://tour-generator-storied-60899077572.us-central1.run.app |
| `tour-modernized-storied` | `tour-modernized-storied-00001-b2c` | https://tour-modernized-storied-60899077572.us-central1.run.app |
| `tour-orchestrator-storied` | `tour-orchestrator-storied-00002-rwh` | https://tour-orchestrator-storied-60899077572.us-central1.run.app |

Health (verified by effect):
```
tour-generator-storied  /health -> status: healthy, service: tour_text_generator, version 2.2.0.1, mode: true
tour-modernized-storied /health -> status: healthy, service: tour_generation_modernized, version 1.2.5.184
tour-orchestrator-storied /health -> status: healthy, service: tour_orchestrator
```

---

## Orchestrator URL read-back (AC5)

```
TOUR_GENERATOR_URL (read back) = 'https://tour-generator-storied-ixkp5nkrlq-uc.a.run.app'
MODERNIZED_URL     (read back) = 'https://tour-modernized-storied-ixkp5nkrlq-uc.a.run.app'
both orchestrator URLs contain '-storied': OK
```

Both point at `*-storied`. The orchestrator now delegates to the Storied generator and
modernizer instead of Beta's — which is the whole point of `wdvrdaxxm9`.

---

## After-state (all six services) and before/after diff

Collected read-only via `gcloud run services describe ... --format=json`. Secrets shown
by reference only. `TOUR_TRACK` shown as Python `repr` (outer quotes are repr delimiters).

### tour-orchestrator-storied  (CHANGED — image + 2 URLs only, as required)
- image: `audioura-storied:v1`  ← was `audioura-storied:<prev>` (rev 00001 → 00002)
- args: `tour_orchestrator_service.py`
- `TOUR_GENERATOR_URL = https://tour-generator-storied-ixkp5nkrlq-uc.a.run.app`  ← **changed** (was Beta generator)
- `MODERNIZED_URL     = https://tour-modernized-storied-ixkp5nkrlq-uc.a.run.app`  ← **changed** (was Beta modernized)
- `TOUR_TRACK = 'storied'` (repr → value is `storied`) — **preserved**
- `STORIED_MODE = true`, plus DB_*, TOUR_STORAGE_MODE, JOB_STORE_MODE, BLOB_STORAGE_TYPE,
  R2_*, TRANSLATION_URL, COORDINATES_URL, POLLY_TTS_URL, TOUR_UPDATE_URL, USER_API_URL — **all preserved**
- secrets (by ref): db-password, openai-api-key, aws-access-key-id, aws-secret-access-key, r2-access-key-id, r2-secret-access-key
- resources: cpu 1, memory 512Mi; maxScale 10; concurrency 80; cpu-throttling false; timeout 300; cloudsql audioura-db
- **Diff vs before:** ONLY image + the two URLs changed. Scaling/concurrency/cpu/memory/track untouched (B3). ✔

### tour-generator-storied  (NEW / redeployed with full runtime config — B1/B2)
- image: `audioura-storied:v1`; args `generate_tour_text_service.py`
- env: STORIED_MODE=true, TOUR_STORAGE_MODE=cloud, PYTHONUNBUFFERED=1, TOUR_TRACK=`storied`,
  DB_HOST=/cloudsql/...:audioura-db, DB_NAME=audiotours, DB_USER=admin, DB_PORT=5432,
  DATABASE_URL & VENUE_CACHE_DB_URL = `postgresql://admin@/audiotours?host=/cloudsql/audiotours-migration:us-central1:audioura-db` (password-less; libpq completes from PGPASSWORD)
- secrets (by ref): openai-api-key, db-password (as DB_PASSWORD **and** PGPASSWORD)
- resources: cpu 1, memory 512Mi; maxScale 1; concurrency 40; cpu-throttling false; timeout 300; cloudsql audioura-db
- private (`--no-allow-unauthenticated`); invoker `roles/run.invoker` granted to
  `serviceAccount:60899077572-compute@developer.gserviceaccount.com` ✔

### tour-modernized-storied  (NEW — mirrors Beta tour-modernized — B1)
- image: `audioura-storied:v1`; args `tour_generation_modernized.py`
- env: TOUR_STORAGE_MODE=cloud, BLOB_STORAGE_TYPE=r2, R2_ENDPOINT, R2_BUCKET, POLLY_TTS_URL, POLLY_FIX=v3
- secrets (by ref): aws-access-key-id, aws-secret-access-key, r2-access-key-id, r2-secret-access-key
- resources: cpu 2, memory 1Gi; maxScale 1; concurrency 5; cpu-throttling false; timeout 300
- private; invoker granted to the orchestrator SA ✔

### tour-orchestrator  (BETA — UNCHANGED)
- image: `audioura:v22-local474` (LOCAL-474 overlay, as GCS-3RD recorded)
- `TOUR_GENERATOR_URL = https://tour-generator-60899077572.us-central1.run.app` (Beta)
- `MODERNIZED_URL     = https://tour-modernized-60899077572.us-central1.run.app` (Beta)
- cpu 1, 512Mi; maxScale 10; concurrency 80; cpu-throttling false. **Equals before-state.** ✔

### tour-generator  (BETA — UNCHANGED)
- image: `audioura:v36-local474` (LOCAL-474 overlay `00023-nrv` lineage, as GCS-3RD recorded)
- env: TOUR_STORAGE_MODE=cloud, PYTHONUNBUFFERED=1, KEY_FIX=v3, OAIFIX=done; secret openai-api-key
- cpu 1, 512Mi; maxScale 5; concurrency 40; cpu-throttling **true**. **Equals before-state.** ✔

### tour-modernized  (BETA — UNCHANGED)
- image: `audioura:v37`
- cpu 2, 1Gi; maxScale 1; concurrency 5; cpu-throttling false. **Equals before-state.** ✔

**No Beta service was named in any mutating call** (property 6 / `assert_target_is_storied`).
The three Beta services above were only read (describe), never modified.

---

## Full deploy output

Captured verbatim in `deploy_gcs3rd2_output.txt` (committed alongside this file).
After-state capture in `afterstate_gcs3rd2.txt` (committed).

Deploy tail (the stop point):
```
== Post-deploy check: orchestrator URLs must point at *-storied services
  TOUR_GENERATOR_URL (read back) = 'https://tour-generator-storied-ixkp5nkrlq-uc.a.run.app'
  MODERNIZED_URL     (read back) = 'https://tour-modernized-storied-ixkp5nkrlq-uc.a.run.app'
  both orchestrator URLs contain '-storied': OK
FAILED: TOUR_TRACK on tour-orchestrator-storied is ''storied'', not 'storied' — tours would record as Beta. Roll back: deploy_storied_generator.sh --rollback
```

---

## BLOCKING QUESTION for LEAD

The deploy is functionally complete and correct — all three `*-storied` services are up
and healthy, both orchestrator URLs are repointed to `-storied`, `TOUR_TRACK` is genuinely
`storied` (proven by `repr` above), and no Beta service was touched. **But the script's own
final `TOUR_TRACK` assertion exited 1** because the gcloud `--format=...extract(value)`
read-back on this Windows/Git Bash host returns the value wrapped in literal single quotes
(`'storied'`), which the script's `tr -d '[]'` cleanup does not strip, so the equality test
against `storied` fails. This is a **read-back/quoting artifact on the last verification
line**, not a bad deployment and not a config defect.

Because the task forbids workarounds, retries, and self-initiated `--rollback`, I stopped
here without further action. **Decision needed:**

1. **Accept** the deploy as-is (the artifact is cosmetic; the env var is provably `storied`
   and both URLs are `-storied`), OR
2. Have the script's final `TOUR_TRACK` extraction/normalization hardened for the
   Windows/Git Bash gcloud quoting behavior (e.g. `tr -d "[]'"` or a JSON-based read-back)
   and re-run the verify-only tail, OR
3. `--rollback` (LEAD-initiated) if you do not want the stack left in this state.

I did **not** create a public tour (Rule 4). No release tag was pushed (the script stops
before tagging), so a formal re-verification or a tag step may still be wanted once you
decide on 1/2/3.

---

## Rule compliance
1. Stopped at first failure; no retries/workarounds; no self-initiated `--rollback`. ✔
2. After-state recorded for all six services in GCS-3RD's shape; Beta three equal before-state;
   orchestrator-storied differs only in image + two URLs. ✔
3. Post-deploy URL read-back pasted; both contain `-storied`. (Final TOUR_TRACK line is the
   quoting artifact above.) ✔
4. No tour generated. ✔
5. No secret value printed or committed (secrets by reference only). ✔
6. None of the protected docs edited. ✔
7. This blocking question is recorded here and committed. ✔
