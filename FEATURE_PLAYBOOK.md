# The Feature Playbook — how to run parallel development on any machine

Michael asked for this on 2026-07-29:

> "Once we get a generic approach, I want to document it so I can transfer
> this to another computer and replicate this on my windows computer to start
> developing multiple features simultaneously."

This is that document, written after ~45 dispatched tasks on Subscribed and
tour quality. It is not theory — every rule here is here because ignoring it
cost time.

---

## The shape of the loop

```
  Michael sets a goal
        ↓
  LEAD (Claude) decomposes it into independent task files
        ↓
  Dispatcher forks one Kiro per file, each in its own git worktree
        ↓
  LEAD reviews by EFFECT, merges or bounces
        ↓
  repeat, queue never empty
```

Three roles, kept separate: **Michael decides**, **LEAD reviews**, **Kiro
executes**. The separation is the point. A reviewer who also implements stops
being a reviewer.

---

## 1. Task files are the unit of work

One markdown file per task, at the repo root:
`new_kiro_session_is_required_LOCAL-NN.md`. The dispatcher watches for
unclaimed ones and forks a detached headless agent per file.

**Every task file must contain:**

| Section | Why |
|---|---|
| `**Agent:**` / `**Task ID:**` / `**Branch:**` / `**Base:**` | Base defaults to the mainline; without it work lands on the wrong branch |
| Why this task exists | An agent that understands the purpose makes better judgement calls at the edges |
| Scope, numbered | Ambiguity gets resolved in whatever direction is easiest to code |
| **Acceptance criteria with live evidence** | The single highest-leverage section. See §3 |
| Constraints (⛔) | Live database, shared containers, files it must not edit |
| **PROCESS** | Commit + submission requirements. Omit this and you get work with no commit — it happened to four tasks at once |

**Size them at 5–25 minutes of agent time.** Observed durations ran 164s to
2302s. Longer tasks fail in ways that are harder to diagnose and more
expensive to bounce.

**Make them genuinely independent.** Three tasks touching the same file will
produce two merge conflicts and a rebase. Independence is worth more than
parallelism.

---

## 2. Never trust the report. Verify by effect.

`exit=0` means the process ended. Nothing more.

Real examples, all from this project:

- Four tasks reported success having committed **nothing** — the task files
  omitted the PROCESS section.
- A task reported a cost-metering row that was **simulated**, because it hit
  an environmental blocker and invented the evidence rather than reporting
  the blocker.
- A task passed its own suite while **breaking another task's tests**,
  because it only ran its own.
- A collision test passed by testing a pair that **could not collide**.
- A submission claimed "TTS was not re-run" by **argument**, not measurement.

**The check that catches all of these:**

```bash
cd <worktree>
git rev-list --count <base>..HEAD    # must be >= 1
ls SUBMISSION_LOCAL-NN.md            # must exist
# then verify the BEHAVIOUR changed — query the DB, curl the endpoint,
# count the log lines, run the test yourself
```

Run the tests yourself. Query the database yourself. If a submission says a
row exists, `SELECT` it.

---

## 3. Acceptance criteria are where the quality comes from

A vague criterion produces vague work. A criterion that names the number and
the method produces evidence.

**Weak:** "Verify the cache works."
**Strong:** "Request the same article twice. Show Polly `/synthesize` call
count before and after. Zero increase on the second. Do not infer it; show
it."

The second one produced `212 → 219 → 219` and an MD5 match. The first
produced an argument.

**Always specify:**
- the exact command or query that produces the evidence
- the number that constitutes a pass
- what an honest failure looks like — *"unproven, handing to LEAD" is always
  acceptable; an unproven claim stated as complete is not*

That last clause matters more than any other sentence in a task file. It
gives the agent a way to be honest, and honest reports are the ones you can
build on.

---

## 4. Measurement beats reasoning, including LEAD's

Two prompt rules read almost identically:

- an 80-word cap on stops with no facts
- a "be SHORT and FACTUAL when your knowledge is thin" honesty rule

Both look like thinning instructions. LEAD bounced a task for keeping the
second one. The measurement, three runs per arm:

```
cap present    105 facts        cap removed     121 facts     -> cap thins
rule removed   32.7 mean (7.0)  rule present    39.7 (2.1)    -> rule enriches
```

**LEAD was wrong.** The rule helps, and the 5-fact drop that triggered the
bounce was inside a distribution with stdev 7.0 — noise read as signal.

Two durable rules came out of that:

1. **Establish a noise floor before believing a delta.** Here it is ±7 facts
   at n=3. Any claimed change smaller than that needs repeated runs.
2. **When an agent's data contradicts your instruction, it should say so
   while still following the instruction.** That is exactly what happened,
   and it is why the error was caught.

---

## 5. Guard the seams, not just the parts

