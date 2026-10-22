// [LOCAL-598 / LOCAL-696] In-app purchase service — consumable packs, tours and
// community passes, on BOTH iOS and Android.
//
// SUBSCRIPTION_LEVELS.md (D613): L3 ($10 pack) and L4 ($25 round) are
// CONSUMABLES, never auto-renewing subscriptions, and nothing is charged
// automatically. Purchases are verified SERVER-SIDE before any allowance is
// granted; the same transaction id can never grant twice.
//
// Flow (in_app_purchase; StoreKit 2 on iOS, Play Billing on Android):
//   1. buy(product) -> buyConsumable on the store.
//   2. The purchase stream delivers a PurchaseDetails. On iOS
//      verificationData.serverVerificationData is the StoreKit 2 JWS signed
//      transaction; on Android it is the opaque Google purchaseToken.
//   3. We POST to /purchases/verify:
//        iOS     {store:'apple',  transaction_id, product,    signed_transaction}
//        Android {store:'google', order_id,       product_id, purchase_token}
//      The server verifies — Apple: the JWS OFFLINE (LOCAL-598, apple mode);
//      Google: the token via the Play Developer API, then it acknowledges and
//      consumes the purchase (LOCAL-696, google mode) — and on OK grants.
//   4. ONLY after the server grants do we completePurchase() to finish the
//      transaction with the store. If verification fails we still complete the
//      transaction (so the store stops re-delivering it) but do NOT grant.
//
// kAndroidBillingEnabled is now true (LOCAL-696); the 11 phase-1 products exist
// on Play with the SAME product ids as Apple.

import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform;

import 'package:in_app_purchase/in_app_purchase.dart';
import 'package:in_app_purchase_storekit/in_app_purchase_storekit.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/endpoints.dart';
import '../screens/debug_log_viewer_screen.dart';

/// [LOCAL-696] Google Play billing is now ON: the server verifies a Google
/// purchase token with the Play Developer API (IAP_VERIFY_MODE=google), exactly
/// as it verifies the Apple JWS. The 11 phase-1 products exist on Play with the
/// SAME product ids as Apple (ClickUp wdvrdayx33). iOS is unchanged.
const bool kAndroidBillingEnabled = true;

/// The two consumable products. The STORE ids are what App Store Connect /
/// the StoreKit config file use; the SERVER product key is what
/// /purchases/verify maps to a level (PRODUCT_LEVELS in entitlements_api.py).
enum IapProduct { l3Pack, l4Round }

extension IapProductIds on IapProduct {
  /// App Store product id (StoreKit). Matches the Xcode StoreKit config file.
  String get storeId {
    switch (this) {
      case IapProduct.l3Pack:
        return 'audioura.pack.l3';
      case IapProduct.l4Round:
        return 'audioura.round.l4';
    }
  }

  /// Server product key sent to /purchases/verify (maps to a level server-side).
  String get serverProduct {
    switch (this) {
      case IapProduct.l3Pack:
        return 'l3_pack_10';
      case IapProduct.l4Round:
        return 'l4_round_25';
    }
  }
}

/// All store ids we query/sell.
const Set<String> kIapStoreIds = {'audioura.pack.l3', 'audioura.round.l4'};

/// Map a StoreKit product id back to the server product key. Returns null for
/// an unknown id (defensive — never grant on something we didn't sell).
String? serverProductForStoreId(String storeId) {
  for (final p in IapProduct.values) {
    if (p.storeId == storeId) return p.serverProduct;
  }
  return null;
}

