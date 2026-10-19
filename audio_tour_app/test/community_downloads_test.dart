import 'package:shared_preferences/shared_preferences.dart';
// [LOCAL-713 / D675] Community-tour download foundation — pure unit tests
// (no running app, no network, no plugins). Covers:
//   * pickDownloadLanguage (preferred if available, else original);
//   * defaultListeningLanguage (phone language when offered, else English);
//   * rowStatusFor (download / on phone / join);
//   * SyncPlanner.plan (the pure sync-on-open policy, incl. NOTHING on cellular
//     when not allowed, deleted ids never re-downloaded, switch gating);
//   * shouldAdvanceSince (since advances only on success).

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/community_downloads.dart';

void main() {
  group('pickDownloadLanguage', () {
    test('preferred when the tour has it', () {
      expect(pickDownloadLanguage(['en', 'es', 'fr'], 'es', 'en'), 'es');
    });

    test('original when the preferred is not available', () {
      expect(pickDownloadLanguage(['en', 'es'], 'de', 'en'), 'en');
    });

    test('original even when available is empty (community-page row case)', () {
      expect(pickDownloadLanguage(const [], 'de', 'en'), 'en');
    });

    test('preferred equals original is fine', () {
      expect(pickDownloadLanguage(['en'], 'en', 'en'), 'en');
    });

    test('falls back to available.first when original is blank', () {
      expect(pickDownloadLanguage(['ru', 'en'], 'de', ''), 'ru');
    });

    test('last resort returns preferred when nothing is available', () {
      expect(pickDownloadLanguage(const [], 'de', ''), 'de');
    });
  });

  group('defaultListeningLanguage', () {
    test('phone language when Audioura offers it', () {
      expect(defaultListeningLanguage('de'), 'de');
      expect(defaultListeningLanguage('ZH'), 'zh'); // case-insensitive
    });

    test('English when the phone language is not offered', () {
      expect(defaultListeningLanguage('pt'), 'en');
      expect(defaultListeningLanguage(''), 'en');
      expect(defaultListeningLanguage(null), 'en');
    });
  });

  group('rowStatusFor', () {
    test('non-member → join to download', () {
      expect(
        rowStatusFor(
          tourId: 10,
          isMember: false,
          isOwner: false,
          onPhoneTourIds: const {},
        ),
        CommunityTourRowStatus.joinToDownload,
      );
    });

    test('member without the tour → download', () {
      expect(
        rowStatusFor(
          tourId: 10,
          isMember: true,
          isOwner: false,
          onPhoneTourIds: const {'7'},
        ),
        CommunityTourRowStatus.download,
      );
    });

    test('tour already on phone (any language) → on this phone', () {
      expect(
        rowStatusFor(
          tourId: 10,
          isMember: true,
          isOwner: false,
          onPhoneTourIds: const {'10'},
        ),
        CommunityTourRowStatus.onThisPhone,
      );
    });

    test('owner can download even without a membership', () {
      expect(
        rowStatusFor(
          tourId: 10,
          isMember: false,
          isOwner: true,
          onPhoneTourIds: const {},
        ),
        CommunityTourRowStatus.download,
      );
    });

    test('owner who has it → on this phone', () {
      expect(
        rowStatusFor(
          tourId: 10,
          isMember: false,
          isOwner: true,
          onPhoneTourIds: const {'10'},
        ),
        CommunityTourRowStatus.onThisPhone,
      );
    });
  });

  group('SyncPlanner.plan', () {
    // Two new tours: t10 (c1) with en+es, t20 (c2) with ru only.
    final tours = [
      const NewCommunityTour(
          communityId: 1,
          tourId: 10,
          languages: ['en', 'es'],
          originalLanguage: 'en'),
      const NewCommunityTour(
          communityId: 2,
          tourId: 20,
          languages: ['ru'],
          originalLanguage: 'ru'),
    ];

    test('plans the new tours in auto-download communities, preferred language',
        () {
      final plan = SyncPlanner.plan(
        newTours: tours,
        onPhoneTourIds: const {},
        deletedTourIds: const {},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        autoDownloadCommunityIds: const {1, 2},
        preferredLanguage: 'es',
      );
      expect(plan.length, 2);
      // t10 has es → preferred; t20 lacks es → original ru.
      expect(plan[0], const PlannedDownload(communityId: 1, tourId: 10, language: 'es'));
      expect(plan[1], const PlannedDownload(communityId: 2, tourId: 20, language: 'ru'));
    });

    test('skips a community whose auto-download switch is OFF', () {
      final plan = SyncPlanner.plan(
        newTours: tours,
        onPhoneTourIds: const {},
        deletedTourIds: const {},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        autoDownloadCommunityIds: const {1}, // only c1 ON
        preferredLanguage: 'en',
      );
      expect(plan.map((d) => d.tourId), [10]);
    });

    test('skips a tour already on the phone', () {
      final plan = SyncPlanner.plan(
        newTours: tours,
        onPhoneTourIds: const {'10'},
        deletedTourIds: const {},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        autoDownloadCommunityIds: const {1, 2},
        preferredLanguage: 'en',
      );
      expect(plan.map((d) => d.tourId), [20]);
    });

    test('never re-downloads a tour the user deleted', () {
      final plan = SyncPlanner.plan(
        newTours: tours,
        onPhoneTourIds: const {},
        deletedTourIds: const {'20'},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        autoDownloadCommunityIds: const {1, 2},
        preferredLanguage: 'en',
      );
      expect(plan.map((d) => d.tourId), [10]);
    });

    test('downloads NOTHING on cellular when not allowed', () {
      final plan = SyncPlanner.plan(
        newTours: tours,
        onPhoneTourIds: const {},
        deletedTourIds: const {},
        connection: SyncConnection.metered,
        cellularAllowed: false,
        autoDownloadCommunityIds: const {1, 2},
        preferredLanguage: 'en',
      );
      expect(plan, isEmpty);
    });

    test('downloads on cellular when the member allowed it', () {
      final plan = SyncPlanner.plan(
        newTours: tours,
        onPhoneTourIds: const {},
        deletedTourIds: const {},
        connection: SyncConnection.metered,
        cellularAllowed: true,
        autoDownloadCommunityIds: const {1, 2},
        preferredLanguage: 'en',
      );
      expect(plan.length, 2);
    });

    test('downloads NOTHING when offline', () {
      final plan = SyncPlanner.plan(
        newTours: tours,
        onPhoneTourIds: const {},
        deletedTourIds: const {},
        connection: SyncConnection.none,
        cellularAllowed: true,
        autoDownloadCommunityIds: const {1, 2},
        preferredLanguage: 'en',
      );
      expect(plan, isEmpty);
    });

    test('preserves input order (newest first from the server)', () {
      final plan = SyncPlanner.plan(
        newTours: tours,
        onPhoneTourIds: const {},
        deletedTourIds: const {},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        autoDownloadCommunityIds: const {1, 2},
        preferredLanguage: 'en',
      );
      expect(plan.map((d) => d.tourId).toList(), [10, 20]);
    });
  });

  group('shouldAdvanceSince', () {
    test('advances when all downloads succeeded and there is a server_time', () {
      expect(shouldAdvanceSince(haveServerTime: true, failedCount: 0), isTrue);
    });

    test('does NOT advance when any download failed', () {
      expect(shouldAdvanceSince(haveServerTime: true, failedCount: 1), isFalse);
    });

    test('does NOT advance without a server_time (transport failure)', () {
      expect(shouldAdvanceSince(haveServerTime: false, failedCount: 0), isFalse);
    });
  });

  group('NewToursResult.fromJson', () {
    test('parses tours + server_time and derives original language', () {
      final r = NewToursResult.fromJson({
        'server_time': '2026-10-18T12:00:00',
        'tours': [
          {
            'community_id': 1,
            'community_name': 'Boston Walkers',
            'tour_id': 10,
            'short_title': 'Beacon Hill — Walk',
            'stop_count': 4,
            'created_at': '2026-10-18T09:00:00',
            'languages': ['en', 'es'],
          },
        ],
      });
      expect(r.serverTime, '2026-10-18T12:00:00');
      expect(r.tours.length, 1);
      final t = r.tours.first;
      expect(t.communityId, 1);
      expect(t.tourId, 10);
      expect(t.languages, ['en', 'es']);
      expect(t.originalLanguage, 'en'); // languages.first
      expect(t.shortTitle, 'Beacon Hill — Walk');
      expect(t.stopCount, 4);
    });

    test('empty languages defaults the original language to en', () {
      final r = NewToursResult.fromJson({
        'tours': [
          {'community_id': 1, 'tour_id': 5, 'languages': []},
        ],
      });
      expect(r.tours.first.originalLanguage, 'en');
    });
  });

  test('[LEAD] recordDeletedTours stores tour_id and server_tour_id, deduplicated', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    await recordDeletedTours(prefs, [
      {'tour_id': '557', 'server_tour_id': '557'},
      {'tour_id': 'abc', 'server_tour_id': '901'},
    ]);
    final set = prefs.getStringList(kDeletedTourIdsPrefKey)!.toSet();
    expect(set, {'557', 'abc', '901'});
  });
}
