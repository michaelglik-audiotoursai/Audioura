// [LOCAL-598] Entitlements client — the app's view of the subscription-levels
// model (SUBSCRIPTION_LEVELS.md, D613).
//
// Talks to the LOCAL-595 user-api endpoints (Service.userDb):
//   GET  /entitlements/me?user_id=...  -> level, allowances left, anniversary,
//                                         warn_renewal, renewal_prompt, can_sell
//   POST /entitlements/app-open {user_id}  -> record activity + the same payload
//   POST /entitlements/lapse    {user_id}  -> drop to L1
//
// The purchase-grant call (/purchases/verify) lives in IapService, next to the
// StoreKit flow that produces the signed transaction.
//
// This file is deliberately thin and free of Flutter imports so the parsing can
// be unit-tested directly. The parse is defensive: a missing or malformed field
// never throws — the model falls back to safe values (level 'l1', empty
// allowances, no prompts), because the UI must degrade gracefully if the user-
// api is briefly unreachable or returns an older shape.

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config/endpoints.dart';
import '../screens/debug_log_viewer_screen.dart';

/// The remaining allowances for the current level, as the user-api reports them
/// under `allowances_left`. Every field is optional — which keys are present
/// depends on the level (period levels report day/month tour counts; pack
/// levels report pack units). Absent means "not applicable at this level".
class Allowances {
  final int? toursTodayLeft;
  final int? toursThisMonthLeft;
  final int? freshLeft;
  final int? editsLeft;
  final int? opsLeft;

  const Allowances({
    this.toursTodayLeft,
    this.toursThisMonthLeft,
    this.freshLeft,
    this.editsLeft,
    this.opsLeft,
  });

  static const Allowances empty = Allowances();

  factory Allowances.fromJson(Map<String, dynamic>? json) {
    if (json == null) return empty;
    int? asInt(dynamic v) => v is int ? v : (v is num ? v.toInt() : null);
    return Allowances(
      toursTodayLeft: asInt(json['tours_today_left']),
      toursThisMonthLeft: asInt(json['tours_this_month_left']),
      freshLeft: asInt(json['fresh_left']),
      editsLeft: asInt(json['edits_left']),
      opsLeft: asInt(json['ops_left']),
    );
  }

  bool get isEmpty =>
      toursTodayLeft == null &&
      toursThisMonthLeft == null &&
      freshLeft == null &&
      editsLeft == null &&
      opsLeft == null;
}

/// The device's entitlement snapshot. Parsed from /entitlements/me and
/// /entitlements/app-open (identical payload shape).
class Entitlements {
  /// 'l1' | 'l2' | 'l3' | 'l4' | 'tester'. Defaults to 'l1' (install level).
  final String level;

  /// ISO-8601 string of the anniversary, or null if the device has no pack.
  final String? anniversaryAt;

  final Allowances allowances;

  /// Within 3 days of the anniversary (and not yet due): show the one-time
  /// banner that nothing renews automatically.
  final bool warnRenewal;

  /// At or past the anniversary: show the renew-or-lapse sheet.
  final bool renewalPrompt;

  /// Whether this level may sell tours (L4 only, flag-gated feature).
  final bool canSell;

  const Entitlements({
    required this.level,
    required this.anniversaryAt,
    required this.allowances,
    required this.warnRenewal,
    required this.renewalPrompt,
    required this.canSell,
  });

  /// Safe default used when the user-api is unreachable: install level, no
  /// prompts, no allowances. The app treats this as "free, nothing to warn
  /// about" so a transient network error never pops a sheet or blocks the UI.
  static const Entitlements unknown = Entitlements(
    level: 'l1',
    anniversaryAt: null,
    allowances: Allowances.empty,
    warnRenewal: false,
    renewalPrompt: false,
    canSell: false,
  );

  factory Entitlements.fromJson(Map<String, dynamic> json) {
    final lvl = json['level'];
    return Entitlements(
      level: (lvl is String && lvl.isNotEmpty) ? lvl : 'l1',
      anniversaryAt: json['anniversary_at'] is String
          ? json['anniversary_at'] as String
          : null,
      allowances: Allowances.fromJson(
          json['allowances_left'] is Map<String, dynamic>
              ? json['allowances_left'] as Map<String, dynamic>
              : null),
      warnRenewal: json['warn_renewal'] == true,
      renewalPrompt: json['renewal_prompt'] == true,
      canSell: json['can_sell'] == true,
    );
  }

  /// Parsed anniversary date, or null if absent/unparseable.
  DateTime? get anniversary {
    final a = anniversaryAt;
    if (a == null) return null;
    return DateTime.tryParse(a);
  }

  /// Human-facing plan name for the levels model.
  String get levelLabel {
    switch (level) {
      case 'l1':
        return 'Free (install)';
      case 'l2':
        return 'Free';
      case 'l3':
        return '\$10 pack';
      case 'l4':
        return '\$25 round';
      case 'tester':
        return 'Tester';
      default:
        return level;
    }
  }
}

class EntitlementsService {
  /// Reads the single stored device id (same key the generate call uses).
  static Future<String> _userId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('user_id') ?? '';
  }

  /// GET /entitlements/me. Returns [Entitlements.unknown] on any failure
  /// (missing id, network error, non-200, malformed body) — never throws.
  static Future<Entitlements> me() async {
    final userId = await _userId();
    if (userId.isEmpty) return Entitlements.unknown;
    try {
      final base = await Endpoints.base(Service.userDb);
      final uri = Uri.parse('$base/entitlements/me')
          .replace(queryParameters: {'user_id': userId});
      final resp = await http
          .get(uri, headers: await Endpoints.apiHeaders(Service.userDb))
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode == 200) {
        return Entitlements.fromJson(
            jsonDecode(resp.body) as Map<String, dynamic>);
      }
      await DebugLogHelper.addDebugLog(
          'ENTITLEMENTS: me() non-200 ${resp.statusCode}');
      return Entitlements.unknown;
    } catch (e) {
      await DebugLogHelper.addDebugLog('ENTITLEMENTS: me() error: $e');
      return Entitlements.unknown;
    }
  }

  /// POST /entitlements/app-open — records activity and returns the current
  /// snapshot (used to drive the renewal sheet / warning banner on launch and
  /// resume). Returns null on failure so the caller can simply do nothing.
  static Future<Entitlements?> appOpen() async {
    final userId = await _userId();
    if (userId.isEmpty) return null;
    try {
      final resp = await Endpoints.post(
        Service.userDb,
        '/entitlements/app-open',
        body: {'user_id': userId},
        timeout: const Duration(seconds: 15),
      );
      if (resp.statusCode == 200) {
        return Entitlements.fromJson(
            jsonDecode(resp.body) as Map<String, dynamic>);
      }
      await DebugLogHelper.addDebugLog(
          'ENTITLEMENTS: app-open non-200 ${resp.statusCode}');
      return null;
    } catch (e) {
      await DebugLogHelper.addDebugLog('ENTITLEMENTS: app-open error: $e');
      return null;
    }
  }

  /// POST /entitlements/lapse — drop to L1 when the user declines to renew.
  /// Returns true on success.
  static Future<bool> lapse() async {
    final userId = await _userId();
    if (userId.isEmpty) return false;
    try {
      final resp = await Endpoints.post(
        Service.userDb,
        '/entitlements/lapse',
        body: {'user_id': userId},
        timeout: const Duration(seconds: 15),
      );
      return resp.statusCode == 200;
    } catch (e) {
      await DebugLogHelper.addDebugLog('ENTITLEMENTS: lapse error: $e');
      return false;
    }
  }
}
