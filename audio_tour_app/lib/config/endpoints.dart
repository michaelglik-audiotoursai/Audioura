import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';
import '../services/app_attestation_service.dart';

enum Service {
  orchestrator,    // :5002
  userDb,          // :5003
  mapDelivery,     // :5005
  treats,          // :5007
  voice,           // :5008
  news,            // :5012
  newsletter,      // :5017
  tourEditing,     // :5022
  customAudio,     // :5023
  tourIdResolution,// :5025
  translation,     // :5030
}

class Endpoints {
  static const _localPorts = {
    Service.orchestrator: 5002,
    Service.userDb: 5003,
    Service.mapDelivery: 5005,
    Service.treats: 5007,
    Service.voice: 5008,
    Service.news: 5012,
    Service.newsletter: 5017,
    Service.tourEditing: 5022,
    Service.customAudio: 5023,
    Service.tourIdResolution: 5025,
    Service.translation: 5030,
  };

  // Path prefix appended to cloud_base_url for each service.
  // Used when a single gateway/domain routes all services.
  static const _cloudPaths = {
    Service.orchestrator: '/orchestrator',
    Service.userDb: '/user',
    Service.mapDelivery: '/map-delivery',
    Service.treats: '/treats',
    Service.voice: '/voice',
    Service.news: '/news',
    Service.newsletter: '/newsletter',
    Service.tourEditing: '/tour-editing',
    Service.customAudio: '/custom-audio',
    Service.tourIdResolution: '/tour-id',
    Service.translation: '/translation',
  };

  /// Default cloud base URL — baked into the build, no user input needed.
  /// This is BETA. Byte-for-byte unchanged behaviour is the one hard
  /// requirement of the Storied-vs-Beta comparison feature (Track B) — never
  /// edit this value or the fallback behaviour below as part of adding Storied.
  static const _defaultCloudBaseUrl = 'https://api.audioura.com';

  /// Storied cloud base URL — the parallel, independently-deployable track
  /// testers can opt into to compare tour quality against Beta. Same request/
  /// response contract as Beta; only the base URL differs. See
  /// TRACK_B_STORIED_VS_BETA.md and DECISIONS.md D347+.
  /// Custom domain, live and verified (Michael 2026-09-01): it takes the SAME
  /// network path as Beta — client → Cloudflare → GCP LB → gateway — differing
  /// only in hostname. Do NOT revert to the bare Cloud Run URL: that returns
  /// 200 but bypasses Cloudflare (no WAF/DDoS, invisible in monitoring, wrong
  /// TLS chain), which breaks the like-for-like comparison this feature exists
  /// for. Note the order: storied-api, not api-storied.
  static const _storiedCloudBaseUrl = 'https://storied-api.audioura.com';

  /// Gateway API key — injected at build time via --dart-define=GATEWAY_API_KEY=...
  /// NEVER hardcode the actual key in source.
  static const _builtInApiKey = String.fromEnvironment('GATEWAY_API_KEY');

  /// Returns the base URL for [s] based on current server_mode.
  /// Local:  http://<server_ip>:<port>
  /// Cloud (interim, bare per-service host):  <cloud_base_url>   (no prefix)
  /// Cloud (gateway, cloud_use_path_prefixes=true):  <cloud_base_url><path_prefix>
  static Future<String> base(Service s) async {
    final prefs = await SharedPreferences.getInstance();
    final mode = prefs.getString('server_mode') ?? 'cloud';
    if (mode == 'cloud') {
      // Baked-in defaults only — never read stored URL overrides in cloud
      // mode. This ensures a dev device behaves identically to a real new
      // user. cloud_track is the one exception: it's a deliberate, visible
      // tester choice (Storied vs Beta), not a debug override.
      return await cloudTrack() == 'storied' ? _storiedCloudBaseUrl : _defaultCloudBaseUrl;
    }
    final ip = prefs.getString('server_ip') ?? Config.defaultServerIp;
    return 'http://$ip:${_localPorts[s]}';
  }

