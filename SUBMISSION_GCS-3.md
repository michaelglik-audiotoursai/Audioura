# SUBMISSION — GCS-3: stage the Storied GENERATOR deploy

**Agent:** Services Kiro · **Base:** storied (`06b890e`) · **Branch:**
`kiro/gcs-3-storied-generator-deploy` · **ClickUp:** `wdvrdaxxm9` (Phase 2)

**Deliverable:** `deploy_storied_generator.sh` at the repo root. Nothing is
deployed — this is `--dry-run` only. The real deploy is Michael's call (runbook
`wdvrdaxn9f`).

Base verified: `git merge-base --is-ancestor 06b890e HEAD` → exit 0. HEAD is
`06b890e` (local `storied`), not `origin/storied`.

---

## The problem being staged (recap, from `PREVIEW_IS_RUNNING_BETA_CODE.md`)

`tour-orchestrator-storied` does not generate. It **delegates**:

- `tour_orchestrator_service.py:671` POSTs to `TOUR_GENERATOR_URL/generate`
- `tour_orchestrator_service.py:769` POSTs to `MODERNIZED_URL/process`

Both URLs point at **Beta** services today. So every Preview tour is written by
Beta's engine, and the Storied-vs-Beta comparison `wdvrdaxxm9` exists to enable
is impossible. Confirmed live 2026-09-15 (tour 422: `track='storied'` while
Beta's `tour-generator` logged the text at 03:31:11).

Both env vars are read at `tour_orchestrator_service.py:56-57`, so both are
repointable without a code change.

---

## What the script stages — three Storied services, one image

All three share **one** `audioura-storied:vN` image (build once, deploy many —
the established `Dockerfile.cloudrun` `COPY *.py` pattern). Only CMD + env differ.

| Service | Status | CMD | Why |
|---|---|---|---|
| `tour-generator-storied` | **new** | `python generate_tour_text_service.py` | The engine that has never run on Preview. Same CMD as Beta's `tour-generator`; serves `/generate` + `/status/<job_id>` (verified `generate_tour_text_service.py:503,557`). |
| `tour-modernized-storied` | **new** | `python tour_generation_modernized.py` | Step 1.5 HTML builder. `MODERNIZED_URL` has the identical delegation defect — see below. |
| `tour-orchestrator-storied` | **rebuilt + repointed** | `python tour_orchestrator_service.py` | Live image `audioura:storied` is ~a month stale (commit `a57dc507`, 2026-08-11). Rebuilt from current `storied` and repointed at the two new services. `TOUR_TRACK=storied` preserved. |

---

## The exact commands `--dry-run` prints (verbatim)

Run: `./deploy_storied_generator.sh --dry-run` — full transcript below, pasted
verbatim (ANSI escapes stripped for readability). **`exit=0` alone proves
nothing; the value is the concrete commands.**

```
== Preflight
  project=audiotours-migration region=us-central1
  image repo=audioura-storied (separate from Beta's shared 'audioura')
  services: tour-generator-storied, tour-modernized-storied, tour-orchestrator-storied
  orchestrator source reads TOUR_TRACK: OK
  orchestrator reads TOUR_GENERATOR_URL and MODERNIZED_URL from env: OK
  generator service exposes /generate and /status: OK
  no untracked .py in build context: OK

== Choosing image tag (repo: audioura-storied)
  no existing tags in audioura-storied — starting at v1
  will build and deploy: us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v1
  branch 'kiro/gcs-3-storied-generator-deploy' not in the release map; this is a Storied build -> using line 2 (storied)
  release tag: v2t1  (line 2, branch kiro/gcs-3-storied-generator-deploy, commit 06b890e6)

== Building us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v1 from Dockerfile.cloudrun (current kiro/gcs-3-storied-generator-deploy)
  [dry-run] docker build -f 'Dockerfile.cloudrun' -t 'us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v1' --build-arg RELEASE_TAG='v2t1' --build-arg GIT_SHA='06b890e6af13a94a17905526f5d4555c3a13ae52' .

== Pushing to Artifact Registry
  [dry-run] gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
  [dry-run] docker push 'us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v1'

== Deploying tour-generator-storied (CMD: python generate_tour_text_service.py)
  [dry-run] gcloud run deploy 'tour-generator-storied'   --region 'us-central1'   --image 'us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v1'   --command 'python'   --args 'generate_tour_text_service.py'   --no-cpu-throttling   --max-instances='1'   --concurrency='5'   --cpu='2'   --memory='1Gi'   --timeout='300'   --quiet

== Deploying tour-modernized-storied (CMD: python tour_generation_modernized.py)
  [dry-run] gcloud run deploy 'tour-modernized-storied'   --region 'us-central1'   --image 'us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v1'   --command 'python'   --args 'tour_generation_modernized.py'   --no-cpu-throttling   --max-instances='1'   --concurrency='5'   --cpu='2'   --memory='1Gi'   --timeout='300'   --quiet

== Resolving new service URLs for the orchestrator repoint
  TOUR_GENERATOR_URL -> https://tour-generator-storied-<hash>-uc.a.run.app
  MODERNIZED_URL     -> https://tour-modernized-storied-<hash>-uc.a.run.app

== Deploying tour-orchestrator-storied (CMD: python tour_orchestrator_service.py) + repointing URLs to Storied
  [dry-run] gcloud run deploy 'tour-orchestrator-storied'   --region 'us-central1'   --image 'us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v1'   --command 'python'   --args 'tour_orchestrator_service.py'   --update-env-vars 'TOUR_TRACK=storied,TOUR_GENERATOR_URL=https://tour-generator-storied-<hash>-uc.a.run.app,MODERNIZED_URL=https://tour-modernized-storied-<hash>-uc.a.run.app'   --no-cpu-throttling   --max-instances='1'   --concurrency='5'   --cpu='2'   --memory='1Gi'   --timeout='300'   --quiet

dry run complete — nothing changed. No Beta service was named.
SCRIPT_EXIT=0
```

Note: the preflight and tag-selection steps are **real reads** (gcloud is
authenticated on this host). The registry query found no `audioura-storied` tags
and correctly started at `v1`; the release-tag helper picked `v2t1`. The
`<hash>` placeholders appear because the two new services don't exist yet, so
`gcloud run services describe` returns nothing under `--dry-run`; on the real
run those resolve to the actual Cloud Run URLs before the orchestrator repoint.

---

## Which script it was modelled on, and what differs

Modelled on **`deploy_storied_service.sh`** (branch `kiro/storied-4`, already
`--dry-run` verified) for the orchestrator half, and on
**`deploy_cloudrun_service.sh`** for the `--repo-image` / separate-repo idea and
the `release_tag.sh` sourcing. I extended into a **new** script rather than
editing `deploy_storied_service.sh` because that script deploys exactly one
service (the orchestrator) — GCS-3 needs **three coordinated services** plus a
two-URL repoint, which is a materially different shape. A new file keeps the
single-service script simple and keeps the multi-service orchestration in one
reviewable place. I did **not** invent a third pattern: identical `say/run/fail`
helpers, identical tag-selection + immutability guard, identical rollback shape,
identical runtime flags.

**What differs from `deploy_storied_service.sh`:**

- Deploys **three** services from one image instead of one.
- Hard-codes the separate repo `audioura-storied` (that script's property 1),
  with an independent `vN` sequence starting at `v1`.
- Adds the **`MODERNIZED_URL` + `TOUR_GENERATOR_URL` repoint** via
  `--update-env-vars` — preserving `TOUR_TRACK` and the ~20 other env vars.
- `assert_target_is_storied()` gates **every** mutating gcloud call.
- Rollback loops over all three services (newest-owning first).

**What differs from `deploy_cloudrun_service.sh`:** that script re-applies a
service's *existing* live config; here the two new services don't exist yet, so
runtime flags are hard-coded (as `deploy_tour_modernized.sh` does), and
`TOUR_TRACK`/URLs are set explicitly rather than read back.

---

## Answer on `MODERNIZED_URL`

**Yes — a `tour-modernized-storied` is needed, and the script creates it.**

`MODERNIZED_URL` (default `tour_orchestrator_service.py:57`) is POSTed to at
`:769` for Step 1.5 ("Process with modernized service"). It currently points at
Beta's `tour-modernized` (`audioura:v37`), which runs `tour_generation_modernized.py`
— Beta's HTML builder. This is **exactly the same defect** as `TOUR_GENERATOR_URL`:
a Storied tour's HTML is built by a Beta service. Repointing only the generator
would leave half the pipeline on Beta and still contaminate the comparison.

So the script deploys `tour-modernized-storied` (same image, CMD
`python tour_generation_modernized.py`) and repoints `MODERNIZED_URL` to it in
the same `--update-env-vars` call. If a later reviewer decides the modernizer
stage is out of scope for the comparison, dropping it is a one-line edit
(remove `tour-modernized-storied` and the `MODERNIZED_URL=` clause) — but the
honest default is to move the whole generation path off Beta, so I included it.

---

## Verification plan for AFTER the real deploy

`track` alone is **not** evidence — tour 422 already proved a Beta-generated
tour can read `track='storied'`. The proof must show **different services wrote
the text**, plus a **visible text difference**.

1. **Confirm the repoint landed** (the script's own post-deploy check does this):
   `tour-orchestrator-storied` env shows `TOUR_TRACK=storied`,
   `TOUR_GENERATOR_URL` contains `tour-generator-storied`, `MODERNIZED_URL`
   contains `tour-modernized-storied`.

2. **Generate one tour per track for the SAME venue** (e.g. the Nice venue used
   for tour 422) — one through `storied-api`, one through the Beta API.

3. **Show the generator logs come from different services** (the decisive step):

   ```
   # Storied job: the tour text MUST be logged by tour-generator-storied,
   # and NOTHING for this job may appear on Beta's tour-generator.
   gcloud run services logs read tour-generator-storied --region us-central1 --limit 100

   # Beta job for the same venue: text MUST appear on Beta's tour-generator.
   gcloud run services logs read tour-generator          --region us-central1 --limit 100
   ```

   Pass condition: the Storied job's generation lines appear **only** on
   `tour-generator-storied`; the Beta job's appear **only** on `tour-generator`.
   (Same check applies to `tour-modernized-storied` vs `tour-modernized` for the
   HTML step.) This is the exact test that failed for tour 422, where the text
   showed up in Beta's `tour-generator` for a `track='storied'` tour.

4. **Show a visible text difference** between the two tours for the same venue —
   the storied engine is ~5,000 lines ahead (D556–D559), so the prose/structure
   should differ. A side-by-side of the two `/download/<job_id>` outputs, or the
   two `audio_tours.tour_content` rows, suffices.

5. **DB sanity, non-destructive:** record `SELECT count(*) FROM audio_tours;`
   before and after; confirm the two new rows carry the expected `track` values.
   No `DELETE FROM audio_tours` at any point.

---

## How the script guarantees no Beta service is touched

- The only service names that reach a mutating gcloud call
  (`gcloud run deploy`, `update-traffic`) are `$GEN_SERVICE`, `$MOD_SERVICE`,
  `$ORCH_SERVICE` — all suffixed `-storied`.
- Every one of those calls is preceded by `assert_target_is_storied "$SVC"`,
  which `fail`s on any name not ending in `-storied`. So even a future edit that
  fat-fingers a Beta name aborts before mutating anything.
- The script **never names** `tour-generator`, `tour-modernized`,
  `tour-orchestrator`, `map-delivery`, `news-orchestrator`,
  `newsletter-processor` or `api-gateway` in any mutating context. (Beta
  `tour-generator` / `tour-modernized` appear only in the **read-only** log-read
  commands in the verification plan and the post-deploy help text.)
- Beta's shared `audioura` image is never built or pushed — only
  `audioura-storied`. A later routine `audioura:vN` bump cannot pick up Storied
  code (property 1).

---

## Process compliance

- **Deployed nothing.** `--dry-run` only; real deploy is Michael's (`wdvrdaxn9f`).
- **No Beta service touched** — enforced in code (above).
- **Did not edit** `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
  `.continuous_dev/STATUS.md`, or `GCLOUD_STORIED_START_HERE.md`.
- **Real `--dry-run` output pasted** above, not just an exit code.
- **No untracked `.py` in the build context** — the script's own guard
  (`git status --porcelain -uall | grep '^??' | grep '\.py$'`) passed OK, and
  `git status` shows only the new `deploy_storied_generator.sh` (a `.sh`, not
  copied by `COPY *.py`). The temporary reference file I extracted while reading
  `kiro/storied-4` was deleted before committing.
- **No `DELETE FROM audio_tours`.** The script never touches the live DB; the
  verification plan only reads counts.
- **Committed on the task branch**, not merged to `storied`.

---

## What I could not verify, and why

- **Live deploy behaviour** — by design; I did not deploy. The `gcloud run
  deploy` lines are proven only as the exact strings `--dry-run` prints.
- **The two new services' real URLs** — they don't exist yet, so under
  `--dry-run` they render as `https://<service>-<hash>-uc.a.run.app`
  placeholders. On the real run the script `describe`s each new service and
  substitutes the actual URL into the orchestrator repoint before running it.
- **That `docker build` succeeds from current `storied`** — not built here (no
  image built during a dry run). The build step is identical to the sibling
  scripts', which are proven, and `Dockerfile.cloudrun` `COPY *.py` bundles the
  17,444-line `generate_tour_text.py` (HEAD == `storied`, confirmed) so the
  engine is present.
- **`--update-env-vars` comma-safety** — the repointed URLs contain no commas,
  so gcloud's comma-delimited env-var parsing is safe for these values. If a
  future URL ever contained a comma, the `--update-env-vars ^:^k=v` alternate
  delimiter form would be required; it is not needed today.
