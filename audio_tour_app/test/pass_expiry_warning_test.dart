// [LOCAL-732] Unit tests for the 3-day pass-expiry warning.
//
// Two parts:
//   • PassExpiryWarning.select — the PURE selector over the JoinedCommunity
//     list: 2 days left → warn; 4 days → no; expired → no; free (no expiry) →
//     no; and (by construction of /communities/mine) the owner's own community
//     is never in the list, so it never warns.
//   • PassWarnedStore — the ONCE rule: a second run with the same expires_at
//     yields no new passes to show; a renewal (new expires_at) warns again; the
//     store keeps only the last 50 keys.
//
// Deterministic: select() takes an injectable `now`. The store uses
// SharedPreferences.setMockInitialValues (no platform channel).

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/services/pass_expiry_warning.dart';

// A fixed "now" in UTC so the day maths is timezone-independent.
final _now = DateTime.parse('2026-10-22T12:00:00Z');

// Build a joined community with an expiry a given Duration AFTER _now.
JoinedCommunity _community({
  required int id,
  required String name,
  required bool active,
  Duration? inFromNow, // null → no expiry (free)
}) {
  final expiresAt =
      inFromNow == null ? null : _now.add(inFromNow).toUtc().toIso8601String();
  return JoinedCommunity(
    id: id,
    name: name,
    active: active,
    expiresAt: expiresAt,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('PassExpiryWarning.select', () {
    test('2 days left → warns', () {
      final list = [
        _community(
            id: 1, name: 'Harbourside', active: true, inFromNow: const Duration(days: 2)),
      ];
      final out = PassExpiryWarning.select(list, now: _now);
      expect(out, hasLength(1));
      expect(out.single.id, 1);
      expect(out.single.name, 'Harbourside');
    });

    test('4 days left → no warning (outside the 72 h window)', () {
      final list = [
        _community(
            id: 2, name: 'Old Town', active: true, inFromNow: const Duration(days: 4)),
      ];
      expect(PassExpiryWarning.select(list, now: _now), isEmpty);
    });

    test('expired (active flag false) → no warning', () {
      final list = [
        _community(
            id: 3,
            name: 'Lapsed',
            active: false,
            inFromNow: const Duration(days: 1)),
      ];
      expect(PassExpiryWarning.select(list, now: _now), isEmpty);
    });

    test('expiry in the past even if flagged active → no warning', () {
      // Defensive: a pass whose expiry already passed is the AT-expiry case,
      // not this 3-day heads-up.
      final list = [
        _community(
            id: 4,
            name: 'JustEnded',
            active: true,
            inFromNow: const Duration(hours: -1)),
      ];
      expect(PassExpiryWarning.select(list, now: _now), isEmpty);
    });

    test('free community (no expiry) → no warning', () {
      final list = [
        _community(id: 5, name: 'Free Folk', active: true, inFromNow: null),
      ];
      expect(PassExpiryWarning.select(list, now: _now), isEmpty);
    });

    test('owner community is never in the mine list, so never warns', () {
      // /communities/mine returns MEMBERSHIPS only; the owner is not a member of
      // their own community (server JOINs community_memberships). So the owner
      // community simply is not present in the input — represented here by an
      // empty list — and nothing warns.
      expect(PassExpiryWarning.select(const <JoinedCommunity>[], now: _now),
          isEmpty);
    });

    test('exactly 72 h left → warns (boundary inclusive)', () {
      final list = [
        _community(
            id: 6, name: 'Edge', active: true, inFromNow: const Duration(hours: 72)),
      ];
      expect(PassExpiryWarning.select(list, now: _now), hasLength(1));
    });

    test('under 24 h left → still warns', () {
      final list = [
        _community(
            id: 7, name: 'Soon', active: true, inFromNow: const Duration(hours: 5)),
      ];
      expect(PassExpiryWarning.select(list, now: _now), hasLength(1));
    });

    test('mix: only the qualifying ones come back', () {
      final list = [
        _community(id: 1, name: 'Warn A', active: true, inFromNow: const Duration(days: 2)),
        _community(id: 2, name: 'Too far', active: true, inFromNow: const Duration(days: 4)),
        _community(id: 3, name: 'Free', active: true, inFromNow: null),
        _community(id: 4, name: 'Warn B', active: true, inFromNow: const Duration(hours: 10)),
        _community(id: 5, name: 'Expired', active: false, inFromNow: const Duration(days: 1)),
      ];
      final out = PassExpiryWarning.select(list, now: _now);
      expect(out.map((p) => p.id), [1, 4]);
    });
  });

  group('PassWarnedStore once-rule', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('first run shows, second run with same expires_at shows nothing', () async {
      final qualifying = PassExpiryWarning.select(
        [
          _community(
              id: 1, name: 'Harbourside', active: true, inFromNow: const Duration(days: 2)),
        ],
        now: _now,
      );

      // First entry: not yet warned → shown.
      final firstShow = await PassWarnedStore.unwarned(qualifying);
      expect(firstShow, hasLength(1));
      await PassWarnedStore.markWarned(firstShow.map((p) => p.warnedKey));

      // Second entry, SAME pass period (same expires_at) → nothing to show.
      final secondShow = await PassWarnedStore.unwarned(qualifying);
      expect(secondShow, isEmpty);
    });

    test('a renewal (new expires_at) warns again', () async {
      final period1 = PassExpiryWarning.select(
        [_community(id: 1, name: 'C', active: true, inFromNow: const Duration(days: 2))],
        now: _now,
      );
      await PassWarnedStore.markWarned(
          (await PassWarnedStore.unwarned(period1)).map((p) => p.warnedKey));
      expect(await PassWarnedStore.unwarned(period1), isEmpty);

      // Renewal: expires_at moves (D701) → a new once-key → warns again. Model
      // the new period as a fresh expiry 2 days out from a LATER now.
      final laterNow = _now.add(const Duration(days: 300));
      final period2 = PassExpiryWarning.select(
        [
          JoinedCommunity(
            id: 1,
            name: 'C',
            active: true,
            expiresAt:
                laterNow.add(const Duration(days: 2)).toUtc().toIso8601String(),
          ),
        ],
        now: laterNow,
      );
      expect(period2, hasLength(1));
      // Different once-key than period 1.
      expect(period2.single.warnedKey, isNot(period1.single.warnedKey));
      final renewalShow = await PassWarnedStore.unwarned(period2);
      expect(renewalShow, hasLength(1));
    });

    test('keeps only the last 50 keys', () async {
      // Write 60 distinct keys; the oldest 10 must be dropped.
      final keys = List.generate(60, (i) => 'pass_warned_${i}_exp');
      await PassWarnedStore.markWarned(keys);
      final prefs = await SharedPreferences.getInstance();
      final stored = prefs.getStringList('pass_warned_keys')!;
      expect(stored, hasLength(PassWarnedStore.maxKeys));
      // The newest 50 survive (indices 10..59); the oldest 10 are gone.
      expect(stored.first, 'pass_warned_10_exp');
      expect(stored.last, 'pass_warned_59_exp');
      expect(await PassWarnedStore.hasWarned('pass_warned_9_exp'), isFalse);
      expect(await PassWarnedStore.hasWarned('pass_warned_10_exp'), isTrue);
    });

    test('warnedKey shape is pass_warned_<id>_<expires_at>', () {
      final p = PassExpiryWarning.select(
        [_community(id: 42, name: 'K', active: true, inFromNow: const Duration(days: 1))],
        now: _now,
      ).single;
      expect(p.warnedKey, 'pass_warned_42_${p.expiresAt}');
    });
  });
}
