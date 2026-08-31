# Beta-Bugs_Fixing — Windows startup

Michael starts Claude and says **"read Beta-Bugs_Fixing.md"**. This file is the whole
briefing. Work top to bottom.

> ## ✅ FIRST ACTION — nothing is waiting on Yury any more (2026-08-28)
>
> **All three tasks below are CLOSED.** Michael verified them on a device on
> 2026-08-28 and instructed (`wdvrdaxvvc`): *"close the issues as verified in GCloud
> manually by me."* Yury never replied — last message 2026-08-16.
>
> | task | outcome |
> |---|---|
> | [`wdvrdaxmq2`](https://app.clickup.com/t/wdvrdaxmq2) concurrent audio | **complete** |
> | [`wdvrdaxmq3`](https://app.clickup.com/t/wdvrdaxmq3) map numbering | **complete** — `WORKS AS DESIGNED — confusing` |
> | [`wdvrdaxqjn`](https://app.clickup.com/t/wdvrdaxqjn) wrong coordinates | **complete** |
>
> ### 🔔 STILL DO THIS AT SESSION START — check ALL tester channels, not just Yury's
>
> Michael gets ClickUp's email alerts; this session gets **nothing**. The only way to
> learn a tester said anything is to look.
>
> **There are three testers, not one.** Until 2026-08-30 this check covered only Yury,
> and a channel Greg created on 2026-08-24 had gone unread for six days. It happened to
> be empty — but that was luck, not process.
>
> | tester | id | DM channel | as of 2026-08-31 |
> |---|---|---|---|
> | Yury Makedonov | `101707192` | `2ky4d0u8-919` | last message **2026-08-16** |
> | Gregory Lepsky | `101714111` | `2ky4d0u8-999` | **0 messages, ever** |
> | igor linkov | `101715779` | **none exists** | never contacted |
>
> **Do not hardcode the channel list.** Enumerate it, so a new tester cannot be missed:
>
> ```
> clickup_get_workspace_members          -> tester ids
> clickup_get_chat_channels              -> find DMs whose creator is a tester id
> clickup_get_chat_channel_messages      -> read each
> ```
>
> Greg and Igor have **no tasks assigned and have never been asked to test anything** —
> see [`wdvrdaxxrd`](https://app.clickup.com/t/wdvrdaxxrd), which holds ready-to-send
> onboarding drafts for both. Their silence is not a signal.
>
> If a tester reports one of the closed bugs as still broken, **check when their tour
> was generated before treating it as a regression** — every fix is in the generator, so
> a tour downloaded earlier keeps the old HTML and coordinates.
>
> Two follow-ups stay open by design: `wdvrdaxnc5` (merge overlapping pins) and
> `wdvrdaxqtf` (real place database + confirmed-vs-estimated markers), both Storied.
>
> <details>
> <summary>Original triage table — kept for the reasoning, no longer actionable</summary>
>
> | task | what we asked him | if he answered |
> |---|---|---|
> | [`wdvrdaxmq2`](https://app.clickup.com/t/wdvrdaxmq2) BETA-1, concurrent audio | generate a **new** tour, confirm one audio at a time | **works** → set **Complete**, cite `audioura:v33` / `tour-modernized-00009-99b`. **fails** → unzip his tour and check `index.html`: the `addEventListener('play'` handler must call `otherAudio.pause()`. If it doesn't, his tour predates the deploy — a false negative, not a regression. |
> | [`wdvrdaxmq3`](https://app.clickup.com/t/wdvrdaxmq3) BETA-2, map numbering | zoom in far, confirm pin #1 appears beside #2 | **confirmed** → close as `WORKS AS DESIGNED — confusing`; real fix is [`wdvrdaxnc5`](https://app.clickup.com/t/wdvrdaxnc5) in Storied. **genuine mismatch** → new defect; check whether the stop's `audio_N.txt` has a `Coordinates:` line, since stops without one are dropped from the map while survivors keep their numbers. |
> | [`wdvrdaxqjn`](https://app.clickup.com/t/wdvrdaxqjn) BETA-4, wrong coordinates | generate a **new** tour, check each pin is where that place actually is | **works** → set **Complete**, cite `audioura:v33`, and record it in `SUBMISSION_BETA_BUGS.md`. **a pin is wrong** → run the stop's name and address through `geocode_stops.resolve_stop()` and read the confidence: a *low*-confidence miss is known behaviour, a *high*-confidence miss is a real regression. **pins in the wrong ocean** → that is [`wdvrdaxqte`](https://app.clickup.com/t/wdvrdaxqte), reversed lat/lng, not this. |
>
> </details>
>
> **Handle things yourself.** Michael's standing instruction, 2026-08-17: close it or
> continue the work here on the Windows laptop; only come to him if you actually need a
> decision. **Do not route tasks back to him** that you could resolve.
>
> **One exception: ask Michael before any GCloud deploy.** Use
> `deploy_tour_modernized.sh`; runbook is [`wdvrdaxn9f`](https://app.clickup.com/t/wdvrdaxn9f).

> ## ✅ STATE AS OF 2026-08-27 — §§0–9 below are history, not a plan
>
> Everything in §§3–7 is **done**. Read them for background only.
>
> ## ✅ DONE — `16140ec` deployed as `v34` on 2026-08-27 and verified
>
> `main` is no longer ahead of production. `tour-modernized` runs **`audioura:v34`**,
> revision **`tour-modernized-00010-84r`**. `v33` is intact and immutable, so
> `./deploy_tour_modernized.sh --rollback` takes seconds.
>
> Verification was run against the **deployed image**, not the source tree:
>
> | check | result |
> |---|---|
> | image contains `fix_reversed_coordinates` | `True` |
> | reversed tour through production `/process` | 9,900 km → **4.2 km**, read from the ZIP's `audio_N.txt` |
> | reversal logged | `[GEOCODE] REVERSED COORDINATES: 3 of 3 stops` |
> | Sydney / Kyoto / Boston / correct-Antananarivo controls | all `action: none` |
> | Sydney end-to-end through production | stayed in Sydney, no `REVERSED` log line |
> | red test — repair stubbed out | **9,900.0 km** vs 4.4 km shipped |
> | Brazil / India / Kenya / Turkey controls (country-centroid anchor) | all `action: none` |
>
> Full evidence is on `wdvrdaxqte`, now **complete**, and in `SUBMISSION_BETA_BUGS.md`.
>
> **The verification probes are reusable** and live in the session scratchpad:
> `control_check.py`, `red_test.py`, `city_probe.py`, `bigcountry_controls.py`. Each
> runs against a built image in one command and needs no live service.
>
> ## ▶️ NEXT ACTION — nothing on the services side; it is all waiting on people
>
> Three tasks now sit in 👤 Michael (Beta):
>
> | task | what it needs |
> |---|---|
> | [`wdvrdaxvvv`](https://app.clickup.com/t/wdvrdaxvvv) | a phone. One newly generated tour answers all three open Yury reports. |
> | [`wdvrdaxvvc`](https://app.clickup.com/t/wdvrdaxvvc) | three rulings: Dockerfile repair, the `#0` label, how to handle Yury's silence |
> | [`wdvrdaxvvg`](https://app.clickup.com/t/wdvrdaxvvg) | nothing from Michael — it is Claude work, see below |
>
> ### ⚠️ One thing needs Michael, and it is the only gate left
>
> **The first Kiro dispatch needs his explicit go-ahead.** Forked headless sessions are
> unattended spend, which is on the hard-stop list and in `wdvrdaxqnz`'s own PROCESS.
> Everything else is ready: preflight passes all six checks and
> `.continuous_dev/PAUSE` is in place, so nothing can fire by accident. Delete that
> file to arm dispatch. The Kiro session task is `wdvrdaxqtg`.
>
> Yury's silence is **no longer a blocker** — all three of his tasks were closed on
> 2026-08-28 on Michael's own device verification.
>
> ### What deploying does NOT affect
>
> Tours already on a device keep the coordinates they shipped with. **Only newly
> generated tours change** — so asking Yury to check an existing tour will always look
> like a failure.
>
> ### After a reboot, do these three things
>
> 1. `cd /d "C:\Users\micha\eclipse-workspace\AudioTours\development"`
> 2. `docker-compose -f docker-compose-beta-local.yml up -d` — the local Beta stack,
>    21 services. Needs `OPENAI_API_KEY` in `.env`. Health-check the chain with
>    `curl localhost:5002/health` (orchestrator) and `localhost:5021/health`
>    (tour-modernized). **Never** `docker-compose up -d` without `-f`, and **never**
>    accept the `--remove-orphans` suggestion — it destroys unrelated long-running
>    containers on this machine.
> 3. Read the FIRST ACTION box above and check the two tester tasks.
>
> Nothing is lost by a reboot: all work is pushed to `origin/main` and
> `origin/storied`, and the running containers are recreatable from the compose file.
>
> ### Yury's six reports — the whole picture
>
> | # | report | state |
> |---|---|---|
> | 1 | two audios play at once | **CLOSED** — fixed, deployed, device-verified by Michael 2026-08-28 — `wdvrdaxmq2` |
> | 2 | audio/map numbering | **CLOSED** as `WORKS AS DESIGNED — confusing`. Not a numbering bug — pin 1 hidden under pin 2. Real fix scheduled Storied `wdvrdaxnc5` — `wdvrdaxmq3` |
> | 3 | stop #6 over Central Islands | **CLOSED** — fixed, deployed, device-verified — `wdvrdaxqjn` |
> | 4 | all pins offset | same fix as #3 |
> | 5 | parking / driving directions | feature filed for Storied — `wdvrdaxqjp` |
> | 6 | tour mislabelled "Museum Tour" | cosmetic, already fixed on `storied` — `wdvrdaxmub` |
>
> ### What is deployed
>
> `tour-modernized` runs **`audioura:v34`**, revision **`tour-modernized-00010-84r`**
> (deployed 2026-08-27). Contains the concurrent-audio fix, coordinate validation,
> *and* the reversed lat/lng repair. Roll back with
> `./deploy_tour_modernized.sh --rollback`; `v33` is intact.
> **Deploying is a hard stop — ask Michael first.** Runbook `wdvrdaxn9f`.
>
> **✅ `main` and production are in sync** as of 2026-08-29.
>
> | service | image | revision | carries |
> |---|---|---|---|
> | `tour-modernized` | **`audioura:v37`** | `tour-modernized-00012-7sg` | all geocode work incl. the thread-safe throttle |
> | `tour-generator` | **`audioura:v36`** | `tour-generator-00022-wgn` | failure attribution (was on `v15`, built 2026-06-10) |
>
> Roll back with `./deploy_tour_modernized.sh --rollback` or
> `./deploy_cloudrun_service.sh tour-generator --rollback`. Old tags are immutable.
>
> **The two fixes were in DIFFERENT services** — `geocode_stops.py` runs in
> `tour-modernized`, `generate_tour_text*.py` in `tour-generator`.
> `deploy_tour_modernized.sh` only covers the first; use
> `deploy_cloudrun_service.sh <service>` for anything else. Check which service runs
> the file you changed before assuming one deploy covers it.
>
> ### Git
>
> `main` and `storied` are both pushed and in sync with origin. `storied` was
> forward-merged on 2026-08-20 (`ccafaf5..dba7f5a`); the Mac Mini session was told via
> `wdvrdaxqth`. Two remote branches appeared that nobody here has inspected:
> `beta-staging` and `fix/dockerfile-build-breaks`.
>
> ### Coordinate work — what it does and does not do
>
> `geocode_stops.py` gathers up to three independent estimates per stop (the model's
> own coordinate, `name + city`, and the full address) and only changes a coordinate
> when two agree within 200 m. Measured over 40 stops in 8 cities against Wikidata:
> median error **87 m → 46 m**, worst 1,616 m → 558 m, zero regressions.
> High-confidence stops average 26 m; low-confidence ones 303 m, and **every error
> over 500 m is in the low-confidence group**.
>
> It is a mitigation, not a cure. It cannot resolve names the model invents
> ("Leslie Spit parking" is a description, not a place) and OSM has no car parks
> mapped near Tommy Thompson Park at all. The cure is `wdvrdaxqtf` in Storied.
>
> ### Fixed on 2026-08-23, deployed 2026-08-27 as `v34`
>
> - **`wdvrdaxqte` — latitude/longitude reversed.** Fixed in `16140ec`. Two checks:
>   impossible latitude (>±90), then compare the tour against its own city and reverse
>   if a majority of stops are 10× closer swapped. All 9 Madagascar stops go from
>   ~9,900 km to 2–7 km; Sydney, Kyoto and Boston untouched. Red test passes.
>   The subtle part was **ordering** — it must run before the plausibility anchor is
>   computed, because the anchor is the median of the stops and is itself in the wrong
>   ocean when everything is mirrored.
>
> ### Open, deliberately unfixed
>
> - **Madagascar text-generation failure — now filed as `wdvrdaxvvg`.** Three attempts
>   on 2026-08-23 all returned `"no stops could be generated"`. **Re-tested 2026-08-27
>   and it works** — 5 stops, correctly-ordered coordinates, all within ~4 km of
>   Antananarivo. Verdict `UNPROVEN — not reproducible`, not `NOT REPRODUCIBLE`.
>   **Do not assume thin coverage.** That same error string meant a bad
>   `OPENAI_API_KEY` in Secret Manager on 2026-06-07
>   (`claude_review_secret_fixes_final_2026_06_07.md:13`). `generate_tour_text()`
>   returns `None` from **nine** places and `generate_tour_text_service.py:62`
>   collapses all nine into one message — making the failure legible is the real fix.
> - **`city_from_address()` returns the country for most of the world — `wdvrdaxvvt`.**
>   Wrong on 8 of 12 real address shapes; `_COUNTRIES` is a hardcoded 16-country
>   allowlist and `_clean_component()`'s state-code regex is `[A-Z]{2}`, so `NSW`
>   survives. **Measured impact is close to nil** — Nominatim resolves both query forms
>   identically, and country-centroid anchors produced no false positives in Brazil,
>   India, Kenya or Turkey. The docstring's 12.75 km claim **does not reproduce**; do
>   not repeat it as fact. Low priority, let it ride with the next deploy.
> - **`generate_tour_text.py:10` imports `enhanced_tour_templates_fixed`**, which is
>   untracked. `tour-generator` will not start from a clean checkout. Flagged, not fixed.
> - **Kiro continuous development is READY on this machine** (2026-08-28) — only a first
>   supervised dispatch is outstanding, and that needs Michael's go-ahead because forked
>   sessions are unattended spend. Session planned — `wdvrdaxqtg`.
>   Branch `port/kiro-dispatcher-windows` (`e40fa34`, `937cc24`), cut from `storied` and
>   pushed. New `portable_lock.py` gives both machines one locking implementation.
>   `python kiro_dispatcher.py --preflight` **passes all six checks**; it forks nothing
>   and costs nothing, so run it first on any machine.
>   Verified on Windows: the lock holds across 8 processes (red test: 1 of 8 survives
>   without it), the semaphore bound holds, a real `storied` worktree checks out all
>   3,248 files at `C:\adev-wt`, and a detached worker outlives a parent that exits in
>   0.09 s.
>   **Two corrections worth carrying forward** — `wdvrdaxqnz` stated both wrongly and its
>   description has been fixed:
>   1. **There is no `KIRO_API_KEY` and no "Kiro portal".** `kiro-cli` authenticates with
>      a stored **login session** (`kiro-cli login --license pro` — Michael's account is
>      Pro / IAM Identity Center; `--license free` is Builder ID). That is why detached
>      headless workers work at all: they inherit the machine's session. A guard built on
>      the API-key claim would have refused to start on a correctly logged-in machine.
>   2. **The installer misreports its path.** It prints `C:\Program Files\Kiro-Cli\`,
>      which does not exist; the binary is at `%LOCALAPPDATA%\Kiro-Cli\kiro-cli.exe`.
>      Don't reinstall thinking it failed.
>   **Not verified on macOS** — the POSIX path is unchanged by construction, but one
>   `git worktree add` on the Mac Mini would settle `core.longpaths`.
>   ⚠️ **No `.continuous_dev/PAUSE` file exists, so dispatch is armed:** any
>   `new_kiro_session_is_required_*.md` at the repo root forks a real session.
> - ~~**Unruled by Michael:** whether the current-location dot should be labelled `#0`.~~
>   **Ruled 2026-08-28 (`wdvrdaxvvc`): declined, keep as is.** The unnumbered dot is
>   intentional — numbering it would invite reading it as a stop on the tour. Settled;
>   do not reopen.
>
> ### Hard-won gotchas — all cost real time
>
> - **Verify by effect, never by exit code.** `docker-compose build` was observed
>   exiting 0 while actually failing.
> - **Grep for imports before deleting any untracked file.** Deleting
>   `enhanced_tour_templates_fixed.py` crash-looped `tour-generator`.
> - **Do not trust a same-named match.** A geocoder never says "I don't know" — it
>   returns its best guess. Wrong answers found this week: a town in Alberta, a rock
>   formation in Colorado, a cycle bridge 12.7 km from the Sydney Opera House.
> - **Git worktrees hit Windows MAX_PATH.** Use a short root (`C:\stwt`) and
>   `git -c core.longpaths=true`.
> - **Postcodes break geocoding.** `"Bennelong Point, Sydney"` resolves; add
>   `NSW 2000, Australia` and it fails by 12.75 km.
> - **Look up ground truth, never recall it.** Two of my confident "correct
>   coordinates" were wrong from memory and produced misleading measurements.

**You are the `Beta_Bugs` session.** Begin every reply with
`[Beta_Bugs]@<MM/DD/YYYY|HH:MM>`. Run `date` if unsure of the time. Keep doing it —
it is easy to use the prefix once and then let it lapse.

Confirmed by Michael 2026-08-18, resolving a conflict: `YURI_BUGS_START_HERE.md`
used to say `Beta_Mobile`, which was wrong on both counts — this is the name, and
the work turned out to be services rather than mobile.

---

## 📋 "READ YOUR QUEUE" — Michael's trigger phrase

When Michael says **"read your queue"**, work autonomously. Do not ask permission
for each step; report what you are doing as you go so he can interrupt.

**The queue, in this order:**

1. Tasks awaiting a tester reply — currently
   [`wdvrdaxmq2`](https://app.clickup.com/t/wdvrdaxmq2) and
   [`wdvrdaxmq3`](https://app.clickup.com/t/wdvrdaxmq3). Read the comments first.
2. 🔵 **Claude — Review (Beta)** — list `1000410000000728`
3. 🟦 **Services — Kiro (Beta)** — list `1000410000000729` — only tasks whose
   description opens `**Agent:** Claude`
4. Any other task whose description opens with `**Agent:** Claude`

Within each, highest priority first, then oldest. Skip anything already `complete`.

> ### ⛔ The Storied Claude — Review list is NOT your queue
>
> List `1000410000000732` belongs to **`Storied_Tours`** on the Mac Mini. Checked on
> 2026-08-18: everything in it is tour-narration quality — `generate_tour_text.py`, the
> story pipeline, POI text rules — which is precisely the scope §0 tells you to stay out
> of. Working it would duplicate or collide with the Mac Mini's session.
>
> If something there genuinely needs Beta-side work, hand it over via a task rather than
> doing it here.

**Work it: investigate, fix, commit, merge to `main`, close tasks, write docs, run
the local Docker stack.** Report outcomes plainly, including failures.

### 🛑 Stop and ask Michael anyway, even in queue mode

- **Any GCloud deploy.** Use `deploy_tour_modernized.sh`; runbook
  [`wdvrdaxn9f`](https://app.clickup.com/t/wdvrdaxn9f).
- **Pushing `origin/storied`** — the branch model makes that his gate.
- **Anything irreversible:** force-push, history rewrite, deleting a pushed branch,
  `DELETE` on the production database.
- **A mobile release** — a version bump and store upload puts a build in testers'
  hands.
- **Unattended cloud spend**, such as scheduled agents.

Agreed with Michael 2026-08-18. Everything else: decide, do it, and say what you did.

You are **not** the Storied session. A separate Claude runs on the Mac Mini on branch
`storied` and owns tour generation and the story pipeline. You will not see its files
and must not pull them in. If you find yourself reading `story_*.py`, `DECISIONS.md` or
`STORIED_COMMUNICATION_*.MD`, you are on the wrong branch — stop.

---

## 0. Where you are

Michael's Windows checkout — confirmed by him on 2026-08-17:

```bat
cd /d "C:\Users\micha\eclipse-workspace\AudioTours\development"
```

`...\AudioTours\development` **is the git clone root** — there is no `development/`
folder inside the repository (verified against `origin/main`). So after that `cd` you
are at the top of the repo, and `audio_tour_app/` sits directly beneath you. Use
`cd /d` so the drive and directory change together.

Then confirm you are in the right repository and on the right branch:

```bat
git remote -v
git branch --show-current
git status
```

Expected: remote `michaelglik-audiotoursai/Audioura`, branch
**`fix/yuri-audio-and-map`**. If not:

```bat
git fetch origin
git checkout fix/yuri-audio-and-map
git pull
```

### Downgrade the local services from Storied to Beta

The Windows laptop has Docker running **Storied** images. This branch is cut from
`main`, so checking it out and rebuilding *is* the downgrade — there is no separate
downgrade procedure.

```bat
git checkout fix/yuri-audio-and-map
docker-compose -f docker-compose-master.yml down
docker-compose -f docker-compose-master.yml build tour-generator
docker-compose -f docker-compose-master.yml up -d
docker ps
curl http://localhost:5000/health
```

Confirm you are on Beta code before testing anything:

```bat
git log --oneline -1
git log --oneline origin/main..HEAD
```

The second command should list only this branch's own commits. If it lists hundreds,
you are on `storied` or on the abandoned `beta/yuri-bugs` — stop and re-checkout.

---

## 1. THE BRANCH RULE — the one thing that must not go wrong

```
main  ──●──────────────  "Beta" IS main. This is what ships to Play + TestFlight.
         \
          ●  fix/yuri-audio-and-map   <- YOU ARE HERE. Only the bug fixes.
         /
storied ●──────────────  Next release. 1865 commits ahead of main.
```

**There is no branch called "Beta". `main` is Beta.**

- **Never** `git merge storied`, `git rebase storied`, or cherry-pick from `storied`.
  It carries the whole story-pipeline rewrite; merging it into `main` would ship all of
  it to Beta testers. `TRACK_B_STORIED_VS_BETA.md`: *"the point of Beta is that it does
  not move while Storied churns."*
- **Ignore `beta/yuri-bugs`.** It was cut from `storied` by mistake on 2026-08-16 and
  carries 1861 commits of Storied work. Do not branch from it or merge it.
- This branch is cut from `main`, so the same fix merges into **both** tracks. That is
  the entire reason it exists.

---

## 2. What Yury reported

Yury Makedonov is a tester. He sent these as **ClickUp DMs**, channel `2ky4d0u8-919`,
on 2026-08-15 — not as tasks, which is why no list contains them. He also said the
first tour generated fine and the content seemed relevant.

**His words, verbatim:**

> Michael, 1st tour was generated OK. Content seems relevant.
> My first comment / bug report:
> * when I want to skip some stops and click on the audio I am interested to listen, I
>   hear two concurrent audios
> * I expect that previous audio should be stopped/paused when I click on the next one

> Comment #2:
> * "Audio 1" corresponds to point #2 on a map.
> * I was confused by such numbering approach
> * I expect the same numbers for Audio and point on a map
> * I expect my current location on a map has a number e.g. #0.
> * Current location is shown on a map but has no number whatsoever.

The app is Flutter: **`audio_tour_app/`**, code in `audio_tour_app/lib/`.

---

## 3. STEP ONE — REPRODUCE BEFORE YOU BELIEVE. Yury can be wrong.

**Do not open a task or write a line of code until you have reproduced each report
yourself.** A tester describes what they saw, which is not always what happened.

For each report, produce one of three verdicts and say which:

| verdict | meaning |
|---|---|
| `CONFIRMED` | you reproduced it; describe the exact steps |
| `NOT REPRODUCIBLE` | you followed his steps and it behaved correctly; say what you saw instead |
| `WORKS AS DESIGNED` | it happens, but it is intended; then it is a UX question for Michael, not a bug |

Bug 2 has a part that is **explicitly not a bug**: *"I expect my current location on a
map has a number e.g. #0"* is Yury's **suggestion**. Michael has not ruled on it. Treat
the audio/map off-by-one as a possible defect and the `#0` label as a separate question
to raise, never as an assumption.

Note the two halves of bug 2 may share one cause: if the map counts "your location" as
pin #1 while the audio list starts at the first real stop, that alone produces both the
off-by-one and the unnumbered-location complaint. Find the cause before proposing a fix.

**Live-artifact rule:** no verdict without a real run — emulator, simulator or device.
"Unproven, could not reproduce on available hardware" is an acceptable report. A guess
stated as a finding is not.

---

## 4. STEP TWO — create the ClickUp tasks

**THE TWO TASKS ALREADY EXIST — do not create duplicates.** Created 2026-08-17 in
🟩 Mobile — Kiro (Beta):

| task | id | url |
|---|---|---|
| BETA-1 — two audios play concurrently | `wdvrdaxmq2` | https://app.clickup.com/t/wdvrdaxmq2 |
| BETA-2 — audio/map numbering off by one | `wdvrdaxmq3` | https://app.clickup.com/t/wdvrdaxmq3 |

Both already carry the verify-first step, acceptance criteria, test plan and a
`## PROCESS` section. **Read them, work them, comment your verdict on them.** Create a
new task only for something neither covers.

If a report turns out `NOT REPRODUCIBLE`, comment that verdict on its task with your
evidence and move it to 🔵 Claude — Review — do not silently close it.

**Use the BETA space, not Storied.** These IDs were read from the live workspace on
2026-08-16 — note they differ from the ones in the Mac Mini's `CLAUDE.md`, which are
the Storied space:

| list | ID |
|---|---|
| 🟩 Mobile — Kiro (Beta) | `1000410000000730` |
| 🟦 Services — Kiro (Beta) | `1000410000000729` |
| 🔵 Claude — Review (Beta) | `1000410000000728` |
| 👤 Michael (Beta) | `1000410000000731` |

These are mobile bugs, so they go to **`1000410000000730`**.

Each task description must start with `**Agent:** Mobile Kiro` and state:

- the reproduction steps YOU verified (not Yury's paraphrase)
- the expected vs actual behaviour
- the branch: `fix/yuri-audio-and-map`
- acceptance criteria, testable
- the test plan
- a `## PROCESS` section — **a task file without one produces `exit=0` and zero
  commits**, which has happened four times on this project

Link Yury as reporter (`101707192`, Yury Makedonov) in the description text.

---

## 5. STEP THREE — dispatch to Kiro

**The continuous-development machinery is NOT on this branch.** `kiro_dispatcher.py`,
`restart.sh` and `.continuous_dev/` live only on `storied`. That is deliberate: they are
Storied tooling and committing them here would carry them into `main` on merge.

**To use the dispatcher without contaminating Beta**, fetch it into your working
directory *without committing it*:

```bat
git fetch origin storied
git show origin/storied:kiro_dispatcher.py > kiro_dispatcher.py
echo kiro_dispatcher.py >> .git\info\exclude
```

`.git\info\exclude` is a local ignore file — it is not tracked, so nothing about this
reaches `main`. **Never `git add kiro_dispatcher.py`.**

Then the model, as it runs on the Mac Mini:

1. Write the work as `new_kiro_session_is_required_BETA-1.md` (and `-2`) at the repo
   root — one file per task, each ending in a `## PROCESS` section.
2. The dispatcher watches for unclaimed files and forks a detached headless
   `kiro-cli chat --trust-all-tools --no-interactive` per file, logging to
   `kiro_sessions_ran.md`.
3. You run the review loop: read the diff, run the tests, verify on a device.

**If `kiro-cli` is not installed on this machine, do the work yourself.** Kiro is a
convenience, not a requirement. Say plainly which you did.

**`.continuous_dev/PAUSE`** — create this file to stop dispatch; delete to resume.
Create it before you walk away, so nothing spends money unattended.

---

## 6. STEP FOUR — review. Never trust the report.

`exit=0` from Kiro means nothing. Verify by effect:

```bat
git rev-list --count origin/fix/yuri-audio-and-map..HEAD
```

must be ≥ 1, the submission doc must exist, and **the behaviour must actually have
changed on a device**.

- **Break the fix and confirm a test goes red.** A test that cannot fail is not
  evidence.
- **"Regression" is a claim about two trees.** If a test fails, check it against a
  clean checkout of `main` before calling it a regression.
- Read the code. Do not pattern-match a grep.

---

## 7. STEP FIVE — merge and deploy

Per `BRANCH_MODEL.md`, which is on this branch — read it.

```bat
git checkout main
git merge --no-ff fix/yuri-audio-and-map
:: bump audio_tour_app/pubspec.yaml  2.1.1+18  ->  2.1.1+19   (see note below)
:: test
git tag -a beta-2.1.1+19 -m "Yuri: concurrent audio + map numbering"
git push origin main --follow-tags
```

Then forward-merge so Storied stays current:

```bat
git checkout storied
git merge main
```

**Do not `git push origin storied`.** It has ~51 unpushed commits behind a field-test
gate that is Michael's to lift.

### The version number — confirmed, not a guess

`origin/main` currently reads `version: 2.1.1+18`, and the only Beta tag is
`beta-2.1.1+18`. So the next Beta build is **`2.1.1+19`**.

Only the build number moves. That follows `BRANCH_MODEL.md`'s own worked example, and
it is what Google Play requires — the **versionCode must increase** for a new upload;
the version *name* may stay. `2.1.2+19` would also be defensible for a user-visible
fix, but the documented convention wins unless Michael says otherwise.

For reference, `storied` is on `2.2.1+1` — a different line entirely. Never copy a
version between the two.

**Never force-push `main`. Never move an existing `beta-*` tag.** The current frozen
Beta is `beta-2.1.1+18` at commit `700d579`.

### Rebuilding services

Each machine builds its **own** images — the Mac Mini is arm64, this machine is amd64.
Never copy images between them. GitHub is the only sync channel.

```bat
git pull
docker-compose -f docker-compose-master.yml build tour-generator
docker-compose -f docker-compose-master.yml up -d
docker ps
```

---

## 8. Ground rules

- **RULE ZERO — do not stop and ask.** Ask only before something irreversible: `DELETE`
  on the live database, `git push --force`, history rewrite, deleting a pushed branch,
  or anything outward-facing. Everything else: decide, do it, and record why.
- **The live database is production data.** Never `DELETE FROM audio_tours`. To hide a
  row, NULL its `lat`/`lng` and back up the values first. Report row counts before and
  after any table you write to.
- **Do not create** `_backup`, `_fixed` or `.bak` files. Use git.
- **Ask Michael, do not assume**, about: the `#0` label for current location; anything
  that changes what a Beta tester sees beyond the two fixes.

## 9. When you finish

Write `SUBMISSION_BETA_BUGS.md` on this branch: per report, the verdict
(CONFIRMED / NOT REPRODUCIBLE / WORKS AS DESIGNED), what changed, how you proved it,
and before/after from a real run. Push the branch. **Do not do the two merges in §7
without telling Michael** — those ship to testers.
