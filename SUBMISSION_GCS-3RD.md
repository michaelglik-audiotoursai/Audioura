# SUBMISSION_GCS-3RD.md

**Agent:** Services Kiro
**Task:** GCS-3RD — deploy the reviewed Storied generator to Preview (execute only)
**Base:** storied @ `384a273` (verified ancestor of HEAD; branch `kiro/gcs-3rd`)
**ClickUp:** `wdvrdaxxm9` (Storied_Tours' deploy request, item 1)
**Authorised by:** Michael, 2026-09-15 15:42 — deploy request in `wdvrdaxxm9` "has my approval"
**Status:** ⛔ **BLOCKED before any mutation.** No deploy was performed. No Cloud Run service
was created, changed, or deleted. See "Blocking question" below.

---

## Base / preflight verification (all read-only)

- `git rev-parse HEAD` = `384a273fd3e94592d8c91ef8d26681839e7d9cbe`
- `git merge-base --is-ancestor 384a273 HEAD` → exit **0** (correct base)
- Branch: `kiro/gcs-3rd`, created from HEAD (not from `origin/*`)
- Worktree contains `deploy_storied_generator.sh` — **yes**
- `Dockerfile.cloudrun` contains `COPY tests/db_connection.py` — **yes**
  (`Dockerfile.cloudrun:57: COPY tests/db_connection.py /app/db_connection.py`)
- Toolchain (Git Bash): gcloud `571.0.0`, docker `27.3.1` (daemon up), git present
- gcloud project = `audiotours-migration`, active account = `michael.glik@gmail.com`

---

## Step 1 — Read-only production schema report

Connected **read-only** to Cloud SQL instance `audiotours-migration:us-central1:audioura-db`,
db `audiotours`, user `admin` (password read from secret `db-password`, never printed) via the
Cloud SQL Auth Proxy (v2.14.1, token auth) + psycopg2 with `set_session(readonly=True)`.

Single statement executed (no DDL/DML):
```sql
SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1;
```

**Result: 46 tables in `public`.**

Storied generator tables of interest:

| Expected table            | Present? | Notes                                            |
|---------------------------|----------|--------------------------------------------------|
| `stop_corpus`             | ✅ yes   |                                                  |
| `work_stories`            | ✅ yes   |                                                  |
| `tour_scores`             | ✅ yes   |                                                  |
| `stop_metrics`            | ✅ yes   |                                                  |
| `tour_edit_blobs`         | ✅ yes   |                                                  |
| `venue_cache` (real name) | ✅ yes   | No table named `venue_cache`; real name is **`venue_corpus`** (present) |

**All Storied tables the generator queries are present.** No missing tables to report.

Full table list (46):
```
article_requests, audio_tours, coordinates, cost_ledger, custom_tours,
device_consolidation_history, device_encryption_keys, dh_aes_keys, dh_server_keys,
domain_tier_cache, job_status, low_balance_events, map_requests, news_audios, news_cache,
newsletter_server_keys, newsletters, newsletters_article_link, plans, referral_codes,
referral_redemptions, revenuecat_webhook_events, shared_tours, stop_corpus, stop_metrics,
subscription_transactions, subscriptions, supported_languages, test_content_storage,
tour_cache, tour_edit_blobs, tour_requests, tour_scores, treats, usage_counters,
user_class_prefs, user_consolidation_map, user_preferences, user_stop_feedback,
user_subscription_credentials, users, venue_corpus, wallet_balance_cache, wallet_ledger,
wallet_subscription, work_stories
```

(Temporary artifacts used for this read-only check — the proxy binary, its log, and helper
scripts — were removed afterward. The working tree was clean before the deploy attempt.)

---

## Step 2 — The deploy: ⛔ BLOCKED (command rejected before any action)

Ran exactly as instructed, from the worktree root in Git Bash:

```bash
bash deploy_storied_generator.sh --apply
```

Output:
```
unknown argument: --apply
```

The script **rejects `--apply`** and exits (code 2) during argument parsing, **before** the
preflight block — so nothing was built, pushed, deployed, or changed.

`deploy_storied_generator.sh` only accepts these flags (from its own `while`/`case` parser and
usage header):

- *(no flags)* → **the real deploy** ("deploy all three (approved runbook only)")
- `--dry-run` → print the exact commands without executing (default-safe review path)
- `--tag <v>` → build/deploy a specific tag
- `--rollback` → revert all three to previous revision
- `-h` / `--help`

There is **no `--apply` flag.** The instruction's literal command cannot succeed.

### Confirmation nothing changed
`gcloud run services list` (storied-named) after the failed invocation:
```
api-gateway-storied
tour-orchestrator-storied
```
`tour-generator-storied` and `tour-modernized-storied` do **not** exist — i.e. the deploy did
not start. State is identical to the "before" capture below.

---

## ⛔ Blocking question (per Rule 1 and Rule 7 — stop, do not work around)

The task says: *"From the worktree root, in Git Bash: `bash deploy_storied_generator.sh --apply`
… Exactly that. No edits, no extra flags."* But the reviewed script has **no `--apply` flag**;
its real-deploy path is the **bare** invocation `bash deploy_storied_generator.sh` (with
`--dry-run` being the only safe-preview flag).

Running the bare command *is* the intended real deploy, but doing so would (a) deviate from the
literal, explicit instruction ("no extra flags", named `--apply`) and (b) is the irreversible,
mutating path that creates two services and repoints the orchestrator. Because the instruction
and the reviewed script disagree on the exact invocation, and the rules forbid workarounds /
require stopping at the first failure, I am **not** improvising the command.

**Please confirm the exact invocation to run.** Most likely LEAD intends:

```bash
bash deploy_storied_generator.sh          # no flags = the real deploy
```

On a one-word confirmation ("run it with no flags") I will execute that bare command and complete
Steps 2–4 (deploy, health/URL read-back verification, before/after tables, digest, URLs/revisions).

---

## Before-state (captured read-only, for the eventual after-diff)

Secrets are referenced by name only; no secret values are shown.

### `tour-orchestrator-storied` (to be updated: image + 2 URLs only)
- ready revision: `tour-orchestrator-storied-00001-pk9`
- image: `us-central1-docker.pkg.dev/audiotours-migration/services/audioura:storied`
- maxScale `10`, concurrency `80`, cpu `1`, memory `512Mi`
- cpu-throttling `false`, startup-cpu-boost `true`
- Cloud SQL annotation: `run.googleapis.com/cloudsql-instances: audiotours-migration:us-central1:audioura-db`
- env values:
  - `DB_HOST=/cloudsql/audiotours-migration:us-central1:audioura-db`, `DB_NAME=audiotours`,
    `DB_USER=admin`, `DB_PORT=5432`
  - `TOUR_STORAGE_MODE=cloud`, `JOB_STORE_MODE=memory`, `BLOB_STORAGE_TYPE=r2`
  - `R2_ENDPOINT=https://4b4aa47cda0cc65f20b20fac0b363ac7.r2.cloudflarestorage.com`, `R2_BUCKET=v1-audiotours-r2-bucket`
  - `TOUR_GENERATOR_URL=https://tour-generator-60899077572.us-central1.run.app`  ← **Beta (pre-deploy)**
  - `MODERNIZED_URL=https://tour-modernized-60899077572.us-central1.run.app`      ← **Beta (pre-deploy)**
  - `TRANSLATION_URL=https://translation-service-60899077572.us-central1.run.app`
  - `COORDINATES_URL=https://coordinates-60899077572.us-central1.run.app`
  - `POLLY_TTS_URL=https://polly-tts-60899077572.us-central1.run.app`
  - `TOUR_UPDATE_URL=https://tour-orchestrator-storied-60899077572.us-central1.run.app`
  - `USER_API_URL=https://tour-orchestrator-storied-60899077572.us-central1.run.app`
  - `TOUR_TRACK=storied`, `STORIED_MODE=true`
  - secrets (by ref): `DB_PASSWORD=db-password:latest`, `OPENAI_API_KEY=openai-api-key:latest`,
    `AWS_ACCESS_KEY_ID=aws-access-key-id:latest`, `AWS_SECRET_ACCESS_KEY=aws-secret-access-key:latest`,
    `R2_ACCESS_KEY_ID=r2-access-key-id:latest`, `R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest`
- IAM policy: none (null)

### `tour-generator-storied`
- **Does not exist** (to be created by the deploy).

### `tour-modernized-storied`
- **Does not exist** (to be created by the deploy).

### Beta controls (must remain unchanged)

**`tour-orchestrator`**
- ready revision: `tour-orchestrator-00025-cvz`
- image: `us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v22-local474`
- maxScale `10`, minScale `0`, concurrency `80`, cpu `1`, memory `512Mi`, cpu-throttling `false`
- Cloud SQL annotation present
- URLs: `TOUR_GENERATOR_URL=https://tour-generator-60899077572.us-central1.run.app`,
  `MODERNIZED_URL=https://tour-modernized-60899077572.us-central1.run.app`
- IAM policy: none (null)

**`tour-generator`**
- ready revision: `tour-generator-00023-nrv`
- image: `us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v36-local474`
- maxScale `5`, minScale `0`, concurrency `40`, cpu `1`, memory `512Mi`, cpu-throttling `true`
- env: `TOUR_STORAGE_MODE=cloud`, `PYTHONUNBUFFERED=1`, `KEY_FIX=v3`, `OAIFIX=done`;
  secret `OPENAI_API_KEY=openai-api-key:latest`
- IAM: `roles/run.invoker` → `serviceAccount:60899077572-compute@developer.gserviceaccount.com`

**`tour-modernized`**
- ready revision: `tour-modernized-00012-7sg`
- image: `us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v37`
- maxScale `1`, concurrency `5`, cpu `2`, memory `1Gi`, cpu-throttling `false`
- env: `TOUR_STORAGE_MODE=cloud`, `BLOB_STORAGE_TYPE=r2`,
  `R2_ENDPOINT=https://4b4aa47cda0cc65f20b20fac0b363ac7.r2.cloudflarestorage.com`,
  `R2_BUCKET=v1-audiotours-r2-bucket`, `POLLY_TTS_URL=https://polly-tts-60899077572.us-central1.run.app`,
  `POLLY_FIX=v3`; secrets (by ref): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
  `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` (each `:latest`)
- IAM: `roles/run.invoker` → `serviceAccount:60899077572-compute@developer.gserviceaccount.com`

---

## Not yet produced (blocked on the invocation confirmation above)
- `--apply` output (the deploy did not run)
- `audioura-storied:v1` digest
- new service URLs and revisions (`tour-generator-storied`, `tour-modernized-storied`)
- after-state table + before/after diff
- orchestrator `TOUR_GENERATOR_URL` / `MODERNIZED_URL` read-back (must contain `-storied`)