/// [LOCAL-677] Curator paid tours. A tour is sold as one of a FIXED set of
/// CONSUMABLE price-tier products (per-tour products can't be created on the
/// fly — D624). The store id the app sells for a tier, mirrored from the server
/// price_tiers config / migrations 022/024/026. Keep in lock-step with
/// TOUR_TIER_PRODUCTS in entitlements_api.py and the price_tiers table.
///
/// [LOCAL-686] The product id is NOT a simple 'tier$tier': the seven legacy .99
/// tiers (1..7) use 'audioura.tour.tier<N>', while the 34 round-dollar ladder
/// tiers (8..41) use 'audioura.tour.usd<dollars>'. This map is the single Dart
/// source of truth; tourProductForTier and kTourStoreIds derive from it.
const Map<int, String> kTierProductIds = {
  // Legacy .99 tiers 1..7 (migrations 022/024).
  1: 'audioura.tour.tier1', 2: 'audioura.tour.tier2', 3: 'audioura.tour.tier3',
  4: 'audioura.tour.tier4', 5: 'audioura.tour.tier5', 6: 'audioura.tour.tier6',
  7: 'audioura.tour.tier7',
  // The round-dollar ladder, tiers 8..41 (migration 026, LOCAL-686).
  8: 'audioura.tour.usd2', 9: 'audioura.tour.usd3', 10: 'audioura.tour.usd4', 11: 'audioura.tour.usd5',
  12: 'audioura.tour.usd6', 13: 'audioura.tour.usd7', 14: 'audioura.tour.usd8', 15: 'audioura.tour.usd9',
  16: 'audioura.tour.usd10', 17: 'audioura.tour.usd11', 18: 'audioura.tour.usd12', 19: 'audioura.tour.usd13',
  20: 'audioura.tour.usd14', 21: 'audioura.tour.usd15', 22: 'audioura.tour.usd16', 23: 'audioura.tour.usd17',
  24: 'audioura.tour.usd18', 25: 'audioura.tour.usd19', 26: 'audioura.tour.usd20', 27: 'audioura.tour.usd25',
  28: 'audioura.tour.usd30', 29: 'audioura.tour.usd35', 30: 'audioura.tour.usd40', 31: 'audioura.tour.usd45',
  32: 'audioura.tour.usd50', 33: 'audioura.tour.usd60', 34: 'audioura.tour.usd70', 35: 'audioura.tour.usd80',
  36: 'audioura.tour.usd90', 37: 'audioura.tour.usd100', 38: 'audioura.tour.usd125', 39: 'audioura.tour.usd150',
  40: 'audioura.tour.usd175', 41: 'audioura.tour.usd200',
};

/// The store product id the app sells for a given price [tier]. Falls back to
/// the legacy 'audioura.tour.tier<N>' shape for an unknown tier (defensive; the
/// server is the source of truth and would reject an id it does not know).
String tourProductForTier(int tier) =>
    kTierProductIds[tier] ?? 'audioura.tour.tier$tier';

/// All tour-tier store ids the app may sell (the 7 legacy .99 tiers + the 34
/// round-dollar ladder tiers = 41 products).
final Set<String> kTourStoreIds = kTierProductIds.values.toSet();

/// [LOCAL-690] True iff [storeId] is a COMMUNITY PASS product. The convention
/// (migration 029 / communities_api.is_community_pass_product) is the prefix
/// 'audioura.pass.'. ONE product per PRICE serves every community AND every
/// length (LEAD review of LOCAL-690); the server records community + length +
/// expiry (non-renewing).
bool isCommunityPassProduct(String storeId) =>
    storeId.startsWith('audioura.pass.');

/// [LOCAL-690C] The community-PASS store product ids — ONE product per PRICE,
/// the same round-dollar ladder as the tour tiers (migration 029 / LOCAL-686)
/// EXCEPT that passes have a $1 floor (LOCAL-704 / D665: every community member
/// pays at least $1 — the commitment fee), whereas tour prices keep the $2
/// floor. So the pass ladder is $1, $2..$20 /$1, $25..$50 /$5, $60..$100 /$10,
/// $125..$200 /$25. Apple's non-renewing subscription product carries no
/// length, so one product serves every community and every length — the LENGTH
/// is sent on /purchases/verify and lives on the community's option. These are
/// the ids added to ios/Audioura.storekit as non-renewing subscriptions.
const List<int> kPassLadderDollars = [
  1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
  25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 125, 150, 175, 200,
];

/// The store product id for a given whole-dollar pass PRICE, e.g. 5 ->
/// 'audioura.pass.usd5'. The server is the source of truth and would reject an
/// id it does not know.
String passProductForDollars(int dollars) => 'audioura.pass.usd$dollars';

/// All community-pass store ids the app may sell (the 34 ladder prices).
final Set<String> kPassStoreIds =
    kPassLadderDollars.map(passProductForDollars).toSet();

