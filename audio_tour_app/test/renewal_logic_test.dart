// [LOCAL-598 D8] Unit tests for the app-open renewal decision logic.
//
// decideRenewalAction turns the server flags (renewal_prompt, warn_renewal,
// anniversary_at) plus the stored "last warned anniversary" into what the app
// should show. The rules under test (SUBSCRIPTION_LEVELS.md):
//   • renewal_prompt wins -> the renew-or-lapse sheet.
//   • warn_renewal -> the banner, but ONCE per anniversary.
//   • a new anniversary warns again.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/renewal_logic.dart';
import 'package:audio_tour_app_dev/services/entitlements_service.dart';

Entitlements _ent({
  bool renewalPrompt = false,
  bool warnRenewal = false,
  String? anniversary,
  String level = 'l3',
}) {
  return Entitlements.fromJson({
    'level': level,
    'anniversary_at': anniversary,
    'renewal_prompt': renewalPrompt,
    'warn_renewal': warnRenewal,
    'allowances_left': {},
  });
}

void main() {
  group('decideRenewalAction — renewal_prompt', () {
    test('due -> show the sheet, no banner', () {
      final a = decideRenewalAction(
        _ent(renewalPrompt: true, anniversary: '2026-11-06T00:00:00'),
        lastWarnedAnniversary: null,
      );
      expect(a.showRenewalSheet, isTrue);
      expect(a.showWarningBanner, isFalse);
      expect(a.markWarnedAnniversary, isNull);
    });

    test('renewal_prompt beats warn_renewal (sheet, not banner)', () {
      final a = decideRenewalAction(
        _ent(
          renewalPrompt: true,
          warnRenewal: true,
          anniversary: '2026-11-06T00:00:00',
        ),
        lastWarnedAnniversary: null,
      );
      expect(a.showRenewalSheet, isTrue);
      expect(a.showWarningBanner, isFalse);
    });
  });

  group('decideRenewalAction — warn_renewal (once per anniversary)', () {
    test('first time this anniversary -> banner + mark it', () {
      final a = decideRenewalAction(
        _ent(warnRenewal: true, anniversary: '2026-11-06T00:00:00'),
        lastWarnedAnniversary: null,
      );
      expect(a.showWarningBanner, isTrue);
      expect(a.showRenewalSheet, isFalse);
      expect(a.markWarnedAnniversary, '2026-11-06T00:00:00');
    });

    test('already warned for THIS anniversary -> nothing', () {
      final a = decideRenewalAction(
        _ent(warnRenewal: true, anniversary: '2026-11-06T00:00:00'),
        lastWarnedAnniversary: '2026-11-06T00:00:00',
      );
      expect(a, RenewalAction.none);
    });

    test('new anniversary warns again even if an older one was warned', () {
      final a = decideRenewalAction(
        _ent(warnRenewal: true, anniversary: '2026-12-06T00:00:00'),
        lastWarnedAnniversary: '2026-11-06T00:00:00',
      );
      expect(a.showWarningBanner, isTrue);
      expect(a.markWarnedAnniversary, '2026-12-06T00:00:00');
    });

    test('warn_renewal true but no anniversary -> nothing (can\'t key it)', () {
      final a = decideRenewalAction(
        _ent(warnRenewal: true, anniversary: null),
        lastWarnedAnniversary: null,
      );
      expect(a, RenewalAction.none);
    });
  });

  group('decideRenewalAction — neither flag', () {
    test('no prompt, no warn -> nothing', () {
      final a = decideRenewalAction(
        _ent(anniversary: '2026-11-06T00:00:00'),
        lastWarnedAnniversary: null,
      );
      expect(a, RenewalAction.none);
    });
  });

  group('Entitlements parsing is defensive', () {
    test('unknown fallback has safe values', () {
      expect(Entitlements.unknown.level, 'l1');
      expect(Entitlements.unknown.renewalPrompt, isFalse);
      expect(Entitlements.unknown.warnRenewal, isFalse);
      expect(Entitlements.unknown.anniversary, isNull);
    });

    test('malformed json -> safe defaults, no throw', () {
      final e = Entitlements.fromJson({
        'level': 123, // wrong type
        'anniversary_at': 42, // wrong type
        'allowances_left': 'nope', // wrong type
        'warn_renewal': 'yes', // not a bool
      });
      expect(e.level, 'l1');
      expect(e.anniversaryAt, isNull);
      expect(e.allowances.isEmpty, isTrue);
      expect(e.warnRenewal, isFalse);
    });

    test('allowances parse ints and ignore the rest', () {
      final e = Entitlements.fromJson({
        'level': 'l4',
        'allowances_left': {
          'ops_left': 25,
          'tours_today_left': 3,
        },
      });
      expect(e.level, 'l4');
      expect(e.allowances.opsLeft, 25);
      expect(e.allowances.toursTodayLeft, 3);
      expect(e.allowances.freshLeft, isNull);
    });

    test('levelLabel is plain words', () {
      expect(_ent(level: 'l1').levelLabel, contains('Free'));
      expect(_ent(level: 'l3').levelLabel, contains('\$10'));
      expect(_ent(level: 'l4').levelLabel, contains('\$25'));
      expect(_ent(level: 'tester').levelLabel, 'Tester');
    });
  });
}
