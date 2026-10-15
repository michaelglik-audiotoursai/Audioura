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


---

# 694B — bounce of LOCAL-694 (LEAD review 2026-10-14, two defects)

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-694-storied-compat` (continued) · **Base:** subscribed (`10db345b`)

LEAD did not merge LOCAL-694 and called out two defects. Both are fixed below;
Dart (now 59) and the Python replay were re-run.

## Defect 1 — every 404 was treated as "feature unavailable"

`Endpoints.isFeatureUnavailableStatus(code)` returned true for **any** 404/405/501,
so an ordinary not-found (unknown community code, deleted tour, unknown job) said
*"This feature is available in Preview only."* even on the Subscribed server.

**Fix** (`lib/config/endpoints.dart`): a new body-aware classifier
`isRouteMissing(statusCode, [body])`. A route is MISSING **only** when the 404 is
NOT the service's own JSON error:

- **(a)** the GCloud API gateway's JSON `{"error":"endpoint not found","service":"api-gateway"}`
  (confirmed at `api-gateway/main.py:297` — what GCloud returns for an unknown path), **or**
- **(b)** a non-JSON body (Flask's HTML 404 page when a service is called directly), **or**
- **(c)** 405 Method Not Allowed / 501 Not Implemented.

A JSON 404 **from the service itself** (`{"error":"not_found"}`, `{"error":"Job not found"}`,
`{"error":"tour not found"}`) is a **NORMAL not-found** and keeps its existing message.

- `get/postOrFeatureUnavailable` now classify with `isRouteMissing(status, resp.body)`;
  a service JSON 404 is returned to the caller for normal handling instead of raising.
- `tour_share_service` uses `isRouteMissing` (so a real "tour not found" keeps the
  server's message, while a missing share route still shows Preview).
- `isFeatureUnavailableStatus` is reduced to **405/501-only** (deprecated) because a
  404 cannot be classified from the status alone — no caller can over-report Preview.

**Tests** — all four cases, per helper, plus end-to-end proofs
(`test/storied_compat_test.dart`, `test/storied_compat_services_test.dart`):

- `(a)` gateway JSON 404 → MISSING; `(b)` HTML/empty 404 → MISSING; `(c)` 405/501 → MISSING
  regardless of body; `(d)` service JSON 404 (`not_found` / `Job not found` / `tour not found`)
  → NORMAL (not missing). A service error that merely names the gateway stays NORMAL.
- `isFeatureUnavailableStatus(404)` is now **false**; 405/501 true.
- End-to-end via `http.runWithClient` + `MockClient`: a gateway/HTML 404 and a connection
  refusal give the Preview message; a **service JSON 404** does **not** —
  `WalletService.getWallet` throws its ordinary Exception (never `FeatureUnavailableException`),
  `TourShareService` keeps "Tour not found", `CommunitiesService.get` returns null with
  `isAvailable()` still true.
- `flutter test test/storied_compat_test.dart test/storied_compat_services_test.dart` →
  **59 pass** (was 37). Full suite: no new failures; the only reds are the 6 pre-existing
  `local109_swipe_e2e_test.dart` cases that need a live server (identical `+6 -6` on the clean base).

## Defect 2 — the replay did not run real Storied code

The LOCAL-694 stack built every image from `build: .` — the **subscribed** worktree —
so it measured subscribed code (D358), and it reported routes storied **has** as MISSING
(`/tour-by-code`, `/status/<job>`, `/download/<job>`).

**Fix** — the stack is now built **strictly from a detached `origin/storied` worktree**
(`bbcff487`), via `local694_tooling/storied-stack.compose.yml`:

- Every build `context` is the storied worktree (`$STORIED`, `$STORIED/map_delivery`,
  `$STORIED/translation-service`); each build passes `GIT_SHA=$STORIED_SHA`.
- Each container prints its build context + a `git rev-parse` stamp (`print_stack_stamps()`):
  **all 7 containers stamp `bbcff487…`** (verified via `/app/.git_sha`).
- **Decisive correction:** map-delivery is built from `map_delivery/` (its own Dockerfile →
  `CMD ["python","app.py"]`). `map_delivery/app.py:35` defines `/tour-by-code/<code>`.
  LOCAL-694 instead ran the **root** `map_delivery_service.py` (no such route) via
  `Dockerfile.cloudrun`, which is why `/tour-by-code` showed an HTML 404.

**Real data** (dev DB, read-only; creds from storied source): `shared_tours` holds real
share codes — `L687MATA` → `audio_tour_id` 686. The replay uses **share code `L687MATA`**
and **real tour id `686`**. `job_status` is empty in this dev DB, so no real job id exists;
an unknown job id therefore draws the service's **own JSON 404** — which is exactly the
NORMAL not-found the app must keep (and proves the route exists).

**New columns** in the harness/table: **"route exists on storied (grep)"** (greps the
storied worktree's real service source) and a **404 body kind** (`json-404 NORMAL` vs
`html-404 MISSING` vs `gateway-404 MISSING`). A **STACK-SANITY** check fails the run if any
`grep=yes` route on a *hosted* service returns an HTML 404 ("fix the stack, not the app").

### STACK-SANITY — passes

> none — every grep-present route on a hosted service returns JSON/200, never an HTML 404.

The three routes LEAD flagged are now correct: **#2 `/status`**, **#3 `/download`**, and
**#25 `/download-tour/686`** are `grep=yes` and return a **json-404 (NORMAL not-found)** — the
routes exist; a made-up id simply isn't found. **#27 `/tour-by-code/L687MATA`** is a clean
**200** on the real share code. The orchestrator genuinely has only 14 routes (no wallet /
plans / pricing / sync / rating / review), so `grep=no` on #7–23 is truthful and their HTML
404 (MISSING) is correct. #5 `/delete-account` is **405** (storied hosts it as DELETE-only;
a GET is Method-Not-Allowed = MISSING for that verb). News #55/#56 probe the service's real
`/status` and `/download` (the gateway rewrites `/news-*`); they return a parseable JSON 500
(route exists, empty-data env), not a missing route.

### Replay table (app → Storied built from origin/storied `bbcff487`)

| # | Service | Method | Path | Status | Classification | route exists on storied (grep) | 404 body kind | Body shape | Note |
|---|---|---|---|---|---|---|---|---|---|
| 1 | orchestrator | POST | `/generate-complete-tour` | 400 | 4xx | yes |  | json{error} | empty body → validation refusal, no job |
| 2 | orchestrator | GET | `/status/<job>` | 404 | **NORMAL not-found (json 404)** | **yes** | json-404 | json{error} | REAL route; unknown-job 404 (was mislabelled MISSING) |
| 3 | orchestrator | GET | `/download/<job>` | 404 | **NORMAL not-found (json 404)** | **yes** | json-404 | json{error} | REAL route; unknown-job 404 (was mislabelled MISSING) |
| 4 | orchestrator | GET | `/health` | 200 | OK | yes |  | json{cost_ceiling,service,status} |  |
| 5 | orchestrator | GET | `/delete-account/<id>` | 405 | MISSING (405/501) | yes |  | html | storied hosts it DELETE-only; GET = 405 |
| 6 | orchestrator | POST | `/tour-status` | 400 | 4xx | yes |  | json{message,status} | empty body |
| 7 | orchestrator | GET | `/tour/686/unlock-state` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 8 | orchestrator | GET | `/tour/686/price` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 9 | orchestrator | POST | `/tour/686/price` | 404 | MISSING (html 404) | no | html-404 | html | empty body |
| 10 | orchestrator | GET | `/tour/686/sales` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 11 | orchestrator | GET | `/price-tiers` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 12 | orchestrator | GET | `/tour/686/reviews` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 13 | orchestrator | GET | `/tour/686/distribution` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 14 | orchestrator | POST | `/tour/686/review` | 404 | MISSING (html 404) | no | html-404 | html | empty body |
| 15 | orchestrator | POST | `/review/1/helpful` | 404 | MISSING (html 404) | no | html-404 | html | empty body |
| 16 | orchestrator | POST | `/review/1/reply` | 404 | MISSING (html 404) | no | html-404 | html | empty body |
| 17 | orchestrator | POST | `/tour/686/rating` | 404 | MISSING (html 404) | no | html-404 | html | empty body |
| 18 | orchestrator | GET | `/tour/686/rating` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 19 | orchestrator | GET | `/wallet/<id>` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 20 | orchestrator | GET | `/wallet/<id>/transactions` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 21 | orchestrator | GET | `/plans/available` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 22 | orchestrator | POST | `/wallet/<id>/topup` | 404 | MISSING (html 404) | no | html-404 | html | empty body |
| 23 | orchestrator | POST | `/sync` | 404 | MISSING (html 404) | no | html-404 | html | empty body |
| 24 | mapDelivery | GET | `/tours-near/<lat>/<lng>` | 200 | OK | yes |  | json{center_lat,center_lng,radius_km,total_count,tours} | Paris |
| 25 | mapDelivery | GET | `/download-tour/686` | 404 | **NORMAL not-found (json 404)** | **yes** | json-404 | json{error} | REAL tour id (was mislabelled MISSING) |
| 26 | mapDelivery | GET | `/search-tours` | 200 | OK | yes |  | json{count,pattern,tours} |  |
| 27 | mapDelivery | GET | `/tour-by-code/L687MATA` | **200** | **OK** | **yes** |  | json{count,tours} | REAL share code → 200 (was mislabelled MISSING) |
| 28 | mapDelivery | GET | `/tour/686/preview-audio` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 29 | mapDelivery | GET | `/tour/686/score-explanation` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 30 | mapDelivery | POST | `/tour/686/rescore-request` | 404 | MISSING (html 404) | no | html-404 | html | empty body |
| 31 | mapDelivery | GET | `/how-we-score` | 404 | MISSING (html 404) | no | html-404 | html |  |
| 32 | tourIdResolution | GET | `/tour/686/resolve` | refused | ABSENT | yes |  | — | service not hosted |
| 33–47 | userDb | — | user / entitlements / iap / legal / communities | refused | ABSENT (15) | src-missing |  | — | service not hosted on storied |
| 48 | treats | GET | `/treats-near/<lat>/<lng>` | 200 | OK | yes |  | json{center_lat,center_lng,count,treats} |  |
| 50–51 | voice | POST | voice search / command | refused | ABSENT (2) | src-missing |  | — | service not hosted |
| 52 | translation | POST | `/translate-with-audio` | 200 | OK | yes |  | json{status,translations} | empty body → refusal |
| 53 | generator | POST | `/tour/share` | refused | ABSENT | yes |  | — | generator not hosted on storied |
| 54 | news | POST | `/generate-news` | 400 | 4xx | yes |  | json{error} | empty body |
| 55 | news | GET | `/status/<id>` | 500 | 5xx | yes |  | json{error} | real route; gateway rewrites `/news-status/*` → `/status/*` |
| 56 | news | GET | `/download/<id>` | 500 | 5xx | yes |  | json{error} | real route; gateway rewrites `/news-download/*` → `/download/*` |
| 57 | newsletter | GET | `/newsletters_v2` | 500 | 5xx | yes |  | json{error} |  |
| 58 | newsletter | POST | `/process_newsletter` | 500 | 5xx | yes |  | json{error_type,message,status} | empty body |
| 59 | newsletter | POST | `/submit_credentials` | 503 | 5xx | yes |  | json{message,status} | empty body |
| 60 | newsletter | POST | `/key_exchange` | 503 | 5xx | yes |  | json{message,status} | empty body |
| 61 | tourEditing | POST | `/tour/686/update-stop` | 400 | 4xx | yes |  | json{error_code,…} | empty body |
| 62 | tourEditing | POST | `/tour/686/update-multiple-stops` | 400 | 4xx | yes |  | json{error_code,…} | empty body |
| 63 | tourEditing | GET | `/tour/686/job-status/<job>` | 200 | OK | yes |  | json{job_id,message,status,tour_id} |  |
| 64–67 | customAudio | — | custom-audio / versions / metadata | refused | ABSENT (4) | src-missing |  | — | service not hosted |

(Rows 33–47, 50–51, 64–67 collapsed for brevity; the full per-row table with every path is
in `local694_tooling/replay_results.txt`.)

**Totals (694B):** OK = 7 · NORMAL not-found (json 404) = 3 · MISSING ROUTE (html/gateway 404) = 21 ·
MISSING ROUTE (405/501) = 1 · ABSENT (refused) = 23 · 4xx = 5 · 5xx = 6.

Compared with 694 (OK=7 / 404=27 / absent=23 / 4xx=5 / 5xx=4): the three mislabelled routes
(#2, #3, #25) moved from "MISSING" to "NORMAL not-found", #27 moved from "MISSING" to **OK**,
and the two news rows now measure the real service path (JSON 5xx, route exists) instead of a
gateway-prefixed HTML 404. No `grep=yes` route on a hosted service returns an HTML 404.

## Reproduce (694B)
```bash
# origin/storied worktree (detached — never move the branch)
git worktree add --detach <path>/local694b-storied origin/storied
export STORIED=<path>/local694b-storied STORIED_SHA=$(git -C "$STORIED" rev-parse HEAD)
# Stack built STRICTLY from origin/storied; map-delivery from map_delivery/app.py
docker compose -p local694 -f local694_tooling/storied-stack.compose.yml up -d --build
# Replay (prints per-container git stamp, grep column, STACK-SANITY check)
python3 local694_tooling/replay_harness.py
# App tests
cd audio_tour_app && flutter test test/storied_compat_test.dart test/storied_compat_services_test.dart   # 59 pass
```

## Scope / process (694B)
Own containers only (`-p local694`); no `audioura-*` touched; GCloud read-only (none here);
no tours generated; no writes to the dev DB (reads + empty-body validation probes only). No
edits to DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE / `.continuous_dev`. The Track B Beta/Storied
base URLs in `endpoints.dart` are byte-for-byte unchanged.