/// The four pass lengths an owner may offer. The length is NOT part of the
/// store product — it is chosen per community and sent to /purchases/verify.
const List<String> kPassLengths = ['day', 'week', 'month', 'year'];

enum IapResultStatus { granted, cancelled, pending, unavailable, failed }

class IapResult {
  final IapResultStatus status;
  final String? message;
  const IapResult(this.status, [this.message]);
}

class IapService {
  IapService._();
  static final IapService instance = IapService._();

  final InAppPurchase _iap = InAppPurchase.instance;
  StreamSubscription<List<PurchaseDetails>>? _sub;

  /// Completer for the in-flight buy(), resolved when the purchase stream
  /// delivers the matching product's terminal state. One purchase at a time.
  Completer<IapResult>? _pending;
  String? _pendingStoreId;
  // [LOCAL-677] When the in-flight purchase is a TOUR unlock, the tour id to
  // send to /purchases/verify so the server writes tour_unlocks for this tour.
  String? _pendingTourId;
  // [LOCAL-690] When the in-flight purchase is a COMMUNITY PASS, the community
  // id to send to /purchases/verify so the server grants/extends membership.
  String? _pendingCommunityId;
  // [LOCAL-690C] The chosen pass LENGTH (day|week|month|year) for the in-flight
  // pass purchase — one store product per price serves every length, so the
  // length must travel to /purchases/verify alongside the community id.
  String? _pendingPassLength;

  bool _initialised = false;

  /// Start listening to the purchase stream exactly once. Safe to call repeatedly.
  Future<void> _ensureListening() async {
    if (_initialised) return;
    _initialised = true;
    // Prefer the StoreKit 2 backend on iOS (SUBSCRIPTION_LEVELS.md asks for
    // StoreKit 2). Enabling it is a no-op on platforms that don't support it.
    if (Platform.isIOS) {
      try {
        await InAppPurchaseStoreKitPlatform.enableStoreKit2();
      } catch (e) {
        await DebugLogHelper.addDebugLog('IAP: enableStoreKit2 skipped: $e');
      }
    }
    _sub = _iap.purchaseStream.listen(
      _onPurchaseUpdates,
      onError: (Object e) async {
        await DebugLogHelper.addDebugLog('IAP: purchaseStream error: $e');
      },
    );
  }

  /// Buy a consumable pack. Resolves once the store+server flow reaches a
  /// terminal state. iOS only — returns `unavailable` on Android (billing off)
  /// and when the store reports IAP unavailable.
  Future<IapResult> buy(IapProduct product) async {
    if (Platform.isAndroid && !kAndroidBillingEnabled) {
      return const IapResult(IapResultStatus.unavailable,
          'In-app purchases are not available on Android yet.');
    }

    final available = await _iap.isAvailable();
    if (!available) {
      return const IapResult(IapResultStatus.unavailable,
          'The store is not available on this device.');
    }

    await _ensureListening();

    // StoreKit 2 is selected via the storekit2 backend when available; the
    // in_app_purchase_storekit plugin exposes it. Querying the product details
    // confirms the product exists in the store / StoreKit config file.
    final response = await _iap.queryProductDetails({product.storeId});
    if (response.error != null ||
        response.productDetails.isEmpty ||
        response.notFoundIDs.contains(product.storeId)) {
      await DebugLogHelper.addDebugLog(
          'IAP: product not found: ${product.storeId} '
          'err=${response.error?.message} notFound=${response.notFoundIDs}');
      return const IapResult(IapResultStatus.unavailable,
          'This pack isn\u2019t available on this store yet. Please try again '
          'later.');
    }

    final details = response.productDetails.first;

    // One purchase at a time.
    if (_pending != null && !_pending!.isCompleted) {
      return const IapResult(
          IapResultStatus.failed, 'Another purchase is already in progress.');
    }
    _pending = Completer<IapResult>();
    _pendingStoreId = product.storeId;

    final param = PurchaseParam(productDetails: details);
    try {
      // CONSUMABLE — never buyNonConsumable, never a subscription.
      await _iap.buyConsumable(purchaseParam: param, autoConsume: false);
    } catch (e) {
      await DebugLogHelper.addDebugLog('IAP: buyConsumable threw: $e');
      _pendingStoreId = null;
      final c = _pending;
      _pending = null;
      if (c != null && !c.isCompleted) {
        return IapResult(IapResultStatus.failed, 'Could not start purchase: $e');
      }
    }

    return _pending!.future;
  }

