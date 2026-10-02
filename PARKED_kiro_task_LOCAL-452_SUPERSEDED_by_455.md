# TASK LOCAL-452 — Make the fleet answer "what code are you running?"

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-452-fleet-provenance
**Base:** storied

## Why this exists

On 2026-08-12 Michael reported that generating a tour failed completely. The pipeline was
fine. The **container had been running code from before the entire LOCAL-4xx chain** —
`/app/generate_tour_text.py` was 6,796 lines against the repo's 15,011 — and it died at
138s on an import that only fails inside the image. It had been like that for over a week
(D410).

Nothing in the system was capable of noticing. `docker ps` said `Up 8 days`. `/health`
said `healthy`. The `code_sha` field said `unknown`, which reads like a missing label
rather than a warning.

The follow-up audit (D412) found two more stale services and had to do it **by hand**:
read `docker-compose-master.yml` for each service's build context, find the real source
file that context copies, and `md5` it against the copy inside the container. That audit
produced **five false positives on its first pass**, because a `find` by basename matched
the repo-root `app.py` for five services that each build from their own subdirectory. An
audit that is easy to get wrong is not a control.

Today only `tour-generator` can answer the question, because only `Dockerfile.generator`
takes a `GIT_SHA` build arg and writes `/app/.git_sha`. The other 20 services report
`unknown` or have no such file.

## What to build

### 1. `GIT_SHA` in every Dockerfile

`Dockerfile.generator` already has the pattern — copy it, do not invent a new one:

```dockerfile
ARG GIT_SHA=unknown
RUN echo "${GIT_SHA}" > /app/.git_sha
```

Apply to all remaining Dockerfiles that build a service in `docker-compose-master.yml`.
Some services build from a subdirectory context (`translation-service`, `user-tracking`,
`tour-update-service`, `coordinates_fromAI`, `map_delivery`, `voice_control`) and have
their own `Dockerfile` with no explicit `dockerfile:` key — do not miss those. Enumerate
from the compose file, not from `ls Dockerfile*`.

Add the matching `args: GIT_SHA: ${GIT_SHA:-unknown}` to each service's `build:` block.

### 2. `code_sha` in every `/health`

Every service already has a `/health` endpoint returning JSON. Add `code_sha`, read from
`/app/.git_sha`, defaulting to `"unknown"` when the file is absent. Keep the existing
fields — the mobile app and other services read them.

### 3. `verify_fleet.sh` at the repo root

One command, no arguments, prints a table and exits non-zero if anything is stale:

```
SERVICE                        REPORTED   HEAD       STATUS
tour-generator                 aef068e    aef068e    MATCH
tour-orchestrator              55b2753    aef068e    STALE (2 commits behind)
...
```

Resolve HEAD with `git rev-parse --short HEAD`. A service that reports `unknown` is
**STALE**, not "unknown" — an unverifiable deployment is not a passing one. That
distinction is the whole point of the task; do not soften it.

### 4. Fix the three broken healthchecks

`map-delivery`, `tour-processor` and `voice-control` have reported `unhealthy` with a
failing streak of **23,594** while answering `HTTP 200` on `/health` perfectly well.
Their healthcheck shells out to `curl`, which is not installed in those images:

```
OCI runtime exec failed: exec: "curl": executable file not found in $PATH
```

Fix by using Python (already present in every image) rather than by installing curl —
adding a package to three images to satisfy a healthcheck is the wrong trade:

```yaml
test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:PORT/health', timeout=5).status==200 else 1)"]
```

Check every service's healthcheck for the same defect, not only these three.

## Acceptance (live-artifact gate)

- `bash verify_fleet.sh` output pasted verbatim, run after rebuilding **all** services,
  showing MATCH for every row.
- The same output with one service deliberately left stale, showing it flagged STALE and
  the script exiting non-zero. A checker that has never gone red is not a checker.
- `docker ps` showing zero `(unhealthy)` containers, and the healthcheck log for one of
  the three fixed services showing a successful probe.
- `curl -s http://localhost:5000/health` and two other services' `/health`, showing
  `code_sha` matching `git rev-parse --short HEAD`.
- Confirm the rebuild did not break anything: generate one tour end-to-end through the
  container (`Musée des Arts Asiatiques, Nice`, 8 stops) and report SUCCESS with a char
  count. The current gate artifact scores 81.2 — you do not need to match it, but a
  failure to generate is a bounce.

## Warnings from the audit that found this

- **Enumerate services from `docker-compose-master.yml`, never from filenames.** Five
  services share the entrypoint name `app.py` and build from different directories.
  Matching by basename is what produced LEAD's false positives.
- **`tour-editing-phase2` has no build of its own** — it pins
  `image: audioura-tour-generator:latest`. Rebuilding that image does not update the
  container; it must be recreated. `verify_fleet.sh` must catch this case, because it is
  exactly the one a human audit skips.
- Some containers date to 2026-07-21. Expect rebuilds to surface unrelated breakage; if
  one does, report it rather than fixing it silently in this task.

## PROCESS

- Work ONLY in your worktree on branch `LOCAL-452-fleet-provenance`.
- Do NOT edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`.
- Record reasoning in `SUBMISSION_LOCAL-452.md` at the worktree root.
- No `DELETE FROM audio_tours`, ever.
- Commit at least once (`git rev-list --count storied..HEAD >= 1`).
- "Unproven, handing to LEAD" is an acceptable report; an unproven claim stated as
  complete is not.
