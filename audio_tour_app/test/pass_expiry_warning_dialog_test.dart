// [LOCAL-732] Widget tests for the 3-day pass-expiry warning dialog.
//
// Builds PassExpiryWarningDialog directly (no network) from a list of
// ExpiringPass with an injectable `now`, so it is deterministic. MainScreen
// shows this SAME widget, so the test exercises the real markup.
//
// Includes the required RED test (see pass_expiry_warning_red_test.dart for the
// once-rule red test): here the red assertion is that the raw ISO expires_at is
// never printed in a row — the dialog shows the short formatted line, not the
// server string.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/services/pass_expiry_warning.dart';
import 'package:audio_tour_app_dev/widgets/pass_expiry_warning_dialog.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

// A fixed "now" and two passes 2 days / 10 hours out (UTC, zone-less like the
// server's common shape).
final _now = DateTime.parse('2026-10-22T12:00:00Z');

List<ExpiringPass> _twoPasses() {
  final e1 = _now.add(const Duration(days: 2)).toUtc().toIso8601String();
  final e2 = _now.add(const Duration(hours: 10)).toUtc().toIso8601String();
  return [
    ExpiringPass(JoinedCommunity(
        id: 7, name: 'Harbourside Walks', active: true, expiresAt: e1)),
    ExpiringPass(JoinedCommunity(
        id: 9, name: 'Old Town Tales', active: true, expiresAt: e2)),
  ];
}

void main() {
  group('PassExpiryWarningDialog', () {
    testWidgets('lists two communities with a Renew link each', (tester) async {
      await tester.pumpWidget(_wrap(PassExpiryWarningDialog(
        passes: _twoPasses(),
        now: _now,
        onRenew: (_) {},
        onLater: () {},
      )));
      await tester.pump();

      expect(find.text('Community pass ending soon'), findsOneWidget);

      // One row + one Renew link per community.
      expect(find.byKey(const Key('pass_warning_row_7')), findsOneWidget);
      expect(find.byKey(const Key('pass_warning_row_9')), findsOneWidget);
      expect(find.byKey(const Key('pass_warning_renew_7')), findsOneWidget);
      expect(find.byKey(const Key('pass_warning_renew_9')), findsOneWidget);
      expect(find.text('Renew'), findsNWidgets(2));
      expect(find.byKey(const Key('pass_warning_later')), findsOneWidget);

      // Each row carries the community name and a short "in N" countdown.
      final row7 = tester.widget<Text>(find.byKey(const Key('pass_warning_row_7')));
      expect(row7.data, startsWith('Harbourside Walks: ends '));
      expect(row7.data, contains('in 2 days'));
      final row9 = tester.widget<Text>(find.byKey(const Key('pass_warning_row_9')));
      expect(row9.data, startsWith('Old Town Tales: ends '));
      expect(row9.data, contains('in 10 hours'));

      // The body explains renewing adds days, in plain English (no store name).
      expect(
          find.textContaining('Renew to keep getting new episodes and tours.'),
          findsOneWidget);
      expect(find.textContaining('adds its days'), findsOneWidget);
    });

    testWidgets('Renew fires with the right community id; Later fires',
        (tester) async {
      final renewed = <int>[];
      var laterCount = 0;
      await tester.pumpWidget(_wrap(PassExpiryWarningDialog(
        passes: _twoPasses(),
        now: _now,
        onRenew: renewed.add,
        onLater: () => laterCount++,
      )));
      await tester.pump();

      await tester.tap(find.byKey(const Key('pass_warning_renew_9')));
      expect(renewed, [9]);

      await tester.tap(find.byKey(const Key('pass_warning_later')));
      expect(laterCount, 1);
    });

    testWidgets('RED: a row never prints the raw ISO expires_at', (tester) async {
      final passes = _twoPasses();
      await tester.pumpWidget(_wrap(PassExpiryWarningDialog(
        passes: passes,
        now: _now,
        onRenew: (_) {},
        onLater: () {},
      )));
      await tester.pump();

      // The raw server string (and its ISO "T..:..:.." time) must be absent:
      // the dialog shows the short formatted line, not the ISO value.
      for (final p in passes) {
        expect(find.textContaining(p.expiresAt), findsNothing);
      }
      expect(find.textContaining('T12:00:00'), findsNothing);
    });
  });
}