  // ─── [LOCAL-677] Curator paid tours ────────────────────────────────────────

  /// Whether the device is in LOCAL server mode (the Mac Mini stack). The TEST
  /// PURCHASE path is only offered there, where the server runs with
  /// IAP_VERIFY_MODE=stub and no Apple/Google products exist yet.
  Future<bool> isLocalStubMode() async {
    final prefs = await SharedPreferences.getInstance();
    return (prefs.getString('server_mode') ?? 'cloud') == 'local';
  }

  /// [LOCAL-699 / LOCAL-734] Whether THIS platform should run the server's
  /// TEST PURCHASE (stub) path rather than drive the real store. Asks the
  /// server (GET /purchases/mode) rather than guessing from the device's
  /// server_mode flag, so the TEST PURCHASE path is offered exactly when the
  /// server will accept a store='stub' body for this platform.
  ///
  /// [LOCAL-734] per_store: the server verifies by platform from ONE stack —
  /// real Apple sandbox on iOS, a TEST PURCHASE on Android (there is no Play
  /// service account locally yet). So the decision is now PER-PLATFORM:
  ///   • if the body carries a `platforms` map (a per_store-aware server), use
  ///     THIS platform's value: 'stub' ⇒ TEST PURCHASE (return true); 'apple'
  ///     or 'google' ⇒ drive the real store (return false). On iOS that means
  ///     StoreKit (real sandbox on a dev/TestFlight build); on Android TEST
  ///     PURCHASE only when android == 'stub'.
  ///   • without `platforms` (an older server), fall back to today's single
  ///     top-level `stub` bool, so behaviour is unchanged for old servers.
  ///
  /// Falls back to the device-side [isLocalStubMode] guess when the endpoint is
  /// unreachable or returns a non-200 / malformed body. The result is NOT
  /// cached: the server mode can change as the tester switches servers.
  Future<bool> purchasesModeIsStub() async {
    try {
      final resp = await Endpoints.get(
        Service.userDb,
        '/purchases/mode',
        timeout: const Duration(seconds: 10),
      );
      if (resp.statusCode == 200) {
        final map = Endpoints.tryDecodeMap(resp.body);
        if (map != null) {
          final decided = stubFromModeResponse(
            map,
            isIOS: Platform.isIOS,
            isAndroid: Platform.isAndroid,
          );
          if (decided != null) return decided;
        }
      }
      await DebugLogHelper.addDebugLog(
          'IAP: /purchases/mode non-200/malformed ${resp.statusCode} '
          '— falling back to device server_mode');
    } catch (e) {
      await DebugLogHelper.addDebugLog(
          'IAP: /purchases/mode error: $e — falling back to device server_mode');
    }
    return isLocalStubMode();
  }

  /// [LOCAL-734] Pure per-platform decision for [purchasesModeIsStub], split out
  /// so it can be unit-tested without a network call or a running server.
  ///
  /// Given a decoded GET /purchases/mode body and the current platform, returns
  /// whether THIS platform should run the TEST PURCHASE (stub) path:
  ///   • if `platforms` is present (a per_store-aware server), decide by this
  ///     platform's value — 'stub' ⇒ true (TEST PURCHASE); 'apple'/'google' ⇒
  ///     false (drive the real store). iOS therefore uses StoreKit; Android
  ///     uses TEST PURCHASE only when android == 'stub'.
  ///   • without `platforms` (a legacy server), fall back to the top-level
  ///     `stub` bool (today's behaviour).
  ///   • if neither is usable, return null so the caller falls back to its
  ///     device-side guess.
  static bool? stubFromModeResponse(
    Map<dynamic, dynamic> map, {
    required bool isIOS,
    required bool isAndroid,
  }) {
    final platforms = map['platforms'];
    if (platforms is Map) {
      final key = isIOS ? 'ios' : 'android';
      final v = platforms[key];
      if (v is String) {
        // Only the stub value means "run the TEST PURCHASE path here".
        return v == 'stub';
      }
    }
    final stub = map['stub'];
    if (stub is bool) return stub;
    return null;
  }

