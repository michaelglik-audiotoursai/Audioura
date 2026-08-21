# Yuri's bugs — start here

> **⚠️ This file is superseded. Read `Beta-Bugs_Fixing.md` instead** — that is the
> live briefing Michael opens sessions with, and it carries the current state.
> Kept for history.

You are the **`Beta_Bugs`** session. Begin every reply with
`[Beta_Bugs]@<MM/DD/YYYY|HH:MM>`.

This file previously said `Beta_Mobile`, which conflicted with `Beta-Bugs_Fixing.md`.
Michael settled it on 2026-08-18: the name is **`Beta_Bugs`**. `Beta_Mobile` was
wrong on both counts — the bug turned out to be in the Python services, not the
Flutter app.

---

## THE BRANCH RULE — read this before you touch anything

You are on **`fix/yuri-audio-and-map`, cut from `main`**, which is the Beta base.

```
main  ──●───────────────────────  Beta on GCloud deploys from here
         \
          ●  fix/yuri-audio-and-map   <- YOU ARE HERE. Only the bug fixes.
         /
storied ●───────────────────────  Storied. 1865 commits ahead of main.
```

**Merge this branch INTO both** when the fixes are proven:

```
main     <- fix/yuri-audio-and-map     Beta gets the fix
storied  <- fix/yuri-audio-and-map     Storied gets the same fix
```

**NEVER merge `storied` into `main`.** `storied` is 1865 commits ahead and carries
the whole story-pipeline rewrite. Beta must not move while Storied churns
(`TRACK_B_STORIED_VS_BETA.md`). That is the entire reason this branch was cut from
`main` and not from `storied`.

**Do not** `git merge storied`, `git rebase storied`, or cherry-pick from it. If a fix
seems to need something from `storied`, stop and ask Michael.

**Ignore `beta/yuri-bugs`.** It was cut from `storied` by mistake on 2026-08-16 and
carries all 1865 Storied commits. It exists only until Michael deletes it. Do not
branch from it, do not merge it.

---

## The two bugs, from Yury Makedonov (tester), 2026-08-15

Reported as ClickUp **DMs**, channel `2ky4d0u8-919` — not tasks, which is why no list
contains them. **Create proper ClickUp tasks for them** so they stop living in a DM.

### BUG 1 — two audios play at once

> when I want to skip some stops and click on the audio I am interested to listen,
> I hear two concurrent audios
>
> I expect that previous audio should be stopped/paused when I click on the next one

Reproduce: start a tour, play a stop, then tap a different stop's audio without
stopping the first. Expected: the first stops. Actual: both play.

Look at the audio player controller — whether tapping a new stop calls `stop()` /
`pause()` on the current player before `play()` on the new one, or whether a second
player instance is created per stop.

### BUG 2 — audio numbering does not match the map

> "Audio 1" corresponds to point #2 on a map.
> I was confused by such numbering approach
> I expect the same numbers for Audio and point on a map
> I expect my current location on a map has a number e.g. #0.
> Current location is shown on a map but has no number whatsoever.

Two parts, probably one cause: if the map counts "your location" as pin #1 while the
audio list starts at the first real stop, that produces both the off-by-one AND the
unnumbered-location complaint.

1. **Fix the off-by-one first** so audio *n* and map pin *n* are the same stop.
2. **The `#0` label for current location is Yuri's SUGGESTION, not a decision.**
   Michael has not ruled on it. Raise it as a question; do not assume.

---

## The app

`audio_tour_app/` — Flutter. Code in `audio_tour_app/lib/`.

**Both tracks run the same mobile app**, which is why one fix serves both. Verify the
files you touch are not among the 27 that `storied` has already changed under
`audio_tour_app/` — if they are, say so in your submission, because the merge into
`storied` will need care.

---

## After the fix — rebuilding services

Each machine builds its **own** Docker images. Never copy images between machines: the
Mac Mini is arm64 (Apple M4) and the Windows box is amd64.

```
git pull
docker-compose -f docker-compose-master.yml build tour-generator
docker-compose -f docker-compose-master.yml up -d
```

GitHub is the only sync channel between the two machines.

---

## Ground rules (from CLAUDE.md)

- **RULE ZERO — do not stop and ask.** Ask only before something irreversible: `DELETE`
  on the live DB, force-push, history rewrite, anything outward-facing. Everything else,
  decide and record why.
- **The live DB is production data.** Never `DELETE FROM audio_tours`. 31 real rows.
- **Do not edit** `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  or anything named `story_*.py` — those belong to the Storied_Tours session.
- **Verify by effect, not by report.** Break the production code and confirm a test goes
  red; a test that cannot fail is not evidence.
- **Live-artifact gate:** no "COMPLETE" without a real run on a device or simulator.
  "Unproven, handing to LEAD" is always acceptable.

## When you finish

Write `SUBMISSION_YURI_BUGS.md` here: what changed, how you proved it, and before/after
from a real device or simulator. Push this branch. **Do not merge it yourself** — the
two merges are Michael's call.
