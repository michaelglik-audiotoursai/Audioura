# STORIED — Michael ↔ Claude (LEAD), volume 02

**Started:** 2026-08-12 17:30 EDT
**Supersedes:** `STORIED_COMMUNICATION_01.MD` (81 KB, 1,517 lines — stopped ~2026-08-06)

---

## What this file is, and what it is not

**This is the conversation: Michael's questions verbatim, LEAD's final answers.**
Nothing else. Not the tool output, not the intermediate status pings, not the
reasoning that led to an answer — only what was asked and what was concluded.

Volume 01 failed at exactly this. It accumulated pasted terminal dumps, a full
usage-credits screen, and running commentary until it was 81 KB, at which point
nobody could find anything in it. **If an entry here cannot be read in under a
minute, it is too long.** Detail belongs in `DECISIONS.md`; this file points at it.

**Michael writes here too.** If something needs saying more clearly than chat
allows — a correction, a standing instruction, a "you misunderstood me" — write it
directly into this file under a dated heading. LEAD reads this file at the start of
every session.

**Rule for LEAD, so this does not die again:** append the exchange *before* moving
on to the next task. Volume 01 stopped because nothing on disk told the next session
to keep it up — see the entry for Q1 below. That rule is now in `CLAUDE.md`.

---

## The three documents, and the difference between them

| File | Holds | Who writes | In git? |
|---|---|---|---|
| **`STORIED_COMMUNICATION_02.MD`** (this) | the conversation — questions and final answers, in order | LEAD, and Michael | yes |
| **`ANSWERS.md`** | an indexed Q&A reference — each real question numbered, linkable, newest first | LEAD | yes (last commit 2026-08-06) |
| **`DECISIONS.md`** | binding rulings with the evidence behind them (D1…D413) | LEAD only | yes |

**Michael's understanding was right, with two corrections.** He said this file
stores the whole conversation and `ANSWERS.MD` holds his questions linked to answer
summaries. Both true. The corrections:

1. **`ANSWERS.MD` is not only Michael's questions.** Several entries are LEAD-raised
   — Q9 (news generation broken in production), Q10 (tours vanishing), Q20 (two
   credentials need rotating). It is "things Michael needs an answer to", whether or
   not he thought to ask.
2. **Neither file has actually been kept short.** `ANSWERS.MD` entries run to pages.
   That is the failure being corrected now, not the design.

The distinction that matters in practice: **this file is chronological, `ANSWERS.MD`
is indexed.** To follow what happened, read this. To find the answer to "what does
the translation cost consist of" six weeks later, use `ANSWERS.MD`'s contents list.

---

# 2026-08-12

## Q1 — "Create STORIED_COMMUNICATION_02.MD as it used to be. Explain the difference between these two documents. Neither should be as verbose as our sessions. Please confirm."

**Confirmed** — the format is as described above: questions and final replies only.

**Why volume 01 stopped:** nothing on disk required it. `CLAUDE.md` never mentioned
either file, so when a session restarted — which happens constantly by design (D252)
— the new session had no way to know the practice existed. It was not a decision to
stop; it was a habit that lived only in one session's context and died with it.
Fixed by adding the rule to `CLAUDE.md`, which every session reads at startup.

**Both files are in git and safe.** LEAD briefly reported `ANSWERS.md` as untracked —
that was wrong. The check spelled it `ANSWERS.MD`; the real file is `ANSWERS.md`, and
macOS finds it either way while git does not. It is tracked, last committed 2026-08-06.
Worth remembering: on this machine a filename check can pass in the shell and fail in
git for no reason but case.

**Naming:** Michael wrote "STORED_COMMUNICATIONS_02". The existing file is
`STORIED_COMMUNICATION_01.MD` — singular, "STORIED". Matched that convention so the
two sort together. Say the word if you want it renamed.

---

## Q2 — "You wrote 'the fleet can't be verified by asking it; it has to be diffed.' Explain in more detail."

**The short version: 20 of 21 services cannot tell you what code they are running,
so the only way to check is to compare their files against the repo one by one.**

Every container has a `/health` endpoint. Only `tour-generator`'s answer is worth
anything, because only `Dockerfile.generator` accepts a `GIT_SHA` build argument,
writes it to `/app/.git_sha`, and reports it. Ask any other service and you get
`unknown`, or the file does not exist at all.

That is why the stale-code problem hid for over a week. Everything looked healthy.
`docker ps` said `Up 8 days`, `/health` said `healthy`, and the tour generator
reported `code_sha: unknown` — which reads like a missing label, not like a warning.
The container was in fact running a 6,796-line `generate_tour_text.py` against the
repo's 15,011, missing the entire LOCAL-4xx chain. Nothing in the system was capable
of noticing.

Finding it required, per service: read `docker-compose-master.yml` for the build
context, find the real source file that context copies, and `md5` it against the
copy inside the container. That is what D412 did. It caught two more stale services
(`tour-editing-phase2`, `tour-orchestrator`) plus `tour-generation-modernized-1` —
and it produced five false positives on the first pass, because a `find` by filename
matched the wrong `app.py` for five services that each build from their own
subdirectory. A manual audit that is easy to get wrong is not a control.

**The task, if you want it dispatched:**

1. `ARG GIT_SHA` in all 20 remaining Dockerfiles, written to `/app/.git_sha`.
2. `code_sha` in every service's `/health` response.
3. `verify_fleet.sh` — one command, prints a table of every service, its reported
   sha, `git rev-parse HEAD`, and MATCH/STALE. Run it before any field test.
4. Fix the healthchecks for `map-delivery`, `tour-processor` and `voice-control`.
   They shell out to `curl`, which is not installed in those images, so all three
   have reported `unhealthy` with a failing streak of **23,594** while answering
   `HTTP 200` perfectly well. A health signal that has been wrong since the image
   was built teaches everyone to ignore health signals.

Roughly a day of work for one Kiro session. **Say "dispatch the fleet task" and it
goes out.** LEAD has not dispatched it unasked because it competes with release work
for the weekly ceiling.

---

## Q3 — "Are we ready to continue working on the Storied release?"

**Yes — and the field-test gate you set on 2026-07-29 is met, for the first time.**

Your gate: *the iPhone field test happens once the internal score reaches 75 at N=8
on the Asian Arts Museum.* Deliberately not softened to N=6.

```
tours/LOCAL320_museum_8stop.txt   Musée des Arts Asiatiques, Nice
8 stops                            base = 75.0
generated 2026-08-12 12:27
```

**Three caveats, stated plainly because the gate is yours to apply, not LEAD's:**

1. **The margin is zero.** 75.0 against a threshold of 75. Not 75.4 — exactly at it.
2. **The artifact predates today's merges.** It was generated at 12:27; LOCAL-447
   through LOCAL-450 and the D410 container fixes all landed after. The score has
   not been reproduced on current code.
3. **It is untracked.** The file is not in git, so there is no commit tying that
   score to a code state.

**What LEAD recommends, in order:**

- **Regenerate LOCAL320 on current code**, in the rebuilt container, and re-score.
  ~3 minutes. If it holds at 75+, the gate is met on code we can name by sha.
- **Then push `storied`.** 204 commits are unpushed, held behind this gate since
  2026-07-29. Nothing reaches the Windows machine until that push happens, which
  also blocks parallel work on Track B.
- **Then the iPhone field test.**

The release is not blocked on engineering. It is blocked on one 3-minute regeneration
and your decision to call the gate met.

---