  /// Buy (unlock) ONE tour at the given price [tier] through the store, then the
  /// server verifies and writes tour_unlocks. iOS only (Android billing off).
  /// Until the Apple/Google tour products exist this returns `unavailable` on a
  /// real store; use [testPurchaseTour] in LOCAL stub mode. [tourId] is the tour
  /// being unlocked (sent to /purchases/verify so the server unlocks that tour).
  Future<IapResult> buyTour(int tier, String tourId) async {
    if (Platform.isAndroid && !kAndroidBillingEnabled) {
      return const IapResult(IapResultStatus.unavailable,
          'In-app purchases are not available on Android yet.');
    }
    final storeId = tourProductForTier(tier);

    final available = await _iap.isAvailable();
    if (!available) {
      return const IapResult(IapResultStatus.unavailable,
          'The store is not available on this device.');
    }
    await _ensureListening();

    final response = await _iap.queryProductDetails({storeId});
    if (response.error != null ||
        response.productDetails.isEmpty ||
        response.notFoundIDs.contains(storeId)) {
      await DebugLogHelper.addDebugLog(
          'IAP: tour product not found: $storeId '
          'notFound=${response.notFoundIDs}');
      return const IapResult(IapResultStatus.unavailable,
          'This tour is not available for purchase right now.');
    }
    final details = response.productDetails.first;

    if (_pending != null && !_pending!.isCompleted) {
      return const IapResult(
          IapResultStatus.failed, 'Another purchase is already in progress.');
    }
    _pending = Completer<IapResult>();
    _pendingStoreId = storeId;
    _pendingTourId = tourId;

    final param = PurchaseParam(productDetails: details);
    try {
      await _iap.buyConsumable(purchaseParam: param, autoConsume: false);
    } catch (e) {
      await DebugLogHelper.addDebugLog('IAP: tour buyConsumable threw: $e');
      _pendingStoreId = null;
      _pendingTourId = null;
      final c = _pending;
      _pending = null;
      if (c != null && !c.isCompleted) {
        return IapResult(IapResultStatus.failed, 'Could not start purchase: $e');
      }
    }
    return _pending!.future;
  }

  /// TEST PURCHASE (LOCAL stub mode only). Completes a fake tour purchase by
  /// posting straight to /purchases/verify with store='stub' and a generated
  /// transaction id — no real store, no charge. The server (IAP_VERIFY_MODE=
  /// stub) accepts any non-empty transaction id and writes tour_unlocks, so the
  /// whole buy→unlock flow can be tested end to end on Michael's phone before
  /// the Apple/Google products exist. Idempotent on the transaction id.
  Future<IapResult> testPurchaseTour(int tier, String tourId) async {
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id') ?? '';
    if (userId.isEmpty) {
      return const IapResult(IapResultStatus.failed,
          'No device id — cannot complete the test purchase.');
    }
    final storeId = tourProductForTier(tier);
    final transactionId =
        'TEST-677-${DateTime.now().millisecondsSinceEpoch}-$tourId';
    final body = <String, dynamic>{
      'store': 'stub',
      'transaction_id': transactionId,
      'product': storeId,
      'user_id': userId,
      'tour_id': tourId,
    };
    try {
      final resp = await Endpoints.post(
        Service.userDb,
        '/purchases/verify',
        body: body,
        timeout: const Duration(seconds: 30),
      );
      if (resp.statusCode == 200) {
        await DebugLogHelper.addDebugLog(
            'IAP: TEST PURCHASE unlocked tour $tourId (tier $tier)');
        return const IapResult(IapResultStatus.granted);
      }
      // 409 already_verified → the tour is already unlocked; treat as success.
      if (resp.statusCode == 409) {
        return const IapResult(IapResultStatus.granted);
      }
      String? msg;
      try {
        final decoded = jsonDecode(resp.body);
        if (decoded is Map && decoded['message'] is String) {
          msg = decoded['message'] as String;
        }
      } catch (_) {}
      await DebugLogHelper.addDebugLog(
          'IAP: TEST PURCHASE non-200 ${resp.statusCode}: ${resp.body}');
      return IapResult(IapResultStatus.failed,
          msg ?? 'The test purchase could not be completed.');
    } catch (e) {
      await DebugLogHelper.addDebugLog('IAP: TEST PURCHASE error: $e');
      return IapResult(IapResultStatus.failed,
          'Could not reach the server for the test purchase: $e');
    }
  }

