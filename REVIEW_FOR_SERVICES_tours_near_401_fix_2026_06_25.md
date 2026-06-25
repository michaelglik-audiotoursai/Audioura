# Review request (for Services Kiro) — `/tours-near` 401: home page shows no nearby tours

**Author:** Claude (independent reviewer)
**Status:** fix applied to working tree, **UNCOMMITTED** — please review, then commit.
**Files touched:** `audio_tour_app/lib/screens/home_screen.dart`
**Related task:** ClickUp `wdvrdaw27b`

---

## 1. Symptom (what Sir Michael observed)
On v2.1.1+15 against the current (locked) gateway:
- **DB validation works, generating a new tour works.**
- **Home page shows NO nearby tours for the current location → 401.**
  - App log: `HOME: Requesting tours from: https://api.audioura.com/tours-near/42.3086149/-71.1942819?radius=50` → `Response status: 401`.
- Relocating to **Nice, France showed tours**; resetting to the current location showed none.

The key fact: it is **NOT** a blanket auth failure — generation and DB calls succeed, so the app *is* carrying the API key on those. Only specific calls fail.

## 2. Investigation
1. A wrong/empty API key would 401 **every** call. Generation + DB succeed → the baked key is correct. So the 401 is **call-specific**, not key-chain-wide.
2. "Nice works" is a **cache artifact**: `home_screen.dart` caches tours on a successful load (`prefs.setString('cached_tours', ...)`). Nice tours were cached during earlier testing (when the gateway was open). The current location has no cache → it forces a **live** `/tours-near` call → 401.
3. Inspected the live call in `_loadNearbyTours()`:
   ```dart
   final uri = await Endpoints.url(Service.mapDelivery, '/tours-near/${lat}/${lng}?radius=50');
   final response = await http.get(
     uri,
     headers: {'Content-Type': 'application/json'},   // ← header map present, but NO X-API-Key
   ).timeout(Duration(seconds: 10));
   ```
   The call sends a `headers:` map — but it's only `Content-Type`, **not** `Endpoints.apiHeaders(...)`, so **no `X-API-Key`** → 401 on the locked gateway.
4. Grepped for the same pattern across the app — **3 cloud calls in `home_screen.dart`** had it, all `Service.mapDelivery`:
   - `:324` → `/tours-near` (nearby tours)
   - `:1070` → `/download-tour/$tourId`
   - `:1453` → `/search-tours`
   (The 13th `http.get` in the file, line ~139, is the external **OpenStreetMap Nominatim** geocoder — correctly keyless; left unchanged.)

## 3. Root cause
These calls were **left keyless** during the earlier "X-API-Key on all requests" work. Both that audit and my review missed them because each call **had a `headers:` argument** — just the wrong one (`Content-Type` only). The audit checked *"has headers"* instead of *"uses `apiHeaders`."* On the previously-open gateway they worked; once the gateway was locked, they began to 401.

## 4. Solution (the change to review)
In `home_screen.dart`, replaced the bare header map with the shared auth helper on all three cloud calls:
```diff
- headers: {'Content-Type': 'application/json'},
+ headers: await Endpoints.apiHeaders(Service.mapDelivery),
```
`Endpoints.apiHeaders(s)` returns `Content-Type` + the baked `X-API-Key` (in cloud mode) + attestation token where applicable — so this restores the key without dropping `Content-Type`. `Service.mapDelivery` matches each call's `Endpoints.url(Service.mapDelivery, …)`. `Endpoints` is already imported; the calls are already `async`/awaited.

## 5. Verification done
- `grep "headers: {'Content-Type'" home_screen.dart` → **0 remaining**.
- `home_screen.dart`: 13 `http.get/post` calls, 12 now use `apiHeaders`; the 1 without is the external OSM geocoder (correct).

## 6. What to review / finish (Services Kiro)
1. **Confirm the diff is correct** in committed code after you commit it: the three calls use `apiHeaders(Service.mapDelivery)`; no `Content-Type`-only cloud calls remain in `home_screen.dart`; build still compiles.
2. **Commit + push** (explicit add): `git add audio_tour_app/lib/screens/home_screen.dart` → commit → push `services-migration`.
3. **One sibling still keyless:** `services/tour_status_service.dart:29` (PUT `/user/$userId`) — should become `apiHeaders(Service.userDb)`.
4. **Audit + state disposition** of the remaining `headers: {'Content-Type'}` hits and confirm they are NOT cloud-reachable: `api_tester.dart` (dev), `map_service.dart` (dead?), `tour_editing_service.dart` (gated in cloud?).
5. Final check: `git grep "headers: {'Content-Type'" audio_tour_app/lib` returns **0 cloud-call** hits.

## 7. Device verification (Sir Michael)
On a fresh build: the home page shows **nearby tours for the current location** (no 401), and downloading a community tour + tour search both work.
