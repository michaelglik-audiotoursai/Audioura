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

# ✅ CURRENT STATE — 2026-10-14 01:10 EDT. READ THIS FIRST; IT SUPERSEDES EVERY DATED SECTION BELOW.

Every `## STATE …` section further down is September history. Where they disagree with
this block, **this block is right**. Written at Michael's request so a restart can continue.

## What is live on Preview right now

| | |
|---|---|
| image | `audioura-storied:v4`, digest `sha256:317b147f…` is **v3**; v4 was built from `d25454a` |
| commit deployed | `d25454a` (storied), release tag **`v2t2`**, pushed |
| revisions | `tour-generator-storied-00006-ls4`, `tour-modernized-storied-00004-ssx`, `tour-orchestrator-storied-00005-82r` |
| flags | `USER_STOPS_ENABLED=true`, `TOUR_TRACK=storied`, `STORIED_MODE=true`, all 100% traffic, `/health` 200 |

Beta/Stable is the frozen control and was untouched by all of it: `tour-generator-00024-tnp`,
`tour-modernized-00012-7sg`, `tour-orchestrator-00026-55j`, `api-gateway-00022-t88`,
`translation-service-00020-k7z`, `map-delivery-00014-bdp`. (Beta revisions moved between
2026-10-04 and 10-13 by someone other than this session — not by us.)

## ⛔ RULE ONE IS CURRENTLY SUSPENDED, BY MICHAEL, BECAUSE KIRO IS GONE

**`kiro-cli.exe` is not on this machine.** Binary and its PATH entry are both absent from
the whole C: drive; `AppData\Local\Kiro-Cli\` survives with `data.sqlite3`, `node.exe` and
`run-receipts`. Last written during the 2026-10-02 deploy — it ran that job and vanished,
which looks like a failed self-update. The Kiro **IDE** is unaffected.

Reinstall is `irm https://cli.kiro.dev/install.ps1 | iex` (host verified live, HTTP 200),
then `kiro-cli whoami` **before** logging in — credentials may have survived in
`data.sqlite3`.

