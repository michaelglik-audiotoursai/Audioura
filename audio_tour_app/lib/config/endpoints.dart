import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';
import '../services/app_attestation_service.dart';

enum Service {
  generator,       // :5000  (tour-generator; hosts POST /tour/share — LOCAL-579)
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
  /// DEBUG ONLY — override orchestrator port via --dart-define=WALLET_DEBUG_PORT=5102
  /// Points the app at the subscribed stack for wallet UI testing.
  /// Has NO effect unless explicitly passed at build time.
  static const _walletDebugPort = int.fromEnvironment('WALLET_DEBUG_PORT');

  static final _localPorts = {
    Service.generator: 5000,
    Service.orchestrator: _walletDebugPort > 0 ? _walletDebugPort : 5002,
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
    Service.generator: '/generator',
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

  /// Subscribed cloud base URL — the Subscribed build's OWN gateway/stack
  /// (D708). Subscribed is a separate deployment with its own services
  /// (user-api, communities, IAP verify, recovery, pricing/role, reports,
  /// moderation) that Beta's gateway (`_defaultCloudBaseUrl`) does not route; a
  /// Subscribed build must therefore NEVER fall through to Beta in cloud mode.
  /// Same host shape and network path as the other tracks
  /// (client → Cloudflare → GCP LB → gateway); only the hostname differs.
  /// Note the order: subscribed-api, not api-subscribed. Selected whenever the
  /// resolved track is 'subscribed' (i.e. Config.isSubscribedBuild). See
  /// LOCAL-764 / LOCAL-737.
  static const _subscribedCloudBaseUrl = 'https://subscribed-api.audioura.com';

  /// Gateway API key — injected at build time via --dart-define=GATEWAY_API_KEY=...
  /// NEVER hardcode the actual key in source.
  static const _builtInApiKey = String.fromEnvironment('GATEWAY_API_KEY');

  /// DEBUG ONLY — override server IP via --dart-define=DEBUG_SERVER_IP=192.168.0.136
  /// Forces local mode when set, regardless of SharedPreferences.
  static const _debugServerIp = String.fromEnvironment('DEBUG_SERVER_IP');

  /// Returns the base URL for [s] based on current server_mode.
  /// Local:  http://<server_ip>:<port>
  /// Cloud (interim, bare per-service host):  <cloud_base_url>   (no prefix)
  /// Cloud (gateway, cloud_use_path_prefixes=true):  <cloud_base_url><path_prefix>
  static Future<String> base(Service s) async {
    // DEBUG: if DEBUG_SERVER_IP is baked in, force local mode to that IP.
    if (_debugServerIp.isNotEmpty) {
      return 'http://$_debugServerIp:${_localPorts[s]}';
    }
    final prefs = await SharedPreferences.getInstance();
    final mode = prefs.getString('server_mode') ?? 'cloud';
    if (mode == 'cloud') {
      // Baked-in defaults only — never read stored URL overrides in cloud
      // mode. This ensures a dev device behaves identically to a real new
      // user. cloud_track is the one exception: it's a deliberate, visible
      // tester choice (Storied vs Beta), not a debug override. The Subscribed
      // build resolves to the 'subscribed' track (D708) and its own host.
      return baseForTrack(s, await cloudTrack());
    }
    final ip = prefs.getString('server_ip') ?? Config.defaultServerIp;
    return 'http://$ip:${_localPorts[s]}';
  }

  /// The cloud base URL for [s] given an already-resolved [track]. Pure (no I/O)
  /// so host selection can be tested for every track in one process without
  /// recompiling for each — the real [base] calls this after resolving
  /// [cloudTrack]. [s] is accepted for forward-compatibility with per-service
  /// hosts/prefixes but every current track uses a single host for all
  /// services. Beta/Storied mappings are unchanged (Track B byte-for-byte
  /// promise); 'subscribed' is the only addition. Any unknown track ⇒ Beta,
  /// matching the pre-Subscribed default.
  @visibleForTesting
  static String baseForTrack(Service s, String track) {
    switch (track) {
      case 'subscribed':
        return _subscribedCloudBaseUrl;
      case 'storied':
        return _storiedCloudBaseUrl;
      default:
        return _defaultCloudBaseUrl;
    }
  }

  /// The track this build reports for tour provenance.
  ///
  /// For the Subscribed build (Config.isSubscribedBuild) this is always
  /// 'subscribed' — Subscribed is its own stack and track (D708), not a
  /// Stable/Preview tester toggle. For Beta/Storied builds it is the tester's
  /// chosen comparison track: 'beta' (default) or 'storied'. Only meaningful in
  /// cloud mode. See TRACK_B_STORIED_VS_BETA.md and LOCAL-737.
  static Future<String> cloudTrack() async {
    if (Config.isSubscribedBuild) return 'subscribed';
    final prefs = await SharedPreferences.getInstance();
    return Config.normalizeTrack(prefs.getString('cloud_track') ?? 'beta');
  }

  /// Sets the tester's chosen comparison track. Does not affect local mode.
  /// The Subscribed build does not use this selector (its track is fixed).
  static Future<void> setCloudTrack(String track) async {
    assert(Config.validTracks.contains(track));
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('cloud_track', track);
  }

  /// Human-facing label for a stored tour's track. Michael 2026-09-01:
  /// testers see Stable/Preview, never the internal branch names beta/storied.
  /// A missing or unknown track ⇒ Stable (that is what every older app made).
  /// Subscribed tours show "Subscribed" (LOCAL-737 / D708).
  /// When [buildNumber] is present it is appended as "(vNNN)" so a tour listed
  /// a week later still identifies the exact build that produced it; when
  /// absent (older tours, or before services populated it) the bare name shows.
  /// Never compute the number in the app — it is read from the tour record.
  static String trackLabel(String? track, {int? buildNumber}) {
    final name = track == 'storied'
        ? 'Preview'
        : (track == 'subscribed' ? 'Subscribed' : 'Stable');
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

  /// Convenience DELETE with apiHeaders and an optional JSON body (used e.g. by
  /// the owner-deletes-a-member-less-community call, LOCAL-702 / D663 §1 d).
  static Future<http.Response> delete(Service s, String path, {Map<String, dynamic>? body, Duration? timeout}) async {
    final uri = await url(s, path);
    final headers = await apiHeaders(s, requestBody: body);
    final request = http.delete(uri, headers: headers,
        body: body != null ? jsonEncode(body) : null);
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
    return s == Service.orchestrator ||
        s == Service.translation ||
        s == Service.generator;
  }

  // ---------------------------------------------------------------------------
  // LOCAL-694 — graceful degradation against a Storied backend.
  //
  // The Storied server (what GCloud runs today) does not host every endpoint
  // the Subscribed app calls. Replaying all 66 calls against a local Storied
  // stack (SUBMISSION_LOCAL-694.md) showed three shapes the app must survive
  // WITHOUT crashing or showing a raw/blank error:
  //   1. 404 / 405 / 501 — the route is missing on Storied. Flask answers with
  //      an HTML body (NOT JSON), so any jsonDecode(body) on the error path
  //      throws FormatException. 27 of the app's calls land here.
  //   2. Connection refused — the whole service is absent on Storied (userDb,
  //      voice, generator, custom-audio, tour-id-resolution: 23 calls). This
  //      surfaces as SocketException / ClientException.
  //   3. 5xx with a JSON body — a server-side error; still parseable.
  //
  // These helpers are the ONE central place that decides "is this a feature
  // the server simply doesn't offer?" and turns it into either a friendly
  // message or a null/empty the caller can render as an empty state. Prefer
  // these over ad-hoc per-call catches.
  // ---------------------------------------------------------------------------

  /// The single user-facing line for a feature the Storied server lacks.
  /// Michael's wording (D661): testers see "Preview", never branch names.
  static const String featureUnavailableMessage =
      'This feature is available in Preview only.';

  /// True when a response means "this ROUTE is not offered by this backend"
  /// (i.e. the feature is unavailable, Preview-only) as opposed to an ordinary
  /// "not found" the server deliberately returned.
  ///
  /// LOCAL-694B (LEAD review 2026-10-14): a bare 404 is NOT enough. On the
  /// Subscribed server an unknown community code, a deleted tour, or an unknown
  /// job all return a 404 whose body is the SERVICE'S OWN JSON error
  /// (e.g. `{"error":"not_found"}`, `{"error":"Job not found"}`). That is a
  /// normal not-found and must keep its existing message — never "Preview only".
  ///
  /// A route is MISSING only when the 404 is NOT the service's own JSON error:
  ///   (a) the GCloud API gateway's JSON `{"error":"endpoint not found",
  ///       "service":"api-gateway"}` — what GCloud returns today for an unknown
  ///       path (LEAD saw it at storied-api.audioura.com/tour-info/431), or
  ///   (b) a non-JSON body — Flask's HTML 404 page when a service is called
  ///       directly, or
  ///   (c) 405 Method Not Allowed / 501 Not Implemented (the route/verb is not
  ///       served at all; body shape is irrelevant).
  ///
  /// [body] is the raw response body; pass it so a JSON 404 can be told apart
  /// from an HTML/gateway 404. When [body] is omitted a 404 is treated
  /// conservatively as a normal not-found (NOT feature-unavailable), so callers
  /// that cannot supply a body never over-report "Preview only".
  static bool isRouteMissing(int statusCode, [String? body]) {
    // 405/501: the route (or that verb on it) simply is not served. Missing.
    if (statusCode == 405 || statusCode == 501) return true;
    if (statusCode != 404) return false;

    // 404: decide by body. A JSON object that is the service's own error is a
    // NORMAL not-found; the gateway's "endpoint not found" is the one JSON 404
    // that still means missing.
    final map = tryDecodeMap(body);
    if (map == null) {
      // Non-JSON (HTML 404 page) or empty body => route missing (case b).
      return true;
    }
    // Case (a): the GCloud gateway's own 404 envelope.
    if (map['service'] == 'api-gateway' &&
        map['error'] == 'endpoint not found') {
      return true;
    }
    // Any other JSON 404 is the service's own not-found => NORMAL, keep message.
    return false;
  }

  /// @Deprecated LOCAL-694B. Status-only classifier retained ONLY so a 405/501
  /// (where the body never matters) can be checked without a body. For 404 this
  /// returns false, because a 404 cannot be classified from the status alone —
  /// use [isRouteMissing(statusCode, body)] instead. Do not use this for 404s.
  static bool isFeatureUnavailableStatus(int statusCode) =>
      statusCode == 405 || statusCode == 501;

  /// Safely decode a response body as a JSON object. Returns null when the body
  /// is empty, not valid JSON (e.g. a Flask HTML 404 page), or not a JSON
  /// object. NEVER throws — this is the defensive replacement for a bare
  /// `jsonDecode(response.body) as Map` on any path that can see a non-200.
  static Map<String, dynamic>? tryDecodeMap(String? body) {
    if (body == null || body.isEmpty) return null;
    try {
      final decoded = jsonDecode(body);
      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
  }

  /// Safely decode a response body as a JSON list. Returns null on empty,
  /// non-JSON (HTML error page), or non-list bodies. Never throws.
  static List<dynamic>? tryDecodeList(String? body) {
    if (body == null || body.isEmpty) return null;
    try {
      final decoded = jsonDecode(body);
      return decoded is List ? decoded : null;
    } catch (_) {
      return null;
    }
  }

  /// True when [error] is a transport-level failure that, against Storied,
  /// means the whole service is absent (connection refused) or unreachable:
  /// SocketException, http.ClientException, TimeoutException. Callers that want
  /// to treat "service not on this server" the same as "route missing" can use
  /// this to map such errors to a [FeatureUnavailableException].
  static bool isServiceAbsentError(Object error) =>
      error is SocketException ||
      error is http.ClientException ||
      error is TimeoutException;

  /// GET that throws [FeatureUnavailableException] when the ROUTE is missing on
  /// the current server (gateway/HTML 404, or 405/501) or the service is absent
  /// (connection refused / unreachable). A service's OWN JSON 404 (a normal
  /// not-found, e.g. `{"error":"not_found"}`) is NOT feature-unavailable and is
  /// returned to the caller as-is for normal handling, as is any other
  /// response. See [isRouteMissing] (LOCAL-694B).
  static Future<http.Response> getOrFeatureUnavailable(
    Service s,
    String path, {
    Duration? timeout,
  }) async {
    final http.Response resp;
    try {
      resp = await get(s, path, timeout: timeout);
    } catch (e) {
      if (isServiceAbsentError(e)) {
        throw FeatureUnavailableException(service: s, path: path, cause: e);
      }
      rethrow;
    }
    if (isRouteMissing(resp.statusCode, resp.body)) {
      throw FeatureUnavailableException(
          service: s, path: path, statusCode: resp.statusCode);
    }
    return resp;
  }

  /// POST counterpart of [getOrFeatureUnavailable]. See that doc.
  static Future<http.Response> postOrFeatureUnavailable(
    Service s,
    String path, {
    required Map<String, dynamic> body,
    Duration? timeout,
  }) async {
    final http.Response resp;
    try {
      resp = await post(s, path, body: body, timeout: timeout);
    } catch (e) {
      if (isServiceAbsentError(e)) {
        throw FeatureUnavailableException(service: s, path: path, cause: e);
      }
      rethrow;
    }
    if (isRouteMissing(resp.statusCode, resp.body)) {
      throw FeatureUnavailableException(
          service: s, path: path, statusCode: resp.statusCode);
    }
    return resp;
  }
}

/// Thrown when a server endpoint the app expects is not offered by the current
/// backend (missing route on Storied, or the whole service absent). Carries a
/// user-safe [message] a screen can show directly; the service/path/status are
/// for logs only. See LOCAL-694 / [Endpoints.featureUnavailableMessage].
class FeatureUnavailableException implements Exception {
  final Service service;
  final String path;
  final int? statusCode;
  final Object? cause;

  /// A user-facing override. Defaults to the standard "Preview only" line.
  final String message;

  FeatureUnavailableException({
    required this.service,
    required this.path,
    this.statusCode,
    this.cause,
    String? message,
  }) : message = message ?? Endpoints.featureUnavailableMessage;

  @override
  String toString() =>
      'FeatureUnavailableException($service $path'
      '${statusCode != null ? ' status=$statusCode' : ''}'
      '${cause != null ? ' cause=$cause' : ''})';
}
