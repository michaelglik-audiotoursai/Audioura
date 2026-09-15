# GCS-2 — `/health` reports a real `code_sha` and `build_number`

**Agent:** Services Kiro
**Base:** storied (`b51576e`)
**Task branch:** `storied-health-code-sha`
**ClickUp:** `wdvrdaxyud`

Verified base before committing:

```
$ git rev-parse HEAD
b51576e3c43e49f978e3f50e2b589e9275fb0d59
$ git merge-base --is-ancestor b51576e HEAD ; echo exit=$?
exit=0
```

Deploy performed: **none.** Everything below was proven by building the
`Dockerfile.cloudrun` image locally and reading `/health` from a running
container. The real deploy is Michael's call (runbook `wdvrdaxn9f`).

---

## 1. Why `code_sha` was `unknown` / `no_manifest` — with evidence

The `/health` chain is:

```
/health  ->  manifest_check.get_health_info()  ->  reads /app/.build_manifest.json
```

`manifest_check.py` returns the sentinel `"no_manifest"` when
`/app/.build_manifest.json` does not exist, and `build_manifest.py`'s
`get_git_sha()` returns `"unknown"` when neither `/app/.git_sha` nor a working
`git` is available.

The **working** pattern already exists in `Dockerfile.generator` and
`Dockerfile.orchestrator`:

```dockerfile
ARG GIT_SHA=unknown
RUN echo "${GIT_SHA}" > /app/.git_sha
RUN python build_manifest.py /app /app/.build_manifest.json
```

But `Dockerfile.cloudrun` — the file the deploy scripts actually build
(`deploy_cloudrun_service.sh:49` and `deploy_tour_modernized.sh:46` both set
`DOCKERFILE="Dockerfile.cloudrun"`) — **declared `ARG GIT_SHA` and promoted it to
`ENV`, but never wrote `/app/.git_sha` and never ran `build_manifest.py`.** So a
cloudrun image had **no `/app/.build_manifest.json` at all**, and
`manifest_check` fell through to `no_manifest` / `unknown`.

The root reason the value cannot be computed inside the container is confirmed
in the Dockerfile itself: it does `COPY *.py /app/`. The `.git` directory is not
in the build context (`.dockerignore` lists `.git/`), so any `git rev-parse` run
inside the image has no repository to read. Confirmed by effect: the image built
in §3 has no `.git`, yet reports the correct SHA — because it comes from the
build arg, not from git.

So the plumbing was empty specifically in the one Dockerfile that ships to Cloud
Run. Half the mechanism (`ARG`/`ENV`, commit `bc1bc49`) was there; the two lines
that write the file and generate the manifest were missing.

---

## 2. What I changed

**Values are baked in at build time as build args — never computed in the container.**

- `Dockerfile.cloudrun`
  - Added `ARG BUILD_NUMBER="unknown"` and `ARG GIT_BRANCH="unknown"`, promoted
    both to `ENV`.
  - After `COPY *.py`, added the missing wiring, mirroring the per-service
    Dockerfiles:
    ```dockerfile
    RUN echo "${GIT_SHA}" > /app/.git_sha \
        && echo "${BUILD_NUMBER}" > /app/.build_number \
        && echo "${GIT_BRANCH}" > /app/.git_branch \
        && python build_manifest.py /app /app/.build_manifest.json
    ```
- `build_manifest.py` — added `get_build_number()` and `get_git_branch()`
  reading `/app/.build_number` and `/app/.git_branch`; added both plus `git_sha`
  to the manifest. Build-arg files are authoritative; the `git` fallback is kept
  only for host/dev runs and can never fire in the cloudrun image.
- `manifest_check.py` — `get_health_info()` now returns `build_number` and
  `git_branch` alongside `code_sha`.
- `tour_orchestrator_service.py`
  - `/health` now calls `manifest_check.get_health_info()` and returns
    `code_sha`, `build_number`, `git_branch`, `build_time`, `manifest_ok`
    (it previously returned none of these).
  - Added `_get_build_identity()` helper; `/status/<job_id>` now surfaces
    `code_sha` and `build_number` **alongside `track`**, in both the in-memory
    and the DB response branches, so the app needs no second call.
- `generate_tour_text_service.py` — `/health` now also surfaces `build_number`
  and `git_branch` (it already had `code_sha`).
- `deploy_cloudrun_service.sh` / `deploy_tour_modernized.sh` — compute
  `BUILD_NUMBER=$(git rev-list --count HEAD)` on the host and pass
  `--build-arg BUILD_NUMBER` and `--build-arg GIT_BRANCH` (`$BRANCH`) to
  `docker build`, next to the existing `RELEASE_TAG` / `GIT_SHA` args.

