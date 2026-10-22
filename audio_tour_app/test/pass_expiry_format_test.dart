// [LOCAL-731 / D701] Unit tests for the shared pass-expiry formatter.
//
// These are deterministic: [PassExpiryFormat.format] takes an injectable `now`,
// and the inputs use explicit zones (or none, to exercise the "treat as UTC"
// path). The expected day/month/year are computed from the LOCAL time the
// parser resolves to, so the suite passes in any machine timezone.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/pass_expiry_format.dart';

void main() {
  group('PassExpiryFormat', () {
    test('null expiry → no line', () {
      expect(PassExpiryFormat.format(null), isNull);
      expect(PassExpiryFormat.format('   '), isNull);
    });

    test('active, more than 1 day left → "Member until <date> · N days left"',
        () {
      // 30 days + a few hours left, measured in UTC.
      final now = DateTime.parse('2026-10-22T15:16:15Z');
      const expires = '2026-11-21T18:16:15Z';
      final out = PassExpiryFormat.format(expires, now: now);

      final localExpiry = PassExpiryFormat.parse(expires)!;
      expect(out, isNotNull);
      expect(out, startsWith('Member until ${PassExpiryFormat.formatDate(localExpiry)} · '));
      expect(out, endsWith('30 days left'));
    });

    test('active, under 24 h left → "ends in N hours" with a time', () {
      final now = DateTime.parse('2026-11-21T10:16:15Z');
      const expires = '2026-11-21T15:16:15Z'; // 5 hours later
      final out = PassExpiryFormat.format(expires, now: now);

      final localExpiry = PassExpiryFormat.parse(expires)!;
      expect(out, isNotNull);
      expect(out, contains('ends in 5 hours'));
      expect(out, contains(PassExpiryFormat.formatTime(localExpiry)));
      expect(out, startsWith('Member until '));
    });

    test('active, exactly 1 hour left → singular "hour"', () {
      final now = DateTime.parse('2026-11-21T14:16:15Z');
      const expires = '2026-11-21T15:16:15Z';
      final out = PassExpiryFormat.format(expires, now: now);
      expect(out, contains('ends in 1 hour'));
      expect(out, isNot(contains('1 hours')));
    });

    test('expired → "Expired on <date>"', () {
      final now = DateTime.parse('2026-11-22T15:16:15Z');
      const expires = '2026-11-21T15:16:15Z'; // yesterday
      final out = PassExpiryFormat.format(expires, now: now);

      final localExpiry = PassExpiryFormat.parse(expires)!;
      expect(out, 'Expired on ${PassExpiryFormat.formatDate(localExpiry)}');
    });

    test('zone-less ISO string is treated as UTC', () {
      // No trailing Z and no offset — the server's common shape.
      const expires = '2026-11-21T15:16:15.422467';
      const withZone = '2026-11-21T15:16:15.422467Z';      // The parser must resolve the zone-less string to the SAME local instant
      // as the explicitly-UTC one.
      expect(PassExpiryFormat.parse(expires),
          PassExpiryFormat.parse(withZone));

      final now = DateTime.parse('2026-11-20T15:16:15Z');
      final out = PassExpiryFormat.format(expires, now: now);
      expect(out, isNotNull);
      expect(out, startsWith('Member until '));
    });

    test('month boundary: expiry on the 1st of the next month', () {
      final now = DateTime.parse('2026-11-28T12:00:00Z');
      const expires = '2026-12-01T12:00:00Z';
      final out = PassExpiryFormat.format(expires, now: now);

      final localExpiry = PassExpiryFormat.parse(expires)!;
      // The formatted date names the month correctly across the boundary.
      expect(out, contains(PassExpiryFormat.formatDate(localExpiry)));
      // 3 whole days.
      expect(out, endsWith('3 days left'));
    });

    test('formatDate / formatTime shapes', () {
      final d = DateTime(2026, 11, 21, 15, 16);
      expect(PassExpiryFormat.formatDate(d), '21 Nov 2026');
      expect(PassExpiryFormat.formatTime(d), '15:16');
      // Zero-padding.
      final e = DateTime(2026, 1, 5, 9, 3);
      expect(PassExpiryFormat.formatDate(e), '5 Jan 2026');
      expect(PassExpiryFormat.formatTime(e), '09:03');
    });
  });

  // [LOCAL-732] The short countdown variant used by the 3-day warning dialog.
  group('PassExpiryFormat.formatShort', () {
    test('2 days left → "<weekday> <d> <mon> · in 2 days"', () {
      final now = DateTime.parse('2026-10-22T12:00:00Z');
      final expires = now.add(const Duration(days: 2)).toUtc().toIso8601String();
      final out = PassExpiryFormat.formatShort(expires, now: now);
      final local = PassExpiryFormat.parse(expires)!;
      expect(out, '${PassExpiryFormat.formatWeekdayDate(local)} · in 2 days');
    });

    test('under 24 h → "... · in N hours"', () {
      final now = DateTime.parse('2026-10-22T12:00:00Z');
      final expires = now.add(const Duration(hours: 5)).toUtc().toIso8601String();
      final out = PassExpiryFormat.formatShort(expires, now: now);
      expect(out, endsWith('· in 5 hours'));
    });

    test('exactly 1 day / 1 hour → singular', () {
      final now = DateTime.parse('2026-10-22T12:00:00Z');
      final oneDay = now.add(const Duration(days: 1)).toUtc().toIso8601String();
      expect(PassExpiryFormat.formatShort(oneDay, now: now), endsWith('· in 1 day'));
      final oneHour = now.add(const Duration(hours: 1)).toUtc().toIso8601String();
      expect(PassExpiryFormat.formatShort(oneHour, now: now), endsWith('· in 1 hour'));
    });

    test('null / blank / expired → null', () {
      final now = DateTime.parse('2026-10-22T12:00:00Z');
      expect(PassExpiryFormat.formatShort(null, now: now), isNull);
      expect(PassExpiryFormat.formatShort('   ', now: now), isNull);
      final past = now.subtract(const Duration(hours: 1)).toUtc().toIso8601String();
      expect(PassExpiryFormat.formatShort(past, now: now), isNull);
    });

    test('formatWeekdayDate shape: "Fri 24 Oct"', () {
      // 2026-10-24 is a Saturday; pick a known weekday deterministically.
      final sat = DateTime(2026, 10, 24); // Saturday
      expect(PassExpiryFormat.formatWeekdayDate(sat), 'Sat 24 Oct');
      final fri = DateTime(2026, 10, 23); // Friday
      expect(PassExpiryFormat.formatWeekdayDate(fri), 'Fri 23 Oct');
    });
  });
}
