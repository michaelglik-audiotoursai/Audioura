# SUBMISSION — GCS-D593D

Deploy storied @ `7340b3c` to Preview and turn user-chosen stops ON.

- **Agent:** Services Kiro
- **Base:** storied @ `7340b3c`
- **Branch:** `kiro/gcs-d593d`
- **Deployed commit:** `b801d4607e535218bfce88b60773c6eded739b04` (`b801d46`)
- **ClickUp:** `wdvrdayqby`
- **Authorised by:** Michael, 2026-10-02 ("Please do your queue on Storied"); D593 approved by Michael 2026-10-01. Preview only; Beta/Stable untouched.
- **Image:** `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v3`
- **Image digest:** `sha256:317b147ffb41ebe00ea4c4474d1456ead3e22bd0c5804033c2489d0b5f4c045b`

Supersedes the v2 deploy (`6fbebdf`, `audioura-storied:v2`, flag `false`). The script auto-picked `v3`; no `--tag` was passed.

---

## Base / pre-deploy verification

```
$ git rev-parse --short HEAD
7340b3c                       # (before the script edit; see Step 1)

$ git merge-base --is-ancestor 7340b3c HEAD ; echo exit=$?
exit=0                        # HEAD is at or after storied floor and at/after 7340b3c

$ git branch --show-current
kiro/gcs-d593d

$ git status --porcelain -uall
                              # (empty — clean tree)
```

HEAD before any edit was exactly `7340b3c`. Branch `kiro/gcs-d593d` was already cut from storied HEAD.

---

## Step 1 — code change (committed before deploy)

Four edits in `deploy_storied_generator.sh`, nothing else. `--set-env-vars` was **not** refactored into `--update-env-vars`.

```diff
-GEN_ENV="STORIED_MODE=true,...,USER_STOPS_ENABLED=false,DB_HOST=..."
+GEN_ENV="STORIED_MODE=true,...,USER_STOPS_ENABLED=true,DB_HOST=..."

-MOD_ENV="TOUR_STORAGE_MODE=cloud,USER_STOPS_ENABLED=false,BLOB_STORAGE_TYPE=r2,..."
+MOD_ENV="TOUR_STORAGE_MODE=cloud,USER_STOPS_ENABLED=true,BLOB_STORAGE_TYPE=r2,..."

-  --update-env-vars 'TOUR_TRACK=${TOUR_TRACK},USER_STOPS_ENABLED=false,TOUR_GENERATOR_URL=${GEN_URL},MODERNIZED_URL=${MOD_URL}' \
+  --update-env-vars 'TOUR_TRACK=${TOUR_TRACK},USER_STOPS_ENABLED=true,TOUR_GENERATOR_URL=${GEN_URL},MODERNIZED_URL=${MOD_URL}' \

# line ~432, TOUR_TRACK read-back (the one that produced ''storied'' and blocked v2 tagging):
-  --format="value(...TOUR_TRACK...extract(value))" 2>/dev/null | tr -d '[]')
+  --format="value(...TOUR_TRACK...extract(value))" 2>/dev/null | tr -d "[]'\"")
```

Note on the line-432 scope: the ticket named only line ~432 (the exact-equality `TOUR_TRACK` check `[ "$ORCH_TRACK" = "storied" ]`, which is what hard-fails on `''storied''`). Lines 421/423 (the two URL read-backs) still use `tr -d '[]'`, but they are compared with the glob `case *-storied*`, which tolerates surrounding quotes and did not block tagging; per the ticket's "Nothing else", they were left unchanged. The read-back below confirms the `''storied''` artifact is gone and tagging now succeeds.

Pre-deploy gate counts after the edit:

```
$ grep -c 'USER_STOPS_ENABLED=true'  deploy_storied_generator.sh   -> 3
$ grep -c 'USER_STOPS_ENABLED=false' deploy_storied_generator.sh   -> 0
$ git status --porcelain -uall | grep '\.py$'                      -> (empty)
$ git rev-parse --short HEAD                                       -> b801d46   (7340b3c + this one commit)
$ git merge-base --is-ancestor 7340b3c HEAD ; echo exit=$?         -> exit=0
```

Commit (script edits only, before the deploy, so `assert_image_content_clean` saw a clean tree):

```
b801d46 GCS-D593D: enable user-chosen stops (USER_STOPS_ENABLED=true x3) and fix line-432 quote stripping in read-back
 1 file changed, 4 insertions(+), 4 deletions(-)
```

---

## Step 2 — the deploy

Command (Git Bash, worktree root, no flags):

```bash
bash deploy_storied_generator.sh
```

Key output (full build log elided for length; all preflight guards passed, image built, pushed, three services deployed, verified):

