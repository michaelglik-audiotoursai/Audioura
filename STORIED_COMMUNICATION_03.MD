# STORIED COMMUNICATION — Volume 03

Opened 2026-08-14 at Michael's instruction. Volume 02 was maintained until
11:17 on 2026-08-14 and then dropped for six exchanges — his words: *"it seems
that you stopped maintaining STORIED_COMMUNICATION_02.MD for what ever reason.
I need this document to search for my own words later as this session may no
longer hold our communication."* He is right; it was dropped. Volume 02 stays
where it is and is not edited further.

**The rule, restated so the next session cannot lose it:** Michael's questions
go in VERBATIM, LEAD's conclusion goes in short, and the entry is appended
BEFORE the next task starts — not at the end of a session. Sessions are killed
by design (D252). Anything held only in context is gone.

Keep entries short. Evidence belongs in `DECISIONS.md`; this file is the thread.

---

## 2026-08-14

### 11:2x — the credit_line worksheet, and what stop 1's keyword turned out to be

❯ *"I would like to make one worked example of a story sentence that ties a
person to the object, please provide the tour file and open it in VS Code and
then at least 'credit_line' for me to work through the example."*

Built `story_worksheet.py` (offline, free, re-runnable). The three keywords:
stop 1 `book`, stop 2 `Sigmund Freud`, stop 3 `Pierre Reverdy`.

**Stop 1's story keyword is a common noun, and that is why the stop is SILENT.**
Every person it names is struck off for already occupying another slot — Miró is
the `artist`, Mourlot the `printed_by`, and Louis Broder, the publisher the whole
story is about, the `publisher`. Proven: drop `publisher` alone from the exclude
list and `_pick_credit_line` returns `Louis Broder`. Not fixed — design question.

### 11:5x — Notes 1 and 2, and the phrase-as-credit_line experiment

❯ *Note 1: multiple stories about the same person are not prohibitive — but then
redundancy means same people at the same event or doing the same activity.
Note 2: the same test we use to judge whether a sentence has value applies to
picking a credit_line. In "The convergence of narrative and imagery in this
exhibit prompts reflection on how journeys from obscurity to enlightenment could
be depicted in unexpected ways elsewhere", Part 3 is the most general ("the book"
of the sentence); Part 1 is the most stop-specific and so the most interesting.
Make Part 1 the credit_line — note it is more than one word — and run it.*

Ran it. The phrase scored higher (67 vs 57) and produced the worse story. Both
arms wrote the SAME story from a byte-identical ladder and subject, because
`credit_line` only feeds RETRIEVAL. **The idea is right and was wired to the
wrong place — clause-specificity belongs at SUBJECT SELECTION.** Note 1 recorded
as D442. Details D442/D443.

### 12:1x — "I do not see this as a story at all"

❯ *"Please provide output of all 4 routines you wrote... It should start with the
matrix and end up with the text. The first one makes a query out of the matrix —
and I want to see that query. The next one calls AI with this query and gets back
the resulting story. Then we validate the story... Then if valid and has more
sentences than 5, we ask to summarize in 3 sentences."*

Built `michaels_chain.py` — HIS chain, not `story_pipeline`'s. Four defects
(D444, D445):

1. **The writer had already REJECTED all three stories and the pipeline reported
   STORY** — status was computed from grounding alone and discarded
   `story_writer`'s own verdict. Every score quoted that day was on rejected
   output.
2. Routine 4 summarised despite Routine 3 returning REJECTED — there is no
   valid/invalid branch in the chain.
3. `split_sentences` could not split after a quotation mark, so a 3-sentence
   summary counted as 2. Museum stops are full of quoted titles. Fixed.
4. **The query asks "what story CAN BE TOLD"** — a question about what is
   possible. GPT-4o answered it correctly and was never asked to tell a story.

### 12:2x — try the same query on Gemini before changing it

❯ *"it is a matter of speaking. before we change the query, can you get the query
results from Gemini on the very same question?"*

**He was right; finding 4 above is withdrawn.** `gemini-3-flash-preview`, same
query, told an actual story — July 1938, Maresfield Gardens, named people, a
Dalí quote. The phrasing was not the blocker, the model was.

The trade is not free: two runs of the same model disagreed on who took Dalí to
Freud (Stefan Zweig vs Leonard Woolf). Chasing that exposed a false CONFIRM in
`verify()` — it accepted "Leonard Woolf accompanied Dalí" against a sentence that
never mentions Woolf. Fixed. D446.

### 12:3x — "I have a feeling that it is our validator that is misbehaving"

**Confirmed, and it is the day's most consequential finding.** Of Gemini's 30
sentences it flagged 5, and **all five are true**. The 25 it passed include every
sentence that says nothing checkable. Mechanism: it asks whether a capitalised
token appears in the source, so a sentence with no new name and no new year
*cannot* fail. **The vaguer the sentence, the safer it is.**

It also cannot see invented places, numbers or reversals — "in Barcelona", "on
the surface of the moon", "using 47 copper plates" and "refused to illustrate"
all pass. `TRUE_TO_SOURCES` means "contains no unfamiliar name or year". D447.

### 12:5x — go through Gemini's first section one by one

Five claims CONFIRMED from sources: the 19 July 1938 meeting; Freud fleeing
Nazi-occupied Vienna; 20 Maresfield Gardens; Dalí sketching Freud; Dalí comparing
Freud's cranium to a snail. **The three sentences our validator rejected are all
among the true ones.** What is actually wrong is narrow: atmospheric invention in
the same voice as fact, and one unsourced gloss. D448.

### 13:1x — MICHAEL'S RULING: descriptions and stories are judged differently

