// LOCAL-694 — end-to-end proof that the SERVICE WRAPPERS (not just the helper)
// turn a Storied 404 / connection-refused into a friendly result and never let
// a raw exception reach the UI.
//
// http 1.x lets us swap the client the app's top-level http.get/post use via
// http.runWithClient + a MockClient, so we can replay the exact Storied
// responses the harness recorded WITHOUT a network. SharedPreferences is mocked
// to cloud mode (the real-user path).
//
// One group per handled service. A regression — e.g. wallet_service going back
// to `throw Exception('Failed to fetch wallet')` on a 404 — turns these red.

import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../lib/config/endpoints.dart';
import '../lib/services/wallet_service.dart';
import '../lib/services/communities_service.dart';
import '../lib/services/tour_share_service.dart';

const _html404 =
    '<!doctype html>\n<html lang=en>\n<title>404 Not Found</title>\n'
    '<h1>Not Found</h1>\n';

/// A client that answers every request with an HTML 404 (the Storied
/// missing-route shape).
MockClient _always404() =>
    MockClient((req) async => http.Response(_html404, 404,
        headers: {'content-type': 'text/html'}));

/// A client that refuses every connection (the Storied absent-service shape).
MockClient _alwaysRefused() =>
    MockClient((req) async => throw const SocketException('Connection refused'));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    // cloud mode = the shipping default; also what Storied testers run.
    SharedPreferences.setMockInitialValues({
      'server_mode': 'cloud',
      'cloud_track': 'storied',
      'user_id': 'local694-test-user',
      'use_mock_wallet': false,
    });
  });

  group('WalletService on a Storied 404', () {
    test('getWallet throws FeatureUnavailableException (not a raw Exception)',
        () async {
      await http.runWithClient(() async {
        expect(
          () => WalletService.getWallet(),
          throwsA(isA<FeatureUnavailableException>()),
        );
      }, _always404);
    });

    test('getAvailablePlans -> FeatureUnavailableException with Preview message',
        () async {
      await http.runWithClient(() async {
        try {
          await WalletService.getAvailablePlans();
          fail('expected FeatureUnavailableException');
        } on FeatureUnavailableException catch (e) {
          expect(e.message, Endpoints.featureUnavailableMessage);
        }
      }, _always404);
    });
  });

  group('WalletService when the service is absent (connection refused)', () {
    test('getTransactions throws FeatureUnavailableException, never SocketException',
        () async {
      await http.runWithClient(() async {
        expect(
          () => WalletService.getTransactions(),
          throwsA(isA<FeatureUnavailableException>()),
        );
      }, _alwaysRefused);
    });
  });

  group('CommunitiesService degrades to safe empty values', () {
    test('on 404: mine() -> [], mapPins() -> [], get() -> null, no throw',
        () async {
      await http.runWithClient(() async {
        expect(await CommunitiesService.mine('u'), isEmpty);
        expect(await CommunitiesService.mapPins(), isEmpty);
        expect(await CommunitiesService.get(1), isNull);
        expect(await CommunitiesService.isAvailable(), isTrue); // 404 == reachable
      }, _always404);
    });

    test('on connection refused: everything safe and isAvailable() == false',
        () async {
      await http.runWithClient(() async {
        expect(await CommunitiesService.mine('u'), isEmpty);
        expect(await CommunitiesService.mapPins(), isEmpty);
        expect(await CommunitiesService.resolveByCode('ABC123'), isNull);
        expect(await CommunitiesService.joinFree(1, 'u'), isNull);
        expect(await CommunitiesService.report(1, userId: 'u'), isFalse);
        expect(await CommunitiesService.isAvailable(), isFalse);
      }, _alwaysRefused);
    });
  });

  group('TourShareService', () {
    test('on 404: Preview-only message, ok == false, never throws', () async {
      await http.runWithClient(() async {
        final r = await TourShareService.share(123);
        expect(r.ok, isFalse);
        expect(r.errorMessage, Endpoints.featureUnavailableMessage);
      }, _always404);
    });

    test('on connection refused (generator absent): Preview-only message',
        () async {
      await http.runWithClient(() async {
        final r = await TourShareService.share(123);
        expect(r.ok, isFalse);
        expect(r.errorMessage, Endpoints.featureUnavailableMessage);
      }, _alwaysRefused);
    });
  });
}
