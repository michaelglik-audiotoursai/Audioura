**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-166
**Base:** storied
**Branch:** kiro/local166-news-503-root-cause

# Find the real cause of the news 503 — without the Docker CLI

Read `SUBMISSION_LOCAL-165.md`, `news_orchestrator_service.py` (around line
138, the quota check), `entitlements.py`, `.continuous_dev/health_no_docker.sh`
(the pattern for working around the wedged CLI).

## ⚠️ Do NOT run any `docker` command. It is wedged — `docker ps` and
`docker exec` both hang past 60s, and this has already cost one task an hour.
Working around it is the point of this task, not an obstacle to complain
about. No container rebuilds, restarts or recreations.

## The confirmed fact

Every news article request fails:

```
POST http://localhost:5012/generate-news
  {"article_text": "...", "secret_id": "..."}
  -> {"allowed":false,"error":"quota_check_failed"}   HTTP 503
```

`/health` returns 200, so the service is up. The failure is inside
`check_news_quota`, which fails closed — correctly — and returns 503.

## The hypothesis, which is NOT established

LOCAL-165 proposed that the container's `entitlements.py` imports
`payment_provider`, absent from a stale image, causing an ImportError.

**Treat that as unproven.** There is a reason to doubt it: the shared
containers run `storied` code, while the `payment_provider` import landed on
the `subscribed` branch. If the deployed image predates that import, the
explanation cannot be right, and the real cause is something else — a
database connection failure from inside the container, a missing env var, or
a different import.

Do not start from the hypothesis. Start from the symptom.

## How to see inside without `docker exec`

The container is unreachable through the CLI but not otherwise:

- Its **logs** may be on disk. Docker Desktop stores container logs under
  `~/Library/Containers/com.docker.docker/Data/` — find the news-orchestrator
  log file and read the traceback directly. The exception text will name the
  cause outright.
- The **service is reachable over HTTP** on 5012. Other endpoints may reveal
  more: `/articles`, `/status/<id>`, `/health`. A more detailed error may
  appear in a different code path.
- **Reproduce it host-side.** Run `check_news_quota` from the repo source
  against `localhost:5433` and see whether it fails the same way. If it
  succeeds on host but fails in the container, the difference *is* the
  answer — and that difference is testable: image contents, env vars, or
  DB hostname resolution.

## Deliverable

The actual exception and the actual cause, quoted. Not a theory.

Then state the minimal fix and **whether it needs a container rebuild.**
Michael must know whether this is a one-line fix or blocked behind the
Docker CLI, because that determines whether he needs to restart Docker
Desktop today.

**Do not fix it in this task.** A change to the shared stack that his phone
uses gets its own task and its own review.

## Acceptance criteria

- The exception text, quoted from a log or reproduced.
- The cause, with the evidence that distinguishes it from the alternatives.
- Explicit yes/no: does the fix require rebuilding the container?
- If you cannot determine the cause without `docker exec`, say exactly what
  you tried and what you would need. An honest dead end beats a guess
  presented as a finding.
- `git status --short` clean.

## ⛔ Constraints

**No `docker` commands of any kind.** No container changes. No fixes.
No `DELETE FROM` anything. Read-only against the database.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `STATUS.md`.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-166.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file changes, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