❯ *"The judgement principles of the stop or exhibit are very different than from
the story. If we describe a stop by providing incorrect or irrelevant description
it annoys our listeners... We are doing it well and I want to keep it that way.
The judgement principles of the story do not have to be relevant or confirmed in
sources, as long as there is not falsehood or contradictions in sources: we
absolutely should not publish a story with wrong facts. But 'Sigmund Freud... who
has just fled Nazi-occupied Vienna' makes Sigmund Freud a human, alive, shows his
state of mind, engages emotions in our listeners... 'it never reaches the object'
— that is a weakness of this story, but to me it is not prohibitive in case if
connecting phrase 'Dali and Freud met only once in London in July 1938' then the
listener knows that the story is about connection of the author and illustrator
of the exhibit. However, my judgement is that this weakness is not prohibitive
and if we do not find a better story, this story is better than none."*

Binding, recorded as **D450**. Description gate = accurate AND relevant. Story
gate = **must-not-be-contradicted**; unconfirmed is allowed, contradicted is not.
"Stakes=0" was a description-shaped ruler applied to a story.

**The actionable half:** to enforce "no falsehood", ask the OPEN question, not
the yes/no question. "Who accompanied Dalí to meet Freud" refuted the Woolf claim
with four sources naming Stefan Zweig and Edward James; every yes/no search had
failed to settle it.

### 13:3x — rebuild the validator, and give me the three scores

❯ *"If we identified the problems in current validator routines we need to change
the validator routines so that it passes through this story **1, correctly
pinpoints errors / hallucinations on the stories we know are not true — this way
we know that the validator is working better instead of not working at all. We
also need to obtain 3 values for this story... History, details, social: all
three independent from 0-100."*

Built `story_validator.py` — the D450 gate. See ANSWERS.MD Q-2026-08-14-3 for
the result, including the one control it still fails.

**Three scores for Gemini section 1: historic 31, detail 0, social 50.**

### 21:3x — three questions about the new gate

❯ *"1. Are all Gemini stories pass our validator? Could it be that some of Gemini
stories actually have incorrect facts in them? 2. Why does the validator wrongly
reject a true obscure claim (and what claim?) about Boris Friedman. 3. How can we
decide how much false rejection is acceptable?"*

**1.** No. The full 30-sentence story is REJECTED — but the number that matters is
that only **5 of 30 sentences were checked at all**. Both contradictions are
spurious: unstripped markdown made the wrong word the actor, giving the queries
"who printed Salvador Dali" and "who founded Salvador Dali". The one real claim in
that sentence — the Woolfs founding The Hogarth Press, which is true — was never
tested. **And yes, Gemini does produce false facts:** the Leonard Woolf claim is
refuted by four sources naming Stefan Zweig and Edward James.

**2.** Not a threshold problem. `named_people` counts "Le Lezard" and "Fine Arts"
as PEOPLE, the query is built from them and becomes *"who gave Le Lezard Fine Arts
2021"*, which cannot find Boris Fridman — so results drift to Alexander Calder's
*Lizard*, Fridman is absent, and absence is read as refutation. The gate asked a
broken question and then believed the silence.

