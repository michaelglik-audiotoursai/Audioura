# Beta-Bugs_Fixing — Windows startup

Michael starts Claude and says **"read Beta-Bugs_Fixing.md"**. This file is the whole
briefing. Work top to bottom.

**You are the `Beta_Bugs` session.** Begin every reply with
`[Beta_Bugs]@<MM/DD/YYYY|HH:MM>`. Run `date` if unsure of the time.

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

Only for reports you marked `CONFIRMED` or `WORKS AS DESIGNED`. A `NOT REPRODUCIBLE`
report gets a comment back to Michael, not a task.

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
:: bump the version in audio_tour_app/pubspec.yaml, e.g. 2.1.1+19
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
