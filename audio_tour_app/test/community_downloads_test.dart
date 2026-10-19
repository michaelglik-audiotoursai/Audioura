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

  // ─── [LOCAL-715 / D675 addendum 1] Language PER COMMUNITY ──────────────────

  group('resolveCommunityLanguage precedence (4 cases)', () {
    test('1. the per-community choice wins over everything', () {
      expect(
        resolveCommunityLanguage(
          communityChoice: 'ru',
          aboutDefault: 'de',
          localeLanguageCode: 'fr',
        ),
        'ru',
      );
    });

    test('2. no community choice → About default', () {
      expect(
        resolveCommunityLanguage(
          communityChoice: null,
          aboutDefault: 'de',
          localeLanguageCode: 'fr',
        ),
        'de',
      );
    });

    test('3. no choice and no About default → phone locale when offered', () {
      expect(
        resolveCommunityLanguage(
          communityChoice: null,
          aboutDefault: null,
          localeLanguageCode: 'es',
        ),
        'es',
      );
    });

    test('4. nothing set and locale not offered → English', () {
      expect(
        resolveCommunityLanguage(
          communityChoice: '',
          aboutDefault: '',
          localeLanguageCode: 'pt',
        ),
        'en',
      );
      // Also: no locale at all → English.
      expect(resolveCommunityLanguage(), 'en');
    });
  });

  group('languageForCommunity (SharedPreferences)', () {
    test('reads the per-community key when set', () async {
      SharedPreferences.setMockInitialValues({
        kListeningLanguagePrefKey: 'de',
        communityLanguagePrefKey(42): 'ru',
      });
      final prefs = await SharedPreferences.getInstance();
      expect(
        languageForCommunity(prefs, 42, localeLanguageCode: 'fr'),
        'ru',
      );
    });

    test('falls back to About default when the per-community key is absent',
        () async {
      SharedPreferences.setMockInitialValues({
        kListeningLanguagePrefKey: 'de',
      });
      final prefs = await SharedPreferences.getInstance();
      expect(
        languageForCommunity(prefs, 42, localeLanguageCode: 'fr'),
        'de',
      );
    });

    test('falls back to the phone locale, else English, when nothing is set',
        () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      expect(languageForCommunity(prefs, 42, localeLanguageCode: 'es'), 'es');
      expect(languageForCommunity(prefs, 42, localeLanguageCode: 'pt'), 'en');
    });

    test('two communities resolve to two different languages', () async {
      SharedPreferences.setMockInitialValues({
        communityLanguagePrefKey(1): 'en', // Boston Walkers in English
        communityLanguagePrefKey(2): 'ru', // Book Club in Russian
      });
      final prefs = await SharedPreferences.getInstance();
      expect(languageForCommunity(prefs, 1), 'en');
      expect(languageForCommunity(prefs, 2), 'ru');
    });
  });

  group('SyncPlanner.plan — per-community language (D675 addendum 1)', () {
    // Each community's new tour carries BOTH languages so the chosen one is
    // always available — this isolates the per-community language selection
    // from the pickDownloadLanguage original-fallback.
    final tours = [
      const NewCommunityTour(
          communityId: 1,
          tourId: 10,
          languages: ['en', 'ru'],
          originalLanguage: 'en'),
      const NewCommunityTour(
          communityId: 2,
          tourId: 20,
          languages: ['en', 'ru'],
          originalLanguage: 'en'),
    ];

    test('two communities with different languages → two download languages',
        () {
      final plan = SyncPlanner.plan(
        newTours: tours,
        onPhoneTourIds: const {},
        deletedTourIds: const {},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        autoDownloadCommunityIds: const {1, 2},
        preferredLanguage: 'en', // the fallback
        languageByCommunity: const {1: 'en', 2: 'ru'},
      );
      expect(plan.length, 2);
      expect(plan[0],
          const PlannedDownload(communityId: 1, tourId: 10, language: 'en'));
      expect(plan[1],
          const PlannedDownload(communityId: 2, tourId: 20, language: 'ru'));
    });

    test('a community absent from the map uses the fallback preferredLanguage',
        () {
      final plan = SyncPlanner.plan(
        newTours: tours,
        onPhoneTourIds: const {},
        deletedTourIds: const {},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        autoDownloadCommunityIds: const {1, 2},
        preferredLanguage: 'ru', // fallback for c2 (not in the map)
        languageByCommunity: const {1: 'en'},
      );
      expect(plan[0].language, 'en'); // c1 from the map
      expect(plan[1].language, 'ru'); // c2 from the fallback
    });

    test(
        'the per-community language still respects pickDownloadLanguage: '
        'unavailable → the tour original', () {
      final plan = SyncPlanner.plan(
        // c2's tour only has en; a Russian choice is not available → original.
        newTours: [
          const NewCommunityTour(
              communityId: 1,
              tourId: 10,
              languages: ['en', 'ru'],
              originalLanguage: 'en'),
          const NewCommunityTour(
              communityId: 2,
              tourId: 20,
              languages: ['en'],
              originalLanguage: 'en'),
        ],
        onPhoneTourIds: const {},
        deletedTourIds: const {},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        autoDownloadCommunityIds: const {1, 2},
        preferredLanguage: 'en',
        languageByCommunity: const {1: 'ru', 2: 'ru'},
      );
      expect(plan[0].language, 'ru'); // c1 has ru
      expect(plan[1].language, 'en'); // c2 lacks ru → original en
    });
  });

  group('communityLanguagePrefKey + listeningLanguageName', () {
    test('the per-community key is listening_language_<id>', () {
      expect(communityLanguagePrefKey(42), 'listening_language_42');
    });

    test('display names mirror the language selector', () {
      expect(listeningLanguageName('en'), 'English');
      expect(listeningLanguageName('ru'), 'Русский');
      expect(listeningLanguageName('zz'), 'zz'); // unknown → the code
    });
  });
}
