// [LOCAL-732] RED test: the once-key check is load-bearing.
//
// The warning must fire ONCE per pass period. This test models the two paths
// the app could take on a SECOND launch:
//   • WITH the once-key check (PassWarnedStore.unwarned) — the real code path —
//     the second launch shows NOTHING.
//   • WITHOUT the check (using the raw selection directly) — the regression —
//     the second launch would STILL have the pass to show.
//
// The first expectation is what the shipped app does and must stay green. The
// second expectation documents the bug this guards against: it shows that if
// MainScreen skipped PassWarnedStore.unwarned and used the raw selection, the
// dialog would reappear on every launch. Delete the once-key check in
// MainScreen and the behaviour collapses onto the (still-populated) raw
// selection — the once-rule tests in pass_expiry_warning_test.dart then fail.

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/services/pass_expiry_warning.dart';

final _now = DateTime.parse('2026-10-22T12:00:00Z');

List<JoinedCommunity> _mine() => [
      JoinedCommunity(
        id: 1,
        name: 'Harbourside',
        active: true,
        expiresAt:
            _now.add(const Duration(days: 2)).toUtc().toIso8601String(),
      ),
    ];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('second launch: once-key check suppresses, raw selection would not',
      () async {
    // ── First launch: select, show, mark warned. ──
    final first = PassExpiryWarning.select(_mine(), now: _now);
    final firstToShow = await PassWarnedStore.unwarned(first);
    expect(firstToShow, hasLength(1)); // shown on first launch
    await PassWarnedStore.markWarned(firstToShow.map((p) => p.warnedKey));

    // ── Second launch, SAME pass period. ──
    final second = PassExpiryWarning.select(_mine(), now: _now);

    // The RAW selection (no once-key check) STILL has the pass — this is the
    // regression a missing check would ship: the dialog every launch.
    expect(second, hasLength(1),
        reason: 'raw selection cannot deduplicate across launches');

    // The REAL path applies the once-key check and shows nothing. If this ever
    // returns the pass again, the "only once" contract is broken.
    final secondToShow = await PassWarnedStore.unwarned(second);
    expect(secondToShow, isEmpty,
        reason: 'the once-key check must suppress the repeat warning');
  });
}