Until it is back, **Michael has twice told this session to do the work directly**
(2026-10-04 "can you finish installation and deployment", 2026-10-13 "work on
wdvrdayz0w"). So LEAD has written and shipped code. **When Kiro returns, RULE ONE
resumes** — it was suspended by necessity, not repealed. Declare it every time you write
shipping code.

## D591 IS LIFTED — the §BEFORE THIS DEPLOY block below is OBSOLETE on this point

**D593, Michael approved 2026-10-01: user-chosen stops ship to Preview.**
`USER_STOPS_ENABLED=true` on all three Storied services. The September instruction
"Igor's work must NOT be deployed" is **no longer in force**. The kill switch
(`user_stops_flag.py`) still exists and still defaults OFF; Preview turns it on
explicitly. The regex fix `19358ae` shipped long ago. Nothing is gated here any more.

## Michael can finally test — this was the real blocker, for a month

His phone registered as **`USER-1073427300`** (2026-10-01 17:09:05, matching the gateway's
`POST /user` 200 to the second — that is build 27 from TestFlight). It was on plan `free`
= **1 tour/day**, which is why Preview showed no tours for weeks while this session kept
asking him to test. Fixed 2026-10-04 by SQL only, no redeploy: `plan='tester'` (100/day),
`users` row count 24 before and 24 after. Reverse with `plan='free'`.

**Lesson, learned the hard way:** on 10-02 LEAD skipped the paid restaurant verification
on the reasoning that Michael would generate real tours within the hour. He could not —
quota — and nobody checked. **Handing a verification to a human only counts if you then
confirm they ran it.**

## Verified by effect on Preview (not by Kiro's report)

- **LOCAL-557 named restaurants** — tour **430**, "Boston Sail Loft, Boston, MA", 1 stop.
  `Stop 1: Boston Sail Loft`; log line `[LOCAL-557] Restaurant request names ['Boston Sail
  Loft']`; `grep -ic 'union oyster|grill 23'` over the whole text = **0**. Left visible in
  the Boston list deliberately (a correct tour, not a junk artifact); coordinates backed up
  as 42.3661 / −71.0537 if it ever needs hiding.
- **LOCAL-572 Wikidata outage fix** — tour **431**, Palais Lascaris 4 stops: **zero**
  `Tier: unresolvable`. The fix holds.
- **`pycountry`** — proved necessary with a control: `v4: 24.6.1 True True` vs
  `v3: ModuleNotFoundError`. Until 10-04 the LOCAL-564 place gate was **inert in production**.
- **FAILED and still open:** 431 delivered **3 of 4** requested stops.
  `[EXISTENCE-GATE] 4/4 verified` → `[D1v2] DROPPED 'The Adoration of the Magi'` → R4
  replenishment ran and did not restore the count. Filed `wdvrdayrhc`; probably the
  production face of the already-open `LOCAL-19`.

## The API keys, after 2026-10-13 — this is the current truth

Three machines, and **as of now the laptop is on its own keys**:

| where | OpenAI | Gemini |
|---|---|---|
| **GCloud** | `openai-api-key:latest` = v4, len 164, `…Nw8A`, `4398cdb0140a` | `GEMINI_API_KEY` v1, len 53, `…bGMw`, `5dbce1c7de78` |
| **this laptop** | len 164, `…hpIA`, **`b40556d2d1fb`** | len 53, `…HX4Q`, **`874596c92160`** |

- **REVOKABLE, in use nowhere:** the len-156 key `b67926c2c667` (= secret versions v2 and
  v3; v2 is the same key plus a trailing newline, so they are **one** key). It was inline
  on `news-generator` until `wdvrdayz0w`. Michael's to revoke at platform.openai.com.
- **`wdvrdayz0w` is DONE** (LEAD, 10-13): `news-generator-00009-skh` resolves both
  `OPENAI_API_KEY` and `DB_PASSWORD` from Secret Manager. Image, SA, scaling and the Cloud
  SQL annotation unchanged; env count still 6; `/health` 200.
- **12 inline credentials remain** across 6 live Beta services — the serious one is
  `news-processor` `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, which **AWS rotation
  (`wdvrdaxay9`) would miss** exactly as it would have missed `news-generator`. Also R2
  pairs inline on `map-delivery` **and** `translation-service`, `INTERNAL_SERVICE_SECRET`
  on two services, and `DB_PASSWORD` inline on four (all equal to `db-password:latest`).
  Not filed as a ticket yet — Michael's call, six live services.
- **Two standing exposures:** the GitHub repo is **PUBLIC** (no live key is in it; the five
  key-shaped tracked strings are placeholders/fixtures with non-matching fingerprints, and
  `.env` was never tracked), and **`GEMINI_API_KEY` has no IP/referrer/app restriction** —
  anyone holding it can spend from anywhere.

## The 2026-10-11 spend mystery — answered, `wdvrdayyqd`

**GCloud did not spend it, and the ticket's window was off by hours.** Gemini is a GCP API
key, so monitoring can measure it: **all** usage came from one credential (Michael's), 3,364×200
and 316×402. Hourly it peaks at **626 calls in the hour 2026-10-11 04:00 UTC** and stops dead
at **10:00–11:00 UTC = 06:55 EDT — the exact minute the Mac's meter went quiet.** The money
went out *before* the "unexplained" gap, not during it.

GCloud's entire output over those three days: **one** article (`d3e6e469`) and **one** Russian
translation (`c2550fe9`) at 2026-10-12 17:26 UTC. Preview: nothing. No Cloud Scheduler at all
(the API is not enabled). The 402s stop as soon as calls succeed, so no retry loop.
Hypothesis for the Mac to confirm: commit `55edf2c` added an *isolated-container live-run
harness*; generation inside its own container would use the same key and never touch the
host's `paid_api_calls` meter.

## Open queue, in order

1. **Deploy `354da34` to Preview** (`wdvrdayu7q`, LOCAL-593/D612 museum factual-integrity).
   It **supersedes `wdvrdayruf` (`690d6ba`) and `wdvrdayrhj` (`ef8fda6`)** — one deploy
   covers all three; close the other two referencing it. Not started.
2. `wdvrdayrhc` — 4 stops requested, 3 delivered (Mac Mini's).
3. `wdvrdayqp3` — dispatcher allowlist, **3rd occurrence**.
4. `wdvrdayrh7` — `_geo_vocab` docstring states the wrong safe direction.
5. Michael's: revoke `b67926c2c667`; decide on the 12 inline credentials; confirm the Mac
   is not on `…Nw8A` before retiring it.

## Gotchas found the hard way in October — do not re-learn these

- **The dispatcher watches `C:\adev-wt\kirotool\`, NOT the repo**, and appends to
  `C:\adev-wt\kirotool\kiro_sessions_ran.md`, a *different file* from the repo copy. A task
  file left in `development/` queues nothing; the dispatcher then claims the Mac Mini's
  tracked `LOCAL-*` files and prints "Dispatched 3 new task(s)", which reads like success.
  That is how `LOCAL-382/383/424` started here on 10-02 (killed in 40 s, no commits,
  worktrees removed, `FAILED` records written to the kirotool copy).
- **Docker Compose gives the shell environment precedence over `.env`.** A **User-scope
  Windows** `OPENAI_API_KEY` held GCloud's key and silently overrode `.env` through two
  `--force-recreate` runs. Removed 10-13. If a container's key does not match `.env`, check
  `[Environment]::GetEnvironmentVariable('NAME','User')` before anything else.
- **`GEMINI_API_KEY` was in no compose service at all** — the local stack ran without it
  while four modules read it. Fixed in `07aef06` (added beside all 8 `OPENAI_API_KEY` lines
  in `docker-compose-beta-local.yml`).
- **`Dockerfile.cloudrun` never reads `requirements_generator.txt`** — it installs a
  hand-maintained `pip install` list. Pinning a dependency in the requirements file puts
  **nothing** in the Cloud Run image. Already burned twice: `cryptography` (`wdvrday52p`)
  and `pycountry` (`wdvrdayrdp`).
- **`COPY *.py /app/` ships every root `.py`, tracked or not.** Michael's
  `audioura_books.py` (his bookkeeping tool, reads his Chase exports) would have gone into
  the server image. Move stray root `.py` files aside for a build and restore them by hash.
- **Verify a deploy by hashing against the WORKING TREE, not `git show <sha>:<file>`.**
  Windows checks out CRLF and Docker copies the working tree, so every file looks changed
  against the git blob. The sound method: `docker inspect … RepoDigests` must equal the
  Cloud Run digest, then hash `/app` files against the clean build worktree.
- **`--update-secrets` fails on a var that is already a literal** ("already been set with a
  different type"). Use `--remove-env-vars X --update-secrets X=secret:latest` in **one**
  call, so only one revision is created and the key is never missing from a serving one.
- **`gcloud logging read` without a `logName` filter returns AUDIT logs.** Counting those
  nearly produced a false "runaway pipeline" report — the ~40-minute "pings" on the news
  services are `killswitch-sa@` calling `ReplaceService`. For real traffic filter
  `logName="projects/…/logs/run.googleapis.com%2Frequests"`, and `%2Fstdout` / `%2Fstderr`
  for application output.
- **Run `date` immediately before every reply.** This session fabricated four timestamps by
  estimating elapsed time and was off by ~7¾ hours; Michael caught it. Long Docker builds
  and `gcloud logging` calls make elapsed time impossible to guess.

---

## 📌 HISTORICAL (2026-09-24) — read `HANDOFF_20260924_MORNING.md`

> ⚠️ **The D591 instruction in this section is OBSOLETE** — see "D591 IS LIFTED" above.
> Kept because the regex-fix and large-museum notes are still useful.

Written by `Storied_Tours` (Mac Mini) on 2026-09-24 and tracked in git, because
`.continuous_dev/STATUS.md` is gitignored and never reaches this machine.

It carries what changed on `storied` overnight and two things that will bite this
deploy if you do not know them:

- **A catastrophic regex backtrack was hanging every LARGE-MUSEUM generation.** Fixed,
  but if your E2E picks a big venue and reports *"status polling failed"*, that is the
  symptom — the generator is busy, not dead. Pick at least one large museum.
- **⛔ ~~User-chosen stops (Igor's work) must NOT be deployed. `storied` HEAD is
  therefore not deployable as-is.~~ LIFTED by D593, 2026-10-01 — they are live on
  Preview with `USER_STOPS_ENABLED=true`. Ignore the rest of this bullet.** Original
  text kept for the record:** Michael, 2026-09-24, asked directly: *"only on
  local Docker before we approve the results of the Igor's test."* (D591). The
  cloud-path threading of `stops` through `_enqueue_cloud_task` / `/run-job` /
  `run_generation` is real but unverified, and it stays unverified until he approves
  Igor's test — **do not verify it in production.** No TestFlight or Play build
  carrying `1bb087e` either.
  The tag `rc-pre-igor-20260923` does not get you around this: the regex fix
  `19358ae` is *after* the tag. If the regex fix must ship before the gate lifts,
  dispatch Kiro to build an env kill switch first.

Also note the OpenAI balance was exhausted overnight and **Michael topped it up on the
morning of 2026-09-24** — so that is resolved, not an open issue.

---

## 🚫 RULE ONE — NEVER WRITE THE CODE. DISPATCH KIRO AND REVIEW IT.

> ⚠️ **TEMPORARILY SUSPENDED since 2026-10-04 — `kiro-cli.exe` is missing from this
> machine and Michael has twice told this session to do the work itself. See "RULE ONE IS
> CURRENTLY SUSPENDED" at the top. Reinstall Kiro and this rule resumes immediately.**
> The rest of this section is the rule as written, and is what to go back to.

**Michael's ruling, 2026-09-15, after this session broke it.** This sits above
everything else in this file, including RULE ZERO's "keep the queue moving".

> "You should not fix issues, only lead for Kiro to fix and for you to do the code
> review. For the future write into your Reminder file: never do the work, only code
> review."

**What went wrong.** Asked to work the queue, this session investigated, wrote, built
and deployed four production services itself — `map-delivery` v40, `news-orchestrator`
v41, both gateways v35, on top of `newsletter-processor` v39. No Kiro was dispatched.
The last dispatcher entry was two weeks old. The work was verified, but **verified by
its own author**, so it reached live traffic with no second pair of eyes. Michael found
out afterwards and had to ask whether Kiro had been involved at all.

**The division of labour is not a preference, it is the quality control.** LEAD writing
code removes the only independent review in the loop — and LEAD then reviewing its own
work is not a review.

| LEAD (this session) does | LEAD does NOT do |
|---|---|
| decompose the problem, decide the approach | write the implementation |
| write the task file and the acceptance criteria | "just fix" a file because it is quick |
| dispatch Kiro | build the image |
| review the diff adversarially, bounce or approve | deploy it |
| merge after review; report to Michael | verify its own code and call it done |

**"It is only a few lines" is exactly the case this rule exists for** — every one of
the four changes above looked small, and one of them (`COALESCE(track, …)` unguarded)
would have turned the whole tour list into a 500 for both tracks if the column had been
missing. Small changes are the ones that ship unreviewed.

**Investigation is still LEAD's job.** Reading code, querying the DB, curling
production, diffing a deployed image to find the cause — all fine and all expected. The
line is at *changing* a file that ships. Diagnose fully, then hand the fix to Kiro with
everything you learned written down, so Kiro does not re-derive it.

**If Kiro is unavailable or blocked**, that is a thing to report to Michael, not a
licence to implement. Park the task and say so.

**Retro-review is the remedy when the rule has already been broken.** Code that shipped
without review does not become reviewed by being correct — dispatch a review task for
it (pattern: `CODE_REVIEW_GCS-1.md` + `new_kiro_session_is_required_GCS-REVIEW-1.md`,
2026-09-15).

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

## ✅ STATE 2026-09-17 11:25 — both deployed with Michael's approval, both verified by effect

| service | image | revision | verified | rollback |
|---|---|---|---|---|
| `translation-service` | `v35-tr1` | `00019-fw8` | Russian on tour 107 created **427**; `/download-tour/427` 200, 2.6 MB, Russian text, audio, `track=beta` | image `:v35` |
| `tour-editing` | `v4` | `00004-zp7` | realistic mixed-script ru edit: v3 input cv 0.57 (false reject), v4 input ru 0.54 (accepted), live 200; English still 400 | revision `00003-vpt` |

- Orphans 424/425/426 are hidden. **368/378 hide re-dispatched as GCS-HIDE2**: GCS-TR1D stopped correctly because LEAD's
  task file said `tour-editing` must be unchanged while LEAD was deploying it in parallel. Never list a service as
  must-not-change while another task is deploying it.
- **Verification lesson:** Kiro's language tests used a stub detector, and the 09-15 "false rejection" was caused mostly
  by LEAD's own Latin test marker (`LEADTEXT…`). Verify language behaviour against **live Comprehend**, with a marker
  in the tour's own script.

## ⏳ STATE 2026-09-17 11:10 — two fixes reviewed and staged, awaiting Michael's deploy approval

| task | branch | staged image | verified | rollback |
|---|---|---|---|---|
| `wdvrdaydr1` translations 404 (GCS-TR1) | `kiro/gcs-tr1` @ `522d25c` (**`main` line**, unmerged) | `translation-service:v35-tr1` = v35 + `translation_service.py` only | LEAD: 6/6 AC tests, red proof on v35, `/app` manifest diff | image `:v35` |
| `wdvrdayd40` language gate (GCS-LANG1) | `kiro/gcs-lang1` @ `d6dacc8`, merged into local `storied` `2109754` | `tour-editing:v4` | LEAD: 7 suites green, independent probe | revision `tour-editing-00003-vpt` |

- **Root cause of translations 404:** the R2 source fetch only ran for tours *without* `tour_content`, so
  R2-migrated tours built a ZIP from `None`. The error was swallowed and an artifact-less row was inserted.
  The cache check then returned that broken row forever.
- **Already done in prod (reversible):** 424, 425 and 426 hidden (`lat`/`lng` NULL; backups in
  `SUBMISSION_GCS-TR1.md` §7). Verified gone from `tours-near` on both hosts.
- **Also orphaned, still visible:** 368 (de) and 378 (zh), from June. Hide them with the deploy.
- **Track decision (LEAD, reversible):** a translation inherits its *source* tour's `track`. Storied_Tours
  asked for track-by-host; argued on `wdvrdaydr1`.
- **Follow-ups:** in TR1, check the cache before the R2 fetch. The app-side "not available for this older
  tour" message is `wdvrdaye0j` (Mac Mini).
- **Local `storied` is 2 ahead of origin** (the LANG1 merge). Push needs Michael.
- **Test hygiene:** never loop-run every file under `tests/`. `gcslang1_lang_stub.py` is a server and hangs.

## ✅ STATE 2026-09-15 16:40 — deploy day. This section supersedes "STATE AT SHUTDOWN" below.

Every change below was written by Kiro, reviewed by LEAD (including LEAD's own real dry-run), deployed by
a Kiro execute-only task, and verified by LEAD by effect. Michael approved in chat: the Preview
tour-editing deploy (~14:22), and the whole `wdvrdaxxm9` deploy request (15:42).

| service | image | revision | what / verified |
|---|---|---|---|
| `tour-editing` (**new**, private) | `tour-editing:v3` | `00003-vpt` | cloud editing: R2 read/persist, Polly authenticated (v2), **narration no longer filename-sanitised and the nav header is stripped from TTS only** (v3, GCS-SAN1). LEAD verified on tour 421: colons, newlines and accents survive; every stop has audio. Rollback: `tour-editing-00002-wc7` |
| `api-gateway-storied` | `api-gateway:v36` | `00003-5zp` | = v35 `main.py` (SHA-proven) + 4 editing routes. **Stable `api-gateway` still v35 `00022-t88`**, so no editing on Stable |
| `tour-orchestrator` (Beta) | `audioura:v22-local474` | `00025-cvz` | overlay: v22 + LOCAL-474 gate only. Env/annotations identical. Rollback `:v22` |
| `tour-generator` (Beta) | `audioura:v36-local474` | `00023-nrv` | overlay: v36 + LOCAL-474 only. Rollback `:v36` |
| `tour-generator-storied` (**new**, private) | `audioura-storied:v1` | `00001-6kn` | real Storied engine, `STORIED_MODE=true`, Cloud SQL |
| `tour-modernized-storied` (**new**, private) | `audioura-storied:v1` | `00001-b2c` | mirrors Beta `tour-modernized` |
| `tour-orchestrator-storied` | `audioura-storied:v1` | `00002-rwh` | URLs now point at the `-storied` services, so **Preview finally runs Storied code** |

Branches: GCS-5R `d4e1e07`, GCS-5R2 `f735ac6`, GCS-5E `a9bd8b0`, GCS-3R `92f71c5`, and GCS-7 `1e7c2cb`
(on `main`'s line, not merged). The first four are merged into local `storied` (`384a273`).
**Local `storied` is ahead of origin; pushing needs Michael.**

**Open, in order:**
1. **Michael's device test** of editing on Android 2.3.2+23, Preview track, tour 421. The steps are in
   the chat and in ClickUp `wdvrdaycwj`. Stable editing waits on it: `deploy_gcs5_tour_editing.sh --stable`.
2. **First real Preview tour:** check the `tour-generator-storied` logs for DB errors (the socket
   `DATABASE_URL` was never exercised), and confirm Beta's `tour-generator` did **not** log it.
3. **Keys (Michael approved 16:43):**
   - **SERP is live:** secret `serp-api-key` v1 (40 bytes), wired to `tour-generator-storied`
     `00002-xql` with `SERP_PROVIDER=serper`. The Beta generator is untouched. On the first real
     Preview tour, confirm `[SQ-S2]` search lines appear rather than "No SERP_API_KEY — skipping".
   - **Gemini is live:** Michael created secret `GEMINI_API_KEY` in the Console (note the
     UPPERCASE name, unlike the other secrets). GCS-KEYS2 added a per-secret accessor grant
     and `--update-secrets GEMINI_API_KEY=GEMINI_API_KEY:latest` on `tour-generator-storied` only,
     giving revision **`00003-2gf`**. All prior secrets are preserved, and Beta is untouched.
   - **Never use `--set-secrets` or `--set-env-vars` on a live service.** They replace the whole
     list. A ClickUp comment requested `--set-secrets` on 2026-09-15; it would have deleted the
     OpenAI, DB and SERP secrets while `/health` still passed.
   - Only `tour-generator-storied` reads SERP or Gemini. The orchestrator and modernizer do not.
   - On the first real Preview tour, confirm in `tour-generator-storied`'s logs: `[SQ-S2]` searches,
     Gemini calls, no DB socket errors, and nothing logged by Beta's `tour-generator`. Then run
     `SELECT DISTINCT track` read-only.
   - `origin/storied` was pushed at `4976943` (16:43).
4. Review `storied-health-code-sha` (`wdvrdaxyud`). `/health` still says `code_sha: no_manifest`.
5. Follow-ups:
   - `deploy_storied_generator.sh` deploys by default, and its `TOUR_TRACK` read-back doesn't strip quotes.
   - Custom (recorded) audio in `tour_editing_phase2.py` still writes to local disk, which is not cloud-safe.
   - Move `tests/db_connection.py` and `tests/stop_anchor_detector_v2.py` to the repo root.
6. `PARKED_kiro_task_GCS-6.md`: its APK part is superseded (Michael builds on Ubuntu). The test-script part is done in chat.

**Lessons from today, do not repeat:**
- A local test against a stub that doesn't require auth hid a production 403 (Polly).
  Stubs must mirror production auth.
- A route diff that compares only YAML missed a code drift in the same image.
  Compare the code inside the running image by SHA.
- A task file named a flag (`--apply`) that the script doesn't have.
  Read the script's argument parser before writing the command.
- Git Bash mangles raw Cyrillic in curl bodies. Send `\u`-escaped JSON files.
- No tour generation for verification on production: `is_test` is ignored unless
  `TOUR_TEST_MODE_ALLOW_REQUEST` is set.

---

## 🔥 STATE AT SHUTDOWN — 2026-09-15 00:13, before Michael ran a system update

**Nothing is in flight. Nothing is armed. `.continuous_dev/PAUSE` exists — remove it to
resume dispatching.** No Kiro processes were running and no task file was unclaimed, so a
reboot loses nothing. Every branch below is **pushed**; the only things that live solely
on this disk are the two build artifacts named at the end.

**Michael should `/clear` before resuming.** Resuming a long conversation after the cache
TTL costs real money for zero work; this section rebuilds the picture cheaply.

### Production right now

| service | image | note |
|---|---|---|
| `map-delivery` | `audioura:v40` | **from main** — `/tours-near` now returns `track` |
| `news-orchestrator` | `audioura:v41` | **from main** — real `/user`, `ensure_user` |
| `api-gateway` / `api-gateway-storied` | `api-gateway:v35` | **from main** — `/user` stub removed |
| `newsletter-processor` | `audioura:v39` | `cryptography` present, `/submit_credentials` works |
| `tour-orchestrator-storied` | `audioura:storied` | **stale — built from `a57dc507`, 2026-08-11** |
| `tour-generator`, `tour-modernized` | `v36`, `v37` | Beta, untouched |

`origin/storied` = **`95957d5`** — the services fixes are now on storied as well as main.

### ⚠️ THE BIG ONE: Preview has never run Storied code

Full evidence in **`PREVIEW_IS_RUNNING_BETA_CODE.md`**. Summary: the storied orchestrator
does not generate — it POSTs to `TOUR_GENERATOR_URL`, which points at **Beta's**
`tour-generator` (`audioura:v36`, `generate_tour_text.py` identical to `main`). Proved by
generating tour **422** on Preview: it records `track='storied'` while Beta's generator
logged the text at 03:31:11. **`MODERNIZED_URL` has the same defect** — found by GCS-3.

So Preview ≡ Stable today and the `wdvrdaxxm9` comparison is impossible until the
generator deploy lands. **`track` alone is never evidence** — tour 422 proves a
Beta-generated tour can read `storied`.

### Four Kiro branches awaiting LEAD review — none deployed, none merged

| branch | what | state |
|---|---|---|
| `kiro/gcs-review-1` @ `093e653` | adversarial review of the 2026-09-15 deploy | **read it** — found a real defect and corrected a too-strong "no drift" claim |
| `gcs-4-services-fixes` @ `19ccdd7` | fixes all four review findings | needs LEAD review |
| `kiro/gcs-3-storied-generator-deploy` @ `b9662fe` | **stages the Storied generator deploy**, dry-run verified | needs LEAD review, then **Michael's approval to deploy** |
| `storied-health-code-sha` @ `94aa3b8` | `wdvrdaxyud` — `code_sha`/`build_number` on `/health` and `/status` | needs LEAD review |

`kiro_sessions_ran.md` records GCS-2, GCS-3, GCS-4 and GCS-REVIEW-1 all `COMPLETED`.

### Android 2.3.2+22 — built, NOT uploaded

```
audioura-2.3.2+22.aab   31.2 MB   <- Play Console upload
audioura-2.3.2+22.apk   60.3 MB   <- sideload/test
```
At the repo root, **gitignored, local only — these do not survive a wipe.** versionCode
22, from **`2c85717`**, signed `CN=Mikhail Glik` (`b3abe5fb…ed3a64`). Matches the
`BUILD_NUMBERS.md` row that says Android 22 is owed, same commit as the iOS 22 already on
TestFlight.

**Upload is manual** — no service-account tooling exists; `PLAY_BUILD_AND_UPLOAD_RUNBOOK.md`
is Play Console by hand. Add the ledger row when uploaded; iOS then takes 23.

⚠️ **Caveat Michael has not yet ruled on:** this was built on Windows with Flutter 3.29.3
directly, because `build_flutter_clean.sh` only runs on the Ubuntu VM. That skips the
ImageMagick icon step, and the committed icons are **five identical 1024×1024 files** that
were never resized — so this build ships a 1024×1024 launcher icon in every density
bucket. It works, but it is heavier than and not comparable to prior releases. Rebuilding
on Ubuntu with Mobile Kiro, same commit and number, is the safe option.

### Worktrees on this machine (all survive a reboot)

`C:\adev-wt\` — `kirotool` (dispatcher), `GCS-2/3/4`, `GCS-REVIEW-1`, `CRYPTOFIX` (main
baseline), `PORT-STORIED`, `BUILD-22` (the 2c85717 build tree, has the signing material
copied in), `STORIED-1..4`, `APK-2312`.

### Loose ends worth a ticket

- `POST /sync` in the gateway is still a hardcoded `{"status":"success"}` — same class of
  lie as the `/user` stub was.
- `Dockerfile.cloudrun` installs a **hand-maintained pip list and never reads
  `requirements.txt`** — that is the only reason `cryptography` was missing for months.
- The shared `audioura:vN` image is a standing hazard for the Beta control: `COPY *.py`
  bakes in the whole repo, so "I diffed one file" never proves no drift. GCS-4 wrote a
  reusable check (`tools/beta_image_drift_check.py`) — review it.

## Hard stops — ask Michael even in queue mode

### 🧪 MICHAEL TESTS ON-DEVICE BEFORE ANYTHING IS DISTRIBUTED

**Michael's ruling, 2026-09-15**, after tour editing shipped in 2.3.2 (22) to TestFlight
and failed on the first Save: *"I would like to test it before distribution otherwise we
will be here again: distributing with obvious errors."*

A green Kiro submission, a LEAD review and a passing curl are **not** the gate. The gate is
Michael exercising the feature on a real device, through the real cloud path
(app → Cloudflare → gateway → service), on a **non-distributed test build**. Order:

1. Kiro implements → LEAD reviews.
2. Deploy to the **Preview/storied path first** (Michael approves the deploy). Beta stays
   untouched until the device test passes.
3. LEAD verifies by effect with curl against `storied-api.audioura.com`.
4. A **sideload/internal test build** goes to Michael only, with a written step-by-step
   test script and the expected result of each step, plus known-unfixed issues listed so he
   does not spend time on them.
5. **Only after Michael reports pass:** Beta gateway, store/TestFlight build for testers.

Why the old flow failed: 2.3.2 (22) fixed the Save All button (LOCAL-475) and was
distributed without anyone pressing Save in cloud mode — the backend had never been
deployed at all. Every check before distribution was local or source-level.

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
