# SUBMISSION — LOCAL-705: re-prove "never crashes on Storied" for the CURRENT app, and make it impossible to regress (D661)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-705-storied-compat-2` (from `subscribed` = `94bc015f`)
**Base check:** `git merge-base --is-ancestor 94bc015f HEAD` → exit 0 ✓
**App build:** `2.4.23+60` → **`2.4.24+61`**

## Why
D661: the Subscribed app must run against a Storied server (Stable on GCloud)
without crashing; features Storied lacks must say *"available in Preview only"*
(or show the screen's empty state). LOCAL-694/694B proved this for build 2.4.18.
Since then 695 (recovery code), 696 (Google Play), 699 (`/purchases/mode`), 700
(join / name-available / regenerate), 701 (community tours), 702 (step-down),
703 (launch window) added **17 new server calls** — each a fresh way to regress.
Michael (2026-10-15): *"it is okay if some new functionality only works on
Preview, but it should not crash on Stable."*

## Result (one line)
Every one of the current app's **84 inventoried server calls** maps to a handled
outcome on a Storied backend — **no crash, no uncaught exception, no infinite
spinner** — and a new Dart regression guard makes it impossible to add a raw
server call in future without either routing it through the storied-compat
helper or consciously allow-listing it with a reason.

---

## What changed

### 1. Routed the one remaining raw-status feature call through the helper
`lib/screens/recovery_code_screen.dart` — `_generate()` and `_restore()` now call
`Endpoints.postOrFeatureUnavailable(...)` and catch `FeatureUnavailableException`,
so a Storied server that lacks `/recovery-code/*` (a route-missing 404, or the
whole orchestrator route absent) shows **"This feature is available in Preview
only."** instead of the old raw *"Could not create a recovery code (404)."* The
present-route handling (201 / 200 / 401 / 409 / 429) is unchanged.

Every other feature call was already crash-safe (verified by reading each one):
the services wrap their `Endpoints.get/post` in `try/catch` and return a safe
default (`null` / `[]` / `false` / an error-result object), so a missing route or
absent service renders the screen's empty state. `wallet_service` and
`tour_share_service` already use the helper / `isRouteMissing` from LOCAL-694B.

### 2. Regression guard — makes a new raw call impossible to ship unnoticed
- `test/storied_compat_guard_test.dart` — scans every `lib/**.dart`, strips
  comments and string literals, and finds every **bare** `http.get/post/put/delete`
  and `Endpoints.get/post/put/delete` call site (the `*OrFeatureUnavailable`
  helpers and the `endpoints.dart` plumbing are exempt — they are the safe path /
  the mechanism). It **fails** if any such file is not in the allow-list, and
  also fails on a **stale** allow-list entry (a file that no longer has a raw
  call), plus requires every entry to carry a non-empty reason.
- `test/storied_compat_allowlist.txt` — the 29 files that make a raw call today,
  each with a one-line reason in one of three shapes: **CORE** (the endpoint IS
  hosted by Storied — map/search/download/generate/status/rating/translate/share/
  sync — still wrapped against transient failure), **SAFE** (try/catch → safe
  default / empty state), or **DEAD** (unreachable code that cannot run, so cannot
  crash: `tour_service.dart`, `map_service.dart`).

A new feature therefore either uses the helper or is a conscious, reasoned
allow-list line — the guard goes red otherwise.

### 3. Per-screen device-like proof (mocked gateway 404)
`test/storied_compat_screens_404_test.dart` — 9 tests. Each swaps the app's HTTP
client (via `http.runWithClient`) for a `MockClient` returning the **exact**
GCloud gateway 404 `{"error":"endpoint not found","service":"api-gateway"}` (and
a connection-refused client), pumps the real screen, and asserts it shows the
Preview message / its empty state, stays usable, and leaves `takeException()`
null with no `ErrorWidget`:

| Screen | On the gateway 404 |
|---|---|
| My communities | join bar + "not joined any communities yet" empty state (reachable); on refused → "Communities is available in Preview only." |
| Community page (by id) | "Community not found." — no crash |
| Community page (by code) | "No community with that code." — no crash |
| Communities About (join) | join field + Create button still render |
| Your plan (buy) | both `$10 Pack` + `Curator` buy buttons visible, no spinner, no crash (entitlements + `/purchases/mode` both 404) |
| Recovery code | tapping *Create my recovery code* → the Preview-only SnackBar, never "(404)" |
| Generate "for my community" | `ownedCommunities()` → `[]` (selector hides), `communityTours()` → `null`; refused also hides |

### 4. App build bumped
`pubspec.yaml`: `2.4.23+60` → `2.4.24+61`.

---

## Tests

- Full storied-compat suite (guard + screens-404 + helper unit + service MockClient
  + recovery + communities + community-tour + UX + plan-buy): **135 passed**.
- `flutter analyze` on the changed file + both new test files: **No issues**.
- Full `flutter test`: **520 passed, 6 failed**. The 6 failures are all in
  `test/local109_swipe_e2e_test.dart`, a **live end-to-end** test that connects to
  a running backend at `localhost:5102` / `127.0.0.1`; with no live server in this
  environment it fails with `SocketException: Connection refused`. Pre-existing and
  unrelated to this change (which only touched `recovery_code_screen.dart` and
  added `test/` files).

---

## Replay — the current app's 84 calls against a Storied stack

**Stack provenance (D358).** Built **strictly from `origin/storied`**
(`bbcff4872db2c6a6ff771153cbe1aa675450b2e3`) in its **own** compose project
`docker compose -p local705` on spare **53xx** ports, joined to the existing
`development_default` DB network read-mostly. All 8 containers carry the
`bbcff487` git stamp. No GCloud, no tour generation, no paid work (cost-bearing
POSTs sent empty bodies to draw a free validation refusal). The `audioura-*` dev
stack was never touched; the stack and the temporary `origin/storied` worktree
were torn down afterwards.

Tooling: `local705_tooling/{inventory.md, replay_harness.py, replay_results.txt,
storied-stack.compose.yml}`.

**How to read it.** `isRouteMissing(status, body)` is the single rule: a
gateway/HTML 404 or a 405/501 is a **missing route** → Preview-only; a service's
**own** JSON 404 is a **normal not-found** that keeps its message; a connection
refusal is an **absent service** → Preview-only. The replay reproduces the exact
bytes each call gets and the "How the app handles it" column states the D661
outcome.

### Summary (83 replayed; treats #48/#49 dedup to one call, as in 694B)

| Outcome | Count | App behaviour |
|---|---|---|
| OK (200) | 7 | feature works — health, tours-near, search, tour-by-code, treats, translate, job-status (the CORE flows) |
| NORMAL not-found (JSON 404) | 3 | status / download / download-tour of a made-up id — keeps its own not-found message |
| 4xx handled (validation/refusal) | 5 | the server's own message / the structured refusal UI |
| 5xx handled (server error) | 6 | offline / try-again message |
| MISSING ROUTE (HTML/gateway 404) | 25 | **Preview-only / empty state** |
| MISSING ROUTE (405/501) | 1 | **Preview-only / empty state** (delete-account 405) |
| ABSENT (connection refused) | 36 | **Preview-only / empty state** (userDb / voice / generator / customAudio / tourIdResolution) |

**Every call maps to a handled outcome. No crash, no uncaught exception, no
infinite spinner.** The 61 MISSING+ABSENT calls all degrade to the Preview-only
message or the screen's empty state through the helpers / the services'
safe-default `try/catch`.

### Stack-sanity note (harness grep false positive, not a defect)
Row **#70** `/communities/1/tours` shows `grep=yes` yet an HTML 404. Verified: on
`origin/storied` (`bbcff487`) the orchestrator hosts **neither**
`/communities/<id>/tours` **nor** `/tour/<id>/community` — both routes were added
*after* `bbcff487` (LOCAL-701). The `grep=yes` is a loose-regex match on an
unrelated `/tours` fallback alternative in the harness pattern; the authoritative
signal is the **HTML 404 the stack actually returned**, which the app correctly
reads as route-missing → Preview/empty state. Row #71 (`/tour/<id>/community`)
correctly shows `grep=no`. So the one flagged row confirms, rather than
contradicts, the D661 behaviour.

### Full replay table

| # | Service | Method | Path | Storied status | Classification | route exists (grep) | 404 body kind | How the app handles it |
|---|---|---|---|---|---|---|---|---|
| 1 | orchestrator | POST | `/generate-complete-tour` | 400 | 4xx handled | yes |  | handled refusal/validation message |
| 2 | orchestrator | GET | `/status/{job}` | 404 | NORMAL not-found | yes | json-404 | keeps its own not-found message |
| 3 | orchestrator | GET | `/download/{job}` | 404 | NORMAL not-found | yes | json-404 | keeps its own not-found message |
| 4 | orchestrator | GET | `/health` | 200 | OK | yes |  | feature works |
| 5 | orchestrator | GET/DELETE | `/delete-account/{user}` | 405 | MISSING (405) | yes |  | Preview-only / empty state |
| 6 | orchestrator | POST | `/tour-status` | 400 | 4xx handled | yes |  | handled message |
| 7 | orchestrator | GET | `/tour/{id}/unlock-state` | 404 | MISSING (html 404) | no | html-404 | Preview-only / free default |
| 8 | orchestrator | GET | `/tour/{id}/price` | 404 | MISSING (html 404) | no | html-404 | Preview-only / Free default |
| 9 | orchestrator | POST | `/tour/{id}/price` | 404 | MISSING (html 404) | no | html-404 | Preview-only / empty state |
| 10 | orchestrator | GET | `/tour/{id}/sales` | 404 | MISSING (html 404) | no | html-404 | Preview-only / 0 default |
| 11 | orchestrator | GET | `/price-tiers` | 404 | MISSING (html 404) | no | html-404 | Preview-only / [] default |
| 12 | orchestrator | GET | `/tour/{id}/reviews` | 404 | MISSING (html 404) | no | html-404 | Preview-only / [] default |
| 13 | orchestrator | GET | `/tour/{id}/distribution` | 404 | MISSING (html 404) | no | html-404 | Preview-only / empty default |
| 14 | orchestrator | POST | `/tour/{id}/review` | 404 | MISSING (html 404) | no | html-404 | Preview-only / null |
| 15 | orchestrator | POST | `/review/{id}/helpful` | 404 | MISSING (html 404) | no | html-404 | Preview-only / null |
| 16 | orchestrator | POST | `/review/{id}/reply` | 404 | MISSING (html 404) | no | html-404 | Preview-only / null |
| 17 | orchestrator | POST | `/tour/{id}/rating` | 404 | MISSING (html 404) | no | html-404 | Preview-only / null (outbox) |
| 18 | orchestrator | GET | `/tour/{id}/rating` | 404 | MISSING (html 404) | no | html-404 | Preview-only / null |
| 19 | orchestrator | GET | `/wallet/{user}` | 404 | MISSING (html 404) | no | html-404 | Preview-only (FeatureUnavailable) |
| 20 | orchestrator | GET | `/wallet/{user}/transactions` | 404 | MISSING (html 404) | no | html-404 | Preview-only (FeatureUnavailable) |
| 21 | orchestrator | GET | `/plans/available` | 404 | MISSING (html 404) | no | html-404 | Preview-only (FeatureUnavailable) |
| 22 | orchestrator | POST | `/wallet/{user}/topup` | 404 | MISSING (html 404) | no | html-404 | Preview-only (FeatureUnavailable) |
| 23 | orchestrator | POST | `/sync` | 404 | MISSING (html 404) | no | html-404 | kept + backoff (outbox) |
| 24 | mapDelivery | GET | `/tours-near/{lat}/{lng}` | 200 | OK | yes |  | feature works (CORE) |
| 25 | mapDelivery | GET | `/download-tour/{id}` | 404 | NORMAL not-found | yes | json-404 | keeps its own not-found message |
| 26 | mapDelivery | GET | `/search-tours` | 200 | OK | yes |  | feature works (CORE) |
| 27 | mapDelivery | GET | `/tour-by-code/{code}` | 200 | OK | yes |  | feature works (CORE) |
| 28 | mapDelivery | GET | `/tour/{id}/preview-audio` | 404 | MISSING (html 404) | no | html-404 | Preview-only / empty state |
| 29 | mapDelivery | GET | `/tour/{id}/score-explanation` | 404 | MISSING (html 404) | no | html-404 | Preview-only / "not available yet" |
| 30 | mapDelivery | POST | `/tour/{id}/rescore-request` | 404 | MISSING (html 404) | no | html-404 | Preview-only / handled result |
| 31 | mapDelivery | GET | `/how-we-score` | 404 | MISSING (html 404) | no | html-404 | Preview-only / empty state |
| 32 | tourIdResolution | GET | `/tour/{id}/resolve` | CONN_REFUSED | ABSENT | yes |  | Preview-only / empty state |
| 33 | userDb | GET | `/user` | CONN_REFUSED | ABSENT | src-missing |  | Preview-only / empty state |
| 34 | userDb | GET | `/health` | CONN_REFUSED | ABSENT | src-missing |  | Preview-only / empty state |
| 35 | userDb | GET | `/entitlements/me` | CONN_REFUSED | ABSENT | src-missing |  | Preview-only / Entitlements.unknown |
| 36 | userDb | POST | `/entitlements/app-open` | CONN_REFUSED | ABSENT | src-missing |  | null (do nothing) |
| 37 | userDb | POST | `/entitlements/lapse` | CONN_REFUSED | ABSENT | src-missing |  | false |
| 38 | userDb | POST | `/l2/queue/join` | CONN_REFUSED | ABSENT | src-missing |  | null |
| 39 | userDb | POST | `/l2/claim` | CONN_REFUSED | ABSENT | src-missing |  | ClaimResult(ok:false) |
| 40 | userDb | POST | `/purchases/verify` | CONN_REFUSED | ABSENT | src-missing |  | IapResult.failed (buy never crashes) |
| 41 | userDb | POST | `/document-acceptance` | CONN_REFUSED | ABSENT | src-missing |  | false |
| 42 | userDb | GET | `/document-acceptance` | CONN_REFUSED | ABSENT | src-missing |  | [] |
| 43 | userDb | POST | `/communities` | CONN_REFUSED | ABSENT | src-missing |  | null (empty state) |
| 44 | userDb | GET | `/communities/by-code/{code}` | CONN_REFUSED | ABSENT | src-missing |  | null (no community) |
| 45 | userDb | GET | `/communities/{id}` | CONN_REFUSED | ABSENT | src-missing |  | null ("not found" page) |
| 46 | userDb | POST | `/communities/{id}/join` | CONN_REFUSED | ABSENT | src-missing |  | null |
| 47 | userDb | GET | `/communities/map` | CONN_REFUSED | ABSENT | src-missing |  | [] |
| 48 | treats | GET | `/treats-near/{lat}/{lng}` | 200 | OK | yes |  | feature works |
| 50 | voice | POST | `/parse_voice_search` | CONN_REFUSED | ABSENT | src-missing |  | falls back to text search |
| 51 | voice | POST | `/process-voice-command` | CONN_REFUSED | ABSENT | src-missing |  | does nothing (logs) |
| 52 | translation | POST | `/translate-with-audio` | 200 | OK | yes |  | feature works (CORE) |
| 53 | generator | POST | `/tour/share` | CONN_REFUSED | ABSENT | yes |  | Preview-only message |
| 54 | news | POST | `/generate-news` | 400 | 4xx handled | yes |  | handled message |
| 55 | news | GET | `/status/{id}` | 500 | 5xx handled | yes |  | offline/try-again |
| 56 | news | GET | `/download/{id}` | 500 | 5xx handled | yes |  | offline/try-again |
| 57 | newsletter | GET | `/newsletters_v2` | 500 | 5xx handled | yes |  | offline/try-again |
| 58 | newsletter | POST | `/process_newsletter` | 500 | 5xx handled | yes |  | offline/try-again |
| 59 | newsletter | POST | `/submit_credentials` | 503 | 5xx handled | yes |  | offline/try-again |
| 60 | newsletter | POST | `/key_exchange` | 503 | 5xx handled | yes |  | offline/try-again |
| 61 | tourEditing | POST | `/tour/{id}/update-stop` | 400 | 4xx handled | yes |  | handled message |
| 62 | tourEditing | POST | `/tour/{id}/update-multiple-stops` | 400 | 4xx handled | yes |  | handled message |
| 63 | tourEditing | GET | `/tour/{id}/job-status/{job}` | 200 | OK | yes |  | feature works |
| 64 | customAudio | POST | `/tour/{id}/stop/{n}/custom-audio` | CONN_REFUSED | ABSENT | src-missing |  | {success:false} |
| 65 | customAudio | DELETE | `/tour/{id}/stop/{n}/custom-audio` | CONN_REFUSED | ABSENT | src-missing |  | false |
| 66 | customAudio | GET | `/tour/{id}/stop/{n}/audio-versions` | CONN_REFUSED | ABSENT | src-missing |  | [] |
| 67 | customAudio | GET | `/tour/{id}/audio-metadata` | CONN_REFUSED | ABSENT | src-missing |  | {} |
| 68 | userDb | GET | `/communities/mine` | CONN_REFUSED | ABSENT | src-missing |  | [] (Preview empty state) **[NEW 690]** |
| 69 | userDb | GET | `/communities/mine-owned` | CONN_REFUSED | ABSENT | src-missing |  | [] (selector hides) **[NEW 701]** |
| 70 | orchestrator | GET | `/communities/{id}/tours` | 404 | MISSING (html 404) | yes* | html-404 | null (page empty state) **[NEW 701]** |
| 71 | orchestrator | GET | `/tour/{id}/community` | 404 | MISSING (html 404) | no | html-404 | null (ordinary tour) **[NEW 701]** |
| 72 | userDb | GET | `/communities/name-available` | CONN_REFUSED | ABSENT | src-missing |  | null ("couldn't check") **[NEW 700]** |
| 73 | userDb | POST | `/communities/{id}/regenerate-code` | CONN_REFUSED | ABSENT | src-missing |  | null **[NEW 700]** |
| 74 | userDb | POST | `/communities/{id}/episodes` | CONN_REFUSED | ABSENT | src-missing |  | false **[NEW 690]** |
| 75 | userDb | POST | `/communities/{id}/import-feed` | CONN_REFUSED | ABSENT | src-missing |  | false **[NEW 690]** |
| 76 | userDb | POST | `/communities/{id}/step-down` | CONN_REFUSED | ABSENT | src-missing |  | null (unchanged state) **[NEW 702]** |
| 77 | userDb | POST | `/communities/{id}/offer-organiser` | CONN_REFUSED | ABSENT | src-missing |  | null **[NEW 702]** |
| 78 | userDb | POST | `/communities/{id}/withdraw-offer` | CONN_REFUSED | ABSENT | src-missing |  | false **[NEW 702]** |
| 79 | userDb | POST | `/communities/{id}/pick-organiser` | CONN_REFUSED | ABSENT | src-missing |  | null **[NEW 702]** |
| 80 | userDb | POST | `/communities/{id}/accept-organiser` | CONN_REFUSED | ABSENT | src-missing |  | null **[NEW 702]** |
| 81 | userDb | DELETE | `/communities/{id}` | CONN_REFUSED | ABSENT | src-missing |  | false **[NEW 702]** |
| 82 | userDb | GET | `/purchases/mode` | CONN_REFUSED | ABSENT | src-missing |  | falls back to device server_mode **[NEW 699]** |
| 83 | orchestrator | POST | `/recovery-code/generate` | 404 | MISSING (html 404) | no | html-404 | **Preview-only SnackBar** (helper-routed) **[NEW 695]** |
| 84 | orchestrator | POST | `/recovery-code/restore` | 404 | MISSING (html 404) | no | html-404 | **Preview-only message** (helper-routed) **[NEW 695]** |

\* #70 `grep=yes` is a harness loose-regex false positive — see the stack-sanity
note above; `origin/storied` has no such route, the HTML 404 is correct, and the
app treats it as route-missing.

---

## Files
- `audio_tour_app/lib/screens/recovery_code_screen.dart` — helper-routed the two
  recovery-code calls (Preview message on a missing route).
- `audio_tour_app/test/storied_compat_guard_test.dart` — the regression-guard scanner.
- `audio_tour_app/test/storied_compat_allowlist.txt` — the reasoned allow-list (29 files).
- `audio_tour_app/test/storied_compat_screens_404_test.dart` — the 9 per-screen gateway-404 tests.
- `audio_tour_app/pubspec.yaml` — build `2.4.24+61`.
- `local705_tooling/{inventory.md, replay_harness.py, replay_results.txt, storied-stack.compose.yml}` — the regenerated inventory + replay.
