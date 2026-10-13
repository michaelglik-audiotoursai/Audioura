// [LOCAL-677] Curator paid tours — the app-side client for pricing + unlock.
//
// Talks to the orchestrator pricing endpoints (tour_pricing_service.py):
//   GET  /tour/<id>/price                        → {is_paid, price_tier, price_label, ...}
//   POST /tour/<id>/price      {user_id, tier}   → curator sets/clears the tier
//   GET  /tour/<id>/unlock-state?user_id=...     → {is_paid, unlocked, locked, ...}
//   GET  /tour/<id>/sales                        → {sales}
//   GET  /price-tiers                            → the tier config (tier→price/label)
//
// Pure network/model glue — the price BADGE on the home list already comes
// inline on the /tours-near payload (price_tier, price_label); these calls are
// for the player's lock/preview gate, the curator's price control and Sales
// count, and the tier picker.

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../config/endpoints.dart';

/// A tour's price state, as returned by the pricing endpoints.
class TourPrice {
  final bool isPaid;
  final int? priceTier;
  final double? priceUsd;
  final String priceLabel; // '$4.99' or 'Free'
  final String? productId;

  const TourPrice({
    required this.isPaid,
    required this.priceTier,
    required this.priceUsd,
    required this.priceLabel,
    required this.productId,
  });

  factory TourPrice.fromJson(Map<String, dynamic> j) => TourPrice(
        isPaid: j['is_paid'] == true,
        priceTier: (j['price_tier'] as num?)?.toInt(),
        priceUsd: (j['price_usd'] as num?)?.toDouble(),
        priceLabel: (j['price_label'] as String?) ?? 'Free',
        productId: j['product_id'] as String?,
      );
}

/// A tour's unlock/preview state for the current device.
class TourUnlockState {
  final bool isPaid;
  final bool unlocked;
  final bool locked; // paid AND not unlocked
  final int freePreviewStops; // how many opening stops play free (1)
  final int? priceTier;
  final double? priceUsd;
  final String priceLabel;
  final String? productId;

  const TourUnlockState({
    required this.isPaid,
    required this.unlocked,
    required this.locked,
    required this.freePreviewStops,
    required this.priceTier,
    required this.priceUsd,
    required this.priceLabel,
    required this.productId,
  });

  factory TourUnlockState.fromJson(Map<String, dynamic> j) => TourUnlockState(
        isPaid: j['is_paid'] == true,
        unlocked: j['unlocked'] == true,
        locked: j['locked'] == true,
        freePreviewStops: (j['free_preview_stops'] as num?)?.toInt() ?? 1,
        priceTier: (j['price_tier'] as num?)?.toInt(),
        priceUsd: (j['price_usd'] as num?)?.toDouble(),
        priceLabel: (j['price_label'] as String?) ?? 'Free',
        productId: j['product_id'] as String?,
      );

  /// A free (or absent) tour is treated as fully unlocked, never locked.
  static TourUnlockState free() => const TourUnlockState(
        isPaid: false,
        unlocked: true,
        locked: false,
        freePreviewStops: 1,
        priceTier: null,
        priceUsd: null,
        priceLabel: 'Free',
        productId: null,
      );
}

/// One row of the price-tier config (for the curator's tier picker).
class PriceTier {
  final int tier;
  final double priceUsd;
  final String label;
  final String productId;

  const PriceTier({
    required this.tier,
    required this.priceUsd,
    required this.label,
    required this.productId,
  });

  factory PriceTier.fromJson(Map<String, dynamic> j) => PriceTier(
        tier: (j['tier'] as num).toInt(),
        priceUsd: (j['price_usd'] as num?)?.toDouble() ?? 0.0,
        label: (j['label'] as String?) ?? '',
        productId: (j['product_id'] as String?) ?? '',
      );
}

class TourPricingService {
  TourPricingService._();