  /// [LOCAL-699] TEST PURCHASE of a LEVEL pack ($10 Pack / Curator) — the
  /// pack/curator equivalent of [testPurchaseTour], for a stub-verification
  /// server (IAP_VERIFY_MODE=stub). Posts straight to /purchases/verify with
  /// store='stub' and a generated transaction id — no real store, no charge —
  /// so the whole buy→grant flow for the plan's Buy buttons can be exercised end
  /// to end on BOTH platforms (iOS and Android) before the Apple/Google pack
  /// products exist. The server grants the level and resets the pack exactly as
  /// a real purchase would. Idempotent on the transaction id (409 → granted).
  Future<IapResult> testPurchasePack(IapProduct product) async {
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id') ?? '';
    if (userId.isEmpty) {
      return const IapResult(IapResultStatus.failed,
          'No device id — cannot complete the test purchase.');
    }
    final transactionId =
        'TEST-699-${DateTime.now().millisecondsSinceEpoch}-${product.serverProduct}';
    final body = <String, dynamic>{
      'store': 'stub',
      'transaction_id': transactionId,
      // The server accepts either the store id or the server key; send the
      // store id so the stub path matches a real purchase's `product`.
      'product': product.storeId,
      'user_id': userId,
    };
    try {
      final resp = await Endpoints.post(
        Service.userDb,
        '/purchases/verify',
        body: body,
        timeout: const Duration(seconds: 30),
      );
      // 200 granted, or 409 already_verified (idempotent) → treat as success.
      if (resp.statusCode == 200 || resp.statusCode == 409) {
        await DebugLogHelper.addDebugLog(
            'IAP: TEST PURCHASE granted ${product.serverProduct}');
        return const IapResult(IapResultStatus.granted);
      }
      String? msg;
      try {
        final decoded = jsonDecode(resp.body);
        if (decoded is Map && decoded['message'] is String) {
          msg = decoded['message'] as String;
        }
      } catch (_) {}
      await DebugLogHelper.addDebugLog(
          'IAP: TEST PURCHASE pack non-200 ${resp.statusCode}: ${resp.body}');
      return IapResult(IapResultStatus.failed,
          msg ?? 'The test purchase could not be completed.');
    } catch (e) {
      await DebugLogHelper.addDebugLog('IAP: TEST PURCHASE pack error: $e');
      return IapResult(IapResultStatus.failed,
          'Could not reach the server for the test purchase: $e');
    }
  }

  /// [LOCAL-690] Buy a COMMUNITY PASS (real store). [passProductId] is a store
  /// pass id (audioura.pass.usd<N>) — ONE product per PRICE; [length]
  /// (day|week|month|year) is the pass length the community offers and
  /// [communityId] the community the pass is for. Both are sent to
  /// /purchases/verify so the server grants/extends membership with the right
  /// expiry. A pass is a non-renewing consumable: buying again extends.
  Future<IapResult> buyCommunityPass(
      String passProductId, int communityId, String length) async {
    if (Platform.isAndroid && !kAndroidBillingEnabled) {
      return const IapResult(IapResultStatus.unavailable,
          'In-app purchases are not available on Android yet.');
    }
    final available = await _iap.isAvailable();
    if (!available) {
      return const IapResult(IapResultStatus.unavailable,
          'The store is not available on this device.');
    }
    await _ensureListening();

    final response = await _iap.queryProductDetails({passProductId});
    if (response.error != null ||
        response.productDetails.isEmpty ||
        response.notFoundIDs.contains(passProductId)) {
      await DebugLogHelper.addDebugLog(
          'IAP: pass product not found: $passProductId');
      return const IapResult(IapResultStatus.unavailable,
          'This pass is not available for purchase right now.');
    }
    final details = response.productDetails.first;

    if (_pending != null && !_pending!.isCompleted) {
      return const IapResult(
          IapResultStatus.failed, 'Another purchase is already in progress.');
    }
    _pending = Completer<IapResult>();
    _pendingStoreId = passProductId;
    _pendingCommunityId = communityId.toString();
    _pendingPassLength = length;

    final param = PurchaseParam(productDetails: details);
    try {
      await _iap.buyConsumable(purchaseParam: param, autoConsume: false);
    } catch (e) {
      await DebugLogHelper.addDebugLog('IAP: pass buyConsumable threw: $e');
      _pendingStoreId = null;
      _pendingCommunityId = null;
      _pendingPassLength = null;
      final c = _pending;
      _pending = null;
      if (c != null && !c.isCompleted) {
        return IapResult(IapResultStatus.failed, 'Could not start purchase: $e');
      }
    }
    return _pending!.future;
  }