### Relationship to `release_tag.sh` (no second versioning scheme)

`build_number` is the **display** number the app shows (git commit count). It is
**not** a replacement for the release tag. `release_tag.sh` still owns identity:
`v<line>t<seq>` (e.g. `v2t...`), which is what makes `git checkout <tag>`
reconstitute a build, precisely because a commit count cannot (main count 75 <
storied count 2126 did not mean main lacked a fix — it had been ported). The
display number answers "which build am I looking at" in the UI; the release tag
answers "reconstitute exactly this". `GIT_SHA` remains the exact commit. All
three ride together in the same manifest.

---

## 3. Exact build command and verbatim `/health` output

Expected values for the built commit:

```
$ git rev-parse HEAD          -> b51576e3c43e49f978e3f50e2b589e9275fb0d59
$ git rev-list --count HEAD   -> 2150
```

Build (values passed explicitly, exactly as the deploy scripts would for a
`storied` deploy):

```
docker build -f Dockerfile.cloudrun -t gcs2-health-test:local \
  --build-arg RELEASE_TAG=v2t999 \
  --build-arg GIT_SHA=b51576e3c43e49f978e3f50e2b589e9275fb0d59 \
  --build-arg BUILD_NUMBER=2150 \
  --build-arg GIT_BRANCH=storied .
```

Build log (manifest step):

```
#10 [6/7] RUN echo "b51576e3c43e49f978e3f50e2b589e9275fb0d59" > /app/.git_sha
    && echo "2150" > /app/.build_number && echo "storied" > /app/.git_branch
    && python build_manifest.py /app /app/.build_manifest.json
#10 0.495 [build_manifest] Wrote /app/.build_manifest.json: 534 files,
    sha=b51576e3c43e49f978e3f50e2b589e9275fb0d59, build_number=2150, branch=storied
```

