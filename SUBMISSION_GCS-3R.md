# SUBMISSION — GCS-3R: make the Storied generator deploy actually work (stage only)

**Agent:** Services Kiro
**Branch:** `kiro/gcs-3r` (from HEAD `0de517c`; `git merge-base --is-ancestor 0de517c HEAD` → 0, base OK)
**Deploy commit staged by the script:** `3fb3325` (this commit; ≥ `0de517c` floor)
**ClickUp:** `wdvrdaxxm9` (deploy approved by Michael in chat 15:42, 2026-09-15)
**Bounce of:** GCS-3 `kiro/gcs-3-storied-generator-deploy @ b9662fe`. Structure kept: separate
`audioura-storied` repo, `assert_target_is_storied`, three services, orchestrator env repoint.

**Nothing was deployed.** No `gcloud run deploy/update`, no IAM change, no `docker push`, no secret
creation. Only read-only `gcloud describe`/`get-iam-policy`/`secrets list` and one authorised local
test tour (2 stops). The real `--apply` is a separate dispatch after LEAD review.

---

## 1. Config table — every env var the Storied generator reads (AC1)

Values below are what the **script sets** on `tour-generator-storied`. "Source" = live config or code
that established the value. R/O/T = **R**equired / **O**ptional-with-default / **T**oggle. Every DB and
key finding was read from the code (grep + file reads) and cross-checked against live Cloud Run.

| Env var | Value set by script | R/O/T | Why / code evidence |
|---|---|---|---|
| `STORIED_MODE` | `true` | **T (required for this task)** | Master switch. `generate_tour_text.py:5452` `os.environ.get("STORIED_MODE","false")==...`. `false` ⇒ Beta-parity pipeline (the whole comparison is lost). |
| `TOUR_STORAGE_MODE` | `cloud` | R | Live Beta generator floor; live orchestrator-storied. Cloud blob/DB storage vs local files. |
| `PYTHONUNBUFFERED` | `1` | O | Live Beta generator. Log flushing so Cloud Run logs appear. |
| `TOUR_TRACK` | `storied` | T | Recorded on tours; orchestrator reads it (`:554`). Set on the generator too for parity. |
| `DB_HOST` | `/cloudsql/audiotours-migration:us-central1:audioura-db` | R | Live orchestrator-storied DB block. libpq treats a `/cloudsql/...` path as a unix-socket dir. Keyword-arg path in `generate_tour_text_service.py:83`, `rag_retriever`, `selection_reason_filter`. |
| `DB_NAME` | `audiotours` | R | Live orchestrator-storied. `dbname=` in every keyword-arg connect. |
| `DB_USER` | `admin` | R | Live orchestrator-storied. |
| `DB_PORT` | `5432` | O | Ignored when a socket is used (libpq), but set for parity with orchestrator. |
| `DB_PASSWORD` | secret `db-password:latest` | R | Keyword-arg connects read it (default `password123` must NOT ship). |
| `DATABASE_URL` | `postgresql://admin@/audiotours?host=/cloudsql/...` (password-less) | **R** | **URL-idiom modules read ONLY this / `VENUE_CACHE_DB_URL`** and otherwise fall back to host `postgres-2` (unresolvable on Cloud Run): `venue_resolver.py:1143-1144`, `work_story_searcher.py:122-123`, `area_resolver.py:1438/1499`. Also enables the S20 tour cache (`generate_tour_text.py:5534` — cache is disabled if unset). Password supplied via `PGPASSWORD` (below). |
| `VENUE_CACHE_DB_URL` | same as `DATABASE_URL` | O | First choice in venue/work-story modules; set explicitly so it can't inherit a stale value. |
| `PGPASSWORD` | secret `db-password:latest` | R (mechanism) | libpq completes the password-less `DATABASE_URL` from `PGPASSWORD`. **Verified locally** (see §2): `psycopg2.connect('postgresql://admin@postgres-2:5432/audiotours')` with `PGPASSWORD` set → `PWLESS_URL_OK`. |
| `OPENAI_API_KEY` | secret `openai-api-key:latest` | **R** | Only truly generation-critical key; tour aborts without it. Live Beta generator + orchestrator-storied. |
| `GEMINI_API_KEY` | **not set** (no secret exists) | O | See degradation report §3. |
| `SERP_API_KEY` | **not set** (no secret exists) | O | See degradation report §3. |
| `GOOGLE_API_KEY` | **not set** (no secret exists) | O | Alias of `GEMINI_API_KEY` only (§3). |
| `NOMINATIM_URL` | **not set** (code default) | O | `geocode_stops.py:59` defaults to public Nominatim; keyless. |

