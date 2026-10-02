**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-312
**Base:** storied
**Branch:** kiro/local312-quality-comms-and-user-index

# Tell the listener when a tour is thin. Never tell an author their work is poor.

Read `quality_guardrails.py`, `tour_scoring_service.py`, `storied_feature_flags.md`,
`DECISIONS.md` **D225**, **D227**.

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
```
Use `command -v <name>`. **Never `find` against `/` or `/Users/micha`** (D213,
D218). **If a command has not returned in ~2 minutes it is the wrong command.**
**Commit early.**

## ⚠️ NO container rebuilds (D48). Ceiling **$0.60**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
LOCAL-309/310/311 are in the scorer. You are in the comms + aggregate layer.
Production real count stays **29**.

## What Michael asked for

> *"Prepare information delivery to users when we generate lower quality tours
> (maybe less than 50? Make this number changeable if we decide to change it
> later). We should not tell the authors when they edit tour, that what they
> produce is poor quality, but we should know about this."*
> *"I would indeed record average evaluation per user but for a different
> reason: later on we may want to ask people for review: then we need to know
> who to ask... of course we will keep user's index private."*

## Scope

### 1. Low-quality message at a configurable threshold

`QUALITY_MESSAGE_THRESHOLD` exists (LOCAL-307) at 60.0. **Set the default to
50.0** per Michael, keep it env-overridable, and update
`storied_feature_flags.md`.

Reuse LOCAL-307's message shapes; do not invent new wording. The messages state
what we found, never apologise, never mention a score.

### 2. The author asymmetry — this is the delicate part

**A listener receiving a thin tour gets told. An author who edits a tour does
not.**

- Generated tour scores below threshold → user-facing message. Already built.
- **Author edits a tour, result scores below threshold → NO message to the
  author, ever.** Record it internally.
- The internal record must be complete: score, delta, which stops changed band.
  Michael's words: *"we should know about this."*

**No user-visible surface may carry a judgement of an author's work** — not an
API field, not a log line the client can read, not a status string. LOCAL-306
already forbids verdicts in the edit delta; extend the same rule to every path
that can reach an author.

Add a test that fails if any author-reachable response contains a quality score
or a judgement word.

### 3. Average evaluation per user — private, for choosing who to ask

Aggregate per user: mean tour score, count, last scored date.

**Purpose is review solicitation**, not ranking. Michael: *"later on we may want
to ask people for review: then we need to know who to ask."*

- **Private by construction.** Never returned by any user-facing endpoint. If a
  client can request it, the design is wrong.
- Store the aggregate keyed to the user id already used by `audio_tours`; do not
  introduce new identifying data.
- Provide an internal query path only — a function or an admin-only route.

### 4. Threshold configurability

Every threshold in the comms path must be env-overridable with the default in
`storied_feature_flags.md`. Michael expects to change 50 without a code change.

## The line you must not cross

**Never surface a score to an author.** This is the whole point of item 2 and the
one thing that must not leak.

**The per-user index is private.** Not "hidden by default" — unreachable from the
client. A future endpoint that exposes it would be a privacy defect, so make it
awkward to expose by accident.

**Do not gate delivery.** `QUALITY_GUARDRAILS_ENABLED` stays **false**; the
regeneration loop stays unwired pending Michael's cost approval (D227).

## Verification
- Threshold default 50.0, overridable; documented.
- A below-threshold **generated** tour → message emitted; paste it.
- A below-threshold **edited** tour → **no** message, internal record written;
  paste both the absence and the record.
- Per-user aggregate over ≥3 tours; show it is not reachable from any client
  endpoint.
- The leak test fails when a judgement string is deliberately introduced.

## Traps
- **Run every example you paste** (D97, D103). Judge protected files from
  `git merge-base` (D147). Honour `AUDIOURA_DB_TARGET`; it governs in-process
  access only (D221).
- Additive schema is allowed but must be declared and added to
  `tests/init_test_db.sh`.

## Acceptance criteria
- Threshold 50.0, env-overridable, documented.
- Listener messaged; author never messaged; internal record complete.
- Leak test present and demonstrably effective.
- Per-user aggregate private and unreachable from clients.
- Guardrails still OFF; nothing gated.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-312.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
