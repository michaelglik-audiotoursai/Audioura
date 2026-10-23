// [LOCAL-738] Create-form logic unit tests (Michael's review C2/C2b/C2c/C2d).
//
// These cover the Flutter-side rules without a running app or network, exactly
// the bugs Michael hit on his iPhone:
//   * ONE price per length: ticking month at $5 and year at $20 sends exactly
//     [{usd5, month}, {usd20, year}] — no cross-product, no "$15/month AND
//     $15/year".
//   * changing a chip changes the payload (the stale-selection bug: what is
//     shown is what is sent).
//   * RED TEST: a price outside the server's allowed list cannot be sent and
//     cannot make the form valid — this test FAILS if an off-list price slips
//     through.
//   * release cadence label ("New tours: weekly") from the stored cadence.
//   * CommunityPass / release_cadence JSON parsing on the community model.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';

void main() {
  // The server's allowed prices (APPLE_LIVE_PASS_PRODUCTS): $1/$5/$10/$20.
  const allowed = {
    'audioura.pass.usd1',
    'audioura.pass.usd5',
    'audioura.pass.usd10',
    'audioura.pass.usd20',
  };

  group('CommunityPassForm.passOptions — one price per length', () {
    test('month at \$5 and year at \$20 -> exactly [{usd5,month},{usd20,year}]',
        () {
      final enabled = {'day': false, 'week': false, 'month': true, 'year': true};
      final price = {
        'day': null,
        'week': null,
        'month': 'audioura.pass.usd5',
        'year': 'audioura.pass.usd20',
      };
      final opts = CommunityPassForm.passOptions(
          enabled: enabled, price: price, allowed: allowed);
      expect(opts, [
        {'product_id': 'audioura.pass.usd5', 'length': 'month'},
        {'product_id': 'audioura.pass.usd20', 'length': 'year'},
      ]);
    });

    test('a ticked length with no price is skipped (never half-sent)', () {
      final enabled = {'day': false, 'week': true, 'month': true, 'year': false};
      final price = {
        'day': null,
        'week': null, // ticked but no price → skipped
        'month': 'audioura.pass.usd1',
        'year': null,
      };
      final opts = CommunityPassForm.passOptions(
          enabled: enabled, price: price, allowed: allowed);
      expect(opts, [
        {'product_id': 'audioura.pass.usd1', 'length': 'month'},
      ]);
    });

    test('changing a chip changes the payload (no stale selection)', () {
      final enabled = {'day': false, 'week': false, 'month': true, 'year': false};
      final price = <String, String?>{
        'day': null,
        'week': null,
        'month': 'audioura.pass.usd5',
        'year': null,
      };
      var opts = CommunityPassForm.passOptions(
          enabled: enabled, price: price, allowed: allowed);
      expect(opts, [
        {'product_id': 'audioura.pass.usd5', 'length': 'month'},
      ]);

      // Organiser taps the $20 chip for month: the payload MUST follow.
      price['month'] = 'audioura.pass.usd20';
      opts = CommunityPassForm.passOptions(
          enabled: enabled, price: price, allowed: allowed);
      expect(opts, [
        {'product_id': 'audioura.pass.usd20', 'length': 'month'},
      ]);
    });

    test('no length on -> empty payload', () {
      final enabled = {'day': false, 'week': false, 'month': false, 'year': false};
      final price = {'day': null, 'week': null, 'month': null, 'year': null};
      expect(
          CommunityPassForm.passOptions(
              enabled: enabled, price: price, allowed: allowed),
          isEmpty);
    });

    // ── RED TEST ──────────────────────────────────────────────────────────
    test('RED: a price OUTSIDE the server list is never sent', () {
      final enabled = {'day': false, 'week': false, 'month': true, 'year': false};
      // $15 is NOT in APPLE_LIVE_PASS_PRODUCTS — exactly what broke on the phone.
      final price = {
        'day': null,
        'week': null,
        'month': 'audioura.pass.usd15',
        'year': null,
      };
      final opts = CommunityPassForm.passOptions(
          enabled: enabled, price: price, allowed: allowed);
      // It must be dropped — sending it would 400 pass_product_not_available.
      expect(opts, isEmpty,
          reason: 'an off-list price (\$15) must never be sent');
      // And the form must not be valid with only an off-list price.
      expect(
          CommunityPassForm.passesValid(
              enabled: enabled, price: price, allowed: allowed),
          isFalse,
          reason: 'an off-list price must not make the form valid');
    });
  });

  group('CommunityPassForm.passesValid', () {
    test('valid when the one ticked length has an allowed price', () {
      expect(
          CommunityPassForm.passesValid(
            enabled: {'day': false, 'week': false, 'month': true, 'year': false},
            price: {
              'day': null,
              'week': null,
              'month': 'audioura.pass.usd5',
              'year': null
            },
            allowed: allowed,
          ),
          isTrue);
    });

    test('invalid when a ticked length has no price', () {
      expect(
          CommunityPassForm.passesValid(
            enabled: {'day': false, 'week': true, 'month': true, 'year': false},
            price: {
              'day': null,
              'week': null,
              'month': 'audioura.pass.usd5',
              'year': null
            },
            allowed: allowed,
          ),
          isFalse);
    });

    test('invalid when no length is on', () {
      expect(
          CommunityPassForm.passesValid(
            enabled: {'day': false, 'week': false, 'month': false, 'year': false},
            price: {'day': null, 'week': null, 'month': null, 'year': null},
            allowed: allowed,
          ),
          isFalse);
    });
  });

  group('CommunityCopy.releaseCadenceLabel', () {
    test('week -> New tours: weekly (default)', () {
      expect(CommunityCopy.releaseCadenceLabel('week'), 'New tours: weekly');
    });
    test('day/month/year', () {
      expect(CommunityCopy.releaseCadenceLabel('day'), 'New tours: daily');
      expect(CommunityCopy.releaseCadenceLabel('month'), 'New tours: monthly');
      expect(CommunityCopy.releaseCadenceLabel('year'), 'New tours: yearly');
    });
  });

  group('PassPrice + Community.release_cadence parsing', () {
    test('PassPrice.fromJson', () {
      final p = PassPrice.fromJson(
          {'product_id': 'audioura.pass.usd5', 'price_usd': 5, 'label': '\$5'});
      expect(p.productId, 'audioura.pass.usd5');
      expect(p.priceUsd, 5.0);
      expect(p.label, '\$5');
    });

    test('Community reads release_cadence, defaults to week when absent', () {
      final withCadence = Community.fromJson({
        'id': 1,
        'name': 'Owls',
        'release_cadence': 'month',
        'passes': [],
      });
      expect(withCadence.releaseCadence, 'month');

      final absent = Community.fromJson({'id': 2, 'name': 'No cadence'});
      expect(absent.releaseCadence, 'week');
    });
  });

  group('CreateResult', () {
    test('ok is true only with a community', () {
      final good = CreateResult(
          community: Community.fromJson({'id': 1, 'name': 'X'}));
      expect(good.ok, isTrue);
      const bad = CreateResult(
          error: 'name_taken', message: 'That community name is taken.');
      expect(bad.ok, isFalse);
      expect(bad.message, 'That community name is taken.');
    });
  });
}
