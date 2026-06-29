# Claude Review — v1.2.9+72 Dual-Environment Networking (commit `5e96203`)

**Date:** 2026-06-03
**Reviewing:** `code_review_v1.2.9.72.md` (Mobile Amazon-Q)
**Verdict:** ✅ **The refactor is well done** — the `Endpoints` resolver is clean, the call-site migration is complete (no stray `http://$ip` literals remain in `home_screen.dart`), and the Local/Cloud toggle matches the design. **But there is one blocking bug: the cloud path prefix will 404 the cellular test as written.** Your Q1 instinct is exactly right. Fix that one thing and ship.

---

## 1. Verified good
- `endpoints.dart` is clean: single source of truth, `server_mode` switch, `Config.defaultServerIp` (no more `.217`/`.218` split), throws a clear error if `cloud_base_url` is unset.
- **Migration is complete.** A search of `home_screen.dart` for `http://$serverIp`, `:5005`, `:5017`, `:5025`, `:5012` returns **nothing** — every service call is now routed through `Endpoints`. Good, thorough conversion.
- Local mode is byte-for-byte the old behavior (`http://<ip>:<port>`), so WiFi dev is unaffected.

---

## 2. 🔴 Blocking — the `/map-delivery` path prefix 404s against the bare Cloud Run host (your Q1)

I checked the deployed service. `map_delivery_service.py` exposes its routes **at root**:
```python
@app.route('/tours-near/<lat>/<lng>', ...)   # line 96
@app.route('/download-tour/<tour_id>', ...)   # line 193
@app.route('/search-tours', ...)              # line 302
```
There is **no `/map-delivery` prefix** on the service. But `endpoints.dart:49` builds `'$cloudBase${_cloudPaths[s]}'`, and `_cloudPaths[Service.mapDelivery] = '/map-delivery'`. So in cloud mode a download URL becomes:

```
https://map-delivery-…run.app/map-delivery/download-tour/42
```

The Flask app has no route for `/map-delivery/download-tour/...` → **404**. Smoke-test step 4 ("tours load from Cloud Run over HTTPS") will fail as shipped.

**Why this happened (my fault, partly):** my design doc proposed the `/map-delivery`-style prefixes for the *single-domain `audioura.com` gateway* end state, where a gateway routes by prefix **and strips it** before forwarding, so the service still sees root routes. In the **interim**, you're hitting the bare per-service host directly — there's no gateway to strip the prefix, so it reaches Flask and 404s. The prefix is correct for the future and wrong for now.

### Fix (and how to keep "no rebuild for audioura.com")
The cleanest fix that satisfies both the interim test *and* the future gateway without a rebuild is to **gate the prefixes behind a flag** rather than hardcoding them on:

```dart
static Future<String> base(Service s) async {
  final prefs = await SharedPreferences.getInstance();
  final mode = prefs.getString('server_mode') ?? 'local';
  if (mode == 'cloud') {
    final cloudBase = (prefs.getString('cloud_base_url') ?? '').trim();
    if (cloudBase.isEmpty) throw StateError('Cloud base URL not set — open About and enter it.');
    // Interim (bare per-service host): no prefix. Gateway (audioura.com): prefixes on.
    final usePrefix = prefs.getBool('cloud_use_path_prefixes') ?? false;
    return usePrefix ? '$cloudBase${_cloudPaths[s]}' : cloudBase;
  }
  final ip = prefs.getString('server_ip') ?? Config.defaultServerIp;
  return 'http://$ip:${_localPorts[s]}';
}
```

- **Now (interim):** `cloud_use_path_prefixes = false` (default) → `cloud_base_url` + root path → `https://map-delivery-…run.app/download-tour/42` ✅ works.
- **Later (audioura.com gateway that path-routes *and strips*):** flip the flag to `true` in About → prefixes applied, gateway strips them, services see root routes. **No rebuild.**

Add a small checkbox in About's cloud section ("Use gateway path routing") wired to `cloud_use_path_prefixes`. If you'd rather not add a control yet, the minimum viable fix for this build is simply to return `cloudBase` (no prefix) in cloud mode — that unblocks the test today; reintroduce prefixes when the gateway exists.

**Reaffirm the interim limitation** (already noted in the design doc): because one `cloud_base_url` points at one host, only the service whose host you enter works in interim cloud mode. For the map-delivery test that's exactly map-delivery; newsletter/news/generation calls in cloud mode will fail until those have hosts (or the gateway lands). Expected, not a bug.

---

## 3. Answers to your other questions

**Q2 — unused `serverIp` param on `_downloadTranslatedVersions`.** Remove it and update the two callers. Dead parameters that *look* like they control routing are a future trap (someone will "fix" routing by setting it and be confused when nothing changes). It's a 2-caller edit, low risk. Do it now while it's fresh.

**Q3 — `processUri2` rename.** Cosmetic and acceptable. One thing to verify: if `_processNewsletterWithUrl` and `_processNewsletterUrl` are **separate methods**, Dart scopes locals per-function, so there is no actual conflict and you can keep `processUri` in both — the `2` suffix is unnecessary. If they're somehow in the same scope, the rename is fine. Either way, non-blocking.

**Q4 — multiple `SharedPreferences.getInstance()` per request.** No concern. `getInstance()` returns a cached singleton after the first load; subsequent calls are effectively free and return the same instance. Calling it inside `Endpoints` plus in the method is fine. No change needed.

**Q5 — `execute_sql` / `postgres/direct` in `direct_db_update.dart` & `api_tester.dart`.** Good that you did **not** migrate them to `Endpoints` — that actually makes them safer here: they still use `serverIp` directly, so in cloud mode they'd hit the **LAN IP** (unreachable off-WiFi), not the Cloud Run URL. So they can't accidentally fire raw SQL at a public endpoint. That said, defense in depth:
1. Add a prominent `// DEV-ONLY — must never reach a public/Cloud Run host` comment, and
2. Better, **guard them to no-op when `server_mode != 'local'`** so a future refactor can't repurpose them against the cloud, and
3. The real fix is to **remove these client-side raw-SQL paths entirely** — the app shouldn't issue SQL to any server. The Services side must independently never expose those endpoints publicly (I flagged the `user-api`/`:5003` service in my Phase E review). Treat (1)+(2) as the mobile interim and (3) as the target.

---

## 4. Bottom line
Approve the architecture; the resolver and the full call-site migration are correct and the toggle is exactly what was asked for. **One change is required before the cellular test will pass: don't apply the `/map-delivery` prefix against the bare Cloud Run host** (§2 — gate it behind a flag, defaulting off, so the `audioura.com` switch later stays rebuild-free). Q2 (remove dead param) and the Q5 dev-tool guard are worth doing in the same build; Q3/Q4 are non-issues.