**3.** Don't set a tolerance — the errors are asymmetric. A false acceptance is
**silent** (an untrue sentence in a visitor's ears, never reported); a false
rejection is **loud and recoverable** (we see it, and under D450 we can ship the
story flagged). Make "no usable evidence" a first-class verdict so a contradiction
is only pronounced when the search demonstrably landed on target. Then require
**100% on a labelled FALSE set** before shipping and drive false rejections down by
fixing the question, never by lowering the bar. Track **false-rejection rate at
zero false-acceptance** — today 1 in 3, and D453 shows the cause is a broken query.

Full evidence: D452, D453, D454.

### 21:5x — MICHAEL'S RULING on false rejection: prefer it, and rescue in a second tier

❯ *"it is better to accept false rejection — meaning reject the correct claim than
accept the incorrect one. We can create a logic of going from claim to claim and
getting the best story which is accepted. If no such story, then we need to use AI
and SERP and Gemini to verify rejections in case they are false to get the required
number of stories."*

Recorded as **D455**. Tier 1 strict and cheap: walk the claims, take the best
ACCEPTED story, doubt rejects. Tier 2 expensive and only on a shortfall: re-examine
the rejections with several models and searches to rescue the false ones.

**Implementing it exposed the real bottleneck.** The old gate silently allowed every
sentence it could not form a question about — 25 of 30 — which is the opposite of
this ruling. Now three-way: UNFALSIFIABLE (allowed), CHECKABLE, UNCHECKED_FACTUAL
(held). Measured:

```
full Gemini story   REJECTED_FALSEHOOD   coverage 0.13   3 of 23 checked
Gemini section 1    HELD_UNCHECKED       coverage 0.00   0 of 5  checked
```

**Section 1 — the story you like — now HOLDS**, because we cannot form an open
question for any of its five factual sentences: `fled`, `sketches`, `considers` and
a bare date are all outside the role-verb list. Not a reason to loosen the rule; it
names the priority. **The binding constraint is question formation, not the
threshold.** Coverage is the number to drive up. Evidence: D455.

## 2026-08-16

### — what are the tiers, and how do we measure

❯ *"What are the tiers 1, 2, + and how do we measure the results?"*

Written in full as `STORY_GATE_TIERS.md`; recorded as **D456**.

**Tier 0** description gate — accurate AND relevant, live, not to be touched.
**Tier 1** cheap, strict, always runs; open questions only; PASSES / HELD_UNCHECKED /
REJECTED_FALSEHOOD. Partially built, coverage 13%.
**Tier 2** expensive, only on a shortfall: re-form the question, re-retrieve, and
**adjudicate on citations only** — models find sources, they never rule on truth.
Not built.
**Tier 3 (+)** widen the subject → ship the weaker verifiable story → ship
description-only → human queue with sources. The human queue is the only path by
which an unverified claim ships.

**Measured at three levels.** Per story: coverage, verdict, Historic/Detail/Social,
object connection. Per gate against a labelled fixture: false acceptance on the FALSE
set (target 0, non-negotiable), false rejection on the TRUE set, stability over 3
runs. Per tour: tier-2 invocation rate, rescue yield, cost, stops with no story.

**Coverage is first because it bounds everything else** — a verdict over 13% of a
story's falsifiable sentences is a statement about 13% of the story.

**Build order:** the labelled fixture (~30 claims) first and unskippable; then
question formation; then markdown stripping and entity typing; then tiers 2 and 3.

### — five questions on the tiers; and a correction to an earlier answer

❯ *"1. What is good about Tier 0... if 'tier 1 cannot currently return a single
accepted story'? 2. Is [question formation] the primary what should we be working on
or something else? 3. Please detail 'Regression 50/61, same 11 pre-existing
failures'. 4. Tier 3 — the '+' — could you give me an example? It could be
miscommunication... 5. What is fixture?"*

**CORRECTION FIRST (D457).** I listed "20 Maresfield Gardens" as one of five confirmed
true claims in Gemini's section 1. **It is false.** The story says the MEETING happened
there; the meeting was at **39 Elsworthy Road**, and the Freuds moved to Maresfield
Gardens in September 1938, two months later. I verified *"Freud lived at Maresfield
Gardens"* — true — and reported it as the claim. Section 1 has four true claims and one
false one; my "passes on truth" verdict is withdrawn.

**1.** Tier 0 is a different product surface. It ships today — 31 tours, field-tested —
and stories are additive, so tier 1's state says nothing about it. Its quality rests
on Michael's field judgement, not on a measurement LEAD has run. It is in the spec so
story work does not regress it.

**2. No — and the answer changed after measuring (D458).** Gemini with Google Search
grounding returns per-sentence citations: **83% of sentences carry a cited source,
against 13% for our post-hoc gate.** Sources included freud.org.uk. It was also more
ACCURATE — it placed the meeting at 39 Elsworthy Road, which is exactly what the
ungrounded version got wrong. **The architecture is the primary work; question
formation is demoted to the fallback for uncited sentences.**

**3.** Seven of the eleven are environmental (services down, container paths and
hostnames used from the host, no API key). Four are real: local413 ranking (3 of 8),
local441 concurrent lookups, contained_regression, local445 parallelism. All eleven
verified failing identically before the day's changes.

**4.** "+" was Michael's own notation, read as "beyond tier 2". Worked example given.

**5.** A fixture is a fixed set of test cases with known right answers, kept in the
repo, used to measure whether an instrument works.

### 10:5x — did you start on Yuri's bugs, and how do I ask a side question

❯ *"1. I am confused: did you start working on Yury's bugs already? Should I clear
this session to save tokens now? 2. If I clear this session + restart will we be able
to continue our discussion to fix validator...? 3. I want to do this from Windows
computer, please make sure that BETA_MOBILE_START_HERE.md is pushed to the origin...
4. Next time if I need you in this session to concentrate on one question, but need to
ask something else, how can I do it: because this time you decided to investigate and
now I am confused what conversation belongs to what. 5. Please have QUESTIONS.MD and
STORIED_COMMUNICATION_03.MD current..."*

**1. No — zero mobile files touched**, verified against the git log. LEAD located the
reports (ClickUp **DMs**, channel `2ky4d0u8-919`, not tasks — that is why every search
missed them) and set up an isolated worktree plus a briefing for another session. **Yes,
clear now** — this session is long, and long sessions are the expensive kind.

**2. Yes.** `restart.sh`, then D440–D458, `STORY_GATE_TIERS.md`, this file,
`QUESTIONS.MD`/`ANSWERS.MD`. Code committed: `story_validator.py`, `michaels_chain.py`,
`story_trace.py`, `story_worksheet.py`, repaired `evaluate_story.py`. Where it stands:
gate passes the good story and catches the known hallucination, coverage 13%, one true
obscure claim still falsely rejected, and D458 says the next move is grounded
generation (83% citation coverage), not question formation.

**3. Pushed and verified** — `beta/yuri-bugs` at `2d0d92a` on origin, file reads back.
**But `storied` has 51 unpushed commits containing ALL of the validator work**, so none
of it is reachable from Windows. Gated on the field test; today's commits are lab
tooling, not tour-pipeline changes. Not pushed — Michael's call, one command either way.

**4. New convention, now in `CLAUDE.md`:** `ASK:` = answer only, no tools, no commits.
`SIDE:` = different topic, logged separately. Combinable. Without a prefix RULE ZERO
still applies. LEAD also now owes a one-line warning before turning something that
might be a question into files and branches.

**5. Done** — `QUESTIONS.MD` created as a pointer index (not a duplicate of
`ANSWERS.MD`), and answers Q-2026-08-16-1..4 written.

### 11:0x — one file, and make the links work

❯ *"I confused things -- Sorry, I want to have only one file: ANSWERS.MD. Please
combine ANSWERS.MD and QUESTIONS.MD into ANSWERS.MD and remove Answers.md. In
ANSWERS.MD I want links to function: in my VS Code they are highlit but nothing
happens when I click on them. Let me know when I should do /clear+restart"*

Done. `QUESTIONS.MD` is gone and its index folded into `ANSWERS.MD`'s existing
Contents block, using the same `<a name>` anchors the older entries already use.

**Why the links did nothing:** they were plain text. VS Code only follows real
markdown links — `[name](file.py#L85)`. The new **Code map** section in `ANSWERS.MD`
uses that form throughout: **Cmd+Click** in the editor, single click in the preview
(**Cmd+Shift+V**). All 30 links verified — every file exists, every line number is
inside the file, three spot-checked to land on the named function.

`CLAUDE.md` now records that there is ONE file and why, and its session-start pointer
moved from volume 02 to volume 03.

### 11:2x — Windows commands for Yuri's bugs, and a branch cut from the wrong base

❯ *"Can you provide the exact commands I need to run on Windows computer to start
Claude.AI session dedicated to fix Yury's bugs in Beta on GCloud and on/in Storied as
the fixes should work on both... Storied fixes and changes should not get into Beta on
GCloud."*

**Checking that constraint found a mistake LEAD made an hour earlier.**
`beta/yuri-bugs` was cut from `storied`, not from the Beta base, and pushed — so it
carries **1861 commits ahead of main**, including all 51 field-test-gated Storied
commits. Merging it into Beta would ship the whole story-pipeline rewrite to GCloud.

**Corrected:** `fix/yuri-audio-and-map`, cut from `origin/main`. Verified to carry one
commit (its briefing) and zero Storied work. Because `main` is an ancestor of
`storied`, the same branch merges cleanly into both tracks.

`beta/yuri-bugs` needs deleting from origin — Michael's call, command supplied.
Recorded as **D459**.

### 11:5x — the Windows startup file

❯ *"Can you create a startup shell to run on Windows Claude called Beta-Bugs_Fixing.md,
that explains to Claude on Windows all it needs to know to identify problems, create
tasks in ClickUp from Yury's MDs and assign them to Kiro and then run internal Kiro as
you do here in the continuous development model to make sure the bugs (if there are
any: Yury can be wrong!) are fixed?"*

`Beta-Bugs_Fixing.md` written and pushed on `fix/yuri-audio-and-map`. Windows: start
Claude, say *read Beta-Bugs_Fixing.md*.

**Three things checking turned up, all handled in the file.**

1. **The Kiro machinery is not on the Beta line.** `kiro_dispatcher.py`, `restart.sh`
   and `.continuous_dev/` exist only on `storied`. Committing them to this branch
   would carry Storied tooling into `main` on merge, so the file shows how to fetch
   the dispatcher into the working directory under `.git/info/exclude` instead —
   never `git add`.
2. **The Beta ClickUp lists are different IDs from the Storied ones in `CLAUDE.md`.**
   Beta 🟩 Mobile — Kiro is `1000410000000730`, not `1000410000000734`. Read live from
   the workspace rather than trusted from the doc.
3. **The Windows path looked mistyped** — `eclipseyour routine-workspace` read like a
   mangled `eclipse-workspace`. **Michael confirmed it on 2026-08-17:** the real path
   is `C:\Users\micha\eclipse-workspace\AudioTours\development`. Corrected in the
   file; the discovery command is gone. Also corrected there: that path IS the git
   clone root, not a subfolder inside the repo — verified against `origin/main`, which
   has no tracked `development/` directory.

Michael's "Yury can be wrong" is built in as the first step: reproduce before opening
a task, and return one of three verdicts — CONFIRMED / NOT REPRODUCIBLE / WORKS AS
DESIGNED. The `#0` label for current location is flagged as Yury's suggestion, not a
defect.

## 2026-08-17

### — Michael's plan for the Beta fix: confirmed with one order correction

❯ *"please confirm that I need on Windows computer do the following: Ask Kiro to do the
following: git checkout main / git merge --no-ff fix/yuri-audio-and-map / bump version
/ tag / push ... then start Claude and ask him to run Beta-Bugs_Fixing.md"*

**The steps are right; the ORDER is inverted.** `fix/yuri-audio-and-map` holds **two
markdown files and zero code changes** — verified `git diff --name-only origin/main..`
returns 0 non-`.md` files. Merging and tagging now would ship a Beta release for
documentation. Claude + `Beta-Bugs_Fixing.md` runs FIRST (verify → derive → implement
→ test); the merge/tag/push is the last step. An ⛔ ORDER MATTERS block is now the
first thing in that file.

**Version — he asked, and he was right that I never logged it.** `origin/main` is
`version: 2.1.1+18`, the only tag is `beta-2.1.1+18`, so the next Beta build is
**`2.1.1+19`** — build number only, per `BRANCH_MODEL.md` and Google Play's rule that
versionCode must increase while the version name may stay. `storied` is on `2.2.1+1`,
a separate line; never copy a version between them. **I had given `2.1.1+19` in chat as
an example and never wrote it to disk — that is the gap he caught, and it is fixed
here and in `Beta-Bugs_Fixing.md`.**

**Two ClickUp tasks created** in 🟩 Mobile — Kiro (**Beta** space, `1000410000000730`
— NOT the Storied list): `wdvrdaxmq2` (concurrent audio) and `wdvrdaxmq3` (numbering).
Both lead with "verify it is a bug — Yury can be wrong" and three allowed verdicts.

**Correction to his wording:** he asked to assign them to *Claude_Storied*. These are
Beta bugs and must not enter a Storied queue — that is the mixing `TRACK_B` exists to
prevent. They are assigned to the Beta Mobile Kiro queue, reviewed in 🔵 Claude —
Review (Beta).

**Docker downgrade added** to the startup file: the Windows laptop runs Storied images,
and since this branch is cut from `main`, checking it out and rebuilding IS the
downgrade. Two commands included to prove you are on Beta code before testing.

**Beta-Staging (his step 6) is NOT covered** by any of this — it is a new GCloud
environment plus a three-way mobile selector (beta / Beta-Staging / Storied), which
extends `TRACK_B_STORIED_VS_BETA.md` from two values to three. Needs its own decision
and its own task before anyone builds it.

### 11:0x — Michael's step-by-step runbook

❯ *"please summarize my steps here in a numbered list with most details possible; for
example, I do not understand what that means -- what I must actually do when you write
things like '1. Downgrade Docker to Beta checkout this branch, rebuild' I need to have
an action for it. After that Please create a task for me in ClickUp in Beta Space and
assign it to me with these exact steps..."*

**Fair criticism — "downgrade Docker" is a description, not an action.** Rewritten as
literal commands, six phases, every step something he types.

Created **[`wdvrdaxmqb`](https://app.clickup.com/t/wdvrdaxmqb)** in 👤 Michael (Beta
space, `1000410000000731`), assigned to Michael.

| phase | what he does |
|---|---|
| **A** | put the laptop on Beta: `cd /d`, fetch, checkout, **prove it is not storied**, `docker-compose down/build/up`, health check |
| **B** | `claude` → *read Beta-Bugs_Fixing.md* → wait. It should only stop for the `#0` decision |
| **C** | bump `2.1.1+18` → `2.1.1+19`, `bash build_flutter_clean.sh`, get the `.aab` onto his phone, test both fixes |
| **D** | only after C passes: merge to `main`, tag `beta-2.1.1+19`, push with `--follow-tags`, forward-merge into `storied` — **never push storied** |
| **E** | Play Console → Closed testing → upload → roll out to Yuri |
| **F** | Beta-Staging — **explicitly out of scope**, needs its own decision |

**Facts verified rather than assumed while writing it:** `PLAY_BUILD_AND_UPLOAD_RUNBOOK.md`
and `build_flutter_clean.sh` are both present on the Beta line; the build command is
`bash build_flutter_clean.sh`; the bundle lands at
`…\development\audioura-release.aab`, not under `audio_tour_app/build/`.

**One honest gap flagged in the task:** an `.aab` cannot be sideloaded, so his own
phone test needs either Play Internal testing or a debug APK — the APK route is not in
the runbook and must be asked for deliberately.

A troubleshooting table closes the task, including "Claude starts reading `story_*.py`
→ it is on the wrong branch, stop it".

### 11:1x — SIDE (Beta): the branch deleted, and "Beta" meant two things

❯ Michael ran `git push origin --delete beta/yuri-bugs` — **done, D459 closed.**

❯ *"Why then you said 'the fix has to reach Beta or he [Yury] never gets it'?"*

**He was right and I was wrong.** I conflated the Play **Beta track** (how Yuri
receives a build) with **GCloud-Beta** (the backend the build talks to). Yuri gets
2.1.1+19 through the track; +19 points at GCloud-Beta-Staging; testers on +18 keep
hitting GCloud-Beta untouched. **The app version is the isolation mechanism, not the
branch.** D460 — and it bans writing "Beta" unqualified from here on.

❯ *"I think we should create a new branch Beta-Staging... is it a good plan? I want to
make sure that testing Beta-Staging we do not miss unexpected regressions that are
working fine now in Beta."*

**Good plan, adopted, one gap and one caveat.** D461.

- **Built it:** `beta-staging` pushed — 5 commits above `origin/main`, all markdown,
  **zero Storied work, measured.** Renamed from `fix/yuri-audio-and-map`, which keeps
  the Windows briefings. `Beta-Bugs_Fixing.md` rewritten for the new flow.
- **The gap:** "beta-staging will go away" must be **merge to `main`, then delete** —
  deleting without merging loses the fixes. Guarded in §7c.
- **The caveat:** both bugs read as **client-side** (player controller; client
  indexing two lists off one server payload). If so, no backend change is needed and
  GCloud-Beta-Staging is not on the critical path for *these* fixes. Flagged as a
  diagnosis to confirm, not a fact.
- **His regression worry, answered:** two sources, and the obvious one is the smaller.
  *Code* is bounded by keeping the diff small. *Environment* is the one that gets
  missed — a hand-built staging env drifts from GCloud-Beta in secrets, env vars, DB.
  **Mitigation is a baseline:** deploy staging from `main`'s own commit, smoke-test
  both endpoints, confirm identical, *then* deploy the fix. Same lesson as the
  `prepush-baseline` worktree — a regression is a claim about two trees. And Yuri must
  be asked to **compare** +18 with +19, not judge +19 alone.
- **Open:** does +19 hard-code the staging URL or expose a selector? Recommend
  hard-coded — a user-facing selector is the unwritten TRACK_B three-way feature and
  does not belong on a bug-fix build.

**ClickUp `wdvrdaxmqb` updated** — phase D was "merge to main", which ships to
GCloud-Beta; put on hold, phases A–C unchanged.

### 13:1x — Michael: verify the Beta forward-merge on Storied local

❯ *"We fixed one problem at Beta Yury reported and pushed it not only into Beta, but
also into Storied. We created a Task for you in Storied space in ClickUp for
verification... can you please find your task verify and update Storied local to make
sure everything is in order."*

**Done. [`wdvrdaxnbw`](https://app.clickup.com/t/wdvrdaxnbw) verified and closed.**
Full outcome in [ANSWERS.MD Q-2026-08-17-1](ANSWERS.MD#q202608171) and D462.

- **Merged clean** — 11 files, **1468 insertions, zero deletions**. Nothing of Storied's
  was modified. Safety tag `pre-beta-merge-20260817` cut first.
- **`.dockerignore` resolution correct**, `[LOCAL-323]` intact, both regression suites
  green.
- **The one item the Beta session left open — `build_web_page_fixed.py:183` — is live
  code, not dead.** Traced Dockerfile → import → import → running container. Fixed
  (`a1f5d9f`), image rebuilt, and verified **from inside the container**.
- **Not pushed** — 66 ahead of `origin/storied`, still behind the field-test gate. The
  file is Storied-only so `main` is owed nothing. No `storied` → `main` merge.

### 13:5x — Michael: "should we not fix wdvrdaxn8y's two Dockerfile breaks now?"

❯ *"Wait, shoudl nto we fix wdvrdaxn8y's two Dockerfile breaks now?"*

**Yes — and noting them instead of fixing them was the stall RULE ZERO exists to
prevent.** Done. D463. Branch `fix/dockerfile-build-breaks` @ `a0d7238`, cut from
`origin/main` and pushed; merged into local `storied` @ `9b4fd14`.

- **The reported break was seven breaks.** `Dockerfile.newsletter-processor` copies only
  the service file, which imports **seven** siblings. `apple_podcasts_processor` is just
  the first one Python reaches. Fixed with `COPY *.py .` — a hand-maintained list that
  drifts from the imports is the defect itself.
- **`psycopg2-binary` 2.9.1 → 2.9.9** — no cp311 wheel was the whole story; 2.9.9 has
  cp39 and cp311 and is already this repo's pin in three other requirements files.
- **Proven red before green**, both images, then rebuilt from the Storied context too.
- **Kept out of `beta-staging`** — D461 bounds that branch to Yuri's fixes so his test
  result stays interpretable. No GCloud deploy.

## 2026-08-18

### 10:2x — Michael: is beta-staging really a thing? and what is the Windows session called?

❯ *"Is beta-staging really a thing? I was thinking about it when I thought that fixing
Yury's bugs would require a new mobile app. It turned out that you on Windows managed to
fix it on server only..."*

**No. It is retired without ever having been used, and the premise it was built on
dissolved.** D464. Measured: `origin/main..origin/beta-staging` is **1 commit, markdown
only**; `origin/beta-staging..origin/main` is **9**, including both audio-fix commits.
D461's merge-before-delete guard exists to stop *fixes* being lost — there are none on it,
and its one commit describes a staging workflow that never ran, on a file `main` has since
rewritten. **Delete without merging**, recorded as a deliberate exception. LEAD did not
delete it — pushed branch, Michael's call (D459 precedent).

The general lesson, and it is on LEAD: D461 reasoned well from a wrong premise. BETA-1 was
not in the Flutter app *or* the backend logic — it was in the **generated HTML**, which a
server fix reaches with no app build at all. **Diagnose the layer before designing the
delivery mechanism.** The environment-parity lesson from D461 survives; only the branch is
retired.

❯ *"We created a task for you here or on Windows — is Claude-Beta how it suppose to call
itself: it does not produce its name and date as I asked."*

**The task is here, in Storied**, and it is not for LEAD:
[`wdvrdaxnc5`](https://app.clickup.com/t/wdvrdaxnc5), 🟩 Mobile — Kiro, **Agent: Mobile
Kiro**, riding the Storied release. It is well specified and its diagnosis is right — the
numbering was never wrong, pin 1 hides under pin 2. Worth keeping from it: `_applyCoordJitter`
fires only on **byte-identical** coordinates and offsets by 8.9 m, which at the default
zoom 14 is **1.3 pixels** — about 28× too small to see.

**On the name: `Beta_Bugs` is canonical, and the omission is the cause of the confusion.**
D465. It signs ClickUp comments *"the Beta_Bugs session"* but never prefixes its replies,
so it reads as "Claude-Beta" — one session, two names, because the one mechanism that
fixes the name was skipped. Added to the `CLAUDE.md` table with its real scope; `Beta_Mobile`
retired in the same edit. The rule gained the sentence it was missing: **on restart, a
session's first act is to adopt its row, or add one before replying.**

❯ *"Are you ready for /clear+restart to dedicate your efforts to improve the validators so
the good storied for humans are not dismissed as inaccurate when there are no evidence
that they are?"*

**Yes — ready now, and the mission is written to disk so the fresh session starts with it**
(`PENDING_REMINDERS.md`, top open item, quoted verbatim). Framed as what it is: a
**false-positive** problem, not a coverage problem. Two instruments are already known to
lie and neither is fixed — **D423** (`beats_in_delivered_text` reports a false `0` while
the beats are demonstrably in the text) and **D243/D462** (exact-match greps reporting
false absence). **Measure how often a gate's rejection is right before tightening
anything.**

---

## 2026-08-18 — the validator session (D466–D482)

❯ *"improve the validators so the good stories for humans are not dismissed as inaccurate
when there is no evidence that they are."*

Measured first. Delivered tours are the wrong instrument — they contain only survivors —
so the false rejections had to come from run drop logs. Found one immediately: the
temporal gate threw away a TRUE Juan Gris / Pierre Reverdy collaboration claiming Gris
"died in 1887". He died in 1927; 1887 is his birth year. Three causes: a regex reading
the final `d` of "published" as "died", a partial snippet shadowing the correct table,
and a publication year being read as the year people met. **D466.**

❯ *"Please confirm the following workflow… Is it accurate description of the algorithm we
use?"*

Accurate as a design, not as a description of the code. The matrix has **15 fields, not
8**; three of yours mean something else (`medium` is the physical medium, not the
exhibition; `venue` is three fields; `credit_line` is a provenance string that
LOCAL-406 regex-parses `donor` and `printer` out of, so it cannot carry your rotating
fact). Retrieval is **Serper.dev only** — Gemini is built and has **zero production
importers**. `evaluate_story` and `story_validator` are **not in the live generator**.
Two of your steps do not exist at all: story-worthiness selection, and the retry loop.
Written up as `STORY_BASELINE.md`.

❯ *"provide evaluation index on each iteration … so I can see when we stop improving"*

`story_iteration_chart.py`, MFA stop 2. Curve 40 → 51 → 61, then flat for five
iterations. **The plateau was the metric, not the material**: `valuation_index` had no
term for the object at all, and raising the snippet cap made the story name "drypoints
and lithographs on sheepskin" while the index FELL, because groundedness penalised proper
nouns absent from the museum's own page. Same mistake as the gates, one layer up.
**D467.**

❯ *"continue development … unless the score goes down for 3 consecutive iterations"*

Four rounds, best validated story **47 → 54 → 63 → 64**. Rule never triggered. The index
now counts the object (D468); the ranker keeps the consequence it was discarding (D469).

❯ *"generate the full tour … maybe we reached the acceptable point for Storied release"*

**No.** Lab 64, production 36. The Hogarth Press fabrication shipped again, and stop 2
came out as two sentences because a gate correctly deleted a false claim and **nothing
replaced it** — the missing retry loop, measured. **D472.**

❯ *"fix them and run the tour again … putting all your lab enhancements into production
if you feel it is a good idea; if not tell my why not."*

Built the retry loop (D474). Worst stop 21 → 32, detail 13 → 33, Hogarth gone. **Did not
port three things and said why**: `evaluate_story` as a gate (calibrated against one
human judgement — yours), the snippet cap default (measured on one exhibition), and the
story-prompt extraction (would make a regression unattributable).

**The retry then taught the model to evade the gate** — told not to repeat or rephrase a
rejected claim, it nominalised the verb and shipped the same falsehood. D476.

❯ *"continue fixing the issues you find as I am going to be at Gym"*

Ten commits. Gate-caused broken English (D475): `_is_well_known` returned **False for
Miró and Dalí** but True for Picasso, so Miró's name was deleted from a sentence about
his own book; the possessive guard tested **the same ASCII literal twice**. Hogarth
escaped a **third** time via an em dash (D478). Built organisation grounding (D479), then
**A/B'd it over three runs per arm and found it cost 5 points** — it was dropping
"Éditions Verve", the real publisher. Widened its evidence base: **45.7 mean, up from
43.7 without it.** D482.

❯ *"How much money did we spent today?"*

**~$3.13** OpenAI + SERP: 16 tour runs ≈ $2.59, lab work ≈ $0.54. $1.94 of that is
estimated because the variance runs were piped through `grep` and their cost lines were
discarded. The **`cost_ledger` under-reports host-side work ~20×** — it recorded $0.1110.

❯ *"Have you been updating ANSWERS.MD and STORIED_COMMUNICATION_03.MD?"*

**No.** DECISIONS.md was updated all day; these two were not touched since 10:22 and
08/17. That is the rule this file exists to enforce, and I broke it for a full session.

---

## 2026-08-18 17:2x — THE 7-STEP STORY SYSTEM, in Michael's words, with status

Michael could not find these steps in this file: the 2026-08-18 entry above summarised
the exchange but never recorded the steps themselves. Recorded verbatim here, because
they are the specification everything else is measured against.

> 1. The system generates tours.
> 2. We analyze the tour stops and determine that some of them would benefit from stories.
> 3. In the loop: stop-by-stop we analyze the sentences and select facts to follow the
>    methodology: Story is connecting a fact with the stop with the exhibition or museum
>    or with the city or with the country.
>       1. Again: Fact —> Stop —> Exhibition
>       2. Making query
>       3. Getting result and evaluating parts for the most interesting story
>       4. Getting the right story size: if too small need to learn more from Internet.
>    Based on that methodology in order to get ready for #2: Making query we build the
>    matrix: canonical_title, english_title, artist, publisher, credit_line, Printed by,
>    medium, venue
> 4. We generate query and ask it to multiple entities such as AI OpenAI.API — do we use
>    any other AI? and/or Serp and/or Gemini
> 5. We evaluate the story assigning a value index.
> 6. We validate story.
> 7. From all validated valid stories we pick the most valuable, make it to 3-5 sentences,
>    in most valuable we can take a larger size. If there are no valid stories, we go to
>    the next fact make it credit_line in our matrix and repeat from #4.

**Status verified against code 2026-08-18 evening — two done, one never started, four partial:**

| # | status | detail |
|---|---|---|
| 1 | ✅ done | — |
| 2 | ❌ **never implemented** | no worthiness check exists; every museum stop is mined at full cost |
| 3 | ⚠️ 3 of 4 | matrix ✅ (15 fields), query ✅, evaluate parts ✅ (D469). **"if too small, learn more" is lab-only** (`story_lab.py` S4) |
| 4 | ⚠️ one engine, one model | Serper.dev + OpenAI. Gemini built in `story_leads.py`, **zero production importers** |
| 5 | ⚠️ fixed, **not wired** | `evaluate_story` improved (D468/D470) and has **0 references in `generate_tour_text.py`** |
| 6 | ✅ done, much stronger | D466, D471, D473, D475–D479, D481 |
| 7 | ⚠️ half built | retry exists (PHASE 5.17) but fires on a post-gate **word floor**, not "no valid story"; **forbids rejected claims instead of rotating to the next fact** (no `focus_fact` in production); packs to a **450-word budget**, not 3–5 sentences |

**5 and 7 are the two that close the loop**, and both work in the lab — which is why the
lab scores 64 and production 45.7. Step 5 is deliberately unwired: the index is calibrated
against one human judgement, so it may REPORT but must not yet GATE (D474).

**`credit_line` still cannot carry Michael's rotating fact** — LOCAL-406 regex-parses
`donor` and `printer` out of that field, so a fact written there is read as a person's
name. It needs its own slot; the lab calls it `focus_fact` (`STORY_BASELINE.md` §2).

---

## 2026-08-18 21:4x — the instrument audit, run as a class

❯ *restart*

Picked up the mission left at 17:0x: audit the instruments as a class rather than one at
a time. Result below, plus one thing you have to do.

**⛔ The OpenAI account is out of credits.** Three measurement runs failed instantly at
the first API call — `credit_balance_exhausted`. Nothing was spent, and **no tour can be
generated at all until you add credits.** That blocks the story work and every score.

**Four defects, found by probe, all in the grounding gates:**

| probe, on the code as it stood | result |
|---|---|
| `check_person_grounded('Salvador Dali', "…Salvador Dalí…")` | **False** |
| `_agent_in_text('Editions Verve', "…Éditions Verve…")` | **False** |
| `_agent_in_text('Ars', 'Arsenal Gallery')` | **True** |
| `_PERSON_MULTI_WORD` on "Édouard Manet met Émile Zola" | **no names found** |

The first means Dalí's own sentences get dropped whenever the model spells him without
the accent. The second is the Éditions Verve rejection you cost five index points to —
the same bug, in the sibling gate, hours after the first was fixed.

**The pattern, and it is the answer to "why is progress slow":** three instruments ask
the same question of the same corpus and only the newest one is right. Each was fixed
correctly by whoever had just been bitten; nothing carried the lesson sideways. There is
now **one** folding primitive (`text_fold.py`) that all of them call, and the new test
suite is table-driven over the gates, so one that forgets goes red the day it is written.

**Two things the mission's framing did not predict:**

1. **The word-boundary hunt came back empty.** All 42 regexes swept mechanically — none
   matches inside a longer word. The boundary bugs were in the substring `in` comparisons,
   which a regex audit would never have reached.
2. **The gates' false-ACCEPTANCE half was untested and broken.** `Tate Modern Press`,
   `The Met Foundation` and `Louvre Editions` all grounded for free against a corpus
   naming none of them, because the exemption matched any name *containing* a famous
   museum's. Inventing a publishing arm for a real museum was the one fabrication shape
   guaranteed to pass. This is your measure 6 — a gate needs a TRUE set, not just a FALSE
   set. The false-rejection half fails loudly and got fixed four times in one day; this
   half fails silently and nobody had looked.

**Verified:** 60/60 new assertions, **21 red on revert** to the old code, and 110
assertions across 10 existing suites still green — all of which were green *before* this
change too, with three gates false-rejecting.

**Not claimed:** the tour score. These are gate-behaviour changes, so **45.7 is stale and
I am not quoting it.** The three runs that would replace it are what the credits block.

## 2026-08-18 22:2x — the credits, and what the runs actually showed

❯ *"I put $30 to OpenAI"* · *"We also are running CERP and Genivi… should I add money?"*

**No — neither needs money.** Probed both: **Serper** (the SERP search provider) returns
200 with credits; **Gemini** returns 200 on all three model names the code uses. The 429
"prepayment credits" note from 08-13 is stale, and my first Gemini probe failed on a
*retired model name*, not billing. Gemini also has **zero production importers** —
`generate_tour_text.py` does not import `story_leads.py`, only the lab does. It is step 4
of your 7-step list, built but unwired; money will not wire it. **OpenAI is where the
spend is**: ~$0.16/run against ~$0.02 of Serper. Top-ups now logged in
`OPENAI_CREDIT_LOG.md` — you asked how much you added last time and nobody had written it
down.

**The runs found a regression I had introduced.** Teaching the person extractor to see
accented capitals made **`Éditions Verve` visible to it as a PERSON**; gate 5.158 then
looked for that "person" on the narrow exhibition page, failed, and dropped the sentence.
That is your Éditions Verve false rejection **through a third gate — one my own fix
opened** — while the org gate grounded the same name correctly one phase later. Fixed:
the person extractor now rejects anything carrying an organisation marker, sharing the org
gate's vocabulary. Only a live run could have caught it.

**And then the measurement contradicted itself, which is the real finding.**

| arm | mean | range |
|---|---|---|
| D482 baseline | 45.8 | 43.0–48.5 |
| after r1 fixes | 47.8 | 43.3–53.7 |
| after r2 fix | 40.8 | 37.0–44.3 |

Three arms, essentially the same code, **7 points apart**. Across all 22 runs today the
single-run sd is **4.9**, so a 3-run mean carries **±5.6** at 95%. **All three arms are
one distribution.**

**So D482's "the org gate cost 5 points" does not survive.** That difference was also
3-vs-3 and also inside the noise. What stands from D482 is the part that never depended on
the number: the drop log **showing** Éditions Verve being removed, and the argument that
the role-claim gate's narrow corpus is load-bearing. Mechanisms survive; the 5 points do
not.

**3 runs can only resolve a ~10-point effect.** To resolve 5 points takes **15 runs per
arm — about $5**. The rule was too weak, not too expensive. New rule in D484: 3 runs to
check for breakage, 15 per arm for a real A/B, and **batch changes between measurements**
— tonight measured three times because two fixes landed in between, which is $1.50 spent
to learn nothing.

**Honest standing: no measurable change in tour quality tonight, in either direction.**
The gate fixes are justified by mechanism and unit evidence, not by a score. **45.7 is
retired**; the best current figure is **42.8 ± 2.1 over 22 runs**.