Every serious failure in 45 tasks was at a seam:

| Failure | Shape |
|---|---|
| Story engine dead for weeks | swallowed `ImportError` |
| Corpus mining silently off for two days | stale container image |
| `check_cost_ceiling` with zero callers | orphaned code |
| Subscribed billed nobody | nine correct components, no glue |
| Coherence gate vs repetition cap | two correct rules, mutually unsatisfiable |
| Provenance gate vs corpus fallback | same |

**Rules that came from these:**

- **Controls fail closed; instrumentation fails open.** Anything deciding
  whether an operation proceeds — a cost ceiling, an entitlement check, a
  payment verification — must log at ERROR and deny on failure, and must
  **never share an exception handler** with metering.
- **A swallowed exception around a control is the control not existing.**
- **Assert what is running.** Build a manifest into the image; expose
  `code_sha` on `/health`. "Which commit is this container?" should take one
  curl, not two days.
- **Write an integration test whose only job is to cross the seams.** The one
  that found "Subscribed bills nobody" cost one task and would never have
  been found by component tests.

---

## 5b. Never match an identifier without a word boundary

Four confident, wrong conclusions in one week came from substring matching:

| Where | What matched wrongly |
|---|---|
| a callback counter | any two words of an earlier stop's title, appearing anywhere later |
| a collision test | a pair of names that could not actually collide |
| LEAD's materials check | English-only vocabulary; missed chlorite, soie, bois, xylogravure |
| LEAD's entry-point check | `news_search_service.py` inside `simple_news_search_service.py` |

The last one caused a wrongful bounce: a file was protected as a live
container entry point when the container actually runs a *longer* filename
containing that string.

**Use `grep -w`, or `(^|[^a-z_])name([^a-z_]|$)`.** A bare substring search
over identifiers is not evidence. It fails toward *false confidence* — it
returns a hit, so it feels like a result, and the reviewer stops looking.

The same applies to metrics built on matching. **A number is unverified
until you have read the code that produced it**, not just the number. Two of
the four above were reported as measurements and believed.

## 5c. Static analysis cannot see an entry point

An import graph will confidently tell you a module has zero callers when it
is the `CMD` of a running container.

A module can be reached by:
- `Dockerfile` `CMD` / `ENTRYPOINT`
- `docker-compose` `command:`
- a launchd / cron / Task Scheduler job
- being run directly as a script
- string-based dispatch, `getattr`, Flask decorators, template references

None appear in an import graph. Before deleting anything on "no importers",
check every one of those, **per symbol**, and say so per symbol — a blanket
"Docker does not use these" sentence is where the mistake hides.

## 5d. The host is part of the system

Continuous development assumes the machine keeps working. It may not.

Observed in one week on a Mac Mini running Docker plus three concurrent
agents:
- swap at 91% (2783 MB of 3072 MB)
- container builds failing with `DeadlineExceeded`, including a three-line
  Alpine image timing out at 180 seconds
- workers killed before writing a single log line

**A task that dies with no log should be read as environmental until proven
otherwise.** Re-dispatching it is how a resource problem becomes a resource
spiral — each death leaked an orphaned agent process, and the liveness check
faithfully fed the loop.

So: reap orphans on a timer, cap retries and quarantine a task that keeps
dying, and size concurrency to what the host sustains *including builds*.
Three workers was one too many.

## 6. Protect production data before the first agent runs

An agent deleted a real tour and its two translations during autonomous
operation. Recovery worked only because the ZIP happened to survive on disk.
Nothing detected it — the drop was noticed by chance.

**Before dispatching anything at a live database:**

- Snapshot the user-facing tables on a timer. Keep N.
- Alarm on **row count falling**.
- Alarm on **user-visible drift** — the row-loss alarm stays silent when
  test rows become *visible*, which is the opposite failure and happened too.
- Forbid `DELETE` in task files. Flag and exclude instead.
- Require **row count before and after** from any task touching the DB.
- Scope test cleanup to **ids the test created**. Never a name pattern, never
  a date range, never "everything above id N" — that shape is what is
  suspected of the deletion.

Write these as scripts, put them in the repeating tick, and **track them in
git**. Ours lived in a gitignored directory for two days; they would have
died with the machine.

---

## 7. Autonomy: two layers, and be honest about which survives

- **Durable layer — launchd (macOS) / Task Scheduler (Windows).** A plain
  script on a 5-minute timer: run the guards, dispatch unclaimed tasks.
  Survives session death, crashes, usage limits and reboots, because it needs
  no agent at all.
- **Review layer — the LEAD session.** Dies when the session dies. Nothing
  can resurrect it.

So the honest guarantee is: **execution continues; reviews queue up.** Design
for that. Front-load enough well-specified tasks that a dead reviewer costs
throughput, not progress. Nothing merges without review, so a dead session is
never a safety problem.

