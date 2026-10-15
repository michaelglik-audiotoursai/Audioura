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

/// LOCAL-694B: the GCloud API gateway's JSON 404 for an unknown path. This is
/// route-missing (the gateway doesn't know the route) and must read as Preview.
const _gateway404 = '{"error":"endpoint not found","service":"api-gateway"}';
MockClient _alwaysGateway404() => MockClient((req) async => http.Response(
    _gateway404, 404,
    headers: {'content-type': 'application/json'}));

/// LOCAL-694B: a SERVICE'S OWN JSON 404 (normal not-found, e.g. an unknown id
/// on a route that EXISTS). This must NOT be treated as feature-unavailable.
MockClient _alwaysServiceJson404(String body) => MockClient((req) async =>
    http.Response(body, 404, headers: {'content-type': 'application/json'}));

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
    test('on HTML 404 (route missing): Preview-only message, ok == false',
        () async {
      await http.runWithClient(() async {
        final r = await TourShareService.share(123);
        expect(r.ok, isFalse);
        expect(r.errorMessage, Endpoints.featureUnavailableMessage);
      }, _always404);
    });

    test('on gateway JSON 404 (route missing): Preview-only message', () async {
      await http.runWithClient(() async {
        final r = await TourShareService.share(123);
        expect(r.ok, isFalse);
        expect(r.errorMessage, Endpoints.featureUnavailableMessage);
      }, _alwaysGateway404);
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

  // LOCAL-694B (LEAD review): the END-TO-END proof that a SERVICE'S OWN JSON
  // 404 (a normal not-found on a route that exists) is NOT turned into the
  // "Preview only" message — it keeps the ordinary not-found handling.
  group('normal not-found (service JSON 404) is NOT feature-unavailable', () {
    test('WalletService.getWallet on JSON 404 -> plain Exception, NOT Preview',
        () async {
      await http.runWithClient(() async {
        // The wrapper returns the response (not route-missing); wallet_service
        // then throws its ordinary "Failed to fetch wallet" Exception.
        try {
          await WalletService.getWallet();
          fail('expected an exception');
        } on FeatureUnavailableException {
          fail('a service JSON 404 must NOT be a FeatureUnavailableException');
        } catch (e) {
          expect(e, isA<Exception>());
          expect(e.toString(), isNot(contains('Preview')));
        }
      }, () => _alwaysServiceJson404('{"error":"not_found"}'));
    });

    test('TourShareService on JSON 404 {error:tour not found} -> server message',
        () async {
      await http.runWithClient(() async {
        final r = await TourShareService.share(123);
        expect(r.ok, isFalse);
        // Keeps the service's own message (capitalised), NOT "Preview only".
        expect(r.errorMessage, 'Tour not found');
        expect(r.errorMessage, isNot(Endpoints.featureUnavailableMessage));
      }, () => _alwaysServiceJson404('{"error":"tour not found"}'));
    });

    test('CommunitiesService.get on JSON 404 -> null (normal), isAvailable true',
        () async {
      await http.runWithClient(() async {
        // A JSON 404 is still a reachable service: isAvailable stays true and
        // the lookup returns null (no community) rather than a Preview state.
        expect(await CommunitiesService.get(1), isNull);
        expect(await CommunitiesService.isAvailable(), isTrue);
      }, () => _alwaysServiceJson404('{"error":"not_found"}'));
    });
  });
}