**Cloud SQL:** `--add-cloudsql-instances audiotours-migration:us-central1:audioura-db` (the annotation the
live orchestrator-storied carries).

`tour-modernized-storied` env (mirrors **live Beta `tour-modernized`** exactly):
`TOUR_STORAGE_MODE=cloud`, `BLOB_STORAGE_TYPE=r2`, `R2_ENDPOINT=…r2.cloudflarestorage.com`,
`R2_BUCKET=v1-audiotours-r2-bucket`, `POLLY_TTS_URL=https://polly-tts-…run.app`, `POLLY_FIX=v3`;
secrets `aws-access-key-id`, `aws-secret-access-key`, `r2-access-key-id`, `r2-secret-access-key`;
cpu 2, 1Gi, concurrency 5, maxScale 1, `--no-cpu-throttling`, timeout 300.

**Resources (generator):** cpu 1, **512Mi**, concurrency 40, maxScale 5, `--no-cpu-throttling`,
`--max-instances=1`, timeout 300. Memory is from a **measured** run (§2), not a guess.
`--no-cpu-throttling` is required because generation runs on a background daemon thread **after** the
HTTP response returns (`generate_tour_text_service.py` `threading.Thread(..., daemon=True)`); with
throttling that thread starves and tours never finish (`remind_Services_ai.md`).

---

## 2. Local end-to-end proof from the built image (AC2, B4)

**Build:** `docker build -f Dockerfile.cloudrun -t audioura-storied:gcs3r-local --build-arg GIT_SHA=0de517c… .`
(HEAD at build time). Then ran the generator container on the local Docker network `development_default`
so it reached the local Postgres (`postgres-2`), with **exactly the env the script sets** except DB
pointed at local Postgres instead of the Cloud SQL socket.

**Request:** `POST /generate {"location":"restaurants in the North End, Boston","tour_type":"","total_stops":2}`

**Result — completed:**
- HTTP `200` on submit (`{"job_id":…,"status":"queued"}`), `/status` reached **`completed`**.
- **Category inferred:** log line `[LOCAL-474] tour_type='' → category='restaurant' (source=inferred)`; tour body header `Tour-Category: restaurant`.
- **Wall time:** ~169 s.
- **Peak memory:** ~**120 MiB** (`docker stats`) → 512Mi is ample; 1Gi would be waste.
- **OpenAI cost:** `[COST_METER] FRESH | tour_generate | $0.105073` (`[COST_CEILING] COST OK: $0.1051 <= target $0.1500`).
- DB connected (no connection errors; SQL executed — the only DB messages were non-fatal
  `relation "stop_corpus" does not exist` before I migrated the local schema).
- Output: 2 real stops (Mamma Maria, Modern Pastry Shop) with orientation, story, directions,
  coordinates and a closing offer — genuine Storied output.

**PGPASSWORD mechanism verified:** a standalone check in the same image —
`psycopg2.connect('postgresql://admin@postgres-2:5432/audiotours')` with only `PGPASSWORD` set —
returned `PWLESS_URL_OK`. So the password-less `DATABASE_URL` + `PGPASSWORD`-from-secret shape the
script uses is valid.

### 2b. BLOCKER found by this run — the image is incomplete (B4b)
The first two attempts **errored mid-generation**, not from config but from the **image**:
`Dockerfile.cloudrun` does `COPY *.py /app/`, which copies **repo-root `.py` only**. The Storied
generator, via `style_validator_detector.py:33-34`, imports two modules that live **under `tests/`**:

```
from db_connection import get_connection
from stop_anchor_detector_v2 import parse_tour_stops
```

