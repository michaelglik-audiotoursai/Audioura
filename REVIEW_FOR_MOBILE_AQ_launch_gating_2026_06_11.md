# For Mobile Kiro — v1 Launch Gating: Three App-Side Blockers

**Date:** 2026-06-11
**Scope:** Flutter/Dart app code — three features that must ship before public launch.
**Branch:** `services-migration`

---

## Blocker 1 — Account Deletion UI

### Current state
No account deletion capability exists. The About screen has: app info, server mode toggle, device info, "Sync User to Database", and "View Debug Logs". No delete button, no deletion API call, no confirmation dialog.

### What's needed
Google Play and Apple App Store both require apps to provide a way to delete user data. Must implement:

1. **"Delete My Account" button** in `about_screen.dart` (red, at bottom, clearly labeled)
2. **Confirmation dialog** — "This will permanently delete your account and all data. Are you sure?"
3. **API call** — `DELETE` (or `POST`) to a user-deletion endpoint via `Endpoints.url(Service.userDb, '/user/$userId')`
4. **On success**: Clear all SharedPreferences, delete local tour/news files, show confirmation snackbar, reset to fresh-install state
5. **On failure**: Show error snackbar, don't clear local data

### Files to modify
| File | Change |
|------|--------|
| `lib/screens/about_screen.dart` | Add "Delete My Account" button + confirmation dialog + deletion logic |
| `lib/config/endpoints.dart` | No change needed — `Service.userDb` already exists |

### Test criteria
- [ ] "Delete My Account" button visible in About screen
- [ ] Tapping shows confirmation dialog with cancel option
- [ ] On confirm: calls deletion endpoint, clears SharedPreferences, deletes `app_flutter/tours/` and `app_flutter/news/` directories
- [ ] After deletion: app behaves like fresh install (new user ID generated on next launch)
- [ ] On server error (no connectivity): shows error, data preserved

### Dependency
- Services team must implement `DELETE /user/<user_id>` on `user-api` (port 5003 / `Service.userDb`)

---

## Blocker 2 — News/Newsletter Cloud Paths

### Current state
News and newsletter services (`Service.news` port 5012, `Service.newsletter` port 5017) are **local-only**. The About screen explicitly states: "News/newsletters remain local until deployed." All article downloads use `Endpoints.url(Service.news, ...)` which correctly resolves to local in local mode — but in cloud mode these services are not yet on Cloud Run, so news features break.

The path healing in `my_news_screen.dart` handles stale iOS container paths (marker: `/Documents/`) but Android doesn't use that marker. The path healing does nothing on Android, which is fine as long as Android paths are stable across reinstalls.

### What's needed
Once news services are deployed to Cloud Run:

1. **Verify `Endpoints.url(Service.news, ...)` routes correctly in cloud mode** — currently it would route to `<cloud_base_url>/news-orchestrator/...` if path prefixes are ON, or bare `<cloud_base_url>/...` if OFF. Need to confirm which shape the deployed news service expects.
2. **Add `apiHeaders()` to news/newsletter download calls** — currently these calls may not include `X-API-Key` in cloud mode
3. **Android path healing** — if cloud-downloaded articles have different path structures, verify the existing heal logic handles them (or add Android-specific marker `app_flutter/`)

### Files to modify
| File | Change |
|------|--------|
| `lib/screens/home_screen.dart` | Add `apiHeaders(Service.news)` to newsletter/article download calls |
| `lib/screens/my_news_screen.dart` | Verify path healing works for Android; add `app_flutter/` marker if needed |
| `lib/config/endpoints.dart` | Verify `_cloudPaths[Service.news]` matches deployed service path |

### Test criteria
- [ ] In cloud mode: article list loads from cloud news service
- [ ] In cloud mode: article download completes and saves to local filesystem
- [ ] Article playback works after download in cloud mode
- [ ] On Android: reinstall app → previously downloaded articles still play (path healing)
- [ ] Newsletter refresh works in cloud mode

### Dependency
- Services team must deploy news-orchestrator and newsletter-processor to Cloud Run
- Gateway must route `/news/...` and `/newsletter/...` paths

---

## Blocker 3 — Existing-Tour Translation (Translate After Download)

### Current state
Translation **only** happens at download time. The flow is:
1. User selects languages in the map download dialog (`home_screen.dart`)
2. English tour is downloaded first
3. `_downloadTranslatedVersions()` calls `TranslationService.translateTour()` → downloads each translated ZIP
4. Translated tours appear as separate entries in Listen page with `is_translation: true`

**There is NO way to translate a tour that was downloaded without selecting languages.** Once on the Listen page, the only option is to delete and re-download with languages selected.

### What's needed
Add a "Translate" action to tours on the Listen page:

1. **"Translate" button/icon** on each tour in `my_tours_screen.dart` (only for non-translated tours, i.e., `is_translation != true`)
2. **Language selection dialog** — show available languages (same as download dialog)
3. **Translation flow** — call `TranslationService.translateTour(tourId: tour['tour_id'], languages: selected)` → download translated ZIPs → save as new entries
4. **Reuse existing `_downloadTranslatedVersions()` logic** from `home_screen.dart` (or extract to shared service)

### Files to modify
| File | Change |
|------|--------|
| `lib/screens/my_tours_screen.dart` | Add translate icon button per tour + language dialog + translation trigger |
| `lib/screens/home_screen.dart` | Extract `_downloadTranslatedVersions()` to a shared service (or keep calling from my_tours_screen via import) |
| (optional) `lib/services/tour_translation_helper.dart` | New file — shared translation+download logic |

### Test criteria
- [ ] Non-translated tours show a "Translate" icon on the Listen page
- [ ] Translated tours (is_translation: true) do NOT show the translate icon
- [ ] Tapping translate shows language selection dialog
- [ ] After selecting languages: translated tours appear as new entries in Listen
- [ ] Translated tours have correct `parent_tour_id` linking back to the English tour
- [ ] Translation works in both local and cloud mode

### Dependency
- Translation service must be running (port 5030 local / cloud endpoint)
- Tour must have a valid numeric `tour_id` in its metadata (UUID tours may need ID resolution first)

---

## Priority Order

1. **Account Deletion** — hard App Store/Play Store requirement, blocks submission
2. **Existing-Tour Translation** — high user value, straightforward to implement
3. **News Cloud Paths** — blocked on services deployment, implement when ready

---

## Version Bump

All three blockers land in a single version bump (or incremental if shipped separately). Do NOT bump version until code compiles and builds cleanly.
