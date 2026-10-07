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

/// [LOCAL-604 D619] One visible plan level, as the user-api reports it under
/// `levels` in /entitlements/me. The app renders these rows and hardcodes
/// nothing — the display name, price, selling flag and referral allowance all
/// come from the server (which reads them from the `plans` table). Hidden
/// levels (tester, admin) are never in this list.
class PlanLevel {
  final String planId; // 'l1' | 'l2' | 'l3' | 'l4'
  final String displayName; // 'Introduction' | 'Free' | '$10 Pack' | 'Curator'
  final double priceUsd;
  final bool canSell; // Curator: may generate tours for sale
  final int referralsAllowed; // free-subscription invitations
  final String? referralPeriod; // 'lifetime' | 'month' | null
  final int? maxStops;

  const PlanLevel({
    required this.planId,
    required this.displayName,
    required this.priceUsd,
    required this.canSell,
    required this.referralsAllowed,
    required this.referralPeriod,
    required this.maxStops,
  });

  factory PlanLevel.fromJson(Map<String, dynamic> json) {
    double asDouble(dynamic v) =>
        v is num ? v.toDouble() : (v is String ? (double.tryParse(v) ?? 0.0) : 0.0);
    int? asInt(dynamic v) => v is int ? v : (v is num ? v.toInt() : null);
    final id = json['plan_id'];
    return PlanLevel(
      planId: id is String ? id : '',
      displayName: json['display_name'] is String && (json['display_name'] as String).isNotEmpty
          ? json['display_name'] as String
          : (id is String ? id : ''),
      priceUsd: asDouble(json['price_usd']),
      canSell: json['can_sell'] == true,
      referralsAllowed: asInt(json['referrals_allowed']) ?? 0,
      referralPeriod:
          json['referral_period'] is String ? json['referral_period'] as String : null,
      maxStops: asInt(json['max_stops']),
    );
  }
}

/// The device's entitlement snapshot. Parsed from /entitlements/me and
/// /entitlements/app-open (identical payload shape).
class Entitlements {
  /// 'l1' | 'l2' | 'l3' | 'l4' | 'tester'. Defaults to 'l1' (install level).
  final String level;

  /// [LOCAL-604] The current level's human display name from the server
  /// (falls back to the level id if absent).
  final String displayName;

  /// [LOCAL-604] The ordered visible levels for the plan page (hidden levels
  /// excluded). Empty if the server did not send them (older payload); the UI
  /// then falls back to the built-in level labels.
  final List<PlanLevel> levels;

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

  /// [LOCAL-604] The device's 1-based place in the free-seat queue, or null if
  /// it is not waiting.
  final int? queuePosition;

  /// [LOCAL-604] A live, unclaimed queue offer code the device holds, or null.
  final String? pendingOfferCode;

  const Entitlements({
    required this.level,
    required this.displayName,
    required this.levels,
    required this.anniversaryAt,
    required this.allowances,
    required this.warnRenewal,
    required this.renewalPrompt,
    required this.canSell,
    required this.queuePosition,
    required this.pendingOfferCode,
  });

  /// Safe default used when the user-api is unreachable: install level, no
  /// prompts, no allowances. The app treats this as "free, nothing to warn
  /// about" so a transient network error never pops a sheet or blocks the UI.
  static const Entitlements unknown = Entitlements(
    level: 'l1',
    displayName: 'Introduction',
    levels: <PlanLevel>[],
    anniversaryAt: null,
    allowances: Allowances.empty,
    warnRenewal: false,
    renewalPrompt: false,
    canSell: false,
    queuePosition: null,
    pendingOfferCode: null,
  );

  factory Entitlements.fromJson(Map<String, dynamic> json) {
    final lvl = json['level'];
    final level = (lvl is String && lvl.isNotEmpty) ? lvl : 'l1';
    final rawLevels = json['levels'];
    final levels = <PlanLevel>[];
    if (rawLevels is List) {
      for (final e in rawLevels) {
        if (e is Map<String, dynamic>) {
          final pl = PlanLevel.fromJson(e);
          if (pl.planId.isNotEmpty) levels.add(pl);
        }
      }
    }
    final offer = json['pending_offer'];
    final offerCode = (offer is Map<String, dynamic> && offer['code'] is String)
        ? offer['code'] as String
        : null;
    int? asInt(dynamic v) => v is int ? v : (v is num ? v.toInt() : null);
    return Entitlements(
      level: level,
      displayName: json['display_name'] is String && (json['display_name'] as String).isNotEmpty
          ? json['display_name'] as String
          : level,
      levels: levels,
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
      queuePosition: asInt(json['queue_position']),
      pendingOfferCode: offerCode,
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

  /// [LOCAL-604 D619] POST /l2/queue/join — ask for a place in the free-seat
  /// queue, with the email the offer code will be sent to. Returns the refreshed
  /// snapshot on success, or null on failure (the caller shows a message).
  static Future<Entitlements?> joinQueue(String email) async {
    final userId = await _userId();
    if (userId.isEmpty) return null;
    try {
      final resp = await Endpoints.post(
        Service.userDb,
        '/l2/queue/join',
        body: {'user_id': userId, 'email': email},
        timeout: const Duration(seconds: 15),
      );
      if (resp.statusCode == 200) {
        return Entitlements.fromJson(
            jsonDecode(resp.body) as Map<String, dynamic>);
      }
      await DebugLogHelper.addDebugLog(
          'ENTITLEMENTS: queue/join non-200 ${resp.statusCode}');
      return null;
    } catch (e) {
      await DebugLogHelper.addDebugLog('ENTITLEMENTS: queue/join error: $e');
      return null;
    }
  }

  /// [LOCAL-604 D619] POST /l2/claim — the single code box. Accepts a
  /// queue-offer code, a friend's invitation code, or a level code; the server
  /// decides which it is and either switches the level/seat or returns a
  /// structured refusal. Returns a [ClaimResult]: on success it carries the
  /// refreshed snapshot so the caller can show the new level immediately.
  static Future<ClaimResult> claim(String code) async {
    final userId = await _userId();
    if (userId.isEmpty) {
      return const ClaimResult(ok: false, message: 'This device has no id yet.');
    }
    try {
      final resp = await Endpoints.post(
        Service.userDb,
        '/l2/claim',
        body: {'user_id': userId, 'code': code},
        timeout: const Duration(seconds: 15),
      );
      final body = (() {
        try {
          final d = jsonDecode(resp.body);
          return d is Map<String, dynamic> ? d : <String, dynamic>{};
        } catch (_) {
          return <String, dynamic>{};
        }
      })();
      if (resp.statusCode == 200) {
        return ClaimResult(
          ok: true,
          entitlements: Entitlements.fromJson(body),
          message: 'Your plan is updated.',
        );
      }
      final msg = body['message'] is String
          ? body['message'] as String
          : 'That code could not be used.';
      await DebugLogHelper.addDebugLog(
          'ENTITLEMENTS: claim non-200 ${resp.statusCode} ${body['error_code']}');
      return ClaimResult(ok: false, message: msg);
    } catch (e) {
      await DebugLogHelper.addDebugLog('ENTITLEMENTS: claim error: $e');
      return const ClaimResult(
          ok: false, message: 'Could not reach the server. Please try again.');
    }
  }
}

/// Result of [EntitlementsService.claim]. On success [entitlements] holds the
/// refreshed snapshot; on failure [message] explains why.
class ClaimResult {
  final bool ok;
  final Entitlements? entitlements;
  final String message;

  const ClaimResult({required this.ok, this.entitlements, required this.message});
}
