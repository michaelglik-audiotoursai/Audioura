# Mobile App Changes — Run Audioura Against BOTH Local WiFi and Cloud Run

**For:** Mobile Amazon-Q
**From:** Claude
**Date:** 2026-06-02
**Goal:** Let the app talk to (1) the current local server `192.168.0.218` over WiFi **and** (2) the Cloud Run test endpoints (e.g. `https://map-delivery-ixkp5nkrlq-uc.a.run.app`) over cellular — without breaking local dev.

---

## 1. The core problem (read this first)

The app's entire networking model assumes **one host, many ports, plain HTTP**:

```dart
// scattered across the app:
'http://$serverIp:5005/download-tour/$tourId'   // map-delivery
'http://$serverIp:5002/download/$jobId'         // orchestrator
'http://$serverIp:5017/newsletters_v2'          // newsletter processor
```

`serverIp` is a single value read from `SharedPreferences('server_ip')` (default `192.168.0.218`), and each service is reached by appending a **different port** on `http://`.

**Cloud Run breaks all three assumptions.** Each service is a **separate hostname** on **HTTPS / port 443**, with **no port suffix**:

```
https://map-delivery-ixkp5nkrlq-uc.a.run.app        (not :5005)
https://tour-orchestrator-…-uc.a.run.app            (different host, not the same IP)
https://newsletter-processor-…-uc.a.run.app         (different host again)
```

So you **cannot** just paste the Cloud Run URL into the existing "server IP" field. The current code would produce `http://map-delivery-…a.run.app:5005/...` — wrong scheme, wrong port, and a host that's only correct for *one* of the ~8 services. The fix is to stop treating the server as "IP + port" and start treating it as **a per-service base URL that depends on the active environment.**

---

## 2. How it works today (the blast radius)

`serverIp` comes from `SharedPreferences('server_ip')` (set in `about_screen.dart`, default `192.168.0.218` per `config.dart`, though several fallbacks say `.217` — see §7). Every call hardcodes `http://$serverIp:<port>`. The mobile-facing services and their ports:

| Port | Service | Example call sites |
|---|---|---|
| 5002 | tour-orchestrator (job download) | `background_service.dart`, `background_tour_monitor.dart` |
| 5003 | user / DB / health (**+ `execute_sql` — see §6**) | `tour_status_service.dart`, `direct_db_update.dart`, `about_screen.dart`, `api_tester.dart` |
| 5005 | **map-delivery** (tours-near, download-tour, search-tours) | `home_screen.dart`, `home_page_flutter_map.dart` |
| 5012 | news download | `home_screen.dart` |
| 5017 | newsletter-processor (newsletters_v2, process_newsletter, get_articles) | `home_screen.dart` |
| 5023 | custom-audio | `custom_audio_service.dart` (already uses a `_getServerUrl()` helper) |
| 5025 | tour-id-resolution (resolve) | `home_screen.dart` |
| 5030 | translation (translate-with-audio) | tour flow |

Because the `http://$serverIp:<port>` literal is duplicated across ~10 files, the right move is to **centralize URL construction** so the local-vs-cloud decision lives in one place.

---

## 3. Recommended design — a single endpoint resolver

Introduce one helper that maps a **logical service** → **base URL**, driven by an **environment mode** stored in SharedPreferences. Every call site changes from a hardcoded literal to `Endpoints.url(Service.mapDelivery, '/download-tour/$tourId')`.

