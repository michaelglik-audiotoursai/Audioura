// [LOCAL-598] In-app purchase service — consumable packs, iOS first.
//
// SUBSCRIPTION_LEVELS.md (D613): L3 ($10 pack) and L4 ($25 round) are
// CONSUMABLES, never auto-renewing subscriptions, and nothing is charged
// automatically. Purchases are verified SERVER-SIDE before any allowance is
// granted; the same transaction id can never grant twice.
//
// Flow (StoreKit 2 via in_app_purchase + in_app_purchase_storekit):
//   1. buy(product) -> buyConsumable on the store.
//   2. The purchase stream delivers a PurchaseDetails with the StoreKit 2 JWS
//      in verificationData.serverVerificationData (the signed transaction).
//   3. We POST {store, transaction_id, product, user_id, signed_transaction}
//      to /purchases/verify. The server verifies the JWS OFFLINE (LOCAL-598
//      D5, IAP_VERIFY_MODE=apple) and, on OK, grants the level.
//   4. ONLY after the server grants do we completePurchase() to finish the
//      transaction with the store. If verification fails we still complete the
//      transaction (so StoreKit stops re-delivering it) but do NOT grant.
//
// Google Play is out of scope for LOCAL-598: kAndroidBillingEnabled is false,
// the plan screen hides the Android buy buttons, and buy() returns
// `unavailable` on Android so nothing is charged.

import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform;

import 'package:in_app_purchase/in_app_purchase.dart';
import 'package:in_app_purchase_storekit/in_app_purchase_storekit.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/endpoints.dart';
import '../screens/debug_log_viewer_screen.dart';

/// Google Play billing is intentionally OFF for LOCAL-598. Flip to true only
/// when the Play Billing path is implemented and the products exist.
const bool kAndroidBillingEnabled = false;

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
          'This product is not available right now.');
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
    final serverProduct = serverProductForStoreId(p.productID);
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

    // StoreKit 2: serverVerificationData is the JWS signed transaction. The
    // transaction id is the store's purchase id.
    final jws = p.verificationData.serverVerificationData;
    final transactionId = p.purchaseID ?? '';

    final body = <String, dynamic>{
      'store': 'apple',
      'transaction_id': transactionId,
      'product': p.productID, // store id; server maps to the product key
      'user_id': userId,
      'signed_transaction': jws,
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
            'IAP: server granted $serverProduct for txn $transactionId');
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
    c!.complete(result);
  }

  /// For tests/teardown.
  Future<void> dispose() async {
    await _sub?.cancel();
    _sub = null;
    _initialised = false;
  }
}