Run + `/health` (generator, port 5000 service — the one in the ticket's curl):

```
docker run -d --name gcs2-health -p 5555:8080 -e PORT=8080 \
  gcs2-health-test:local python generate_tour_text_service.py
curl http://localhost:5555/health
```

Verbatim output:

```json
{"build_number":"2150","build_time":"2026-09-15T02:47:44.051963+00:00","code_sha":"b51576e3c43e49f978e3f50e2b589e9275fb0d59","cost_ceiling":{"hard_limit_aborts":0,"last_abort_cost":null,"last_abort_job_id":null,"target_warnings":0},"git_branch":"storied","manifest_ok":true,"mode":"false","service":"tour_text_generator","status":"healthy","version":"2.2.0.1"}
```

Orchestrator (`python tour_orchestrator_service.py`), verbatim:

```json
{"build_number":"2150","build_time":"2026-09-15T02:47:44.051963+00:00","code_sha":"b51576e3c43e49f978e3f50e2b589e9275fb0d59","cost_ceiling":{"hard_limit_aborts":0,"last_abort_cost":null,"last_abort_job_id":null,"target_warnings":0},"git_branch":"storied","manifest_ok":true,"service":"tour_orchestrator","status":"healthy"}
```

`/status` surfaces the same identity (helper verified inside the running
orchestrator container, since a full job needs a DB):

```
$ docker exec gcs2-orch python -c "import tour_orchestrator_service as t, json; print(json.dumps(t._get_build_identity()))"
{"code_sha": "b51576e3c43e49f978e3f50e2b589e9275fb0d59", "build_number": "2150"}
```

### Acceptance criteria

1. `code_sha` = `b51576e3c43e49f978e3f50e2b589e9275fb0d59` (real), `build_number`
   = `2150` (numeric) — **not** `unknown`, **not** `no_manifest`. ✅
2. `2150` equals `git rev-list --count HEAD` for the built commit — proven by
   building and comparing, not by reading code. ✅
3. Storied vs Beta report different numbers — proven in §5. ✅
4. An older client ignoring the new fields is unaffected: all fields are
   additive top-level keys on `/health` and `/status`; nothing existing was
   renamed or removed. ✅
5. No change to tour-generation behaviour. The edits touch `/health`, `/status`,
   the manifest generator and the Dockerfile build steps only — no generation
   code path. ✅

---

## 4. Red test — build with the build-arg omitted

```
docker build -f Dockerfile.cloudrun -t gcs2-health-redtest:local .
```

Build log:

```
#10 [6/7] RUN echo "unset" > /app/.git_sha && echo "unknown" > /app/.build_number
    && echo "unknown" > /app/.git_branch && python build_manifest.py ...
#10 0.316 [build_manifest] Wrote /app/.build_manifest.json: 534 files,
    sha=unset, build_number=unknown, branch=unknown
```

`/health` verbatim:

```json
{"build_number":"unknown","build_time":"2026-09-15T02:49:42.069424+00:00","code_sha":"unset","cost_ceiling":{"hard_limit_aborts":0,"last_abort_cost":null,"last_abort_job_id":null,"target_warnings":0},"git_branch":"unknown","manifest_ok":true,"mode":"false","service":"tour_text_generator","status":"healthy","version":"2.2.0.1"}
```

The field degrades to a **clear sentinel** (`code_sha:"unset"`,
`build_number:"unknown"`) — it does **not** silently report a stale or wrong
number. This is the important property: the value is only ever what the build
arg wrote into *this* image's `/app/.build_number`; it is never computed at
runtime and never inherited from a previous image, so the "quietly reports the
previous image's number" failure cannot happen.

---

## 5. Beta vs Storied report different numbers

Simulated a beta build (a `main`-line image) with a different build number:

```
docker build -f Dockerfile.cloudrun -t gcs2-beta-sim:local \
  --build-arg GIT_SHA=aaaa111 --build-arg BUILD_NUMBER=75 --build-arg GIT_BRANCH=main .
```

`/health` verbatim:

```json
{"build_number":"75","build_time":"2026-09-15T02:51:34.478850+00:00","code_sha":"aaaa111","cost_ceiling":{...},"git_branch":"main","manifest_ok":true,"mode":"false","service":"tour_text_generator","status":"healthy","version":"2.2.0.1"}
```

| build   | code_sha  | build_number | git_branch |
|---------|-----------|--------------|------------|
| storied | b51576e…  | 2150         | storied    |
| beta    | aaaa111   | 75           | main       |

Different branch → different numbers. That difference is the entire point of the
Storied-vs-Beta comparison.

---

## 6. What a `main` port would require

`main` is the control (Beta) and was **not** ported in this task, per the ticket.
A port would require more than this change because `main` has neither piece:

1. **`build_manifest.py` does not exist on `main`.** It would have to be added
   (the file, plus the `.dockerignore` exception `!build_manifest.py` so
   `build_*.py` does not exclude it).
2. **`manifest_check.py`** would likewise need to be present on `main` for
   `/health` to read the manifest.
3. **`main`'s `Dockerfile.cloudrun` has no `ARG` lines at all** (no `RELEASE_TAG`,
   `GIT_SHA`, `BUILD_NUMBER`, or `GIT_BRANCH`). All four `ARG`/`ENV` declarations
   and the `RUN echo … > /app/.git_sha … && python build_manifest.py` step would
   have to be added. Without the `ARG` lines the `--build-arg` values are
   silently discarded.
4. **`main`'s deploy path** would need the same `--build-arg BUILD_NUMBER` /
   `--build-arg GIT_BRANCH` additions, and a `BUILD_NUMBER=$(git rev-list --count
   HEAD)` computed on the host.
5. `/health` and `/status` on `main`'s orchestrator would need the same
   additive fields.

Because Beta is the control, doing this now would make Beta drift, so it is
deliberately left for a separate task.

---

## 7. Things I could not verify, and why

- **Cloud Run behaviour after a real deploy** — not verified by design. The
  ticket says deploy nothing; I proved everything from a locally-built container.
  The mechanism is identical (same Dockerfile, same build args), so the deployed
  `/health` should match, but I did not run it in Cloud Run.
- **`/status` full end-to-end with a real completed job** — the `/status`
  response requires a job in memory or a Postgres row. I did not stand up the DB.
  Instead I verified the exact values `/status` inserts by calling
  `_get_build_identity()` inside the running orchestrator container (§3). I did
  not touch the live DB at all, so there are no row counts to report.
- **`git_branch` in a real deploy shows the deploy branch.** In my local proof I
  passed `GIT_BRANCH=storied` explicitly. On a real deploy the scripts pass
  `$BRANCH` (`git rev-parse --abbrev-ref HEAD`); on this worktree the checked-out
  branch is the task branch `storied-health-code-sha`, so a deploy from here
  would label `git_branch` with the task branch name. That is cosmetic — the
  release-line mapping in `release_tag.sh` (main/beta→1, storied→2) is what the
  deploy scripts gate on, and `build_number`/`code_sha` are unaffected.

Nothing is claimed complete that was not proven by reading `/health` from a
running container.