  /// The tester's chosen comparison track: 'beta' (default) or 'storied'.
  /// Only meaningful in cloud mode. See TRACK_B_STORIED_VS_BETA.md.
  static Future<String> cloudTrack() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('cloud_track') ?? 'beta';
  }

  /// Sets the tester's chosen comparison track. Does not affect local mode.
  static Future<void> setCloudTrack(String track) async {
    assert(track == 'beta' || track == 'storied');
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('cloud_track', track);
  }

  /// Human-facing label for a stored tour's track. Michael 2026-09-01:
  /// testers see Stable/Preview, never the internal branch names beta/storied.
  /// A missing or unknown track ⇒ Stable (that is what every older app made).
  /// When [buildNumber] is present it is appended as "(vNNN)" so a tour listed
  /// a week later still identifies the exact build that produced it; when
  /// absent (older tours, or before services populated it) the bare name shows.
  /// Never compute the number in the app — it is read from the tour record.
  static String trackLabel(String? track, {int? buildNumber}) {
    final name = track == 'storied' ? 'Preview' : 'Stable';
    return buildNumber != null ? '$name (v$buildNumber)' : name;
  }

  /// Whether a stored track should render as the Preview (Storied) track.
  /// Missing/unknown ⇒ false (Stable), matching backward-compat behaviour.
  static bool isPreviewTrack(String? track) => track == 'storied';

  /// Convenience: returns a fully-formed [Uri] for [s] + [path].
  static Future<Uri> url(Service s, String path) async =>
      Uri.parse('${await base(s)}$path');

  /// Convenience GET with apiHeaders included automatically.
  static Future<http.Response> get(Service s, String path, {Duration? timeout}) async {
    final uri = await url(s, path);
    final headers = await apiHeaders(s);
    final request = http.get(uri, headers: headers);
    return timeout != null ? request.timeout(timeout) : request;
  }

  /// Convenience POST with apiHeaders included automatically.
  static Future<http.Response> post(Service s, String path, {required Map<String, dynamic> body, Duration? timeout}) async {
    final uri = await url(s, path);
    final headers = await apiHeaders(s, requestBody: body);
    final request = http.post(uri, headers: headers, body: jsonEncode(body));
    return timeout != null ? request.timeout(timeout) : request;
  }

  /// Returns the correct news article download URI, handling the cloud path
  /// difference: local uses /download/<id>, cloud gateway uses /news-download/<id>.
  static Future<Uri> newsDownloadUrl(String articleId, String userId) async {
    final prefs = await SharedPreferences.getInstance();
    final mode = prefs.getString('server_mode') ?? 'cloud';
    final baseUrl = await base(Service.news);
    final path = mode == 'cloud' ? '/news-download/$articleId' : '/download/$articleId';
    return Uri.parse('$baseUrl$path').replace(queryParameters: {'user_id': userId});
  }

  /// Returns the correct news status polling URI.
  /// Local: /status/<id>, Cloud: /news-status/<id>
  static Future<Uri> newsStatusUrl(String articleId) async {
    final prefs = await SharedPreferences.getInstance();
    final mode = prefs.getString('server_mode') ?? 'cloud';
    final baseUrl = await base(Service.news);
    final path = mode == 'cloud' ? '/news-status/$articleId' : '/status/$articleId';
    return Uri.parse('$baseUrl$path');
  }

  /// Returns HTTP headers for [s]. In cloud mode, adds X-API-Key for
  /// cost-bearing/write endpoints (orchestrator, translation).
  /// Local mode: Content-Type only (LAN services don't require a key).
  /// If [requestBody] is provided and [s] is a protected service,
  /// attaches X-App-Attestation token (Phase 1-2 attestation).
  static Future<Map<String, String>> apiHeaders(Service s, {Map<String, dynamic>? requestBody}) async {
    final prefs = await SharedPreferences.getInstance();
    final headers = {'Content-Type': 'application/json'};
    final mode = prefs.getString('server_mode') ?? 'cloud';
    if (mode == 'cloud') {
      // ALWAYS use baked-in key — never read stored overrides in cloud mode.
      final key = _builtInApiKey;
      if (key.isNotEmpty) headers['X-API-Key'] = key;

      // Attestation for cost-bearing endpoints only
      if (_isProtectedService(s) && requestBody != null) {
        final token = await AppAttestationService.getToken(requestBody);
        if (token != null) headers['X-App-Attestation'] = token;
      }
    }
    return headers;
  }

  /// Services that incur cost and require attestation in production.
  static bool _isProtectedService(Service s) {
    return s == Service.orchestrator || s == Service.translation;
  }
}
