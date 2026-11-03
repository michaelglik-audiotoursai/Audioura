# SUBMISSION — LOCAL-854: our own map-tile cache server (D757)

**Branch:** `LOCAL-854-tile-proxy`
**Base:** subscribed (contains `70737c2a`) — verified
`git merge-base --is-ancestor 70737c2a HEAD` exits 0.

## Problem (D757)

The app loaded map tiles straight from `tile.openstreetmap.org`, and its
"fallback" hosts (`a/b/c.tile.openstreetmap.org`) are the SAME OSM CDN. That is
three problems: OSM's tile policy forbids heavy/commercial use of that server;
from Vietnam the OSM host fails DNS/connect intermittently (Michael's field
tests — the grey Home map); and the fallbacks fail together because they are the
same CDN. LOCAL-853 added an app-side cache/retry/fallback; LOCAL-854 adds the
server-side piece: our own read-through cache in front of a tile origin.

## What I built

### 1. `tile_proxy/` — Flask + gunicorn, its own build context
- `GET /{z}/{x}/{y}.png`, `z` 0–19 and `x`/`y` validated against `2**z`;
  anything else → **400**.
- **Read-through cache**: Google Cloud Storage bucket (`TILE_CACHE_BUCKET`) when
  set, else a local dir (`TILE_CACHE_DIR`) for tests — no cloud creds needed
  locally.
- On a miss, fetch from `TILE_ORIGIN`
  (default `https://tile.openstreetmap.org/{z}/{x}/{y}.png`) with the required
  descriptive User-Agent `Audioura/1.0 (+https://audioura.com; audiotoursai@gmail.com)`.
  **Only 200 image/png** is stored.
- Response: `Cache-Control: public, max-age=604800` + `ETag`.
- **Concurrency cap 4** on origin fetches per instance (`BoundedSemaphore`).
- On origin failure: serve a **stale** cached copy if present, else **502**.
- `/health`.
- Logs `[LOCAL-854] tile hit|miss|stale z/x/y`.
- **Origin switchable to MapTiler with no code change**: `TILE_ORIGIN` is a URL
  template with an optional `{key}` read from `TILE_ORIGIN_KEY` (env/secret,
  never logged, never committed).
- Never prefetches or bulk-downloads.

Files: `app.py`, `requirements.txt` (pinned), `gunicorn.conf.py`, `Dockerfile`
(python:3.12-slim, non-root), `.dockerignore`.

### 2. App points at the proxy (no hard-coded secret)
- `audio_tour_app/lib/config/map_tiles.dart`: default `MAP_TILE_URL` is now a
  **non-secret proxy placeholder** (`tile-proxy-subscribed.audioura.com`),
  overridable at build time via `--dart-define=MAP_TILE_URL=...`. LEAD supplies
  the real Cloud Run host at build; no host secret in the repo.
- Direct OSM stays as the **LAST** fallback: the fallback list ends with the
  canonical `tile.openstreetmap.org`.
- OSM attribution stays visible: new `lib/widgets/osm_attribution.dart`
  (`RichAttributionWidget` → `© OpenStreetMap contributors`), wired into the
  Home map, the tour map, and the organiser map picker.

### 3. Deploy notes — `tile_proxy/DEPLOY.md`
Cloud Run `tile-proxy-subscribed` (min 0, max 3, 256Mi); bucket with 90-day
lifecycle; runtime SA with `objectAdmin` on that bucket only; expected monthly
cost ≈ $1–5. Marked clearly: **do not deploy from here**.

## Verification (evidence)

### Flutter tests — 22/22 pass
`flutter test test/map_tiles_url_order_local854_test.dart test/resilient_tile_provider_local853_test.dart`
- 6 new tests assert: primary is the proxy (NOT an OSM host); the ordered list
  starts with the proxy; direct OSM (canonical host) is the LAST fallback; every
  OSM host appears only after the proxy; the primary leads and is not duplicated.
- 16 existing LOCAL-853 provider tests still pass (no regression).
- `flutter analyze` on the changed files: `map_tiles.dart` + `osm_attribution.dart`
  clean; the two large screens have **0 error-severity** issues (only
  pre-existing info lints).

### Live container run — budget $0, no paid APIs
Built `local854-tiles:dev`, ran `docker run --rm --name local854-tiles -p 5854:8080`
(my own name/port, never an `audioura-*` container).
- **Miss → hit**: 3 Ho Chi Minh City tiles (`12/3262/1924`, `12/3263/1924`,
  `12/3262/1925`) fetched twice. Pass 1 logged `[LOCAL-854] tile miss` ×3;
  pass 2 logged `[LOCAL-854] tile hit` ×3. All 200 image/png with
  `Cache-Control: public, max-age=604800` and `ETag: W/"12-3262-1924-43072"`.
- **Validation**: `z=20` → 400, `z=1 x=5` → 400, `z=0/0/0` → 200.
- **Stale-on-origin-down**: primed `12/3262/1924` into a mounted cache, then
  restarted with an unreachable `TILE_ORIGIN`. The cached tile was still served
  **200** (43072 bytes, origin never contacted); an uncached tile (`12/9/9`)
  returned **502** with `[LOCAL-854] tile unavailable`.
- **Total OSM origin tiles fetched: ~5** (≤ 20). Container stopped, cache
  cleaned afterward.

## Process / guardrails
- Committed selectively to `LOCAL-854-tile-proxy` (no `git add -A`).
- Did not touch DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md,
  TRAVEL_PROJECTS.md. No `DELETE`, no live DB writes, no shared `audioura-*`
  containers, nothing installed on Michael's phones. Did not deploy.