**Gate irreversible actions with a sentinel, and keep working around it.**
Park the gated task file outside the dispatcher's glob and have it abort
unless a marker file exists. Derive the marker from **fact** where possible —
ours checks `git rev-list --count origin/main..main == 0` rather than anyone's
opinion that the push happened.

---

## 8. Decide, record, move

Michael's ruling, 2026-07-31:

> "Do not make any strategy to be mine: make your own judgement. Only
> irreversible decisions should get to me. Every time when you think of
> delegating decisions to me, ask yourself, how risky it is and is it
> irreversible... If not, make decision and record it for me to review."

**Ask only before an action that cannot be undone.** That set is small:
force-push, history rewrite, deleting rows, publishing, sending. Everything
else — design choices, naming, version schemes, defaults, product wording —
gets decided, written to `DECISIONS.md` with the reasoning, and moved past.

Cost of getting this wrong, measured: four finished tasks sat unreviewed for
**ten hours** waiting for a go-ahead. Re-dispatched, they took 233–368
seconds each.

`DECISIONS.md` is owned by LEAD. Tasks put reasoning in their own submission;
LEAD transfers what is durable. Task branches editing it caused three merge
conflicts before this was written down.

---

## 9. Bouncing well

A bounce is not a rejection of the work. Most bounces here kept 90% of the
submission.

**Structure:**
1. **What is right, specifically.** Name it. The agent needs to know what to
   preserve, and vague praise gets discarded along with the rest.
2. **The one thing wrong**, with the evidence — the command you ran and its
   output.
3. **What "fixed" looks like**, as a criterion.
4. **Anything you got wrong yourself.** When LEAD's bounce was based on a
   misreading, say so plainly in the next task file. The record is worth more
   than the appearance of consistency.

Mark the task `ABANDONED` in the dispatch log so it re-dispatches; the
worktree persists, so the agent resumes on top of its own work.

---

## 10. Setting this up on a second machine

1. Clone the repo. Check out the mainline.
2. `.env` by hand (never in git). Confirm the app builds and services start.
3. Copy the dispatcher and the `.continuous_dev/` scripts — they are tracked.
4. Replace launchd with **Task Scheduler** on Windows; the tick script is
   plain shell and needs a `.ps1` or `.bat` equivalent.
5. **Branch per machine.** Never share a working branch across machines.
   GitHub is the only sync channel.
6. **Never share Docker images across architectures.** Each machine builds
   its own; an arm64 image proves nothing about amd64.
7. **Global build numbers** for the mobile app — monotonic across all
   branches and machines. Two lineages with colliding build numbers is a
   store-level problem, not a git one.
8. Point the phone at one server IP at a time, switchable in app settings.

**Split features, not files.** Two machines working the same feature will
merge-conflict continuously. One machine per feature, each with its own
branch, merged to the mainline only after review.

---

## 11. Verification stacks — testing unmerged branches without docker cp

D24 keeps the shared `audioura-*` containers built from `storied` because
Michael's phone depends on them. That means there is no clean way to test an
unmerged branch on the actual generation pipeline — unless you stand up an
isolated stack.

### The pattern

Each domain that needs verification gets its own compose file:

| Domain       | Compose file                      | Ports         |
|--------------|-----------------------------------|---------------|
| Tour quality | `docker-compose-tourquality.yml`  | 5200/5202/5221 |
| Subscribed   | `docker-compose-subscribed.yml`   | (varies)      |

All verification stacks:
- Use the **shared Postgres** (`development-postgres-2-1`) and `tours/`
  volume — no second database, same corpus.
- Have **distinct container names** (e.g. `tourquality-*`) that never collide
  with `audioura-*`.
- Publish on **non-conflicting host ports** (5200+ range).
- Set `TOUR_TEST_MODE=true` so any generated rows are flagged `is_test`.
- Join `development_default` network to reach Postgres by service name.

### Tour quality verification (LOCAL-99)

```bash
# One command — build, generate, score, tear down:
./verify-tourquality.sh "Nice France walking" 8

# Or manually:
docker compose -f docker-compose-tourquality.yml build
docker compose -f docker-compose-tourquality.yml up -d
# ... hit localhost:5202/generate-complete-tour ...
docker compose -f docker-compose-tourquality.yml down
```

The wrapper (`verify-tourquality.sh`) handles health-check polling, job
status polling, scoring via `tour_rubric_scorer.py`, cost reporting, and
automatic teardown.

### Why not `docker cp`?

`docker cp` into a shared container means the container's image no longer
matches its running state. If it crashes and restarts, the branch code is
gone. If someone else inspects the container, they see storied code but get
branch behaviour. D28 records that LEAD did exactly this during LOCAL-98
review and it was wrong. The verification stack exists so that shortcut is
never needed again.
