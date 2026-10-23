// [LOCAL-748] Integration test for the sync-on-open SHELL's new-tour
// ANNOUNCEMENT pass (community_tours_sync.dart). When /communities/new-tours
// returns a new tour in a community the member belongs to, the shell emits ONE
// "New tour in <community>: <tour>" message — once per tour, NEVER for a tour in
// a community the user OWNS. The pure policy is proven in
// community_downloads_local748_test.dart; here we prove the GLUE via seams.

import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/community_downloads.dart';
import 'package:audio_tour_app_dev/services/community_tours_sync.dart';
import 'package:audio_tour_app_dev/services/tour_download_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    // Neutral defaults — a run with nothing held, no owned communities.
    CommunityToursSync.fetchActiveCommunityIds = (userId) async => const {};
    CommunityToursSync.fetchOwnedCommunityIds = (userId) async => const {};
    CommunityToursSync.fetchServerVersion = (tourId) async => null;
    CommunityToursSync.reDownload =
        (tourId, {required newVersion, updatedAt}) async =>
            const TourDownloadResult(TourDownloadStatus.failed);
    CommunityToursSync.download =
        (tourId) async => const TourDownloadResult(TourDownloadStatus.ok);
    CommunityToursSync.onRefreshMessage = (_) {};
    CommunityToursSync.onNewTourAnnouncement = (_, __) {};
    _mockConnectivityWifi();
  });

  NewToursResult oneNewTour({
    int tourId = 733,
    int communityId = 10,
    String name = 'Salem TV tour',
  }) =>
      NewToursResult(
        tours: [
          NewCommunityTour(
            communityId: communityId,
            tourId: tourId,
            languages: const ['en'],
            originalLanguage: 'en',
            communityName: 'Salem TV show funs',
            shortTitle: name,
          ),
        ],
        serverTime: '2026-10-23T00:00:00Z',
      );

  test('a new tour the member does NOT own → ONE "New tour in …" message',
      () async {
    SharedPreferences.setMockInitialValues({'user_id': 'u1'});
    CommunityToursSync.fetchNewTours = (userId, {since}) async => oneNewTour();
    // The member belongs to community 10 but does NOT own it.
    CommunityToursSync.fetchOwnedCommunityIds = (userId) async => const {};

    final messages = <String>[];
    CommunityToursSync.onNewTourAnnouncement = (a, msg) => messages.add(msg);

    await CommunityToursSync.instance.run();

    expect(messages, ['New tour in Salem TV show funs: Salem TV tour']);
  });

  test('a new tour in a community the member OWNS → NO message', () async {
    SharedPreferences.setMockInitialValues({'user_id': 'u1'});
    CommunityToursSync.fetchNewTours = (userId, {since}) async => oneNewTour();
    CommunityToursSync.fetchOwnedCommunityIds = (userId) async => const {10};

    final messages = <String>[];
    CommunityToursSync.onNewTourAnnouncement = (a, msg) => messages.add(msg);

    await CommunityToursSync.instance.run();

    expect(messages, isEmpty);
  });

  test('a tour is announced at most once across two sync runs', () async {
    SharedPreferences.setMockInitialValues({'user_id': 'u1'});
    CommunityToursSync.fetchNewTours = (userId, {since}) async => oneNewTour();
    CommunityToursSync.fetchOwnedCommunityIds = (userId) async => const {};

    final messages = <String>[];
    CommunityToursSync.onNewTourAnnouncement = (a, msg) => messages.add(msg);

    await CommunityToursSync.instance.run();
    // Second run: the same tour comes back, but it was already announced.
    await CommunityToursSync.instance.run();

    expect(messages.length, 1);
  });

  // [LOCAL-748] The repair path end-to-end: an OLD record (downloaded before
  // this fix) has NO community_id, so the refresh skips it. After the community
  // page stamps it (stampCommunityIdOnSavedRecords), the SAME sync run now sees
  // it and RefreshPlanner (inside the shell) re-downloads it when the server
  // version is higher.
  test('a stamped old record is re-downloaded when the server version rose',
      () async {
    // The bare record as saved on 7332bfb5: no community_id.
    final bare = jsonEncode({
      'title': 'Salem Witch Walk',
      'path': '/tmp/salem_716',
      'tour_id': '716',
      'server_tour_id': '716',
    });

    // Before stamping: the refresh does NOT see it (no community_id).
    SharedPreferences.setMockInitialValues({
      'user_id': 'u1',
      'saved_tours': [bare],
    });
    CommunityToursSync.fetchActiveCommunityIds = (userId) async => const {10};
    CommunityToursSync.fetchServerVersion =
        (tourId) async => (version: 2, updatedAt: '2026-10-23');
    final reBefore = <int>[];
    CommunityToursSync.reDownload =
        (tourId, {required newVersion, updatedAt}) async {
      reBefore.add(tourId);
      return const TourDownloadResult(TourDownloadStatus.ok);
    };
    await CommunityToursSync.instance.run();
    expect(reBefore, isEmpty, reason: 'no community_id → skipped');

    // Stamp the record (what the community page does on load) and persist it.
    final prefs = await SharedPreferences.getInstance();
    final stamped = stampCommunityIdOnSavedRecords(
      savedToursJson: prefs.getStringList('saved_tours') ?? const [],
      communityId: 10,
      communityTourIds: {'716'},
    );
    expect(stamped, isNotNull);
    await prefs.setStringList('saved_tours', stamped!);

    // After stamping: the SAME refresh now re-downloads it.
    final reAfter = <int>[];
    CommunityToursSync.reDownload =
        (tourId, {required newVersion, updatedAt}) async {
      reAfter.add(tourId);
      return const TourDownloadResult(TourDownloadStatus.ok);
    };
    final result = await CommunityToursSync.instance.run();
    expect(reAfter, [716]);
    expect(result.refreshed, 1);
  });
}

/// Mock connectivity_plus so the sync sees Wi-Fi (unmetered) in the test host.
void _mockConnectivityWifi() {
  const channel = 'dev.fluttercommunity.plus/connectivity';
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(
    const MethodChannel(channel),
    (call) async {
      if (call.method == 'check') return <String>['wifi'];
      return null;
    },
  );
  const eventChannel = 'dev.fluttercommunity.plus/connectivity_status';
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(
    const MethodChannel(eventChannel),
    (call) async => null,
  );
}
