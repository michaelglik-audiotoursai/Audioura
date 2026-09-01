# GCLOUD_STORIED — Windows laptop start-here

Michael starts Claude on the Windows laptop and says **"read GCLOUD_STORIED_START_HERE.md"**.
This file is the whole briefing. Work top to bottom.

**You are the `GCloud_Storied` session.** Begin every reply with
`[GCloud_Storied]@<MM/DD/YYYY|HH:MM>`. Run `date` for the real time. Keep doing it — it
has lapsed twice and Michael has had to ask twice.

> Renamed from `Beta_Bugs` on 2026-08-31 when the work moved from fixing Beta to
> deploying Storied. **Older ClickUp comments and commits signed `Beta_Bugs` are this
> same session**, not a different agent.

---

## ⛔ Read this before touching anything

| | |
|---|---|
| **Working tree branch** | **`storied`** — Michael's decision 2026-08-31. Do not switch it without asking. |
| **`Beta-Bugs_Fixing.md` on this branch is STALE** | It is the 2026-08-17 version. The current one is on `main`. **Do not follow it here.** |
| **The tree is SHARED with Kiro** | Run `git status` before any git operation. **Never `git add -A`, `git stash`, `git checkout <branch>`, or `git reset`** — each destroys another agent's in-flight work. |

### 🚨 The dispatcher will sweep up the Mac Mini's tasks on this branch

`kiro_dispatcher.py` finds work by globbing `new_kiro_session_is_required_*.md` in the
working tree. On `main` none are tracked, so that was safe. **On `storied` the Mac Mini's
task files ARE tracked**, so a plain dispatch picks up its queue.

This happened on 2026-08-31: a dispatch intended for 2 jobs started **5**, three of them
`LOCAL-382/383/424` belonging to `Storied_Tours`. They were killed within a minute and
produced nothing, and `FAILED` records were written so they cannot re-dispatch.

**Before dispatching, check what will be picked up:**

```bash
cd C:/adev-wt/kirotool
AUDIOURA_WATCH_DIR="C:/Users/micha/eclipse-workspace/AudioTours/development" \
  python -c "import sys;sys.path.insert(0,'.');import kiro_dispatcher as k;\
print([p.name for p in k.find_task_files() if not k.already_claimed(p.name)])"
```

If anything `LOCAL-*` appears in that list, **stop** — write a terminal record for it
first, or it will run and cost money. This needs a real fix (an allowlist, or the
dispatcher only claiming files it created).

---

## Where things live

| what | where |
|---|---|
| repo | `C:\Users\micha\eclipse-workspace\AudioTours\development` (this IS the clone root) |
| **dispatcher tooling** | **`C:\adev-wt\kirotool`** — its own worktree on `port/kiro-dispatcher-windows` |
| Kiro job worktrees | `C:\adev-wt\<TASK-ID>` |
| Flutter SDK (Windows) | `C:\Users\micha\eclipse-workspace\flutter` — **3.29.3**, not on PATH |
| Kiro CLI | `C:\Users\micha\AppData\Local\Kiro-Cli\kiro-cli.exe` — **2.20.1** |

**The dispatcher lives in its own worktree deliberately.** It is tracked on `storied`, so
a `git checkout` in the main tree overwrites it with the macOS version and destroys any
uncommitted Windows fixes. That happened on 2026-08-31 and cost both encoding fixes.

```bash
cd C:/adev-wt/kirotool
AUDIOURA_WATCH_DIR="C:/Users/micha/eclipse-workspace/AudioTours/development" \
PATH="$PATH:/c/Users/micha/AppData/Local/Kiro-Cli" python kiro_dispatcher.py --preflight
```

`--preflight` forks nothing and costs nothing. Expect all six checks OK.

`.continuous_dev/PAUSE` blocks all dispatch. **Create it before walking away.**

---

## Current state — 2026-09-01

### Production (Beta) — healthy, and it is the CONTROL

| service | image | revision |
|---|---|---|
| `tour-modernized` | `audioura:v37` | `tour-modernized-00012-7sg` |
| `tour-generator` | `audioura:v36` | `tour-generator-00022-wgn` |

**Beta must not drift.** Under `wdvrdaxxm9` it is the control in a Beta-vs-Storied
quality comparison; any change to its behaviour invalidates every comparison a tester
makes. Baseline captured in `BETA_BASELINE_2026_08_31.md` (branch
`services-kiro/beta-baseline-2026-08-31`, commit `9247f10`).

Already deployed and easy to miss: **`tour-orchestrator-storied`** and
**`api-gateway-storied`** exist in Cloud Run already. Phase 2 is partly "update an
existing service", not "create one".

### Local Docker — running Storied

23 containers, built from `storied@edfeaac`. Verified by effect: `TOUR_TRACK` present in
the running orchestrator, which exists only on `storied`.