  /// [LOCAL-690] TEST PURCHASE of a community pass (LOCAL stub mode only).
  /// Posts straight to /purchases/verify with store='stub' so the whole
  /// buy→membership flow can be tested before the Apple/Google pass products
  /// exist. Idempotent on the transaction id.
  Future<IapResult> testPurchaseCommunityPass(
      String passProductId, int communityId, String length) async {
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id') ?? '';
    if (userId.isEmpty) {
      return const IapResult(IapResultStatus.failed,
          'No device id — cannot complete the test purchase.');
    }
    final transactionId =
        'TEST-690-${DateTime.now().millisecondsSinceEpoch}-$communityId';
    final body = <String, dynamic>{
      'store': 'stub',
      'transaction_id': transactionId,
      'product': passProductId,
      'user_id': userId,
      'community_id': communityId.toString(),
      'length': length,
    };
    try {
      final resp = await Endpoints.post(
        Service.userDb,
        '/purchases/verify',
        body: body,
        timeout: const Duration(seconds: 30),
      );
      if (resp.statusCode == 200 || resp.statusCode == 409) {
        await DebugLogHelper.addDebugLog(
            'IAP: TEST PASS membership in community $communityId');
        return const IapResult(IapResultStatus.granted);
      }
      String? msg;
      try {
        final decoded = jsonDecode(resp.body);
        if (decoded is Map && decoded['message'] is String) {
          msg = decoded['message'] as String;
        }
      } catch (_) {}
      return IapResult(IapResultStatus.failed,
          msg ?? 'The test purchase could not be completed.');
    } catch (e) {
      return IapResult(IapResultStatus.failed,
          'Could not reach the server for the test purchase: $e');
    }
  }

  Future<void> _onPurchaseUpdates(List<PurchaseDetails> purchases) async {
    for (final p in purchases) {
      await _handleOne(p);
    }
  }

  Future<void> _handleOne(PurchaseDetails p) async {
    switch (p.status) {
      case PurchaseStatus.pending:
        // Still in flight — don't resolve yet.
        return;
      case PurchaseStatus.canceled:
        await _finishIfNeeded(p);
        _resolve(p.productID, const IapResult(IapResultStatus.cancelled));
        return;
      case PurchaseStatus.error:
        await DebugLogHelper.addDebugLog(
            'IAP: purchase error for ${p.productID}: ${p.error?.message}');
        await _finishIfNeeded(p);
        _resolve(
            p.productID,
            IapResult(IapResultStatus.failed,
                p.error?.message ?? 'The purchase failed.'));
        return;
      case PurchaseStatus.purchased:
      case PurchaseStatus.restored:
        final result = await _verifyAndGrant(p);
        // Always finish the transaction so StoreKit stops re-delivering it,
        // whether or not the server granted (a failed verify must not loop).
        await _finishIfNeeded(p);
        _resolve(p.productID, result);
        return;
    }
  }

