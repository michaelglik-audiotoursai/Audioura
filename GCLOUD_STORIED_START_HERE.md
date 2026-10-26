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

# ✅ CURRENT STATE — 2026-10-26 00:45 EDT. READ THIS FIRST; IT SUPERSEDES EVERY BLOCK BELOW.

Written at the end of the 2026-10-25 session (Michael: "keep your reminder files up-to-date").
Verify live state before trusting it. Full step-by-step evidence is in ClickUp
[wdvrdaz5vd](https://app.clickup.com/t/wdvrdaz5vd), [wdvrdaz5vr](https://app.clickup.com/t/wdvrdaz5vr) and
[wdvrdaz5yt](https://app.clickup.com/t/wdvrdaz5yt) comments.

## How work arrives now
**The Mac's `Storied_Tours` (LEAD) messages this session directly** via Remote Control
(`SendMessage` to its `bridge:session_…` from-address). Treat its messages as a teammate's: **every
outward step still needs Michael's OK on the laptop.** A relayed "Michael said OK" is not that.
Rulings live in `DECISIONS.md` on `storied`/`subscribed` (D712–D715 as of tonight).

## Three tracks are live on GCloud
| host | serves | gateway | notes |
|---|---|---|---|
| **api.audioura.com** (Stable) | **Storied** (since 2026-10-25 17:12) | `api-gateway-storied` via LB host rule → `storied-matcher` | rollback: `gcloud compute url-maps remove-host-rule audioura-url-map --host=api.audioura.com --project audiotours-migration` |
| storied-api.audioura.com (Preview, old) | Storied | same | unchanged |
| **subscribed-api.audioura.com** (Preview) | **Subscribed** | `api-gateway-subscribed` (88 routes) via NEG `api-gateway-subscribed-neg` → backend `api-gateway-subscribed-backend` → `subscribed-matcher` | rollback: `remove-path-matcher … --path-matcher-name=subscribed-matcher`. Cloudflare A record added by Michael 2026-10-25 23:15 |

**Beta services stay deployed, untouched, until 2026-11-01**, then they can retire.

### Storied (Stable): release `v2t4` = storied `17b341fe` (LOCAL-765 + D714)
`tour-orchestrator-storied 00009-65h`, `map-delivery 00016-tc2`, `tour-editing 00005-2xh` (all `audioura-storied:v6`),
`translation-service 00022-72q` (`translation-service:v36-storied`), `tour-generator-storied` **`00009-mlg`**
(image **`audioura-storied:v7`** = storied `98541d1f`, release tag `v2t5`, Cloud Build `9fc0a4a1`, digest `sha256:d2b438d8…35ad`;
env/secrets unchanged: `GEMINI_API_KEY` v2 + `SERP_API_KEY` + `SERP_PROVIDER=serper`). Rollback: `gcloud run services update-traffic
tour-generator-storied --to-revisions=tour-generator-storied-00008-dhd=100 --region us-central1 --project audiotours-migration`.
- **Task D of wdvrdaz5yt DONE 2026-10-26 10:40 EDT** (Michael's "go D"). Test tour **448** Watertown City Hall (1 stop, landmark,
  track storied, $0.0428): venue-parts ran with `GEMINI key present=True`, LOCAL-275 closing offer ran, 0 tracebacks; download 200
  with `audio_1.mp3`; listed on api.audioura.com. Left in place as a real tour.
- **wdvrdaz64g (Subscribed AAB for Play Internal testing): BUILT 2026-10-26 10:43, waiting for Michael to upload by hand.**
  `C:\adev-wt\aab77\audioura-subscribed-2.4.31+77.aab` (sha256 56f803d0…), from a detached worktree `C:\adev-wt\GCS-PLAY77` @ subscribed
  `6d6aeed7`, `--build-name=2.4.31 --build-number=77 --dart-define=APP_TRACK=subscribed` + GATEWAY_API_KEY from build_secrets.env.
  Billing 8.0.0, upload key B3:AB:E5…3A:64. Host proven on the API-36 emulator: only api-gateway-subscribed got requests.
  After the upload: record 77 in BUILD_NUMBERS (on `subscribed`) and comment the opt-in link + "Available" time on wdvrdaz64g.
  First-launch setState crash = LOCAL-773; testers get the later build, not 77.
- **2026-10-26 afternoon:** build **77** live on Internal testing 11:24, but the Pixel kept getting 2.3.2+20 (Closed). Build **78**
  (2.4.32, subscribed `d27d06e4`, LOCAL-773 fix, `C:\adev-wt\aab78\…`) live 14:00 and **installed on the Pixel-7 from the Play Store**.
  Internal opt-in link: https://play.google.com/apps/internaltest/4701219869553974677 (the `/apps/testing/<pkg>` link opts into CLOSED).
  **wdvrdaz660 DONE 14:45:** tour-generator-storied **00010-ldx** (`audioura-storied:v8` = storied `3122cd71`, rollback 00009-mlg),
  test tour **449** $0.026, fact sheets 1/1. **wdvrdaz66n DONE:** tour-generator-subscribed **00004-x42** (`subscribed-generator:85af16c4`,
  rollback 00003-9r7), test tour **450** OK. Subscribed has STORIED_MODE=false (no fact sheets) and grounding/news on: ~$0.58/tour.
  **wdvrdaz6a7 DONE 16:20 EDT:** tour-generator-subscribed **00005-67j** = env-only `STORIED_MODE=true` (D717; rollback 00004-x42);
  voice-subscribed **00002-xz5** (85af16c4, rollback 00001-jf9). Test tour **451** (1 stop, thin). UNVERIFIED: the fact-sheet log lines,
  because Cloud Logging reads returned 500 or empty from ~19:48Z; re-check later. **Bug:** generators keep jobs in memory, and with 2 instances
  (seen at 19:48 despite maxScale=1) the orchestrator gets "Job not found" while the job keeps running and spending. Waiting on LEAD.
  Evidence without logs: `paid_api_calls` (cols ts, service, kind, model, usd) and Cloud Monitoring `run.googleapis.com/container/instance_count`.
- **DB writes 2026-10-26 16:24 EDT (Michael's "Go A and B" on the laptop):** (A) `level_codes` 0 → 1, admin code hash a582f5e3…8127
  (redeemed by USER-41659366, now admin; then **revoked** 20:28Z at Michael's request: 1 code, 0 active). (B) `plans` l2 `by_reference_only` true → **false, permanent** (D719 as amended;
  caps unchanged 1/day, 3/month, 5 stops). Stable never reads it. The plan-screen counter bug (counts failed/started rows) is fixed in code by
  LOCAL-777; do NOT sweep stale 'started' rows. D718: until LOCAL-775 ships, deploy a generator only when paid_api_calls shows no activity for ~5 min.
- **RU translation report (16:35):** server side OK (tour 453 = ru of 452, Polly Tatyana). The app's translated download got **402 purchase_required**
  because `tour_generator_screen._processAdditionalLanguages` omits `?user_id=` (creator exemption). The $3 (tier 9) was set by Michael in Generate; the creator exemption is correct. Fix = LOCAL-780 (one download helper adds user_id).
- **Laptop remote access (for Vietnam, from 10-28):** Tailscale "mercury" 100.68.122.8 (expiry off, unattended). Exit node = mikhails-mac-mini
  (`tailscale set --exit-node=100.106.181.69 --exit-node-allow-lan-access=true`; `--exit-node=` to turn it off; keep it OFF by default).
  Screen: TigerVNC 1.15 → 100.106.181.69, user `micha`; menu = **Ctrl+Alt+M**; "Full screen on all monitors" (the Mac has 2 screens).
- **Found, not fixed (pre-existing, handed to the Mac):** `fact_extractor.py` and the LOCAL-192 style retry call `gpt-3.5-turbo`,
  which OpenAI now answers with **404**, so fact sheets are 0/N and style retries keep the original. 95 references across the code.
- `GEMINI_API_KEY` **v2** = new key `gcloud-storied-2026-10` (uid `bb7f1e39…`, …ECA0), restricted to generativelanguage,
  created by gcloud and piped straight into the secret. v1 stays disabled.

### Subscribed (Preview): release `v3t1` = subscribed `3c0cfae6`, with later images per service
12 new services, all `-subscribed`, private except the gateway, compute SA, Cloud SQL:
tour-orchestrator `00004-vpl` · tour-generator `00003-9r7` · tour-modernized `00003-r88` · translation `00003-ncj` (`46adfa2f`) ·
map-delivery `00002-mgq` (`455eff72`) · news-orchestrator `00003-sn6` (`46adfa2f`) · newsletter `00002-tb6` · tour-editing `00002-mlg` ·
tour-id-resolution · user-api · voice · api-gateway-subscribed. Images: `services/subscribed-<svc>:<sha>`.
Read-only reuse of Beta's `treats-service`, `news-generator`, `news-processor`, `polly-tts`. `CUSTOM_AUDIO_URL` → tour-editing-subscribed (dead code).
- Deploy script: `C:\adev-wt\bsub\deploy_subscribed.sh` (refuses to touch an existing service). Key audit: `C:\adev-wt\bsub\audit_keys.py`.
- Test tours **444** (Gardner), **445** (Trinity), **446** (BPL): track subscribed, rated general, listed on subscribed-api only.
  **447** = es translation of 446. All 404 on api.audioura.com. Left in place as real tours.

## Database (shared Cloud SQL): what changed 2026-10-25
- Backup **`1792967357689`** (22:29Z) before Subscribed migrations.
- **043s**: global `uq_audio_tours_original_name` replaced by `uq_audio_tours_original_name_nonsub` (Subscribed exempt) + `idx_audio_tours_name_track`.
- **010–051** applied (47 → 80 tables). ⚠️ **Each migration file carries its own `BEGIN/COMMIT`**: a "dry run with ROLLBACK"
  commits anyway. Never trust an outer transaction around these files.
- **052**: `audio_tours_track_check` now allows `'subscribed'`. It was the only live-only constraint (audited).
- **053**: `paid_api_calls` table (it never existed on Cloud SQL, so the daily cap was inert).
- Plans: **tester = 10/day** (Michael's override of D715; was 100). Michael (`USER-1073427300`) = Subscribed **admin**;
  the other 2 testers = `tester` in `device_entitlement`.
- audio_tours = 340 (beta 318, storied 18, subscribed 4: 444–447).

## Spend control (wdvrdaz5yt)
- **A ✅** `DAILY_PAID_LIMIT_USD=20` live on Subscribed orchestrator/generator/modernized/translation. Each has `METER_ROLE=listener`,
  `METER_ROLE_TOKEN` ← secret `meter-role-token`, **and** the same secret mounted at **`/run/meter-secret/role_token`**
  (+`METER_ROLE_TOKEN_FILE`). Never mount under `/opt/meter`: it hides the meter code. Proven: 20 listener rows, cap total matched.
  **Gap:** the meter hooks only `requests`, so **Polly / AWS Translate (botocore) are never counted**. Mac task LOCAL-769.
- **B ✅** Michael edited the existing budget → "Audioura Monthly Spend", $100/mo, 50/90/100%. It is the one wired to Pub/Sub topic
  `billing-killswitch`, a Cloud Function that only throttles 8 **Beta** service names to maxScale=1 and never touches
  `-storied`/`-subscribed`.
- **C** daily 08:00 spend report: BigQuery dataset `billing_export` created; Michael enabled the export 00:42. First table
  `gcp_billing_export_v1_01EE1F_6D9958_ABBB49` within ~24 h. Still needs the OpenAI **Admin** key from Michael. AWS dropped.
- **D** open (see Storied above).

## New secrets (values never shown)
`admin-api-key`, `recovery-code-pepper`, `attestation-nonce-secret`, `meter-role-token`, `credential-blind-index-key`.
KMS: compute SA has `cryptoKeyEncrypterDecrypter` on key `credential-encryption` only.

## Tooling learned tonight: do not re-learn
- **Git Bash rewrites any arg that starts with `/`** (`/run/x` → `C:/Program Files/Git/run/x`) when calling gcloud. Use PowerShell,
  or prefix values so they don't start with `/` (the `^|^` delimiter trick worked). Scan env after every deploy.
- `bq` fails under Git Bash (`python3.13: command not found`). Run it from PowerShell.
- `gcloud builds submit` crashes on deep or Unicode paths in the repo. Build from a minimal `git archive` into a short dir (`C:\adev-wt\bsub*`).
- Cloud SQL proxy: `C:\Users\micha\AppData\Local\Temp\claude\…\scratchpad\cloud-sql-proxy.exe --token "$(gcloud auth print-access-token)" --port 5447 …`;
  kill it with `Get-Process cloud-sql-proxy | Stop-Process`.
- Repo bugs fixed upstream by LEAD tonight: newsletter Dockerfile `COPY *.py ./` + google-cloud-kms; the gateway Dockerfile copies the
  subscribed routes; `map_delivery/app.py` hard-coded `postgres-2`; news and cost_meter `/cloudsql` socket URLs; manifest `JOB_STORE_MODE=database`.

---

# CURRENT STATE — 2026-10-20 ‹SUPERSEDED by the 2026-10-26 block above›

Written at Michael's request at the end of the 2026-10-16 session so a fresh session can
continue without re-deriving anything. Where this disagrees with anything below, **this is
right**. Verify live state rather than trusting it — it is point-in-time.

## Both exposed API keys are rotated. This is finished, not in progress.

| key | what happened |
|---|---|
| **OpenAI** | Michael created `gcloud-2026-10` and pasted it as **`openai-api-key` version 5** (last 4 **`…fIoA`**, 164 chars, sha256 `a3d2145ec91f`). Six services rolled onto it, both tracks proved a real tour, then Michael **revoked the old `…Nw8A`** (`MyFirstOpenAPI_Key`, created Oct 2024, last used Oct 4 2026). Secret versions **4, 3 and 2 are DISABLED** — all three held that same key (v3 and v2 are v4 with `sk-proj-` stripped). Version 1 is a 26-char placeholder, left enabled. **Review and destroy 4/3/2 on or after 2026-10-19.** |
| **Gemini** | **No GCloud service has ever read `GEMINI_API_KEY`** — zero references across every service, job and function. Michael deleted the AI Studio key `…bGMw` (uid `9f2aeb5d…`, the credential behind the runaway spend in wdvrdayyqd); **`GEMINI_API_KEY:1` is DISABLED** in Secret Manager so the dead value cannot be wired into a future deploy. Two keys remain in the project: `mac-mini-2026-10` (…1Qfg, live on the Mac) and `Windows-Laptop` (…HX4Q, this machine). |

**The lesson that made the OpenAI half safe: match a key by its LAST FOUR characters, never by prefix.** Every project key starts `sk-proj-`. Task wdvrdaxaw9's Part 2 told us to revoke "the `sk-proj-wpIW…` key" but not "`…Nw8A`" — the same key. Acting on it would have taken down all tour generation on both tracks. Michael's own screenshot settled the remaining doubt: `Last used Oct 4` proved no machine anywhere, including the Mac, was still on it.

## The OpenAI key now sits on THREE services, down from six

`tour-generator` · `tour-generator-storied` · `news-generator` — all via `openai-api-key:latest`.

Removed as vestigial, each proven by effect afterwards with a real tour: **`tour-orchestrator`** and **`tour-orchestrator-storied`** (`tour_orchestrator_service.py` has never contained `openai` or `OPENAI_API_KEY` in *any* commit on *any* branch — `git log --all -S` is empty — and none of the ten local modules it imports reads it either), and **`coordinates`**, which was then deleted outright.

## What is live right now

| track | service | revision | image |
|---|---|---|---|
| Preview | `tour-orchestrator-storied` | `00008-j6t` | **`audioura-storied:v5`** (commit `3ab1e566`, tag **`v2t3`**) |
| Preview | `tour-generator-storied` | `00007-twm` | `audioura-storied:v4` (commit `d25454a`, tag `v2t2`) |
| Preview | `tour-modernized-storied` | `00004-ssx` | `audioura-storied:v4` |
| Beta | `tour-orchestrator` | `00029-f9x` | **`audioura:v23`** (commit `056529c1`, tag **`v1t1`**) |
| Beta | `tour-generator` | `00025-wqg` | `audioura:v36-local474` |
| Beta | `news-generator` | `00010-486` | `audioura:v16` |

**Beta is no longer an untouched control.** Michael explicitly authorised a `main` change and a Beta deploy on 2026-10-16. Note the Preview generator is still on **v4**, so the LOCAL-593/D612 work merged at `354da34` is **still not deployed** — rolling `audioura-storied:v5` onto `tour-generator-storied` would ship it, which is task wdvrdayu7q and needs its own verification.

**19 Cloud Run services now; `coordinates` was deleted.** Its spec was saved to the session
scratchpad as `coordinates_service_spec_20261016.yaml` (image `audioura:v5`, 256Mi,
concurrency 80, maxScale 2, timeout 240s, compute SA) and `audioura:v5` is still in
Artifact Registry, so it can be recreated from `gcloud run services replace`.
`COORDINATES_URL` is still set on both orchestrators and now points at nothing — harmless,
since the code reaches it only after Nominatim fails, but worth removing one day.

## GCS-C1 — a tour can no longer be stored unreachable

`tours-near` filters on `audio_tours.lat`/`lng`, so a row with NULL coordinates or `0,0`
can never be returned to any listener **while the app reports success**. Two holes did
exactly that, caught live on Preview job `36b13113`:

```
19:13:02  ==== COORDINATES CHECK IN ORCHESTRATE_TOUR_ASYNC ====
19:13:02  Coordinates from modernized service: [None, None]
```

…and no `No coordinates received` line after it. **That absence was the bug.** `[None, None]`
is a list of length 2, so it passed `len(coordinates) < 2`, the fallback never ran, and the
row was written with NULL coordinates. Separately, every failure branch of
`get_coordinates_direct()` returned `(0, 0)` and stored it verbatim — the Gulf of Guinea —
and the `coordinates` service it called had returned **500 on every request** since it was
built against `openai<1.0.0`, so `(0, 0)` was the only value it could ever produce.

Fixed on **`storied` `3ab1e566`** and **`main` `056529c1`** (identical change), both pushed
and deployed. `subscribed` is ClickUp wdvrdaz10j, assigned to the Mac Mini.

- `_usable_coordinates()` — two finite, non-null, in-range numbers, and not `(0,0)`. A point on the equator **or** the prime meridian alone still passes; only the intersection is refused.
- The fallback asks **Nominatim first, in-process**, via `geocode_stops.geocode()`: free, no API key, stdlib-only, already in the image. Using the LLM HTTP service as the safety net meant the net was made of the material `geocode_stops.py` exists to replace (model coordinates measured 1.0–2.4 km wrong — Yury's BETA-4).
- Total failure stores **NULL, never `0,0`**, logged at ERROR with the job id.
- Same treatment in `tour_worker_service.py`. **The deployed `tour-worker` image (`audioura:v19`) does NOT have the fix** — it is out of the request path (`GENERATION_MODE` defaults to `thread`), so it needs a rebuild before `cloud_tasks` mode is ever switched on.

**Proven in production, same input, after the fix and after the service was deleted:**

```
20:03:28  Coordinates from modernized service: [None, None]
20:03:28  No USABLE coordinates from modernized service ([None, None]) — resolving for: Fenway Park, Boston, MA
20:03:28  [GCS-C1] Nominatim for 'Fenway Park, Boston, MA': (42.3464614, -71.0970999)
20:03:28  Using coordinates: [42.3464614, -71.0970999]
```

51 ms. `tests/test_gcs_c1_coordinate_guard.py` has 40 assertions including a **red test**
that reproduces the original predicate and asserts it accepted `[None, None]` and `[0, 0]`
— so a revert to a length check keeps that test passing while the rest fail.

## ⚠️ THE LIVE DB WAS DELETED FROM, ON MICHAEL'S EXPLICIT INSTRUCTION

D141 says **no task may `DELETE FROM audio_tours`**. On 2026-10-16 Michael said *"get rid
off them compeltely and everythign connected to them"* about the 11 unreachable tours, and
it was done. **This does not repeal D141** — it was an owner override of it, made
reversible first. Do not treat it as precedent.

| | |
|---|---|
| deleted | 11 unreachable tours (121, 124, 125, 140, 141, 142, 368, 378, 424, 425, 426) + **this session's own 4 verification rows** (432–435) |
| row counts | `audio_tours` **345 → 330**, `stop_metrics` **17 → 12** (cascade). `tour_requests`, `tour_scores`, `custom_tours`, `user_stop_feedback`, `shared_tours`, `users` all unchanged |
| R2 | 6 objects `tours/{121,124,125,140,141,142}.zip` deleted, each confirmed 404 |
| backup | **`C:\Users\micha\AudiouraBackups\unreachable_tours_20261016\`** — all 25 columns of all 11 rows, a `restore.sql` with full INSERTs + a `setval`, the 6 zips size-matched before deletion, and the 432–435 rows |
| safety | 5 of the 11 were **translations** of live tours. The transaction asserted parents 107 (Waban, Newton), 120, 144, 207, 284 were still present **with coordinates** before committing, and would have rolled back otherwise |

**Final DB state: 330 rows, 0 with a NULL coordinate, 0 at `0,0`.** No audio was lost —
`audio_tour` was NULL on all 11 and the R2 zips were ~2 KB each, i.e. failed generations.

## Tooling this session had to work out — do not rediscover it

- **Docker Desktop is not running and has not been since 2026-10-13.** Build on **Cloud Build** instead; it needs no local Docker and keeps Michael's untracked root files (`audioura_books.py`, the Chase/Schwab CSVs, the LLC agreement) out of the build context, which `COPY *.py` from this dirty tree would otherwise ship. Recipe: copy the tracked build inputs from a **clean worktree** into a scratch dir, write a `cloudbuild.yaml` whose single docker step passes `-f Dockerfile.cloudrun` and the `RELEASE_TAG`/`GIT_SHA` build args, then `gcloud builds submit --config cloudbuild.yaml --substitutions=_IMAGE=…,_RELEASE_TAG=…,_GIT_SHA=…`. Storied's Dockerfile also needs `tests/db_connection.py`, `tests/stop_anchor_detector_v2.py`, `story_type_taxonomy.json` and `templates/`; `main`'s needs only root `*.py`.
- **Cloud SQL access: the proxy binary is gone from this machine and ADC is not configured.** Download `cloud-sql-proxy.x64.exe` from `storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v<ver>/` into a scratch dir and run it with **`--token "$(gcloud auth print-access-token)"`** plus `--port 544x audiotours-migration:us-central1:audioura-db`. Then `psycopg2` (installed in user site-packages, so **run plain `python`, not `python -I`**) to `127.0.0.1:<port>`, db `audiotours`, user `admin`, password from `gcloud secrets versions access latest --secret=db-password`. The instance has **no authorized networks**, so never consider connecting directly. Kill the proxy when done.
- **R2** is `v1-audiotours-r2-bucket` at `https://4b4aa47cda0cc65f20b20fac0b363ac7.r2.cloudflarestorage.com`, reachable with boto3 and the `r2-access-key-id` / `r2-secret-access-key` secrets, `region_name='auto'`.
- **`gcloud` inside a bash `for` loop eats the loop's input.** Every `gcloud` call in a loop needs `< /dev/null`, or the loop runs once and the rest silently vanish.
- Console encoding is cp1252: printing non-Latin tour names crashes with `UnicodeEncodeError`. Use `PYTHONIOENCODING=utf-8`, or `.encode('ascii','replace')`.

## Open, and what the next session should pick up

1. **ClickUp wdvrdaz108 — two concurrent tours collapse into one `audio_tours` row.** Not a race: `store_audio_tour()` dedupes on `lower(tour_name)` and the unique index `uq_audio_tours_original_name` **ignores `track`**, so the first track to generate a place owns that name forever. Worse, `origin/main` still carries the **pre-LOCAL-156 destructive `UPDATE`** that overwrites the existing row's `audio_tour`, `lat`, `lng` and `tour_content`; `55c9a83b` fixed it on 2026-08-02 and `7963e3a5` ported it to `storied` on 08-03, but **it never reached `main`**. On 2026-10-16 Beta overwrote a Preview row's audio. The task carries the full fix: cherry-pick `55c9a83b` to `main`, add `track` to the dedupe key and to a new `CONCURRENTLY`-built partial unique index (checked: zero conflicting groups), and make the insert `ON CONFLICT … DO NOTHING` + re-select. `tour_worker_service.py` has the same destructive UPDATE.
2. **ClickUp wdvrdaz10j** — the `subscribed` third of GCS-C1, for the Mac Mini.
3. **ClickUp wdvrdayu7q** — deploy `354da34` (LOCAL-593/D612) to the Preview **generator**. Supersedes wdvrdayruf (`690d6ba`) and wdvrdayrhj (`ef8fda6`); one deploy covers all three. `audioura-storied:v5` already contains it.
4. **`SERP_API_KEY` is wired to nothing.** `tour-generator-storied` logs `[INTERPRETIVE] No SERP_API_KEY — cannot search` on every stop, while a `serp-api-key` secret sits unused in Secret Manager. Same shape as the Gemini gap. Costs money per search, so it is Michael's decision, not a bug fix.
5. **Daily tour quota may not be enforced on GCloud at all.** Two full tours wrote **no** `tour_requests` row, yet `entitlements.get_tours_used_today()` counts that table, and `USER_API_URL` points at `http://user-api-2:5000`, which is not a deployed service. If nothing writes the meter, the per-plan limit is decorative. Unfiled; it is a cost-control question.
6. Older and still open: wdvrdayrh7 (`_geo_vocab` docstring states the wrong safe direction), wdvrdayrhc (Palais Lascaris delivered 3 of 4 stops — the production face of LOCAL-19), wdvrdayqp3 (the dispatcher claims the Mac's `LOCAL-*` files — 3rd occurrence), wdvrdayj16 (Beta cost baseline), wdvrdaye2a, wdvrdayced, and the Play upload of +26 blocked on the Play Console invite for `play-publisher@audiotours-migration.iam.gserviceaccount.com`.
7. **wdvrdaxaw9 still is not closed.** Its step 4 (Mac `.env` + restart) is the Mac's and unknown from here; step 7 (old AWS key Inactive → Delete) is Michael's in the AWS console and unreadable from here (`polly-tts-user`, account 437474201737, lacks `iam:ListAccessKeys`); **its Part 2 text is still wrong and must be rewritten before anyone acts on it.**
8. Michael still has to field-test on Preview: Newton church, Logan, a large museum (the hang fix), and **user-chosen stops from the phone** — confirm `user_explicit` in the generator logs when he does.

## Still true, still suspended

**Kiro CLI is still gone** (re-checked 2026-10-20: not on PATH, `AppData\Local\Kiro-Cli\kiro-cli.exe` absent). **RULE ONE remains suspended** and this session keeps writing shipping code directly, as Michael instructed on 2026-10-04, 10-13 and 10-16. When Kiro returns, RULE ONE resumes.

---

# CURRENT STATE — 2026-10-14 01:10 EDT ‹SUPERSEDED by the 2026-10-20 block above›

> Kept for its reasoning and evidence. Where it disagrees with the 2026-10-20 block,
> the newer block wins. Much of it is now history: the keys it describes have been
> rotated and the Preview orchestrator has moved on.

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