```bash
docker-compose -f docker-compose-beta-local.yml up -d
```

⚠️ **Never a bare `docker-compose up -d`** (no root `Dockerfile`; it cannot build), and
**never accept `--remove-orphans`** — `tour-editing-1` is an orphan relative to
`beta-local` and would be destroyed.

---

## The live task: `wdvrdaxxm9` — deploy Storied alongside Beta

| phase | state |
|---|---|
| 0. Prep | ✅ done |
| 1. Schema | ✅ **no migration needed** — `track` and `low_confidence_stops` both self-heal via idempotent `information_schema`-guarded `ALTER`s in `store_audio_tour()` |
| 2. Deploy Storied | **staged**, dry-run verified — ⛔ needs Michael |
| 3. Routing / URL | ⛔ needs Michael's decision |
| 4. Mobile selector | Mobile Kiro, blocked on the same URL |
| 5. Verify | baseline ready |

### Findings that changed the plan — do not re-derive

1. **The service reads `TOUR_TRACK`, not `TRACK`** (`tour_orchestrator_service.py:554`).
   `os.getenv('TOUR_TRACK','beta')` **defaults to `'beta'`**, so the plan's `TRACK=storied`
   would have deployed cleanly and recorded **every Storied tour as Beta** — silently
   destroying the comparison. Verify after deploy with
   `SELECT DISTINCT track FROM audio_tours;`
2. **Use a separate image repo `audioura-storied`.** All services share `audioura`
   differing only by `CMD`, which is safe *only* because they run the same branch.
   Building `audioura:vN` from `storied` would let a routine "update tour-generator to
   vN" ship Storied code into Beta.
3. Staged script: `deploy_storied_service.sh` (branch `kiro/storied-4`). `--dry-run`
   verified correct.

### URL scheme — recommended, awaiting Michael

**Subdomain `storied-api.audioura.com`**, not a path prefix: the mobile selector must
change only the host, or path parity breaks.

Routing today is `Cloudflare (proxied) → GCP LB 34.36.147.30 → api-gateway-backend →
api-gateway`. `audioura-url-map` has **no host rules**.

⚠️ **The GCP managed cert has never worked**: `audioura-cert` reads
`api.audioura.com: FAILED_NOT_VISIBLE`, because the name resolves to Cloudflare, not the
LB. Cloudflare terminates TLS. **Do not add the subdomain to that cert** — it would fail
identically. Mirror the existing `api` DNS record instead.

---

## Hard stops — ask Michael even in queue mode

- **Any GCloud deploy.** Runbook `wdvrdaxn9f`.
- **Pushing `origin/storied`.**
- **Anything irreversible:** force-push, history rewrite, deleting a pushed branch,
  `DELETE` on the production DB.
- **A mobile release** — version bump + store upload reaches testers.
- **Unattended cloud spend**, including Kiro dispatches beyond agreed work.

## Testers — check ALL THREE at session start

Michael gets ClickUp's email alerts; this session gets nothing.

| tester | id | DM channel |
|---|---|---|
| Yury Makedonov | `101707192` | `2ky4d0u8-919` — last message 2026-08-16 |
| Gregory Lepsky | `101714111` | `2ky4d0u8-999` — **0 messages ever** |
| igor linkov | `101715779` | none exists |

**Enumerate, do not hardcode:** `clickup_get_workspace_members` → tester ids;
`clickup_get_chat_channels` → DMs created by them. A channel Greg opened went unread for
six days because the check was hardcoded to Yury.

Greg and Igor have never been asked to test anything — drafts ready in `wdvrdaxxrd`.

## Hard-won gotchas

- **Verify by effect, never by exit code.** `docker-compose build` has exited 0 while
  failing; `exit=0` from Kiro means nothing.
- **Check which service runs your file before deploying.** `deploy_tour_modernized.sh`
  covers one service; `geocode_stops.py` runs in `tour-modernized`,
  `generate_tour_text*.py` in `tour-generator`.
- **No untracked `.py` in the build context.** `Dockerfile.cloudrun` does `COPY *.py`, so
  an untracked file becomes production code with no version history. That is how
  `enhanced_tour_templates_fixed.py` drifted for months.
  Check: `git status --porcelain -uall | grep "^??" | grep "\.py$"` must be empty.
- **Windows defaults to cp1252.** Always pass `encoding="utf-8"` to `read_text`,
  `write_text`, `open`, and `subprocess(text=True)`. A subprocess decode error surfaces
  as `stdout=None`, not an exception.
- **Android signing key**: backed up in Secret Manager, restore procedure in
  `ANDROID_SIGNING_KEY_RECOVERY.md` and ClickUp `wdvrdaxy5u`. Play App Signing **is
  enabled**, so a lost upload key is recoverable.
