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
  static const _defaultCloudBaseUrl = 'https://api.audioura.com';

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
      // Use stored URL if set, otherwise fall back to compiled-in default
      final cloudBase = (prefs.getString('cloud_base_url') ?? '').trim();
      final effectiveBase = cloudBase.isNotEmpty ? cloudBase : _defaultCloudBaseUrl;
      // Path prefixes are hardcoded OFF (api.audioura.com routes by root path)
      return effectiveBase;
    }
    final ip = prefs.getString('server_ip') ?? Config.defaultServerIp;
    return 'http://$ip:${_localPorts[s]}';
  }

  /// Convenience: returns a fully-formed [Uri] for [s] + [path].
  static Future<Uri> url(Service s, String path) async =>
      Uri.parse('${await base(s)}$path');

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
      // Use stored key if set, otherwise fall back to compiled-in key from --dart-define
      final storedKey = (prefs.getString('gateway_api_key') ?? '').trim();
      final key = storedKey.isNotEmpty ? storedKey : _builtInApiKey;
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
