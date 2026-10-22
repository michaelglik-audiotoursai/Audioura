// [LOCAL-734] Unit tests for IapService.stubFromModeResponse — the pure
// per-platform decision behind purchasesModeIsStub(). They cover the three
// cases from the ticket:
//   • iOS on a per_store server -> StoreKit (NOT stub);
//   • Android on a per_store server whose android value is 'stub' -> TEST
//     PURCHASE (stub);
//   • a legacy server with no `platforms` key -> fall back to the top-level
//     `stub` bool (today's behaviour).
//
// Pure Dart: no network, no running server, no Platform plugin.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/iap_service.dart';

void main() {
  group('stubFromModeResponse — per_store (platforms present)', () {
    // The Mac Mini local stack: ios drives real Apple sandbox, android runs the
    // TEST PURCHASE. Legacy top-level stub is FALSE (must not sway a new app).
    final perStore = {
      'mode': 'per_store',
      'stub': false,
      'verifies_real': true,
      'platforms': {'ios': 'apple', 'android': 'stub'},
    };

    test('iOS uses StoreKit (not the stub path)', () {
      final decided = IapService.stubFromModeResponse(
        perStore,
        isIOS: true,
        isAndroid: false,
      );
      expect(decided, isFalse);
    });

    test('Android with android==stub uses the TEST PURCHASE path', () {
      final decided = IapService.stubFromModeResponse(
        perStore,
        isIOS: false,
        isAndroid: true,
      );
      expect(decided, isTrue);
    });

    test('Android with android==google drives real Play billing (not stub)', () {
      final decided = IapService.stubFromModeResponse(
        {
          'mode': 'per_store',
          'stub': false,
          'platforms': {'ios': 'apple', 'android': 'google'},
        },
        isIOS: false,
        isAndroid: true,
      );
      expect(decided, isFalse);
    });
  });

  group('stubFromModeResponse — legacy server (no platforms key)', () {
    test('falls back to the top-level stub bool (true)', () {
      final decided = IapService.stubFromModeResponse(
        {'mode': 'stub', 'stub': true, 'verifies_real': false},
        isIOS: true,
        isAndroid: false,
      );
      expect(decided, isTrue);
    });

    test('falls back to the top-level stub bool (false) on both platforms', () {
      final body = {'mode': 'apple', 'stub': false, 'verifies_real': true};
      expect(
        IapService.stubFromModeResponse(body, isIOS: true, isAndroid: false),
        isFalse,
      );
      expect(
        IapService.stubFromModeResponse(body, isIOS: false, isAndroid: true),
        isFalse,
      );
    });

    test('malformed body (no platforms, no stub) returns null → caller guesses',
        () {
      final decided = IapService.stubFromModeResponse(
        {'mode': 'weird'},
        isIOS: true,
        isAndroid: false,
      );
      expect(decided, isNull);
    });
  });
}
