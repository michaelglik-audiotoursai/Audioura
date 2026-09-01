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
| 3. Routing / URL | ✅ **DONE** — `storied-api.audioura.com` live, TLS correct both hops |
| 4. Mobile selector | Mobile Kiro — **unblocked**, building now |
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

### URL / TLS — DONE 2026-09-01, do not redo

**`https://storied-api.audioura.com`** is live and verified end to end.

```
Cloudflare (proxied) -> GCP LB 34.36.147.30 -> api-gateway-storied-backend
                                            -> api-gateway-storied -> tour-orchestrator-storied
```

Beta is unchanged: `api.audioura.com` still falls through to the default backend.

Built: NEG `api-gateway-storied-neg`, backend `api-gateway-storied-backend` (**scheme
`EXTERNAL`** — the classic LB rejects `EXTERNAL_MANAGED`), and a host rule on
`audioura-url-map`. Cloudflare `A` record `storied-api` -> `34.36.147.30`, proxied.

**TLS was rebuilt and this matters.** The Google managed cert `audioura-cert` was
*expiring 2026-09-04 and could not renew* — `FAILED_NOT_VISIBLE`, because the name
resolves to Cloudflare rather than the LB, so Google could not validate it. Replaced with
a **Cloudflare Origin CA certificate valid to 2041**, covering `*.audioura.com`, attached
to `audioura-https-proxy`. Cloudflare is on **Full (strict)** with Always Use HTTPS.

`openssl` reports `Verify return code: 21` against the origin — **expected and correct**.
Origin CA certs are trusted only by Cloudflare, which is what makes them immune to the
renewal problem.

**Origin port 80 is closed** (`audioura-http-rule` deleted 2026-09-01). Safe because
`endpoints.dart:56` hardcodes `https://api.audioura.com`; the only `http://` in the app is
local mode pointing at a LAN IP. Cert and key live OUTSIDE the repo at
`AudioTours\cloudflare_v1.pem` and `AudioTours\claudflare_v1.key` (the typo is only on the
key) — **the private key cannot be re-downloaded from Cloudflare**.

---

## 🔥 Picked up mid-flight — read before doing anything else (2026-09-01 17:10)

1. **Docker Desktop is RUNNING again** (started 2026-09-01 16:55). 22 containers up from
   the previous session's images. `tour-editing-1` sits `Exited (255)` — it is the orphan
   the briefing warns about, and it was already failing; **do not "fix" it with
   `--remove-orphans`**, that destroys it.

2. **`/tours-near` returns `track` — VERIFIED against a running service, 2026-09-01.**
   Commit `a10b457`, on local `storied` (unpushed) and on pushed `feat/track-in-api`.
   Evidence and the full test table are in ClickUp `wdvrdaxywb`. Three results: default
   reads `beta`; a row set to `storied` reads `storied` (**the red test** — without it a
   hardcoded `'beta'` passes everything else); `NULL` reads `beta` via COALESCE. Local dev
   Postgres only, `audio_tours` 291 rows before and after, production only ever read.

   **Which file is live is now proved, not assumed.** The live response carries
   `is_custom`, which only `map_delivery_service.py` emits — `app.py` emits neither
   `is_custom` nor `language`, `map_delivery/app.py` emits `language`/`original_tour_id`
   and no `is_custom`. So **production runs `map_delivery_service.py`**, which is the file
   that was changed. (The ClickUp task description points at `app.py:154` — wrong file.)

   ⚠️ **The local Docker stack CANNOT test this endpoint.**
   `docker-compose-beta-local.yml` builds `map-delivery` with `build: ./map_delivery`, so
   the container runs `map_delivery/app.py` — a different, older implementation of the
   same route. A green local stack proves nothing here. The verification above was done by
   `docker cp`-ing `map_delivery_service.py` into `development-map-delivery-1` and running
   it on port 5099 (needs `pip install requests`; that image lacks it).

   The other trap still stands: the unpack line `tour_id, ... requests = tour` appears
   **twice** (`:159`, `:395`, different endpoints); only `:159` follows the modified query.

   **Local dev Postgres was behind production schema** — it had neither `track` nor
   `is_test`. Both added additively (`ADD COLUMN IF NOT EXISTS`). Expect the same gap
   again on any fresh local DB.

   Still owed on `wdvrdaxywb`: `/status/<job_id>` (AC2) and the download/manifest payload,
   neither started; AC3 (a real Storied tour reading `'storied'`) needs the Phase 2 deploy.

3. **`wdvrdaxxmb` is unblocked except the version suffix.** Mobile Kiro can build the
   selector, the URL fix, `track` storage and the labels now. Still owed by services:
   `/status`, the manifest payload, and a per-tour `build_number`.

### Version scheme — SETTLED 2026-09-01: release tags, not commit counts

```
v<line>t<seq>        e.g.  v2t357        display: "Stable v2t357"
```

**`<line>` is a permanent release-line identity** — `beta=1`, `storied=2`,
`subscribed=3`. **Not** the Stable/Preview slot. A promoted build keeps its number, so
`v2t357` reads the same whether it is Preview or Stable — that is how you see where a
build came from. It also makes ordering arithmetic: `v3t…` Preview is always above any
`v2t…` Stable.

**Commit counts were tried and rejected.** They could order builds but not reconstitute
one, and they lied: `main` (75) contained the reversed-coordinate fix while `storied`
(2126) did not, because `LOCAL-470` **ported** the fix instead of merging it. A tag pins
an exact commit, so `git checkout v2t357` gives precisely what shipped.

**Generated by the deploy scripts, never by hand** — `release_tag.sh`, wired into
`deploy_cloudrun_service.sh` and `deploy_tour_modernized.sh` (commit `bc1bc49`, branch
`feat/release-tagging`). They compute, create and **push** the tag after a verified
deploy, and refuse if image content (`*.py`, `Dockerfile*`, `requirements*.txt`) is
uncommitted. The guard is narrow on purpose — this tree is shared with Kiro and always
has dirty docs.

✅ **VERIFIED 2026-09-01** that the `ARG` lands in a built image.
`docker build -f Dockerfile.cloudrun --build-arg RELEASE_TAG=v2t999 --build-arg
GIT_SHA=deadbeef` then `printenv` inside it returns `v2t999` / `deadbeef`. **Red test:**
the same build with no `--build-arg` returns `unset` / `unset`, the declared defaults —
so the value genuinely comes from the build argument and is not baked in. Both
`deploy_cloudrun_service.sh:155` and `deploy_tour_modernized.sh:148` pass both args, and
both scripts use `Dockerfile.cloudrun`, the only Dockerfile carrying the `ARG` lines.
`Dockerfile.modernized` has none — do not deploy an image through it expecting a version.
(`Dockerfile.cloudrun` had **no `ARG`** at all until commit `bc1bc49`; without it
`--build-arg` is silently discarded and the whole scheme is a no-op that looks fine.)

The per-tour field is **`release_tag`** (string), optional, `null` for older tours.

### Outstanding decision for Michael

Ship `2.2.1+2` (compliance rebuild) **first**, then `2.3.1+1` with the selector — or fold
them into one upload? Recommendation: ship compliance first; Google's extension buys a
month but the rebuild is already built and only needs a device test, and the task itself
says not to couple them. His call.

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