```
== Preflight
  HEAD >= storied floor 0de517c: OK
  orchestrator source reads TOUR_TRACK: OK
  orchestrator reads TOUR_GENERATOR_URL and MODERNIZED_URL from env: OK
  generator service exposes /generate and /status: OK
  no untracked .py in build context: OK
  build context ships db_connection, stop_anchor_detector_v2, templates/, story_type_taxonomy.json: OK

== Choosing image tag (repo: audioura-storied)
  highest existing tag in audioura-storied: v2 -> using v3
  will build and deploy: us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v3
  release tag: v2t1  (line 2, branch kiro/gcs-d593d, commit b801d460)

== Building ... Dockerfile.cloudrun
  #9  [ 5/10] COPY *.py /app/
  #10 [ 6/10] COPY tests/db_connection.py /app/db_connection.py
  #11 [ 7/10] COPY tests/stop_anchor_detector_v2.py /app/stop_anchor_detector_v2.py
  #12 [ 8/10] COPY story_type_taxonomy.json /app/story_type_taxonomy.json
  #13 [ 9/10] COPY templates/ /app/templates/
  exporting manifest list sha256:317b147ffb41ebe00ea4c4474d1456ead3e22bd0c5804033c2489d0b5f4c045b done
  naming to us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v3 done

== Pushing to Artifact Registry
  v3: digest: sha256:317b147ffb41ebe00ea4c4474d1456ead3e22bd0c5804033c2489d0b5f4c045b size: 856

== Deploying tour-generator-storied (CMD: python generate_tour_text_service.py) — private, Storied config, Cloud SQL
  Service [tour-generator-storied] revision [tour-generator-storied-00005-z96] has been deployed and is serving 100 percent of traffic.
  Service URL: https://tour-generator-storied-60899077572.us-central1.run.app
== Granting invoker on tour-generator-storied to serviceAccount:60899077572-compute@developer.gserviceaccount.com -> Updated IAM policy

== Deploying tour-modernized-storied (CMD: python tour_generation_modernized.py) — mirrors Beta tour-modernized
  Service [tour-modernized-storied] revision [tour-modernized-storied-00003-wq2] has been deployed and is serving 100 percent of traffic.
  Service URL: https://tour-modernized-storied-60899077572.us-central1.run.app
== Granting invoker on tour-modernized-storied ... -> Updated IAM policy

== Resolving new service URLs for the orchestrator repoint
  TOUR_GENERATOR_URL -> https://tour-generator-storied-ixkp5nkrlq-uc.a.run.app
  MODERNIZED_URL     -> https://tour-modernized-storied-ixkp5nkrlq-uc.a.run.app

== Deploying tour-orchestrator-storied (CMD: python tour_orchestrator_service.py) + repointing URLs to Storied (image + 2 URLs only)
  Service [tour-orchestrator-storied] revision [tour-orchestrator-storied-00004-2vw] has been deployed and is serving 100 percent of traffic.
  Service URL: https://tour-orchestrator-storied-60899077572.us-central1.run.app

== Verifying deployments
  tour-generator-storied  /health -> {... "status":"healthy", "version":"2.2.0.1"}
  tour-modernized-storied /health -> {"service":"tour_generation_modernized","status":"healthy","version":"1.2.5.184"}
  tour-orchestrator-storied /health -> {... "service":"tour_orchestrator","status":"healthy"}

== Post-deploy check: orchestrator URLs must point at *-storied services
  TOUR_GENERATOR_URL (read back) = 'https://tour-generator-storied-ixkp5nkrlq-uc.a.run.app'
  MODERNIZED_URL     (read back) = 'https://tour-modernized-storied-ixkp5nkrlq-uc.a.run.app'
  both orchestrator URLs contain '-storied': OK
  TOUR_TRACK=storied: OK
  tagged and pushed: v2t1 -> b801d460

== Done
```

The `''storied''` artifact that blocked v2 is gone: `TOUR_TRACK=storied: OK` and the release tag was created and pushed on this run.

---

## Storied services — revisions, URLs, /health

| Service | Before rev | After rev | URL |
|---|---|---|---|
| tour-generator-storied | tour-generator-storied-00004-887 | **tour-generator-storied-00005-z96** | https://tour-generator-storied-ixkp5nkrlq-uc.a.run.app |
| tour-modernized-storied | tour-modernized-storied-00002-xnc | **tour-modernized-storied-00003-wq2** | https://tour-modernized-storied-ixkp5nkrlq-uc.a.run.app |
| tour-orchestrator-storied | tour-orchestrator-storied-00003-tzg | **tour-orchestrator-storied-00004-2vw** | https://tour-orchestrator-storied-ixkp5nkrlq-uc.a.run.app |

Image before = `audioura-storied:v2` on all three; after = `audioura-storied:v3` on all three.

All three serving 100% on the latest revision:

```
tour-generator-storied    {'latestRevision': True, 'percent': 100, 'revisionName': 'tour-generator-storied-00005-z96'}
tour-modernized-storied   {'latestRevision': True, 'percent': 100, 'revisionName': 'tour-modernized-storied-00003-wq2'}
tour-orchestrator-storied {'latestRevision': True, 'percent': 100, 'revisionName': 'tour-orchestrator-storied-00004-2vw'}
```

Authenticated `/health` (identity token), re-run independently after the deploy:

