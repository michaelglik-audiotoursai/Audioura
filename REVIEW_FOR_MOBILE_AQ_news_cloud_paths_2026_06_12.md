# For Mobile Amazon-Q — News Cloud Paths (wire the app to cloud news)

**Date:** 2026-06-12
**From:** Claude (independent reviewer)
**Why now:** The **news services pipeline is live and verified end-to-end in the cloud** (gateway → orchestrator → generator → processor → polly-tts → 200, on `audioura:v24`). The only thing left for **Audio mode** to work in the July-1 Beta is the **app**: it still treats news as local-only in cloud mode ("News/newsletters remain local until deployed"). This is launch-blocking — news is half the app.

---

## Scope

Make the app use the **cloud** news endpoints when in cloud mode, the same way tours already do. Backend is ready and routed; this is app wiring only.

**Cloud news endpoints (gateway, root-path routed, API-key gated):**
- `POST /generate-news`
- `GET /news-status/<id>`
- `GET /news-articles`
- `GET /news-download/<id>`
(Newsletter equivalents on `Service.newsletter` if newsletters are in Beta scope.)

## Files to modify
| File | Change |
|------|--------|
| `lib/screens/home_screen.dart` | Use `Endpoints.url(Service.news, ...)` for news calls in cloud mode; add `Endpoints.apiHeaders(Service.news)` to news/newsletter requests. |
| `lib/screens/my_news_screen.dart` | Remove the "news stays local" gating; verify Android path healing for cloud-downloaded articles. |
| `lib/config/endpoints.dart` | Confirm `_cloudPaths[Service.news]` and the path shape match the deployed gateway routes above (prefixes are OFF by default → bare `<cloudBase>/<path>`). |

## Action items
- [ ] In **cloud mode**, point the news calls at `Service.news` cloud endpoints (not the local server). Remove/replace the "News/newsletters remain local until deployed" limitation.
- [ ] Attach `apiHeaders(Service.news)` (the `X-API-Key`) to article list + download + generate calls in cloud mode.
- [ ] Confirm the app's news paths exactly match the gateway public paths (`/generate-news`, `/news-status/<id>`, `/news-articles`, `/news-download/<id>`).
- [ ] Verify Android path healing works for cloud-downloaded articles (add an `app_flutter/` marker if the heal logic needs it).
- [ ] (If newsletters are in Beta) do the same for `Service.newsletter`.

## Test criteria (cloud mode, real device)
- [ ] Article list loads from the cloud news service.
- [ ] Generating a news article completes (200) and the audio downloads + saves locally.
- [ ] Playback works after download in cloud mode.
- [ ] Reinstall on Android → previously downloaded articles still play (path healing).
- [ ] (If in scope) newsletter refresh + playback work in cloud mode.

## Notes
- Backend is confirmed working (v24); if a call fails, it's almost certainly an **app-side** path/header mismatch, not the server.
- Minor future item (not this task): `/generate-news` is cost-bearing — news quota already enforces fail-closed, and attestation can be extended to it later (post-launch, when enforcement turns on).

**Done = the cloud-mode end-to-end test passes on a real device.** This is the last piece for Audio mode in the Beta.
