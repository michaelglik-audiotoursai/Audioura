# Git Branch Strategy — Audioura

**Created:** 2026-05-28, at session close (post-A#74 cleanup, post-A#75 v6 migration).
**Owner:** Sir Michael. Maintained by Claude IO.

This document is the authoritative description of the Audioura git layout, current branches, and the recommended workflow for the upcoming services-migration phase.

---

## Current state (verified 2026-05-28)

**Repository:** `https://github.com/michaelglik-audiotoursai/Audioura.git` (private).

**Local clones:**
- **Windows:** `C:\Users\micha\eclipse-workspace\AudioTours\development\` — Sir Michael's primary working tree. Shared with Mobile Q, Services Q, Advisor Q, iOS Q.
- **Mac Mini:** `~/Development/Audioura-build/` — fresh clone, used only for iOS builds via Mac Mini Kiro CLI.
- **Ubuntu VM:** Mobile Q's Android build environment (path TBD per Mobile Q).

**Branches on remote (`origin`):**

| Branch | HEAD | Role | Status |
|---|---|---|---|
| `Newsletters` | `2001bee` (2026-05-28) | Active development branch since November 2025 | **Current default.** 194 commits ahead of main. All A#56–A#75 work shipped here. |
| `main` | `da7c0cc v1.2.7+5 - Audioura rebrand` | Historical stable | 194 commits behind Newsletters. Hasn't moved since early-stage rebrand work. |
| `ios-dev` | `7f7b63a v1.2.9.49` | Stale — last touched April 2026 | Predates A#56 / map feature. Safe to delete. |

---

## Recommended action: consolidate to main, branch for next phase

Sir Michael asked: "can we merge Newsletters to main and then open the new branch?"

**Yes — cleanly. Here's why and how.**

### Why it works cleanly

I verified:

```
$ git merge-base --is-ancestor main Newsletters
  YES - Newsletters can fast-forward main
$ git log Newsletters..main
  (empty — main has zero commits Newsletters doesn't)
$ git rev-list --count main..Newsletters
  194
```

`main` is **purely behind** Newsletters. There's no divergence. Merging `Newsletters → main` is a **fast-forward** — no merge commit, no conflict, no history rewriting. After the merge, `main` HEAD = `Newsletters` HEAD = `2001bee`.

### The operations, in order

```cmd
:: All commands on Windows, in C:\Users\micha\eclipse-workspace\AudioTours\development

:: --- Step 1: Make sure local Newsletters is current with remote ---
git checkout Newsletters
git pull origin Newsletters
git status -uno
:: Expected: "Your branch is up to date with 'origin/Newsletters'."

:: --- Step 2: Update local main to current remote main (so the fast-forward path is correct) ---
git checkout main
git pull origin main
:: Local main is now at da7c0cc.

:: --- Step 3: Fast-forward main to Newsletters ---
git merge --ff-only Newsletters
:: This is the merge. The "--ff-only" flag refuses any non-fast-forward,
:: so if anything is unexpectedly different, the command stops without making a mess.
:: Expected: "Fast-forward" and "Newsletters -> main" advance.

:: --- Step 4: Tag this state as a release marker ---
git tag -a v1.2.9+65 -m "Mobile-app stable state at A#75 close: news article healing + brick-red icon + InAppWebView v6 migration"

:: --- Step 5: Push main and the tag to origin ---
git push origin main
git push origin v1.2.9+65

:: --- Step 6: Create the new services-migration branch from main ---
git checkout -b services-migration main
git push -u origin services-migration

:: --- Step 7: (Optional) Delete the stale ios-dev branch ---
:: Only do this when you're sure ios-dev has nothing you care about.
git push origin --delete ios-dev
git branch -D ios-dev

:: --- Step 8: (Optional, later) Decide what to do with Newsletters ---
:: Two reasonable options:
::   (a) Keep Newsletters as a parallel branch for any continued mobile-app work.
::       Then services-migration is for backend work only. They can merge into main
::       independently as each phase completes.
::   (b) Delete Newsletters after the new branch is established.
::       New mobile-app work goes onto feature branches off main.
:: I recommend (a) for now — keep Newsletters until services-migration's M05 lands.
:: It costs nothing to keep, and Mac Mini Kiro CLI already knows it.
```

### After all that, the branch picture is

| Branch | HEAD | Role |
|---|---|---|
| `main` | `2001bee` (formerly Newsletters HEAD) | Stable, fast-forwarded from Newsletters |
| `Newsletters` | `2001bee` (same as main for now) | Active mobile-app work (small/hotfix changes) |
| `services-migration` | `2001bee` (same starting point) | All M01-M05 migration work happens here |
| Tag `v1.2.9+65` | `2001bee` | Permanent marker of "mobile-app stable" |

---

## Workflow going forward

### For services-migration work

```cmd
git checkout services-migration
git pull origin services-migration
# ... do work, commit, push ...
git push origin services-migration
```

Services Q's M01-M05 assignments commit to this branch. When M05 (production cutover) is complete and verified for ~1 week:

```cmd
git checkout main
git merge --ff-only services-migration   # or --no-ff if you want a merge commit
git tag -a v2.0.0 -m "GCP production cutover complete - api.audioura.io live"
git push origin main v2.0.0
```

### For mobile-app work (smaller items, A#76+)

Continue on `Newsletters` as before. When ready to consolidate:

```cmd
git checkout main
git merge --ff-only Newsletters
git tag -a v1.2.9+NN -m "..."
git push origin main v1.2.9+NN
```

### Mac Mini Kiro CLI's view

Mac Mini's `~/Development/Audioura-build/` is on Newsletters (per its remind doc). After your Step 5 push of `main`:

```bash
cd ~/Development/Audioura-build
git fetch origin
git checkout Newsletters
git pull origin Newsletters
# Newsletters head matches main now; nothing visibly changes
```

Mac Mini doesn't need to switch branches unless you decide to retire Newsletters (option (b) above). For the services-migration phase, Mac Mini Kiro CLI stays on Newsletters (or whatever branch you keep as the mobile-app track).

---

## Branch naming conventions (recommended going forward)

- **`main`** — stable, releasable. Tagged with `v<X.Y.Z+B>` for each release.
- **`<topic>`** — work-in-progress. Names: `services-migration`, `app-store-prep`, `newsletter-feature-X`. Merged to main when done. Deleted after merge.
- **No long-lived development branches** beyond the current `Newsletters` while we phase out that pattern.

After services-migration lands and v2.0.0 ships, plan to retire `Newsletters` entirely and use main + topic-branch flow exclusively.

---

## What this doc is NOT

- **Not a `git_source_control_for_q.md` rewrite.** The original `git_source_control_for_q.md` (which described the Windows + Mac Mini + USB sneakernet structure) was lost in A#74. If you want it back, that's a follow-up — it was Q-facing operational detail. This doc covers the strategic branch decisions you asked about.
- **Not authoritative on the Mac Mini's git config or auth.** Those live in Mac Mini Kiro CLI's `remind_macmini.md`.

---

## Where this doc lives

`C:\Users\micha\eclipse-workspace\AudioTours\development\git_branch_strategy.md`. Git-tracked. Sir Michael's reference for branch decisions.
