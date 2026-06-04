# Code Review — v1.2.9+72 Dual Environment Networking
**Date:** 2026-06-02
**Commit:** `5e96203`
**Branch:** `services-migration`
**Reviewer request from:** Android Amazon-Q

---

## What was implemented

The app previously hard-coded all server calls as `http://$serverIp:<port>/<path>`, where `serverIp` came from a single SharedPreferences key. This broke for Cloud Run, which uses HTTPS, per-service hostnames, and no port suffix.

**Solution:** Introduced a centralized `Endpoints` resolver plus a Local/Cloud toggle in the About screen.

---

## Files changed

### NEW — `lib/config/endpoints.dart`
- Defines `enum Service` with 8 values (orchestrator, userDb, mapDelivery, news, newsletter, customAudio, tourIdResolution, translation)
- `Endpoints.base(Service s)` — reads `server_mode` from SharedPreferences; returns `http://$ip:$port` for local, `$cloudBaseUrl$pathPrefix` for cloud
- `Endpoints.url(Service s, String path)` — convenience wrapper returning a `Uri`
- Cloud path prefixes: `/map-delivery`, `/orchestrator`, `/user`, `/news`, `/newsletter`, `/custom-audio`, `/tour-id`, `/translation`
- Default local IP reads from `Config.defaultServerIp` (`.218`) — no more `.217` fallbacks

### MODIFIED — `lib/screens/about_screen.dart`
- Added `_serverMode` state (`'local'` / `'cloud'`), `_cloudBaseUrlController`
- Added `_setServerMode()`, `_saveCloudBaseUrl()` methods
- Added Local/Cloud `ChoiceChip` toggle (persisted as `server_mode`)
- Local mode: existing IP field shown unchanged
- Cloud mode: editable `cloud_base_url` field shown with hint `https://api.audioura.com`, warning note about interim partial deployment
- `_testServerConnectivity()` now calls `Endpoints.url(Service.userDb, '/health')` — reflects active mode
- `_syncUserToDatabase()` now calls `Endpoints.url(Service.userDb, '/user')`
- Fixed: all `.217` fallbacks removed, now consistently uses `.218` via `Config.defaultServerIp`

### MODIFIED — `lib/screens/home_screen.dart`
All service calls migrated to `Endpoints`:
| Method | Old | New |
|---|---|---|
| `_loadNearbyTours` | `http://$ip:5005/tours-near/...` | `Endpoints.url(Service.mapDelivery, ...)` |
| `_downloadTour` | `http://$ip:5005/download-tour/$id` | `Endpoints.url(Service.mapDelivery, ...)` |
| `_downloadSingleTour` | `http://$ip:5005/download-tour/$id` | `Endpoints.url(Service.mapDelivery, ...)` |
| `_downloadSingleTourSilent` | `http://$ip:5005/download-tour/$id` | `Endpoints.url(Service.mapDelivery, ...)` |
| `_downloadTranslatedVersions` | `http://$ip:5005/download-tour/$id` | `Endpoints.url(Service.mapDelivery, ...)` |
| `_searchTours` | `http://$ip:5005/search-tours?...` | `Endpoints.url(Service.mapDelivery, ...)` |
| `_resolveParentEditTourId` | `http://$ip:5025/tour/$id/resolve` | `Endpoints.url(Service.tourIdResolution, ...)` |
| `_saveTourToMyTours` | `http://$ip:5025/tour/$id/resolve` | `Endpoints.url(Service.tourIdResolution, ...)` |
| `_loadNewsletters` | `http://$ip:5017/newsletters_v2` | `Endpoints.url(Service.newsletter, ...)` |
| `_processNewsletterWithUrl` | `http://$ip:5017/process_newsletter` | `Endpoints.url(Service.newsletter, ...)` |
| `_processNewsletterUrl` | `http://$ip:5017/process_newsletter` | `Endpoints.url(Service.newsletter, ...)` |
| `_processNewsletter` | `http://$ip:5017/get_articles_by_newsletter_id` | `Endpoints.url(Service.newsletter, ...)` |
| `_downloadAndSaveArticle` | `http://$ip:5012/download/$id?...` | `Endpoints.base(Service.news)` + string concat |

All now-unused `serverIp` local variable declarations removed.

### MODIFIED — `lib/services/custom_audio_service.dart`
- `_getServerUrl()` simplified to `await Endpoints.base(Service.customAudio)` — single source of truth

---

## Behavior in each mode

**Local WiFi (default, `server_mode=local`)**
- Identical to previous behavior: `http://192.168.0.218:<port>/...`
- User can still edit the IP field in About → saves to `server_ip`

**Cloud (`server_mode=cloud`)**
- All service calls go to `<cloud_base_url>/<service-path-prefix>/<endpoint>`
- Example: if `cloud_base_url=https://map-delivery-ixkp5nkrlq-uc.a.run.app`, map-delivery calls become `https://map-delivery-ixkp5nkrlq-uc.a.run.app/map-delivery/download-tour/42`
- HTTPS — no cleartext permission needed in cloud mode

---

## Questions for Claude to review

1. **Cloud path prefix double-segment**: In the interim (single Cloud Run host for map-delivery), the URL becomes `https://map-delivery-xxx.run.app/map-delivery/download-tour/42` — the host already implies map-delivery, and the path prefix `/map-delivery` adds a redundant segment. Will the Cloud Run service route on `/map-delivery/...` correctly, or should the cloud path for `Service.mapDelivery` be empty string `''` until a gateway is in place?

2. **`_downloadTranslatedVersions` still takes `serverIp` parameter**: The parameter is now unused (the method uses `Endpoints` internally). It was left in the signature to avoid breaking the two callers (`_downloadSingleTour`, `_downloadSingleTourSilent`). Should it be removed from the signature and callers updated, or left for now?

3. **`_processNewsletterUrl` uses `processUri2` variable name**: This was necessary to avoid a naming conflict with `processUri` already declared in `_processNewsletterWithUrl` in the same compilation unit. Is this acceptable or should the method be refactored?

4. **`prefs` variable retained in some methods**: Some methods (e.g. `_processSelectedArticles`, `_downloadAndSaveArticle`) still get `prefs` but only use it for non-server operations (reading saved lists, writing back). This is correct — `Endpoints` reads its own `prefs` instance internally. Any concern about multiple `SharedPreferences.getInstance()` calls per request?

5. **Security note from Claude design doc (§6)**: `direct_db_update.dart` and `api_tester.dart` still contain `/execute_sql` and `/postgres/direct` endpoints that go through `serverIp` directly (not migrated to `Endpoints`). These are dev-only tools, but they must NOT be reachable via Cloud Run. Should those files be flagged with a comment warning, or is the Services team handling the deployment-side guard?

---

## Smoke test for this version

1. **Local mode (default)**: Open app → Home → tours load on map from `192.168.0.218:5005` ✅
2. **About screen**: See Local/Cloud toggle, default = Local WiFi ✅
3. **Switch to Cloud mode**: Enter `https://map-delivery-ixkp5nkrlq-uc.a.run.app` → Save → toggle to Cloud
4. **Off WiFi (cellular)**: Open app → Home → tours load from Cloud Run endpoint over HTTPS
5. **Switch back to Local**: Toggle back → tours load from LAN again
6. **Test connection button**: Hits `/health` on whichever mode is active
7. **Voice search mic**: Unrelated to networking — should still work as per A#78

---

## Version
`pubspec.yaml`: `1.2.9+72`
Commit: `5e96203` on `services-migration`