`tests/db_connection.py` and `tests/stop_anchor_detector_v2.py` are **not at repo root**, so they never
reach `/app`. It also reads two non-`.py` assets that `COPY *.py` skips: `templates/spine_restaurant.txt`
and `story_type_taxonomy.json`. Symptoms in the container log:
`No module named 'db_connection'` → then `No module named 'stop_anchor_detector_v2'` →
`No such file or directory: '/app/templates/spine_restaurant.txt'` / `story_type_taxonomy.json`.
Result: **a Storied tour boots, passes `/health`, then fails mid-generation** regardless of env.

**Fix applied (this branch):** added to `Dockerfile.cloudrun` after `COPY *.py`:
```dockerfile
COPY tests/db_connection.py /app/db_connection.py
COPY tests/stop_anchor_detector_v2.py /app/stop_anchor_detector_v2.py
COPY story_type_taxonomy.json /app/story_type_taxonomy.json
COPY templates/ /app/templates/
```
With these present, the same request completed (the run reported above). The deploy script also grew a
preflight guard (`assert_build_context_complete`) that **refuses to build** until the Dockerfile ships
these, so this class of defect can't recur silently.

> **Open blocking question for LEAD:** copying app modules out of `tests/` is the minimal fix, but those
> modules arguably belong at repo root (they are runtime dependencies, not tests). Options: (a) keep the
> `COPY tests/… ` lines as-is (done), or (b) `git mv tests/db_connection.py tests/stop_anchor_detector_v2.py`
> to root and adjust imports. (a) is lower-risk for this deploy and is what ships now; (b) is cleaner but
> touches import paths repo-wide and is out of GCS-3R scope. Flagging for a follow-up decision.

---

## 3. Gemini / SERP / Google degradation report (B1.2)

**Secret Manager has no Gemini/SERP/Google key** (`gcloud secrets list`: only `openai-api-key`,
`db-password`, `aws-*`, `r2-*`, `gateway-api-key`, `internal-service-secret`, Android keys). The script
**does not create them and copies nothing from `.env`.** What the pipeline does without each:

| Key | Stage it powers | Absent behavior | Tour completes? | Quality impact |
|---|---|---|---|---|
| `SERP_API_KEY` | Web **story-mining** (SQ-S1/S2 `search_stories_for_stop/_for_tour`), SERP-confirmed dated leads, interpretive quote verification, exhibition/dining web lookups | **Skips silently.** `work_story_searcher._serp_search():834` → `if not SERP_API_KEY: print("[SQ-S2] No SERP_API_KEY — skipping"); return [], 0.0`. Module docstring: "Never fails the tour — degrades gracefully." Unverified quotes are dropped. | **Yes** | **HIGH** — the headline Storied feature. Falls back to corpus/cache + model knowledge. A warm `work_stories` cache masks it; a cold Preview DB shows the most loss. |
| `GEMINI_API_KEY` | Second model for **cross-model agreement** (LOCAL-488), grounded Gemini fact-check with sources, restaurant/stop knowledge fallback | **Skips / OpenAI-only.** `story_leads.py:117` `key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY'); if not key: return ''`. STEP-4 fan-out logs "providers span fewer than two model families … set GEMINI_API_KEY" and skips. | **Yes** | **MEDIUM** — loses the strongest misattribution catch and per-sentence source grounding. Generation still runs on OpenAI. |
| `GOOGLE_API_KEY` | **None of its own** — only an alternate name for `GEMINI_API_KEY` (`… or os.environ.get('GOOGLE_API_KEY')`). Not used for Maps/Places/geocoding anywhere. | Identical to Gemini-absent. | **Yes** | **None independently.** Not creating it has zero geocoding consequence. |
| `NOMINATIM_URL` (context) | Stop-coordinate geocoding sanity-check | Has a default (`geocode_stops.py:59` → public OSM Nominatim); failures return `None` ("no opinion"), never abort. Keyless. | **Yes** | **LOW/none** from omission. |

