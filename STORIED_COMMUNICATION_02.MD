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

## Q4 — "Are the docker services working correctly now? Were they broken before?"

**Yes to both.** I had only proven it for `tour-generator`, so I audited all 21 services
by comparing each container's entrypoint against its own build context.

Two more were stale. **`tour-editing-phase2`** was running the *same* pre-LOCAL-4xx
generator code that broke your tour — it pins `image: audioura-tour-generator:latest` with
no build of its own, so rebuilding the image never touched it; a container keeps its old
image until recreated. **`tour-orchestrator`** was 1,865 lines against the repo's 2,017,
and **`tour-generation-modernized-1`** 539 against 554. All rebuilt.

The three `unhealthy` flags are false alarms: `map-delivery`, `tour-processor` and
`voice-control` run `curl` in their healthcheck and curl is not installed in those images.
Failing streak **23,594**, all three answering `HTTP 200` fine.

My first sweep also produced five false positives by matching the wrong `app.py` — five
services build from their own subdirectories. Recorded as **D412**, and later partly
**corrected by D419** (see Q6).

---

## Q5 — "Dispatch the fleet task. Regenerate LOCAL320 and if it holds at 75+, push storied."

**Gate met with margin, and `storied` is pushed.** Regenerated on current code in the
rebuilt container: **81.2** at N=8, up from 75.0. Committed as
`tours/LOCAL320_museum_8stop_GATE_ce61b01.txt` so the score is tied to a nameable code
state — the old artifact was untracked, which was one of my three caveats.

The push was not clean and you should know why: **origin had a commit we did not** —
Track B from the Windows machine. Merging it conflicted in `DECISIONS.md` because **both
machines had independently allocated D347**. Track A keeps D347–D414; Track B renumbered
to D415/D416, content untouched; and Track B now allocates from **D500 up**, written into
the file. Two machines appending to one file cannot share a counter.

---

## Q6 — "Explain 'the fleet can't be verified by asking it.'" — and my correction

**I was wrong about the cause, and the correction matters more than the original claim.**

What I told you: only `Dockerfile.generator` takes a `GIT_SHA` build arg, so no other
service can report what code it runs. **False.** 19 Dockerfiles already had
`ARG GIT_SHA` + `.git_sha`, and compose already passed the arg, a week before any of
today's work. I probed with `cat /app/.git_sha || echo "(no .git_sha)"`, read the output
`unknown` as "no mechanism", when it meant "built without GIT_SHA exported".

The real gaps are narrower: a plain `docker-compose build` stamps every image `unknown`,
only the generator surfaces the sha in `/health`, and nothing aggregates it. **D419.**

That was the second measurement of mine overturned in one day (D413 was the first, on the
retrieval ordering). Both were caught by re-running my own number — the standing check
that says to do exactly that.

---

## Q7 — "Kiro CLI is asking to access data from other apps. Is it yours? Should I allow it?"

**It is the executor I dispatch tasks to — and my recommendation was to deny.**

Nothing queued needs it; the one running worker had nothing open outside the repo. The
grant is persistent rather than per-session, Kiro runs `--trust-all-tools` so it never
asks before acting, and this repo still has an unrotated credential in pushed git history
(D223). Denying fails loudly and diagnosably; allowing fails silently and permanently.

Precedent: the 2026-08-06 Downloads/Documents prompts, traced to overnight Kiro sessions
running whole-home `find` commands hunting a `python3` binary not on PATH. Fixed by
stating `/usr/bin/python3` as fact in every task file since LOCAL-300. In `ANSWERS.md`.

**Honest limit:** macOS protects `TCC.db`, so I cannot prove which action triggered the
prompt.

---

## Q8 — "Why are the file names different? MFA_UNBOUND_FOR_REVIEW.txt vs TOUR_MFA_UNBOUND_20260812.txt — which one am I supposed to reference?"

Two different tours of the same exhibition, seven hours apart, each with its own review.
Not duplicates.

| | morning | evening |
|---|---|---|
| tour | `TOUR_MFA_UNBOUND_20260812.txt` 5,769 ch | `tours/MFA_UNBOUND_FOR_REVIEW.txt` 6,207 ch |
| review | `ASSESSMENT_MFA_UNBOUND_20260812.md` | `MFA_UNBOUND_EVALUATION_LEAD.md` |
| commit | `ca59ca8` | `d7f8e68` |

Michael had the evening tour open next to the morning tour's review. Both are committed,
so neither can vanish. Fixed going forward by generating **one** tour whose review shares
its name stem, in the repo root, with no second copy: `TOUR_MFA_20260812_2030.txt` and
`TOUR_MFA_20260812_2030_REVIEW.md`.

## Q9 — "You wrote 'the action plan' — is it done?"

