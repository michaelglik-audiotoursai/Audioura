# SUBMISSION — LOCAL-694: Subscribed app degrades gracefully against a Storied server

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-694-storied-compat` · **Base:** subscribed (`10db345b`)
**Build:** `2.4.15+50` → **`2.4.15+51`**

## Goal (D661, Michael 2026-10-14)
Subscribed can go to GCloud only once app `2.4.15+50+` works against the **Storied**
backend GCloud runs today. Features Storied lacks may be unavailable, but the app
must **never crash or show a blank/raw error** — it must say e.g. *"This feature is
available in Preview only."*

## What was done (one commit per step)
1. **Inventory** — every server call in `audio_tour_app/lib` (`local694_tooling/inventory.md`): 67 call sites across 12 services.
2. **Local Storied stack** — built from `origin/storied` (`bbcff487`) in an isolated compose project `docker compose -p local694` on spare `53xx` ports (`local694_tooling/storied-stack.compose.yml`). No GCloud, no tour generation, no `audioura-*` containers touched. Services talk to the existing dev DB (read-mostly) via the `development_default` network.
3. **Replay** — Python harness (`local694_tooling/replay_harness.py`) replayed all calls with realistic params; status + body shape recorded (`local694_tooling/replay_results.txt`). Cost-bearing POSTs were sent with empty bodies to draw a free validation refusal — never a real job.
4. **App** — one central place in `lib/config/endpoints.dart` (`FeatureUnavailableException`, `featureUnavailableMessage`, `isFeatureUnavailableStatus`, `tryDecodeMap`/`tryDecodeList`, `isServiceAbsentError`, `get/postOrFeatureUnavailable`) + call-site fixes.
5. **Tests** — 37 Dart tests (`test/storied_compat_test.dart`, `test/storied_compat_services_test.dart`), all pass; 68 pass including the existing wallet/communities/share suites.
6. **Build bump** `+50 → +51`.

## The Storied stack
Built from `origin/storied`'s own compose service set. It runs the directly-called
services (orchestrator, map-delivery, treats, news-orchestrator, newsletter,
tour-editing-phase2, translation). It **deliberately does not host** the services
Storied's compose never defines — `user_api` (userDb), `voice_control`,
`generate_tour_text` (generator), `tour_id_resolution`, `custom_audio` — so the
app's calls to those hit connection-refused, which is exactly the GCloud condition.

Host→container ports: orchestrator `5302→5002`, map-delivery `5305→5005`,
treats `5307→5006`, news-orchestrator `5312→5012`, newsletter `5317→5017`,
tour-editing-phase2 `5322→5022`, translation `5330→5030`.

## Replay table (app → Storied, 2.4.15+51)

Five outcome classes: **OK** (200), **MISSING ROUTE** (404/405/501 — route not on
Storied; Flask returns an **HTML** body), **ABSENT** (whole service not hosted →
connection refused), **4xx** (JSON validation refusal), **5xx** (JSON server error,
here from empty-data env, not a Storied gap).

| # | Service | Method | Path | Status | Class | Body shape |
|---|---|---|---|---|---|---|
| 1 | orchestrator | POST | `/generate-complete-tour` | 400 | 4xx | json{error} |
| 2 | orchestrator | GET | `/status/<job>` | 404 | MISSING | json{error} |
| 3 | orchestrator | GET | `/download/<job>` | 404 | MISSING | json{error} |
| 4 | orchestrator | GET | `/health` | 200 | OK | json{cost_ceiling,service,status} |
| 5 | orchestrator | GET | `/delete-account/<id>` | 405 | MISSING | HTML |
| 6 | orchestrator | POST | `/tour-status` | 400 | 4xx | json{message,status} |
| 7 | orchestrator | GET | `/tour/<id>/unlock-state` | 404 | MISSING | HTML |
| 8 | orchestrator | GET | `/tour/<id>/price` | 404 | MISSING | HTML |
| 9 | orchestrator | POST | `/tour/<id>/price` | 404 | MISSING | HTML |
| 10 | orchestrator | GET | `/tour/<id>/sales` | 404 | MISSING | HTML |
| 11 | orchestrator | GET | `/price-tiers` | 404 | MISSING | HTML |
| 12 | orchestrator | GET | `/tour/<id>/reviews` | 404 | MISSING | HTML |
| 13 | orchestrator | GET | `/tour/<id>/distribution` | 404 | MISSING | HTML |
| 14 | orchestrator | POST | `/tour/<id>/review` | 404 | MISSING | HTML |
| 15 | orchestrator | POST | `/review/<id>/helpful` | 404 | MISSING | HTML |
| 16 | orchestrator | POST | `/review/<id>/reply` | 404 | MISSING | HTML |
| 17 | orchestrator | POST | `/tour/<id>/rating` | 404 | MISSING | HTML |
| 18 | orchestrator | GET | `/tour/<id>/rating` | 404 | MISSING | HTML |
| 19 | orchestrator | GET | `/wallet/<id>` | 404 | MISSING | HTML |
| 20 | orchestrator | GET | `/wallet/<id>/transactions` | 404 | MISSING | HTML |
| 21 | orchestrator | GET | `/plans/available` | 404 | MISSING | HTML |
| 22 | orchestrator | POST | `/wallet/<id>/topup` | 404 | MISSING | HTML |
| 23 | orchestrator | POST | `/sync` | 404 | MISSING | HTML |
| 24 | mapDelivery | GET | `/tours-near/<lat>/<lng>` | 200 | **OK** | json{center_lat,center_lng,count,radius_km,tours} |
| 25 | mapDelivery | GET | `/download-tour/<id>` | 200 | **OK** | ZIP (PK) |
| 26 | mapDelivery | GET | `/search-tours` | 200 | **OK** | json{count,pattern,tours} |
| 27 | mapDelivery | GET | `/tour-by-code/<code>` | 404 | MISSING | HTML |
| 28 | mapDelivery | GET | `/tour/<id>/preview-audio` | 404 | MISSING | HTML |
| 29 | mapDelivery | GET | `/tour/<id>/score-explanation` | 404 | MISSING | HTML |
| 30 | mapDelivery | POST | `/tour/<id>/rescore-request` | 404 | MISSING | HTML |
| 31 | mapDelivery | GET | `/how-we-score` | 404 | MISSING | HTML |
| 32 | tourIdResolution | GET | `/tour/<id>/resolve` | refused | **ABSENT** | — |
| 33 | userDb | GET | `/user` | refused | ABSENT | — |
| 34 | userDb | GET | `/health` | refused | ABSENT | — |
| 35 | userDb | GET | `/entitlements/me` | refused | ABSENT | — |
| 36 | userDb | POST | `/entitlements/app-open` | refused | ABSENT | — |
| 37 | userDb | POST | `/entitlements/lapse` | refused | ABSENT | — |
| 38 | userDb | POST | `/l2/queue/join` | refused | ABSENT | — |
| 39 | userDb | POST | `/l2/claim` | refused | ABSENT | — |
| 40 | userDb | POST | `/purchases/verify` | refused | ABSENT | — |
| 41 | userDb | POST | `/document-acceptance` | refused | ABSENT | — |
| 42 | userDb | GET | `/document-acceptance` | refused | ABSENT | — |
| 43 | userDb | POST | `/communities` | refused | ABSENT | — |
| 44 | userDb | GET | `/communities/by-code/<code>` | refused | ABSENT | — |
| 45 | userDb | GET | `/communities/<id>` | refused | ABSENT | — |
| 46 | userDb | POST | `/communities/<id>/join` | refused | ABSENT | — |
| 47 | userDb | GET | `/communities/map` | refused | ABSENT | — |
| 48 | treats | GET | `/treats-near/<lat>/<lng>` | 200 | **OK** | json{center_lat,center_lng,count,treats} |
| 50 | voice | POST | `/parse_voice_search` | refused | ABSENT | — |
| 51 | voice | POST | `/process-voice-command` | refused | ABSENT | — |
| 52 | translation | POST | `/translate-with-audio` | 200 | **OK** | json{status,translations} |
| 53 | generator | POST | `/tour/share` | refused | ABSENT | — |
| 54 | news | POST | `/generate-news` | 400 | 4xx | json{error} |
| 55 | news | GET | `/news-status/<id>` | 404 | MISSING | HTML |
| 56 | news | GET | `/news-download/<id>` | 404 | MISSING | HTML |
| 57 | newsletter | GET | `/newsletters_v2` | 500 | 5xx | json{error} |
| 58 | newsletter | POST | `/process_newsletter` | 500 | 5xx | json{error_type,message,status} |
| 59 | newsletter | POST | `/submit_credentials` | 503 | 5xx | json{message,status} |
| 60 | newsletter | POST | `/key_exchange` | 503 | 5xx | json{message,status} |
| 61 | tourEditing | POST | `/tour/<id>/update-stop` | 400 | 4xx | json{error_code,message,recoverable,status,suggested_action} |
| 62 | tourEditing | POST | `/tour/<id>/update-multiple-stops` | 400 | 4xx | json{error_code,...} |
| 63 | tourEditing | GET | `/tour/<id>/job-status/<job>` | 200 | **OK** | json{job_id,message,status,tour_id} |
| 64 | customAudio | POST | `/tour/<id>/stop/<n>/custom-audio` | refused | ABSENT | — |
| 65 | customAudio | DELETE | `/tour/<id>/stop/<n>/custom-audio` | refused | ABSENT | — |
| 66 | customAudio | GET | `/tour/<id>/stop/<n>/audio-versions` | refused | ABSENT | — |
| 67 | customAudio | GET | `/tour/<id>/audio-metadata` | refused | ABSENT | — |

**Totals:** OK = 7 · MISSING ROUTE (404/405/501) = 27 · ABSENT (refused) = 23 · 4xx = 5 · 5xx = 4.

### Core flows that MUST work on Storied — all green
map + tours-near (#24 **200**), search (#26 **200**), download & play (#25 **200** ZIP,
#63 job-status **200**), translate (#52 **200**), treats (#48 **200**). Generate (#1)
returns a JSON **400** only because the probe sends an empty body on purpose — the
route exists and is handled. Ratings (#17/18) and share code (#27) are 404 on this
Storied build and share (#53) is absent; all three are now handled (below), so a
tester sees a graceful message, not a crash.

## How every class is handled (no unhandled case)

| Class | What the server returns | How the app handles it | Where |
|---|---|---|---|
| OK (200) | JSON / ZIP | normal parse (unchanged core flows) | all callers |
| MISSING ROUTE (404/405/501) | **HTML** body | `isFeatureUnavailableStatus` → `FeatureUnavailableException` (Preview message); `tryDecodeMap/List` return **null** instead of throwing on the HTML | `endpoints.dart`; wallet_service, tour_share_service; existing 200-gated callers (ratings, reviews, pricing, score, status) already ignore non-200 |
| ABSENT (connection refused) | SocketException | `isServiceAbsentError` → Preview message / safe default | `endpoints.dart`; communities_service (→ `[]`/`null`/`false`, `isAvailable()`=false), tour_share_service (→ Preview message), entitlements/iap/voice already catch |
| 4xx | JSON refusal | parsed by existing defensive code (structured error → UI) | generate, tour-status, generate-news, tour-editing |
| 5xx | JSON error | existing try/catch → safe default / message (not a Storied gap: empty-data env) | newsletter/subscription services |

### Central helper (`lib/config/endpoints.dart`)
- `FeatureUnavailableException` — user-safe `message` (default *"This feature is available in Preview only."*).
- `featureUnavailableMessage` — the one wording.
- `isFeatureUnavailableStatus(code)` — 404 / 405 / 501.
- `tryDecodeMap` / `tryDecodeList` — safe JSON decode; **null** on an HTML 404 / empty / shape mismatch; never throws.
- `isServiceAbsentError(e)` — SocketException / http.ClientException / TimeoutException.
- `getOrFeatureUnavailable` / `postOrFeatureUnavailable` — raise the exception on missing route or absent service.

### User-visible changes
- **Wallet** (`wallet_service` + `wallet_screen` + `PaywallScreen`): previously threw a raw `Exception('Failed to fetch wallet: 404')` the screen rendered as text. Now a friendly *"Preview only"* empty state.
- **Communities** (`communities_service` + `my_communities_screen`): previously an **uncaught** `SocketException` + an unguarded `jsonDecode` on an HTML body — would crash on Storied. Now every method degrades to a safe empty value; the screen shows *"Communities is available in Preview only."* via an `isAvailable()` probe.
- **Share** (`tour_share_service`): a missing/absent generator now gives the *"Preview only"* message instead of a misleading "check your connection".

## Tests
`flutter test` — 68 pass (37 new + 31 existing wallet/communities/share), no regressions.
- `test/storied_compat_test.dart` — the central helper, one group per replay class: 404/405/501 classified; HTML 404 → null, no throw; refusal errors → absent; exception carries the Preview message and leaks no status.
- `test/storied_compat_services_test.dart` — end-to-end via `http.runWithClient` + `MockClient` replaying Storied's 404 and connection-refused shapes: `WalletService` raises `FeatureUnavailableException` (not a raw Exception); `CommunitiesService` degrades to `[]`/`null`/`false` with `isAvailable()`=false; `TourShareService` returns the Preview message. No exception reaches the UI.

## Reproduce
```bash
# Storied stack (isolated, spare ports, reads dev DB)
git worktree add --detach <path>/local694-storied origin/storied
docker compose -p local694 -f local694_tooling/storied-stack.compose.yml up -d --build
# Replay
python3 local694_tooling/replay_harness.py
# App tests
cd audio_tour_app && flutter test test/storied_compat_test.dart test/storied_compat_services_test.dart
```

## Scope / process
Own containers only (`-p local694`); no `audioura-*` touched; no GCloud; no tours
generated. No edits to DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE.md /
`.continuous_dev/*`. The `Track B` Beta/Storied base URLs in `endpoints.dart` were
left byte-for-byte unchanged.