**Fairness verdict:** With `OPENAI_API_KEY` + `STORIED_MODE=true` (both provided), a Preview without
Gemini/SERP/Google **produces a complete tour end-to-end** and is a **fair test of Storied's structure,
plumbing and Beta-parity**, but it **understates story quality** (SERP is the biggest lever; Gemini
second). GOOGLE and NOMINATIM cost nothing to omit. To measure true top-end Storied quality you'd want
`SERP_API_KEY` (and ideally `GEMINI_API_KEY`) — but that is an outward-facing change for Michael, out of
scope here.

---

## 4. `--dry-run` output (AC4)

Run: `./deploy_storied_generator.sh --dry-run` (tree clean; nothing executed). Abridged to the mutating
commands (full preflight prints all guards OK, incl. "HEAD >= storied floor 0de517c" and "build context
ships db_connection, stop_anchor_detector_v2, templates/, story_type_taxonomy.json"):

**Repo / build:** `us-central1-docker.pkg.dev/audiotours-migration/services/**audioura-storied**:v1`
(separate from Beta's `audioura`), built from `Dockerfile.cloudrun`, `--build-arg GIT_SHA=3fb3325…` (HEAD).

**tour-generator-storied** — new, private, full config, Cloud SQL:
```
gcloud run deploy 'tour-generator-storied' --region 'us-central1' \
  --image '…/audioura-storied:v1' --command 'python' --args 'generate_tour_text_service.py' \
  --no-allow-unauthenticated \
  --add-cloudsql-instances 'audiotours-migration:us-central1:audioura-db' \
  --set-env-vars 'STORIED_MODE=true,TOUR_STORAGE_MODE=cloud,PYTHONUNBUFFERED=1,TOUR_TRACK=storied,\
DB_HOST=/cloudsql/audiotours-migration:us-central1:audioura-db,DB_NAME=audiotours,DB_USER=admin,DB_PORT=5432,\
DATABASE_URL=postgresql://admin@/audiotours?host=/cloudsql/audiotours-migration:us-central1:audioura-db,\
VENUE_CACHE_DB_URL=postgresql://admin@/audiotours?host=/cloudsql/audiotours-migration:us-central1:audioura-db' \
  --set-secrets 'OPENAI_API_KEY=openai-api-key:latest,DB_PASSWORD=db-password:latest,PGPASSWORD=db-password:latest' \
  --no-cpu-throttling --max-instances=1 --concurrency='40' --cpu='1' --memory='512Mi' --timeout='300' --quiet
gcloud run services add-iam-policy-binding 'tour-generator-storied' --region 'us-central1' \
  --member='serviceAccount:60899077572-compute@developer.gserviceaccount.com' --role='roles/run.invoker' --quiet
```

**tour-modernized-storied** — new, private, mirrors Beta:
```
gcloud run deploy 'tour-modernized-storied' --region 'us-central1' \
  --image '…/audioura-storied:v1' --command 'python' --args 'tour_generation_modernized.py' \
  --no-allow-unauthenticated \
  --set-env-vars 'TOUR_STORAGE_MODE=cloud,BLOB_STORAGE_TYPE=r2,R2_ENDPOINT=https://…r2.cloudflarestorage.com,\
R2_BUCKET=v1-audiotours-r2-bucket,POLLY_TTS_URL=https://polly-tts-…run.app,POLLY_FIX=v3' \
  --set-secrets 'AWS_ACCESS_KEY_ID=aws-access-key-id:latest,AWS_SECRET_ACCESS_KEY=aws-secret-access-key:latest,\
R2_ACCESS_KEY_ID=r2-access-key-id:latest,R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest' \
  --no-cpu-throttling --max-instances='1' --concurrency='5' --cpu='2' --memory='1Gi' --timeout='300' --quiet
gcloud run services add-iam-policy-binding 'tour-modernized-storied' --region 'us-central1' \
  --member='serviceAccount:60899077572-compute@developer.gserviceaccount.com' --role='roles/run.invoker' --quiet
```

**tour-orchestrator-storied** — image + the two URLs ONLY (B3):
```
gcloud run deploy 'tour-orchestrator-storied' --region 'us-central1' \
  --image '…/audioura-storied:v1' --command 'python' --args 'tour_orchestrator_service.py' \
  --update-env-vars 'TOUR_TRACK=storied,\
TOUR_GENERATOR_URL=https://tour-generator-storied-<hash>-uc.a.run.app,\
MODERNIZED_URL=https://tour-modernized-storied-<hash>-uc.a.run.app' --quiet
```
No `--set-env-vars` (would wipe ~20 vars), **no** resource/scaling/throttling flags (live stays
maxScale 10, concurrency 80, cpu 1, 512Mi, cpu-throttling false, Cloud SQL annotation).

**`assert_target_is_storied` guards** every mutating call: the three `gcloud run deploy`, both
`add-iam-policy-binding`, and the three `update-traffic` in `--rollback`. No Beta service is ever named.

---

## 5. Post-deploy check the script prints (AC5)

After deploy the script reads `TOUR_GENERATOR_URL` and `MODERNIZED_URL` back off
`tour-orchestrator-storied` and **fails unless both contain `-storied`** (plus confirms
`TOUR_TRACK=storied`):
```
ORCH_GEN_URL=$(gcloud run services describe tour-orchestrator-storied --region us-central1 \
  --format="value(spec.template.spec.containers[0].env.filter(\"name:TOUR_GENERATOR_URL\").extract(value))" | tr -d '[]')
case "$ORCH_GEN_URL" in *-storied*) : ;; *) fail "… still delegating to Beta. Roll back: $0 --rollback";; esac
```
I verified the read-back expression works against the live service today — it returns
`['https://tour-generator-60899077572.us-central1.run.app']` (Beta), i.e. the check would **correctly
fail right now** and will pass only once the deploy repoints the URLs. This is verification by effect,
not by exit code.

---

## Live evidence gathered (read-only)

- Beta `tour-generator`: env `TOUR_STORAGE_MODE=cloud`, `OPENAI_API_KEY`(secret), `PYTHONUNBUFFERED=1`; cpu 1/512Mi/concurrency 40/maxScale 5/**cpu-throttling true**/timeout 300 — the floor. Storied needs DB+STORIED_MODE+TOUR_TRACK and **`--no-cpu-throttling`**.
- Beta `tour-modernized`: env/secrets mirrored above; cpu 2/1Gi/concurrency 5/maxScale 1/cpu-throttling false/timeout 300.
- Live `tour-orchestrator-storied`: maxScale 10, concurrency 80, cpu 1, 512Mi, timeout 300, cpu-throttling false, Cloud SQL annotation; already carries DB_HOST=/cloudsql/…, TOUR_TRACK=storied, STORIED_MODE=true (confirms B3 — the GCS-3 forced flags would have downgraded it).
- Beta `tour-generator` IAM: exactly `roles/run.invoker` for `serviceAccount:60899077572-compute@developer.gserviceaccount.com`, not public (B2 template).
- Secret Manager: no gemini/serp/google secret (B1.2).

## Acceptance criteria
1. Config table — §1. ✓
2. One local end-to-end tour, 200/completed, category inferred, memory + cost — §2. ✓
3. Gemini/SERP/Google degradation report — §3. ✓
4. `--dry-run` with all required properties — §4. ✓
5. Post-deploy `-storied` read-back check — §5. ✓
Extra: B4b image-completeness blocker fixed + guarded — §2b. ✓

## PROCESS notes / disclosures
- Windows host; script authored/run in Git Bash (`C:\Program Files\Git\bin\bash.exe`). Script uses
  `set -euo pipefail`; file writes used `encoding utf-8` implicitly (ASCII content).
- Local test DB only. No writes to production Postgres. No `DELETE FROM audio_tours`. One authorised
  2-stop OpenAI tour ($0.105).
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  `GCLOUD_STORIED_START_HERE.md`, `BUILD_NUMBERS.md`.
- **Disclosure:** while cleaning up local Docker test artifacts I also removed a pre-existing throwaway
  container `l474-gen-before` (a disposable earlier generator test, host port 5100→5000). It was not
  part of the `development-*` compose stack, which is fully intact (10 containers + Postgres healthy).
  If it is still needed it can be recreated; I could not restore it.
- Files committed on `kiro/gcs-3r` (`3fb3325`): `deploy_storied_generator.sh` (rewritten),
  `Dockerfile.cloudrun` (B4b COPY fix). This submission committed separately.