```dart
// lib/config/endpoints.dart
enum Service { orchestrator, userDb, mapDelivery, news, newsletter, customAudio, tourIdResolution, translation }

class Endpoints {
  // 'local' = WiFi LAN (http + ip + port). 'cloud' = Cloud Run (https + per-service host).
  static Future<String> _mode() async =>
      (await SharedPreferences.getInstance()).getString('server_mode') ?? 'local';

  // LOCAL: one IP, per-service ports
  static const _localPorts = {
    Service.orchestrator: 5002, Service.userDb: 5003, Service.mapDelivery: 5005,
    Service.news: 5012, Service.newsletter: 5017, Service.customAudio: 5023,
    Service.tourIdResolution: 5025, Service.translation: 5030,
  };

  // CLOUD: a single EDITABLE base URL (typed in About, persisted as 'cloud_base_url')
  // plus a per-service path prefix. This is what lets Sir Michael type the test
  // domain now and 'https://api.audioura.com' later WITHOUT a rebuild.
  static const _cloudPaths = {
    Service.orchestrator: '/orchestrator', Service.userDb: '/user',
    Service.mapDelivery: '/map-delivery', Service.news: '/news',
    Service.newsletter: '/newsletter', Service.customAudio: '/custom-audio',
    Service.tourIdResolution: '/tour-id', Service.translation: '/translation',
  };

  static Future<String> base(Service s) async {
    final prefs = await SharedPreferences.getInstance();
    if ((prefs.getString('server_mode') ?? 'local') == 'cloud') {
      final cloudBase = (prefs.getString('cloud_base_url') ?? '').trim();
      if (cloudBase.isEmpty) throw StateError('Cloud base URL not set in About');
      // Single-domain path routing (audioura.com end state):
      return '$cloudBase${_cloudPaths[s]}';   // e.g. https://api.audioura.com/map-delivery
      // INTERIM (raw run.app, one host per service): see note below.
    }
    final ip = prefs.getString('server_ip') ?? '192.168.0.218';
    return 'http://$ip:${_localPorts[s]}';
  }

  static Future<Uri> url(Service s, String path) async =>
      Uri.parse('${await base(s)}$path');
}
```

Then every call site becomes:

```dart
// before:
final url = 'http://$serverIp:5005/download-tour/$tourId';
// after:
final uri = await Endpoints.url(Service.mapDelivery, '/download-tour/$tourId');
```

This keeps **local WiFi behavior identical** (default `server_mode=local`) and makes **cloud** a per-service host lookup. You can migrate call sites incrementally — start with the map-delivery ones (§5).

---

## 4. About-screen UX — two editable fields + a toggle (one build, no rebuild ever)

This is the part Sir Michael cares about most: **everything is a field he can type; nothing requires a rebuild.** Replace the single "server IP" box with:

- A **mode switch**: "Local (WiFi)" vs "Cloud (Cellular/Test)" → persisted as `server_mode`.
- **Local mode** keeps the existing editable **IP field** (`server_ip`). He can have different IPs on different WiFi networks and just type the right one — exactly as today.
- **Cloud mode** shows an editable **"Cloud base URL" field** (`cloud_base_url`). He types the test domain now (e.g. `https://map-delivery-ixkp5nkrlq-uc.a.run.app` while only that service is deployed, or a gateway domain), and later just edits it to `https://api.audioura.com` — **no rebuild**. The resolver appends each service's path (`/map-delivery`, `/orchestrator`, …).
- The connectivity check (`about_screen.dart:501`, currently hardcoded `http://$serverIp:5003/health`) should hit the **active** environment via `Endpoints.url(...)` so "Test connection" reflects whichever field is in use.

