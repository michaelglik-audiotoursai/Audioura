// [LOCAL-752 C] An explicit download/re-download of a tour must REMOVE it from
// `deleted_tour_ids` (kDeletedTourIdsPrefKey), so RefreshPlanner/SyncPlanner stop
// skipping it forever.
//
// Michael's history (2026-10-23): he DELETED community tour 716 on the Pixel
// (deleted set holds "716"), then RE-DOWNLOADED it from the community page. The
// organiser's edit took the server to v3, but the Pixel never re-downloaded it:
// RefreshPlanner skips any id in `deleted_tour_ids`, and "716" was still there.
// The fix: an explicit download clears the id, so the next sync refresh picks up
// v3 and shows "… was updated by the organiser."
//
// Pure tests of the two seams the fix introduces:
//   * removeFromDeletedTourIds(Set, ids)  — pure set operation (dependency-free);
//   * clearDeletedTourIds(prefs, ids)     — the SharedPreferences-backed clear the
//     download path calls (download → save removes the id from the stored list).
//
// Also an end-to-end guard with the REAL RefreshPlanner: a held tour whose id was
// deleted is skipped; once the id is cleared, the SAME planner re-downloads it.

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/community_downloads.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('removeFromDeletedTourIds (pure)', () {
    test('removes the given id from the set', () {
      final set = {'716', '800'};
      final out = removeFromDeletedTourIds(set, [716]);
      expect(out.contains('716'), isFalse);
      expect(out.contains('800'), isTrue);
    });

    test('is a no-op when the id was not deleted', () {
      final set = {'800'};
      final out = removeFromDeletedTourIds(set, [716]);
      expect(out, {'800'});
    });

    test('accepts int and string ids', () {
      final set = {'716', '900'};
      final out = removeFromDeletedTourIds(set, ['716', 900]);
      expect(out, isEmpty);
    });
  });

  group('clearDeletedTourIds (SharedPreferences)', () {
    test('an explicit download clears the deleted id', () async {
      SharedPreferences.setMockInitialValues({
        kDeletedTourIdsPrefKey: <String>['716', '800'],
      });
      final prefs = await SharedPreferences.getInstance();
      await clearDeletedTourIds(prefs, [716]);
      final after =
          (prefs.getStringList(kDeletedTourIdsPrefKey) ?? const []).toSet();
      expect(after.contains('716'), isFalse,
          reason: 're-downloading 716 must clear it from deleted_tour_ids so the '
              'organiser edit can reach the member (LOCAL-752 C).');
      expect(after.contains('800'), isTrue);
    });

    test('no deleted list present → no crash, nothing to clear', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      await clearDeletedTourIds(prefs, [716]);
      expect(prefs.getStringList(kDeletedTourIdsPrefKey) ?? const [], isEmpty);
    });
  });

  group("Michael's history → RefreshPlanner re-downloads after clear", () {
    final held = [
      HeldCommunityTour(
        tourId: 716,
        communityId: 10,
        savedVersion: 1,
        serverVersion: 3, // organiser edited → v3
        language: 'en',
        isCommunityTour: true,
        name: 'Walking tour in Danvers, MA',
      ),
    ];

    test('still-deleted 716 is skipped (the bug)', () {
      final plan = RefreshPlanner.plan(
        held: held,
        activeCommunityIds: {10},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        deletedTourIds: {'716'},
      );
      expect(plan, isEmpty);
    });

    test('once cleared, the SAME planner re-downloads 716 to v3', () {
      final cleared = removeFromDeletedTourIds({'716'}, [716]);
      final plan = RefreshPlanner.plan(
        held: held,
        activeCommunityIds: {10},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        deletedTourIds: cleared,
      );
      expect(plan.length, 1);
      expect(plan.first.tourId, 716);
      expect(plan.first.serverVersion, 3);
    });
  });
}