**No. Zero of the five.** The five prose fixes from `MFA_UNBOUND_EVALUATION_LEAD.md`
(publisher-appositive corruption, Hogarth conflation, orientation on every stop,
first-mention rule for people, per-stop length balance) were never dispatched. Everything
went to that document's *footnote* — the candidate non-determinism — via LOCAL-453/454/456,
plus the fleet chain LOCAL-452/455 which burned two 60-70 minute runs and committed
nothing. Three of the five defects are still visible in tonight's tour. Recorded as D423.

## Q10 — "Nothing points to the stop, but there are stories — the opposite of what it used to be. The stories are not very good, but they are stories and they are factual. But no obvious correlation with the stop though they are about the stop."

Confirmed, and measurable. The beats are real and correctly assigned — Boris Fridman /
Louis Broder / Mourlot Frères on stop 1, Dalí / Freud / Torf on stop 2, Gris / Reverdy on
stop 3 — and all 8 people appear in the delivered text. **None is attached to the object in
the case.** Broder arrives as "a renowned figure in the world of artist's books" instead of
as the maker of *this* vellum and *these* 40 lithographs. Body sentences describing the
physical object: stop 1 → 1, stop 2 → 0, stop 3 → 0.

Also found while checking: `[LOCAL-410] beats_in_delivered_text=0` contradicts
`[LOCAL-390] beats_in_output=3/3/2` in the same run. LOCAL-390 is right. We have been
quoting a broken instrument. D423.

## Q11 — "Isolate in the code the subroutines that create the stories, so we can run and improve each one. One subroutine at a time."

Built as `story_lab.py`, six stages in Michael's order, one JSON state file per run so a
stage can be run, inspected, hand-edited, and the next stage run on the edit:

```
S1 fact -> stop -> exhibition    S4 the right size (learn more if thin)
S2 making the query              S5 writing
S3 result + evaluation           S6 validation
```

First run found that 6 of stop 1's 9 queries exact-phrase-search
`"Le Lézard aux plumes d'or (The Lizard with Golden Feathers)"` — a string that exists
nowhere, because the English gloss is our own addition.
`generate_tour_text.py:4000 _strip_parenthetical_translation()` already returns the correct
bare title and is simply not applied. Written up as LOCAL-457, parked until the joint
session so the pipeline is not rewritten underneath it.

**One honest limitation:** S5 cannot run the writer. The story prompt is inline in
`generate_tour_text()`, a 10,443-line function, so it is not callable. Extracting it is the
next piece of work. D424.


## Incidents worth remembering from 2026-08-12

**A task worktree seized port 5000 for about an hour.** LOCAL-454 ran `docker-compose up`
from `~/audioura-worktrees/LOCAL-454`; compose names its project after the directory, so
it became `local-454` and its `ports: "5000:5000"` **removed** the canonical
`audioura-tour-generator-1`. Worktree isolation covers files — not host ports, container
names, or images. Restored and verified at HEAD; the guard is LOCAL-455's job (D419/D420).

**Writing ABANDONED without parking the task file causes a re-dispatch.** I marked
LOCAL-452 abandoned and the dispatcher immediately re-claimed it on a premise already
corrected. The two acts must happen together. Killing the dispatcher is also not enough —
the detached `kiro-cli-chat` worker survives and must be found by working directory
(D420).

**Two tasks were stopped mid-flight and salvaged by hand** (LOCAL-452 at 62 min, LOCAL-454
at 37 min), both with an hour of uncommitted work. Task files now say: commit as soon as
anything works — partial and committed beats complete and lost.

---

at 08/12/2026 19:53 
❯ Is it a good time to do /clear + restart?

Good timing question — but one thing has to happen first, and it's the rule I put in CLAUDE.md this afternoon: today's exchanges aren't in the conversation log yet.

  Pushed to storied, ran 1 shell command

[Storied_Tours]@08/12/2026|19:58

Yes — now is a good time, and I've just made it safe. The one thing that would have been lost is written to disk: today's Q4–Q7 and the three incidents are in STORIED_COMMUNICATION_02.MD, committed and pushed (afae00d). That was the rule I added to CLAUDE.md this afternoon, and I'd have been the first to break it.

State right now:

uncommitted changes    none
unpushed commits       0        (origin/storied == storied == afae00d)
port 5000              audioura-tour-generator-1, healthy, code-current
in flight              LOCAL-455 only (26 min), one worker
audio_tours            31 real rows, no ROW LOSS

What survives the clear: everything that matters. The LOCAL-455 worker is a detached process — it keeps running, writes its own COMPLETED record to kiro_sessions_ran.md, and a fresh session picks it up from disk. Both salvage commits, all task files, D409–D420, the parked LOCAL-456 — all on disk and pushed.