  /// Current device id (anonymous secret_id).
  static Future<String> _userId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('user_id') ?? '';
  }

  /// The unlock/preview state of a tour for this device. Falls back to a
  /// free/unlocked state on any error (a network hiccup never locks a tour the
  /// user might already own — the player re-checks before a locked stop plays).
  static Future<TourUnlockState> unlockState(String tourId) async {
    try {
      final userId = await _userId();
      final resp = await Endpoints.get(
        Service.orchestrator,
        '/tour/$tourId/unlock-state?user_id=${Uri.encodeComponent(userId)}',
        timeout: const Duration(seconds: 10),
      );
      if (resp.statusCode == 200) {
        return TourUnlockState.fromJson(
            json.decode(resp.body) as Map<String, dynamic>);
      }
    } catch (_) {}
    return TourUnlockState.free();
  }

  /// [LOCAL-677C / D654] An unlock-state check that reports whether the SERVER
  /// actually answered. The player needs this to tell an explicit "not unlocked"
  /// (a refund, LOCAL-672 — the tour should lock on the next online check) apart
  /// from a network failure (offline → a downloaded tour must stay playable).
  ///
  /// Returns (answered, state): answered is true ONLY when the server returned
  /// 200. On any error / non-200, answered is false and state is a free default
  /// the caller should IGNORE in favour of the offline (always-playable) rule.
  static Future<({bool answered, TourUnlockState state})> unlockStateChecked(
      String tourId) async {
    try {
      final userId = await _userId();
      final resp = await Endpoints.get(
        Service.orchestrator,
        '/tour/$tourId/unlock-state?user_id=${Uri.encodeComponent(userId)}',
        timeout: const Duration(seconds: 10),
      );
      if (resp.statusCode == 200) {
        return (
          answered: true,
          state: TourUnlockState.fromJson(
              json.decode(resp.body) as Map<String, dynamic>)
        );
      }
    } catch (_) {}
    return (answered: false, state: TourUnlockState.free());
  }

  /// The price of a tour (badge/label). Free on any error.
  static Future<TourPrice> price(String tourId) async {
    try {
      final resp = await Endpoints.get(
        Service.orchestrator,
        '/tour/$tourId/price',
        timeout: const Duration(seconds: 10),
      );
      if (resp.statusCode == 200) {
        return TourPrice.fromJson(
            json.decode(resp.body) as Map<String, dynamic>);
      }
    } catch (_) {}
    return const TourPrice(
        isPaid: false,
        priceTier: null,
        priceUsd: null,
        priceLabel: 'Free',
        productId: null);
  }

  /// Curator: set or clear the price tier on their own tour. [tier] null clears
  /// (makes the tour free). Returns (ok, errorCode, message). errorCode is
  /// 'not_curator' | 'not_owner' | 'invalid_tier' | 'unknown_tour' on refusal.
  static Future<({bool ok, String? code, String? message})> setPrice(
      String tourId, int? tier) async {
    try {
      final userId = await _userId();
      final resp = await Endpoints.post(
        Service.orchestrator,
        '/tour/$tourId/price',
        body: {'user_id': userId, 'tier': tier},
        timeout: const Duration(seconds: 15),
      );
      if (resp.statusCode == 200) {
        return (ok: true, code: null, message: null);
      }
      String? code;
      String? message;
      try {
        final decoded = json.decode(resp.body);
        if (decoded is Map) {
          code = decoded['error'] as String?;
          message = decoded['message'] as String?;
        }
      } catch (_) {}
      return (ok: false, code: code, message: message);
    } catch (e) {
      return (ok: false, code: 'network', message: '$e');
    }
  }

  /// Curator: how many unlocks (sales) a tour has. 0 on any error.
  static Future<int> salesCount(String tourId) async {
    try {
      final resp = await Endpoints.get(
        Service.orchestrator,
        '/tour/$tourId/sales',
        timeout: const Duration(seconds: 10),
      );
      if (resp.statusCode == 200) {
        final decoded = json.decode(resp.body);
        return (decoded['sales'] as num?)?.toInt() ?? 0;
      }
    } catch (_) {}
    return 0;
  }

  /// The price-tier config for the curator's tier picker. Empty on error.
  static Future<List<PriceTier>> priceTiers() async {
    try {
      final resp = await Endpoints.get(
        Service.orchestrator,
        '/price-tiers',
        timeout: const Duration(seconds: 10),
      );
      if (resp.statusCode == 200) {
        final decoded = json.decode(resp.body);
        final list = (decoded['tiers'] as List?) ?? [];
        return list
            .map((e) => PriceTier.fromJson(e as Map<String, dynamic>))
            .toList();
      }
    } catch (_) {}
    return const [];
  }
}