**Interim caveat (raw Cloud Run hosts).** Cloud Run currently gives each service a *different* `*-uc.a.run.app` hostname, which a single base-URL field can't express for all services at once. Two ways to handle it:
- **For the test now:** only map-delivery is deployed, so set `cloud_base_url` to the map-delivery host and only map-delivery routes there (everything else stays local / unavailable). One field is enough.
- **For full cloud:** put the services behind **one domain with path routing** (a gateway / load balancer, or subdomains) — which is the natural `audioura.com` end state. Then the single editable `cloud_base_url` field addresses every service via its path prefix, and the domain swap is a one-field edit. (If you ever need raw multi-host run.app before that gateway exists, add an optional per-service override field, but the single-domain approach is what makes Sir Michael's "just type the domain" requirement clean.)

---

## 5. Minimal path to enable Kiro's cellular test *right now*

Only **map-delivery** is deployed today, and the test is just "fetch existing tours over cellular." So you don't need to convert everything first. Smallest viable change:

1. Add the `server_mode` flag + the `Endpoints` helper above with **only** `Service.mapDelivery` populated in `_cloudHosts`.
2. Convert just the **map-delivery** call sites (`home_screen.dart` lines ~314, 1055, 1203, 1239, 1275, 1518; `home_page_flutter_map.dart` 67, 155) to `Endpoints.url(Service.mapDelivery, …)`.
3. In About, add the Local/Cloud switch.
4. Test: switch to Cloud, off WiFi, open an existing tour → it should download from `https://map-delivery-ixkp5nkrlq-uc.a.run.app/download-tour/<id>` over 443.

Note: in cloud mode, features that hit *other* (not-yet-deployed) services — tour generation (5002/5030), news (5012), newsletters (5017) — will throw the "not configured" error by design. That's expected until Kiro deploys those and you fill in `_cloudHosts`. **Tour playback itself is unaffected**: tours are downloaded as a ZIP and played from a local `file://` WebView, so once a tour is downloaded it plays offline regardless of mode.

---

## 6. ⚠️ Security must-fix before any public Cloud Run exposure

The app calls **arbitrary-SQL endpoints** directly from the client:

- `direct_db_update.dart`: `http://$serverIp:5003/execute_sql` and `:5003/sql`
- `api_tester.dart`: `:5002/sql`, `:5003/postgres/direct`

On a LAN these are merely risky. On a **public Cloud Run URL they are a critical vulnerability** — anyone on the internet could hit the public endpoint and run SQL against the database. Before any of those services are exposed publicly:

- **Do not** deploy the SQL/`execute_sql`/`postgres/direct` endpoints with public ingress, and
- **Remove or replace** these client-side direct-DB code paths with proper, authenticated service endpoints.

Please flag this to Kiro/Services as well — it's a deployment-gating item, not just a mobile concern. The mobile app should not be issuing raw SQL to a server at all in the cloud topology.

---

## 7. Other notes
- **iOS ATS / Android cleartext:** local mode uses `http://` to a LAN IP, which requires the existing ATS exception (iOS `NSAllowsLocalNetworking`) and Android cleartext permission. **Cloud mode is HTTPS**, so it's ATS-clean and needs no exception — switching to Cloud actually *relaxes* the platform networking constraints. Keep the LAN exception for local mode; don't globally enable arbitrary cleartext.
- **Default-IP inconsistency:** `config.dart` defaults to `.218` but several `about_screen.dart` fallbacks use `.217` (lines 77, 372, 496). Unify them (use `Config.defaultServerIp`) to avoid the app silently pointing at the wrong LAN box.
- **`custom_audio_service.dart`** already has a `_getServerUrl()` helper — fold it into the new `Endpoints` resolver so there's one source of truth.
- **No cert pinning needed** — Cloud Run presents valid public TLS certs.

---

## 8. Summary

One build. Two editable fields and a toggle, all in About, all runtime — **no rebuild to change either address.**

| | Local (WiFi) | Cloud (Cellular/Test/Prod) |
|---|---|---|
| Scheme | `http://` | `https://` |
| Address | **editable IP field** (`server_ip`, e.g. `192.168.0.218`) | **editable base-URL field** (`cloud_base_url`, e.g. the test host now → `https://api.audioura.com` later) |
| Port | per-service (5002, 5005, 5017, …) | 443 (implicit) |
| Per-service routing | base IP + port | base URL + path prefix (`/map-delivery`, …) |
| Selected by | `server_mode=local` | `server_mode=cloud` |

**Requirements coverage:** (1) single build with fillable fields ✅; (2) editable local IP retained ✅; (3) editable cloud domain, swappable to `audioura.com` with no rebuild ✅.

**Do:** centralize URL building in one `Endpoints` resolver, add the Local/Cloud toggle plus the two editable fields, convert the map-delivery call sites first to unblock the cellular test. **Don't:** expose the `execute_sql`/`/sql`/`postgres/direct` endpoints on any public URL (§6).