What dies: the review loop. ScheduleWakeup is session-scoped, so no one will review LOCAL-455 until you re-arm it. That's the normal pattern, not a problem.

On return, three lines:

1. restart — rebuilds git state, row counts, queue, scores from disk
2. resume continuous dev
3. Tell it: check port 5000 first — docker ps --filter publish=5000 must show audioura-tour-generator-1, not a local-4xx container

The one flag I'd raise before you go: the worktree port guard doesn't exist yet — that's what LOCAL-455 is building. Its task file explicitly forbids docker-compose up from a worktree, but LOCAL-454 did exactly that an hour ago (before the prohibition existed) and took port 5000 for an hour. So there's a small, real chance you come back to a seized port. It's cheap to fix — the restore is three commands and it's written into the resume instructions — but it's a genuine unattended risk rather than zero.

If you'd rather not carry that risk, say so and I'll touch .continuous_dev/PAUSE and stop LOCAL-455 before you clear; the cost is ~26 minutes of its work, which I'd salvage the way I salvaged the last two. My recommendation is to let it run — it's the task that closes this hole permanently, and the failure mode is recoverable in minutes.

One more thing worth knowing: this session is long, and long high-context sessions are the expensive kind against the weekly ceiling. Clearing now is the cheaper path regardless of the queue.

  Settings  Status   Config   Usage   Stats

   Session

 Total cost:            $37.18
 Total duration (API):  49m 38s                                                                                                  Total duration (wall): 3h 27m 3s                                                                                         Total code changes:    1411 lines added, 8 lines removed
 Usage by model:
        claude-opus-5:  4.5k input, 200.0k output, 57.4m cache read, 347.6k cache write ($37.18)
     claude-haiku-4-5:  635 input, 14 output, 0 cache read, 0 cache write ($0.0007)

 Current session
 ████████                                           16% used
 Resets 11:30pm (America/New_York)

 Current week (all models)
 ████████████████████▌                              41% used                                                                     Resets Aug 18 at 12am (America/New_York)                                                                                   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

 What's contributing to your limits usage?                                                                                     Approximate, based on local sessions on this machine — does not include other devices or claude.ai

 Last 24h · these are independent characteristics of your usage, not a breakdown

 78% of your usage was at >150k context
  Longer sessions are more expensive even when cached. /compact mid-task, /clear when switching to new tasks.                                                                                           
 45% of your usage came from sessions active for 8+ hours
  These are often background/loop sessions. Continuous usage can add up quickly so make sure it is intentional.                                                                                                                                                                                                                               Skills                  % of usage
 /claude-api                     2%
                                                                                                                                d to day · w to week                                                                                                        
 Usage credits
 ████████████████████████████████████████████▉      89% used                                                                  $112.49 / $125.00 spent · Resets Sep 1 (America/New_York)



---

at 08/14/2026 11:0x
❯ Note 1: multiple stories about the same person are not prohibitive — but then
  redundancy means same people at the same event or doing the same activity.
  Note 2: the same test we use to judge whether a sentence has value applies to
  picking a credit_line. In "The convergence of narrative and imagery in this exhibit
  prompts reflection on how journeys from obscurity to enlightenment could be depicted
  in unexpected ways elsewhere", Part 3 is the most general ("the book" of the
  sentence); Part 1 is the most stop-specific and so the most interesting. Make Part 1
  the credit_line — note it is more than one word — and run it.

[Storied_Tours]@08/14/2026|11:17

Ran both arms live on stop 2. **The phrase scored higher (67 vs 57) and produced the
worse story**, and the reason matters more than the number: both arms wrote the SAME
story from a byte-identical ladder, sourceable set and subject. `credit_line` only
feeds RETRIEVAL — the story's subject is picked from the handle ladder, which never
sees it. So the run measured "is a phrase a good web query": no, it lost freud.org.uk
for academia.edu, and Detail fell 6 → 0.

The idea is right; it is wired to the wrong place. Clause-specificity belongs at
SUBJECT SELECTION, upstream, not in the query builder.

Two side findings: `valuation_index` has no vagueness penalty, so it preferred four
vague sentences to three specific ones — sixth instrument failure of this shape. And
the same baseline scored 65 in the earlier sweep and 57 today on identical inputs, so
single-run differences under ~10 points are noise.

Note 1 recorded as D442: a person must not be struck off the keyword ladder merely for
occupying another slot, but the same-people/same-event redundancy check has to exist
before that exclusion is removed. Full evidence in D442/D443.

---

## CLOSED 2026-08-14 — continued in `STORIED_COMMUNICATION_03.MD`

Maintenance of this file lapsed after the 11:17 entry and Michael caught it. Volume 03
opens at that point and carries the rest of 2026-08-14. Nothing further is appended here.
