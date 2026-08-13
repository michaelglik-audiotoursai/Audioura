# TASK LOCAL-455 — Finish fleet provenance, and stop worktrees from seizing the fleet

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-455-fleet-provenance-r2
**Base:** LOCAL-452-fleet-provenance

> **PARKED — do not dispatch until LEAD removes the `PARKED_` prefix.** This task runs
> `docker-compose build` across the fleet, and LOCAL-454 currently owns port 5000. Two
> tasks doing docker work at once is what produced the incident this task exists to fix.

## Why this exists

LOCAL-452 was dispatched on a premise that was wrong, ran for ~62 minutes, died with
nothing committed, and along the way a *different* task took the fleet's main port down.
All three are recorded in D419. Read it before starting.

**Your base branch already contains LOCAL-452's work**, committed by LEAD as `5ba4179`
and labelled **UNVERIFIED**: `code_sha` added to `/health` across 20 services, plus
`verify_fleet.sh`. Nothing in it has been tested, rebuilt, or executed. Treat every line
as unreviewed — read it, keep what is right, fix what is not, and say in your submission
which is which.

## READ THIS BEFORE YOUR FIRST DOCKER COMMAND

**Never run `docker-compose up` from your worktree.** That is the exact incident this task
exists to fix, and the guard you are building does not exist yet, so nothing will stop
you. Compose names its project after the directory, so from
`~/audioura-worktrees/LOCAL-455` you become project `local-455`, and any service with a
`ports:` mapping will **remove** the canonical container and seize the host port. Port
5000 is the iPhone app's port. It was taken for roughly an hour today.

What is safe from the worktree:

- `docker build -f <dockerfile> -t <name>-local455 .` — builds bind no ports.
- `docker run --rm` **without `-p`**, on `--network development_default` if it needs the DB.

What must run from `~/Audioura` (the canonical checkout), never the worktree:

- any `docker-compose up`, `down`, `restart`, or `--force-recreate`.

If you genuinely need the fleet rebuilt to verify `verify_fleet.sh`, say so in your
submission and hand that step to LEAD rather than doing it from the worktree. "Unproven,
handing to LEAD" is always acceptable; seizing port 5000 is not.

## Correction you must not repeat

D412 claimed only `Dockerfile.generator` takes `GIT_SHA`. **False.** 19 Dockerfiles
already carry `ARG GIT_SHA` / `RUN echo "${GIT_SHA}" > /app/.git_sha`, and compose already
passes `args: GIT_SHA: ${GIT_SHA:-unknown}`. LOCAL-452 discovered this — it touched zero
Dockerfiles — and **said nothing**. That silence cost an hour.

**If your task file is wrong, say so in the submission and proceed on what the code
actually shows.** Working around a bad instruction without reporting it is the failure
here, not the workaround.

## Defect 1 — provenance depends on the operator remembering

`docker-compose build` with `GIT_SHA` unset stamps every image `unknown`. That is how the
week-long staleness in D410 stayed invisible. The mechanism works — after a rebuild with
`GIT_SHA` exported, `audioura-tour-orchestrator-1` holds `ce61b01` — it just is not
automatic.

Make it automatic. A wrapper script (`build.sh` / `fleetctl`) that exports
`GIT_SHA=$(git rev-parse --short HEAD)` and then calls compose is acceptable and probably
best; a `.env` file is not, because it goes stale silently. Whatever you choose, a
developer typing the obvious command must not be able to produce an `unknown` image.
Document the one command in the script's header.

## Defect 2 — finish and verify what LOCAL-452 started

`code_sha` in every service's `/health`, read from `/app/.git_sha`, defaulting to
`"unknown"`. Keep every existing field — other services and the mobile app read them.

`verify_fleet.sh` exists in your base, unrun. It must print service / reported sha / HEAD
/ MATCH-STALE and **exit non-zero** if anything is stale. A service reporting `unknown` is
**STALE**, not "unknown" — an unverifiable deployment is not a passing one.

## Defect 3 — a worktree can seize the fleet's ports (the serious one)

On 2026-08-12 at 18:54, LOCAL-454 ran compose from `~/audioura-worktrees/LOCAL-454`.
Compose names the project after the directory, so it became project `local-454`, and its
`ports: "5000:5000"` **removed** `audioura-tour-generator-1` and took over port 5000 — the
port the iPhone app uses. Worktree isolation covers files. It does not cover host ports,
container names, or images.

Fix it so a task cannot do this by accident:

- A guard that refuses to run compose with host port bindings when the working directory
  is under `~/audioura-worktrees/`. A `docker-compose.override.yml` in each worktree that
  strips `ports:` is one route; a preflight check in the dispatcher's task preamble is
  another. Pick one, justify it, and make it hard to bypass by accident rather than
  impossible to bypass deliberately — tasks legitimately need to run containers for
  acceptance, just not on the fleet's ports.
- The proof is behavioural: from a worktree, attempt the thing LOCAL-454 did, and show it
  refused. A guard that has never refused anything is not a guard (D418).

## Acceptance (live-artifact gate)

- `bash verify_fleet.sh` after a full rebuild: every row MATCH, output pasted verbatim.
- The same script with one service deliberately left stale: that row STALE, exit code
  non-zero. Show both.
- `docker ps` with **zero** `(unhealthy)` containers. The three `curl` healthchecks
  (`map-delivery`, `tour-processor`, `voice-control`) are still broken — fix with Python,
  already present in every image, rather than installing curl.
- Three services' `/health` showing `code_sha` equal to `git rev-parse --short HEAD`.
- The worktree port guard refusing a real attempt, output pasted.
- **`audioura-tour-generator-1` exists and owns port 5000 when you finish.** If your work
  displaces it, restoring it is part of the task, not LEAD's cleanup.
- One tour end-to-end through the container to prove the mass rebuild broke nothing, and
  it must show D417 in effect: `Musée Picasso` → 10,285 chars from `stop_corpus`,
  `Île Sainte-Marguerite` → 13,500 chars live.
- Regression: `test_sq4_merge.py`, `test_palais_fix_lead_fixture.py`,
  `test_local12_fact_retrieval_fix.py`, and the 447–451 suites (76 tests).

## Time

LOCAL-452 died at ~62 minutes. If you approach that, **commit what works and submit it as
partial** rather than pressing on — an hour of uncommitted work vanished last time and
LEAD had to salvage it by hand. Commit early and often; partial and committed beats
complete and lost.

## PROCESS

- Work ONLY in your worktree on branch `LOCAL-455-fleet-provenance-r2`.
- Do NOT edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`.
- Record reasoning in `SUBMISSION_LOCAL-455.md` at the worktree root.
- No `DELETE FROM audio_tours`, ever.
- Commit at least once (`git rev-list --count LOCAL-452-fleet-provenance..HEAD >= 1`).
- Run every test you cite and paste the real output. "Unproven, handing to LEAD" is
  always acceptable; "all pass" when one does not is not (D418).
