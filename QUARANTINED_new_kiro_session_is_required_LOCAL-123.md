**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-123
**Branch:** kiro/local123-docker-builder-diagnosis

# Diagnose the hung Docker builder — do not restart anything

Read `DECISIONS.md` D32, `SUBMISSION_LOCAL-112.md`, `remind_macmini.md`.

## The problem

Docker builds have been hung for hours. A three-line Alpine image times out
at 180 seconds:

```
FROM alpine
RUN true
->  DeadlineExceeded: context deadline exceeded
```

Meanwhile every running container is healthy — all six services return 200,
tour downloads work, the database is fine. **This is builder-specific.**

Already ruled out by LEAD:
- **Build context** — `tours/` (390 MB) is in `.dockerignore`
- **Memory** — swap fell from 2783 MB to 2199 MB with no change
- **Cache** — reclaimed 3.9 GB of buildx cache, no change

Consequences: LOCAL-112 died four times before anyone understood why, no
task can verify a service change, and LEAD cannot confirm the swipe route
registration over HTTP.

## ⛔ DO NOT RESTART DOCKER

Michael is away and his phone depends on these services. They are
`restart: unless-stopped`, so they *should* return — but "should" is not
good enough with nobody watching. **Diagnose only.** If the answer is
"restart Docker Desktop", say so and stop; LEAD will decide.

Equally: do not stop, remove or rebuild any `audioura-*` container.

## Scope — investigation only

1. **Where exactly does it hang?** `docker build --progress=plain` on a
   trivial Dockerfile. Which step never completes — context transfer,
   pulling the base image, the RUN, or exporting?
2. **Is it the network?** A build needs to reach the registry. Can the
   daemon pull at all? `docker pull alpine` separately from a build.
3. **Buildkit vs the legacy builder.** `DOCKER_BUILDKIT=0 docker build ...`
   uses a different path entirely. If the legacy builder works, that
   isolates it to buildkit and gives an immediate workaround.
4. **Daemon state.** `docker info`, `docker version`, and the Docker Desktop
   logs — is the VM under pressure, is the disk full, is there a stuck
   builder worker?
5. **Disk.** `docker system df` reported 87 images and 5.86 GB earlier. What
   does the VM's own disk look like, not the host's?

## Deliverable

`DOCKER_DIAGNOSIS.md`: what you tested, what you observed, and the most
likely cause with your confidence in it. If a workaround exists that needs
no restart — legacy builder, a different context, a smaller image — say so
precisely enough that LEAD can use it this session.

## Acceptance criteria

- Verbatim output from each diagnostic, not summaries.
- A named most-likely cause, with confidence stated.
- Any no-restart workaround, with the exact command.
- Explicit confirmation that no container was stopped, removed or rebuilt,
  and that Docker was not restarted. `docker ps` before and after.

## ⛔ Constraints

No `DELETE FROM audio_tours`. Row count before and after (88 now).
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `STATUS.md`.
Verify `tours-near/43.7009358/7.2683912?radius=50` returns
`[1,12,14,17,21,24,27,28,29]` when you finish.

## PROCESS

Work in YOUR worktree only.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` ≥ 1;
(2) `SUBMISSION_LOCAL-123.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file changes, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.

---

## AMENDED BY LEAD — 2026-08-02. Do not run a build at all.

Two prior attempts died, each after almost exactly an hour. That timing is
itself the finding: **the builder does not fail, it hangs until something
kills the caller.** Your worker is being consumed by the fault it was sent
to investigate.

One more death and the quarantine guard parks this task. So:

**Do NOT run `docker build`, even with `--progress=plain`, even on a trivial
Dockerfile.** LEAD has already established that a three-line Alpine image
times out at 180s. Re-establishing it costs a worker.

### Investigate only what cannot hang

- `docker info`, `docker version` — daemon state, storage driver, warnings
- `docker system df` and the VM's own disk usage
- `docker pull alpine` **with a 60s timeout** — does the daemon reach the
  registry at all? This is the single most useful signal and it is not a
  build.
- `docker buildx ls`, `docker buildx inspect` — is a builder node wedged?
- Docker Desktop logs: `~/Library/Containers/com.docker.docker/Data/log/`
  or `log show --predicate 'process == "com.docker.backend"' --last 2h`
- Whether `DOCKER_BUILDKIT=0` would use a different path — **report whether
  it is available, do not test it with a build**

Wrap every docker command in a timeout so a hang cannot take the worker:

```python
subprocess.run([...], capture_output=True, timeout=60)
```

### Deliverable unchanged

`DOCKER_DIAGNOSIS.md` — what you could observe without building, the most
likely cause, your confidence, and whether a restart is the only remedy.
"Cannot determine without a restart" is an acceptable conclusion.

Still: **do not restart, stop, remove or rebuild anything.**
