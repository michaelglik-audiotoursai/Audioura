// [LOCAL-736] A finished store purchase is never lost across an app restart.
//
// Before LOCAL-736 a pass/tour purchase that Apple/Play finished while the app
// was closed was redelivered at the next launch, found NO in-memory context,
// mapped to no server product, and was FINISHED (completePurchase) without ever
// being verified or granted — a paid listener got nothing (LEAD's log, the
// audioura.pass.usd1 line on 2026-10-22). These tests lock in the fix:
//
//   • UNIT: a purchased update with NO in-memory context but a PERSISTED pass
//     context verifies with a body that carries community_id + length.
//   • RED:  a purchased pass update with NO context anywhere does NOT call
//     completePurchase (it must be left for the store to redeliver). This test
//     FAILS if the code ever finishes a context-less paid transaction again.
//   • UNIT: after a 200, the persisted context for that product is cleared.
//   • Plus the pure helpers shouldFinishPassOrTour / verifyBodyAdditionsFor /
//     StagedPurchaseContext round-trip.
//
// All seams are injected (completePurchaseOverride, readStagedContextOverride,
// verifyPostOverride), so there is no network, no running server and no real
// StoreKit/Play plugin.

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:in_app_purchase/in_app_purchase.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/iap_service.dart';

PurchaseDetails _purchased(String productId, {String? txnId}) {
  final d = PurchaseDetails(
    purchaseID: txnId ?? 'txn-$productId',
    productID: productId,
    verificationData: PurchaseVerificationData(
      localVerificationData: 'local',
      serverVerificationData: 'JWS-signed-transaction',
      source: 'app_store',
    ),
    transactionDate: '0',
    status: PurchaseStatus.purchased,
  );
  // The store asks us to finish it; the point of the fix is WHETHER we do.
  d.pendingCompletePurchase = true;
  return d;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const passProduct = 'audioura.pass.usd1';

  // in_app_purchase registers a platform the first time InAppPurchase.instance
  // is constructed (via IapService.instance), picked from defaultTargetPlatform.
  // The default in `flutter test` is android, whose billing client fires an
  // auto-connect pigeon call that leaks a PlatformException into the suite. We
  // never drive the real store here — every store/verify/finish path is
  // injected — so pin the target platform to iOS (the StoreKit backend, which
  // does not auto-connect), matching how the fix runs on Michael's iPhone.
  setUpAll(() {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
  });

  tearDownAll(() {
    debugDefaultTargetPlatformOverride = null;
  });

  setUp(() {
    SharedPreferences.setMockInitialValues({'user_id': 'device-123'});
  });

  tearDown(() async {
    final svc = IapService.instance;
    svc.completePurchaseOverride = null;
    svc.readStagedContextOverride = null;
    svc.verifyPostOverride = null;
    svc.debugAttemptedTxnThisLaunch.clear();
  });

  group('pure helpers', () {
    test('shouldFinishPassOrTour: pack always finishes', () {
      expect(
          shouldFinishPassOrTour(
              isPack: true, hadContext: false, verified: false),
          isTrue);
    });

    test('shouldFinishPassOrTour: pass/tour with NO context never finishes', () {
      expect(
          shouldFinishPassOrTour(
              isPack: false, hadContext: false, verified: false),
          isFalse);
      // Even a (spurious) verified=true cannot finish a context-less txn.
      expect(
          shouldFinishPassOrTour(
              isPack: false, hadContext: false, verified: true),
          isFalse);
    });

    test('shouldFinishPassOrTour: pass/tour with context finishes only when verified',
        () {
      expect(
          shouldFinishPassOrTour(
              isPack: false, hadContext: true, verified: false),
          isFalse); // failed verify -> leave for next launch
      expect(
          shouldFinishPassOrTour(
              isPack: false, hadContext: true, verified: true),
          isTrue);
    });

    test('verifyBodyAdditionsFor: pass carries community_id + length', () {
      final ctx = StagedPurchaseContext.forPass('42', 'month', nowMs: 1);
      expect(verifyBodyAdditionsFor(ctx),
          {'community_id': '42', 'length': 'month'});
    });

    test('verifyBodyAdditionsFor: tour carries tour_id', () {
      final ctx = StagedPurchaseContext.forTour('tour-9', nowMs: 1);
      expect(verifyBodyAdditionsFor(ctx), {'tour_id': 'tour-9'});
    });

    test('StagedPurchaseContext JSON round-trips a pass', () {
      final ctx = StagedPurchaseContext.forPass('7', 'week', nowMs: 1234);
      final parsed =
          StagedPurchaseContext.tryParse(jsonEncode(ctx.toJson()))!;
      expect(parsed.isPass, isTrue);
      expect(parsed.communityId, '7');
      expect(parsed.length, 'week');
      expect(parsed.stagedAtMs, 1234);
    });

    test('StagedPurchaseContext.tryParse rejects malformed/empty', () {
      expect(StagedPurchaseContext.tryParse(null), isNull);
      expect(StagedPurchaseContext.tryParse(''), isNull);
      expect(StagedPurchaseContext.tryParse('not json'), isNull);
      expect(StagedPurchaseContext.tryParse('{"kind":"pass"}'), isNull);
    });
  });

  group('redelivery after restart (no in-memory context)', () {
    test('UNIT: persisted pass context -> verify body carries community_id + length',
        () async {
      final svc = IapService.instance;
      Map<String, dynamic>? captured;

      // No in-memory context (fresh launch). Persisted context exists.
      svc.readStagedContextOverride = (storeId) async =>
          storeId == passProduct
              ? StagedPurchaseContext.forPass('42', 'month', nowMs: 1)
              : null;
      svc.verifyPostOverride = (body) async {
        captured = body;
        return http.Response('{"ok":true}', 200);
      };
      svc.completePurchaseOverride = (_) async {};

      await svc.debugHandlePurchasedOrRestored(_purchased(passProduct));

      expect(captured, isNotNull);
      expect(captured!['community_id'], '42');
      expect(captured!['length'], 'month');
      expect(captured!['user_id'], 'device-123');
    });

    test('RED: a pass update with NO context anywhere does NOT call completePurchase',
        () async {
      final svc = IapService.instance;
      var completeCalled = false;
      var verifyCalled = false;

      // No in-memory context AND no persisted context -> no context at all.
      svc.readStagedContextOverride = (_) async => null;
      svc.verifyPostOverride = (body) async {
        verifyCalled = true;
        return http.Response('{"ok":true}', 200);
      };
      svc.completePurchaseOverride = (_) async {
        completeCalled = true;
      };

      await svc.debugHandlePurchasedOrRestored(_purchased(passProduct));

      // The core guarantee: a paid, context-less transaction is NOT finished
      // (left for the store to redeliver), and we never even verify it.
      expect(completeCalled, isFalse,
          reason: 'a context-less paid transaction must never be finished');
      expect(verifyCalled, isFalse);
    });

    test('UNIT: after a 200 the persisted context for that product is cleared',
        () async {
      final svc = IapService.instance;
      // Seed a real persisted context in (mock) SharedPreferences.
      SharedPreferences.setMockInitialValues({
        'user_id': 'device-123',
        kStagedContextKey(passProduct): jsonEncode(
            StagedPurchaseContext.forPass('42', 'month', nowMs: 1).toJson()),
      });

      svc.verifyPostOverride = (_) async => http.Response('{"ok":true}', 200);
      svc.completePurchaseOverride = (_) async {};

      // Sanity: it is present before.
      final before = await SharedPreferences.getInstance();
      expect(before.getString(kStagedContextKey(passProduct)), isNotNull);

      await svc.debugHandlePurchasedOrRestored(_purchased(passProduct));

      final after = await SharedPreferences.getInstance();
      expect(after.getString(kStagedContextKey(passProduct)), isNull,
          reason: 'a verified purchase spends (clears) its staged context');
    });

    test('a failed verify (5xx) leaves the transaction UNFINISHED and context intact',
        () async {
      final svc = IapService.instance;
      SharedPreferences.setMockInitialValues({
        'user_id': 'device-123',
        kStagedContextKey(passProduct): jsonEncode(
            StagedPurchaseContext.forPass('42', 'month', nowMs: 1).toJson()),
      });
      var completeCalled = false;
      svc.verifyPostOverride = (_) async => http.Response('server error', 500);
      svc.completePurchaseOverride = (_) async {
        completeCalled = true;
      };

      await svc.debugHandlePurchasedOrRestored(_purchased(passProduct));

      expect(completeCalled, isFalse,
          reason: 'a failed verify must leave the txn for the next launch');
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString(kStagedContextKey(passProduct)), isNotNull,
          reason: 'context is only cleared after a 200/409');
    });

    test('per-launch retry guard: the same txn is attempted at most once per launch',
        () async {
      final svc = IapService.instance;
      svc.readStagedContextOverride = (_) async =>
          StagedPurchaseContext.forPass('42', 'month', nowMs: 1);
      var verifyCount = 0;
      svc.verifyPostOverride = (_) async {
        verifyCount++;
        return http.Response('server error', 500); // fail so it stays pending
      };
      svc.completePurchaseOverride = (_) async {};

      final p = _purchased(passProduct, txnId: 'txn-A');
      await svc.debugHandlePurchasedOrRestored(p);
      await svc.debugHandlePurchasedOrRestored(p); // redelivered same launch

      expect(verifyCount, 1,
          reason: 'at most one server attempt per txn id per app start');
    });
  });
}