  /// Send the StoreKit 2 JWS signed transaction to /purchases/verify and grant
  /// only on the server's OK.
  Future<IapResult> _verifyAndGrant(PurchaseDetails p) async {
    // [LOCAL-677] A TOUR unlock: the product is a tour-tier id and a tour id was
    // staged by buyTour(). Verify with tour_id so the server writes tour_unlocks
    // for that tour (it does NOT change the buyer's level).
    final bool isTourPurchase =
        kTourStoreIds.contains(p.productID) && _pendingTourId != null;

    // [LOCAL-690] A COMMUNITY PASS: a pass product (audioura.pass.*) and a
    // community id staged by buyCommunityPass(). Verify with community_id so the
    // server grants/extends membership (non-renewing; expiry = now + duration).
    final bool isPassPurchase =
        isCommunityPassProduct(p.productID) && _pendingCommunityId != null;

    final serverProduct = (isTourPurchase || isPassPurchase)
        ? p.productID
        : serverProductForStoreId(p.productID);
    if (serverProduct == null) {
      return const IapResult(
          IapResultStatus.failed, 'Unknown product — not granted.');
    }

    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id') ?? '';
    if (userId.isEmpty) {
      return const IapResult(IapResultStatus.failed,
          'No device id — cannot verify purchase.');
    }

    // StoreKit 2 (iOS): serverVerificationData is the JWS signed transaction.
    // Google Play (Android): serverVerificationData is the opaque purchaseToken.
    // The transaction id is the store's purchase id (iOS) / order id (Android).
    final String verificationData = p.verificationData.serverVerificationData;
    final transactionId = p.purchaseID ?? '';

    final bool isGoogle = Platform.isAndroid;

    final body = <String, dynamic>{
      'user_id': userId,
      if (isTourPurchase) 'tour_id': _pendingTourId,
      if (isPassPurchase) 'community_id': _pendingCommunityId,
      if (isPassPurchase && _pendingPassLength != null)
        'length': _pendingPassLength,
    };
    if (isGoogle) {
      // [LOCAL-696] Android/Google: send the Play fields. The server verifies
      // the token with the Play Developer API, then acknowledges + consumes it.
      body.addAll(<String, dynamic>{
        'store': 'google',
        'product_id': p.productID,
        'order_id': transactionId,
        'purchase_token': verificationData,
      });
    } else {
      // iOS/Apple path — unchanged (StoreKit 2 JWS verified offline server-side).
      body.addAll(<String, dynamic>{
        'store': 'apple',
        'transaction_id': transactionId,
        'product': p.productID, // store id; server maps to the product key
        'signed_transaction': verificationData,
      });
    }

    try {
      final resp = await Endpoints.post(
        Service.userDb,
        '/purchases/verify',
        body: body,
        timeout: const Duration(seconds: 30),
      );
      if (resp.statusCode == 200) {
        await DebugLogHelper.addDebugLog(
            'IAP: server granted $serverProduct for txn $transactionId '
            '(${isGoogle ? 'google' : 'apple'})');
        return const IapResult(IapResultStatus.granted);
      }
      // 409 already_verified: the transaction was processed before — treat as
      // success (idempotent) so a redelivery doesn't look like a failure.
      if (resp.statusCode == 409) {
        return const IapResult(IapResultStatus.granted);
      }
      String? msg;
      try {
        final decoded = jsonDecode(resp.body);
        if (decoded is Map && decoded['message'] is String) {
          msg = decoded['message'] as String;
        }
      } catch (_) {}
      await DebugLogHelper.addDebugLog(
          'IAP: verify non-200 ${resp.statusCode}: ${resp.body}');
      return IapResult(IapResultStatus.failed,
          msg ?? 'The purchase could not be verified. You were not charged in error.');
    } catch (e) {
      await DebugLogHelper.addDebugLog('IAP: verify error: $e');
      return IapResult(IapResultStatus.failed,
          'Could not reach the server to verify your purchase: $e');
    }
  }

  Future<void> _finishIfNeeded(PurchaseDetails p) async {
    if (p.pendingCompletePurchase) {
      try {
        await _iap.completePurchase(p);
      } catch (e) {
        await DebugLogHelper.addDebugLog('IAP: completePurchase error: $e');
      }
    }
  }

  void _resolve(String productId, IapResult result) {
    // Only resolve the buy() future for the product it started.
    if (_pending == null || _pending!.isCompleted) return;
    if (_pendingStoreId != null && _pendingStoreId != productId) return;
    final c = _pending;
    _pending = null;
    _pendingStoreId = null;
    _pendingTourId = null;
    _pendingCommunityId = null;
    _pendingPassLength = null;
    c!.complete(result);
  }

  /// For tests/teardown.
  Future<void> dispose() async {
    await _sub?.cancel();
    _sub = null;
    _initialised = false;
  }
}