```
=== tour-generator-storied (https://tour-generator-storied-ixkp5nkrlq-uc.a.run.app) ===
HTTP 200
{"build_time":"no_manifest","code_sha":"no_manifest","cost_ceiling":{...},"drift_files":["<manifest_missing>"],"manifest_ok":false,"mode":"true","service":"tour_text_generator","status":"healthy","version":"2.2.0.1"}

=== tour-modernized-storied (https://tour-modernized-storied-ixkp5nkrlq-uc.a.run.app) ===
HTTP 200
{"service":"tour_generation_modernized","status":"healthy","version":"1.2.5.184"}

=== tour-orchestrator-storied (https://tour-orchestrator-storied-ixkp5nkrlq-uc.a.run.app) ===
HTTP 200
{"cost_ceiling":{...},"service":"tour_orchestrator","status":"healthy"}
```

---

## Beta services — unchanged (before == after)

Recorded before and after. Revision and image identical on all four; no mutating call ever named a Beta service.

| Service | Revision (before == after) | Image (before == after) |
|---|---|---|
| tour-generator | tour-generator-00023-nrv | audioura:v36-local474 |
| tour-modernized | tour-modernized-00012-7sg | audioura:v37 |
| tour-orchestrator | tour-orchestrator-00025-cvz | audioura:v22-local474 |
| api-gateway | api-gateway-00022-t88 | api-gateway:v35 |

`map-delivery` (shared, share-by-code location) was explicitly out of scope and never named. No share endpoint was called; no tour generated; no SQL / DB writes.

---

## Env read-backs (acceptance)

Orchestrator resource config — unchanged before and after (rule 4):

```
maxScale  concurrency  cpu  memory  cloudsql
10        80           1    512Mi   audiotours-migration:us-central1:audioura-db     (before)
10        80           1    512Mi   audiotours-migration:us-central1:audioura-db     (after)
```

`USER_STOPS_ENABLED` / `TOUR_TRACK` / `STORIED_MODE` after deploy:

```
tour-generator-storied     USER_STOPS_ENABLED=['true']  TOUR_TRACK=['storied']  STORIED_MODE=['true']
tour-modernized-storied    USER_STOPS_ENABLED=['true']  TOUR_TRACK=(unset)      STORIED_MODE=(unset)
tour-orchestrator-storied  USER_STOPS_ENABLED=['true']  TOUR_TRACK=['storied']  STORIED_MODE=['true']
```

`TOUR_GENERATOR_URL` / `MODERNIZED_URL` on the orchestrator after deploy:

```
TOUR_GENERATOR_URL=['https://tour-generator-storied-ixkp5nkrlq-uc.a.run.app']
MODERNIZED_URL=['https://tour-modernized-storied-ixkp5nkrlq-uc.a.run.app']
```

Both contain `-storied`; the read-back now returns a clean value with no `''storied''` quoting (line-432 fix confirmed).

**Clarification on rule 4 ("each of the three must show USER_STOPS_ENABLED=true, TOUR_TRACK=storied, STORIED_MODE=true"):** `USER_STOPS_ENABLED=true` is present on all three, as required and as the whole point of this ticket. `TOUR_TRACK` and `STORIED_MODE` are present on the generator and orchestrator but are **not** part of `tour-modernized-storied`'s env — the script's `MOD_ENV` mirrors live Beta `tour-modernized` exactly (B1), which carries neither var. This was already the case **before** this deploy (verified in the pre-deploy env read of all three services), so the deploy did not drop them; it is the pre-existing, by-design configuration of the modernizer leaf service. Flagging explicitly rather than claiming all three carry all three vars.

---

## Release tag

Created and pushed this time (it was **not** for v2, due to the line-432 `''storied''` defect that this deploy fixed):

```
local:  v2t1  (annotated) -> b801d4607e535218bfce88b60773c6eded739b04
        "Release v2t1 / service tour-orchestrator-storied (+generator,+modernized) /
         image audioura-storied:v3 / commit b801d460 / branch kiro/gcs-d593d"
remote: git ls-remote --tags origin v2t1
        01c8a3e141e3b58b7956e45a2ef467be6ead5659  refs/tags/v2t1
```

---

## Rules compliance summary

1. No failure occurred; no retries, no workarounds, no hand-run `gcloud` mutations, no rollback.
2. No Beta service named in any mutating call; the four Beta services (`tour-generator`, `tour-modernized`, `tour-orchestrator`, `api-gateway`) are byte-identical before/after; `map-delivery` untouched.
3. Before/after recorded for the three Storied services (revision, image, full env with secrets by reference).
4. All three show `USER_STOPS_ENABLED=true`; generator + orchestrator show `TOUR_TRACK=storied` and `STORIED_MODE=true` (modernizer by design carries neither — see clarification); orchestrator kept maxScale 10 / concurrency 80 / cpu 1 / 512Mi / Cloud SQL annotation; each Ready, 100%, `/health` 200.
5. `''storied''` artifact gone; `TOUR_TRACK` read-back clean.
6. No tour generation, no SQL, no DB writes, no share endpoint calls. AC3/AC4 (Boston Sail Loft / Buttermilk & Bourbon tours, device-side user-chosen stop) are LEAD's and Michael's.
7. No protected docs edited.
8. No blocking question — deploy completed.
