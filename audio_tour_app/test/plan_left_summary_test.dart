// [LOCAL-733 / D703] Unit tests for the Flutter-free PlanLeftSummary helper
// that phrases "what is left" for the plan card, the post-purchase message and
// the Generate-screen line.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/entitlements_service.dart';
import 'package:audio_tour_app_dev/utils/plan_left_summary.dart';

Entitlements _ent(String level, Map<String, dynamic> allowances,
    {String? anniversary, String? displayName}) {
  return Entitlements.fromJson({
    'level': level,
    'display_name': displayName ??
        {'l1': 'Introduction', 'l2': 'Free', 'l3': '\$10 Pack', 'l4': 'Curator'}[level] ??
        level,
    'anniversary_at': anniversary,
    'allowances_left': allowances,
    'levels': const [],
  });
}

void main() {
  group('cardLine', () {
    test('\$10 Pack adds "left" and the end date', () {
      final line = PlanLeftSummary.cardLine(
          _ent('l3', {'fresh_left': 8, 'edits_left': 6}),
          endDate: '22 Nov 2026');
      expect(line,
          '\$10 Pack · 8 new tours and 6 stop-adding edits left · until 22 Nov 2026');
    });

    test('Curator reports operations', () {
      final line = PlanLeftSummary.cardLine(_ent('l4', {'ops_left': 29}),
          endDate: '22 Nov 2026');
      expect(line,
          'Curator · 29 operations (new tours or edits) left · until 22 Nov 2026');
    });

    test('Free uses its own today phrasing, no "until"', () {
      final line = PlanLeftSummary.cardLine(_ent('l2', {'tours_today_left': 1}));
      expect(line, 'Free · 1 new tour left today');
    });

    test('Free falls back to the monthly count when today is absent', () {
      final line =
          PlanLeftSummary.cardLine(_ent('l2', {'tours_this_month_left': 3}));
      expect(line, 'Free · 3 new tours left this month');
    });

    test('Introduction renders nothing', () {
      expect(PlanLeftSummary.cardLine(_ent('l1', {})), isNull);
    });
  });

  group('generateLine', () {
    test('pack -> "in your pack"', () {
      expect(PlanLeftSummary.generateLine(_ent('l3', {'fresh_left': 3})),
          '3 new tours left in your pack');
    });

    test('Curator -> operations in your pack', () {
      expect(PlanLeftSummary.generateLine(_ent('l4', {'ops_left': 12})),
          '12 operations left in your pack');
    });

    test('Free -> left today', () {
      expect(PlanLeftSummary.generateLine(_ent('l2', {'tours_today_left': 1})),
          '1 new tour left today');
    });

    test('Introduction -> null (hidden)', () {
      expect(PlanLeftSummary.generateLine(_ent('l1', {})), isNull);
    });
  });

  group('purchaseMessage', () {
    test('pack says what you now have and until when', () {
      final msg = PlanLeftSummary.purchaseMessage(
          _ent('l3', {'fresh_left': 8, 'edits_left': 6}),
          endDate: '22 Nov 2026');
      expect(msg, 'You now have 8 new tours and 6 edits until 22 Nov 2026.');
    });

    test('Curator message', () {
      final msg = PlanLeftSummary.purchaseMessage(_ent('l4', {'ops_left': 29}),
          endDate: '22 Nov 2026');
      expect(msg,
          'You now have 29 operations (new tours or edits) until 22 Nov 2026.');
    });
  });
}
