# The work queue — what to do when nobody is typing

**Michael, 2026-09-22:** *"I will be in and out of the office and I want you to work to
the maximum capacity… at some point the time budget runs out and then you stop because no
money will be coming in — that is expected: that is the opposite side problem. For now I
want to increase your utilization."*

**The problem this fixes.** A Claude session only exists between messages. When Michael
stops typing, the session ends and the machine goes idle — last night it sat unused for
ten hours. Nothing was broken; nothing was *scheduled*. `CLAUDE.md` RULE ZERO already says
*"when a long unattended stretch is expected, self-schedule"*, and LEAD had not been.

**The stop switch:** `touch .continuous_dev/PAUSE`. Everything below halts at its next
tick. Nothing needs to be told, and no session needs to be running.

---

## The four tiers, in strict priority order

Work the highest tier that has anything in it. Drop a tier only when it is empty or
**stalled**.

### 1. CURRENT WORK — what Michael and LEAD are doing right now
The cycle: **build → evaluate → diagnose → change → build**. Today that is tour quality:
generate a batch, score it with `tour_quality.py`, find the defect, fix it, regenerate.

**Run it without asking.** Fixing a bug is `git revert`-able; generating inside the
ceiling is reversible. RULE ZERO covers both.

**The stall rule — Michael's, and it is what makes unattended work safe:**
> *"you ran for 3 cycles and see no improvement and need me for consultation"*

**Three cycles with no measurable improvement = stalled.** "Improvement" is not a
feeling: it is `tour_quality.score_batch` — fewer defects, or `consistent` going true.
On a stall, write what was tried and what it changed, then drop to tier 2. Do not attempt
a fourth variation of the same idea.

### 2. CURRENT RELEASE (priority: high) — ClickUp
Tasks for the release in flight. **Source of truth is ClickUp**; if its API is down (it
has been before, and the offline queue pattern exists) fall back to a spreadsheet or a
markdown file and post retroactively.

**If this tier empties, tell Michael.** His words: *"you would need to remind me so it is
either the situation we expect and all is good, or we will add more work tasks."* An empty
tier 2 is information, not an error.

### 3. MAINTENANCE — whenever the load is light
Always available, never urgent. Logged in ClickUp before, during, or after, and marked
complete. His examples:
- memory cleanup
- **making tours cheaper and/or faster** — the D565 baseline is $0.244/tour, n=3, ±13%
- **preparing for `/clear` + autostart** — so a cleared session resumes without a human
- (add more as they are found)

### 4. NEXT RELEASE (lowest) — a different repository
Maintenance-heavy and in another repo, so it costs more to pick up and put down. Still
better than idling. Only when 1–3 are empty or stalled.

---

## How it actually runs while nobody is typing

Three mechanisms, and only one of them needs a Claude session:

| mechanism | needs a session? | spends |
|---|---|---|
| `kiro_dispatcher.py` — launchd tick every 5 min, claims a task file, forks Amazon `kiro-cli` | **no** | OpenAI/Gemini only |
| `tour_loop.py --ceiling N` — generate, score, report | no | OpenAI/Gemini only |
| `CronCreate` — wakes LEAD to review and file the next batch | yes | the Claude plan |

**The dispatcher is the workhorse.** It runs while Michael sleeps and while no Claude
session exists at all, and it does not touch his Claude plan.

## Hard stops — never without asking, at any hour

- deploying anything
- writing to the production database
- deleting what Michael has not agreed to lose
- spending past the stated ceiling
- **judging whether a tour is interesting** — `tour_quality.py` cannot, and says so


---

# THE 30-MINUTE CHECK — Michael's standing instruction, 2026-09-23

> *"there were no reasons why I should have asked you for the status at 8 AM: you could
> have done this and come up with the plan yourself and then executed it continuously
> over night unless you get 3 consistent failures."*

He is right, and the cost was concrete: seven tasks ran overnight, **four produced nothing
and their deliverables were then deleted** by the prune script. A check at 00:45 would have
caught it while the evidence was still on disk. Instead it was found at 08:07 because he
asked.

## Every 30 minutes, while work is in flight

1. **Did the planned tasks actually finish?** `COMPLETED` in `kiro_sessions_ran.md` proves
   nothing — CLAUDE.md: *"`exit=0` from Kiro means nothing. Verify by effect."* Check for
   **commits**: `git rev-list --count storied..<branch>`. Zero commits means it failed,
   whatever it logged.
2. **If something failed, diagnose it before re-dispatching.** The worker log in
   `kiro_session_logs/` shows what it did. Four of last night's four had *written their
   files* — the failure was not committing, which is a different bug from not working.
3. **Replan and execute.** Do not wait to be asked. RULE ZERO.
4. **If there is not enough time to evaluate properly, wait** rather than half-check.

## The three-failure rule

**Three consistent identical failures = stop and ask Michael.** Not three failures — three
of the *same* failure, which means the approach is wrong rather than the run unlucky.

**And even then, do other work.** A blocked thread is not a blocked queue; drop to the next
tier in the list above.

## Always keep FIVE tasks ready

His rule: there must be five tasks available for when the current thread blocks, needs his
judgement, or finishes. **If the backlog falls below five, tell him** — *"we can come up
with these tasks together"*. An empty backlog is information to report, never a reason to
idle.


---

# THE CRITIC RUNS BEFORE MICHAEL DOES — standing rule, 2026-09-23

> *"Please ALWAYS run Amazon-Q reviewer before asking for my review, then analyse the
> review, if you agree with findings, report to me, but not stop to try to fix the issues
> found. I can always have an option to review myself. If no issues found, then you are
> stuck for my final word/review."*

**Never hand Michael a tour that has not been critiqued first.** The order is:

1. Generate.
2. Score with `tour_quality.py` — the counters.
3. **Run the kiro/Amazon-Q critic** — the judgement no counter makes.
4. **Verify each finding.** A finding is a CLAIM. Two have already been wrong: one said
   "4 of 6 files" when it was 2, another reported a stop missing that was present (the
   file had been truncated on the way in).
5. **Fix what survives verification.** Do not stop at reporting — *"not stop to try to
   fix the issues found"*.
6. **Then** hand it to Michael, with the findings and what was done about them.

**If the critic finds nothing, say so plainly and stop** — that is the one state where
his word is the only thing left, and it is a legitimate place to be blocked.

His reasoning is that he should be the LAST reviewer, not the first. Every defect a
machine can find should already be gone before he spends his attention.
