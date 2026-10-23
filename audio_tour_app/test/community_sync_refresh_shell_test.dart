// [LOCAL-746] Integration test for the sync-on-open I/O SHELL's held-tour
// refresh pass (community_tours_sync.dart). The pure policy is proven in
// community_refresh_planner_test.dart; here we prove the GLUE around it via the
// test seams: it gathers the held community tours from saved_tours, asks the
// server for each one's version, re-downloads only the ones whose version rose
// for an active community, keeps the old copy on a failed re-download, and emits
// EXACTLY ONE "<tour> was updated by the organiser." message per refreshed tour.

import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/community_tours_sync.dart';
import 'package:audio_tour_app_dev/services/tour_download_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Reset the seams to their test doubles before each test.
  setUp(() {
    CommunityToursSync.fetchNewTours = (userId, {since}) async => null;
    CommunityToursSync.fetchActiveCommunityIds = (userId) async => const {1};
    CommunityToursSync.onRefreshMessage = (_, {int? tourId}) {};
  });

  String recordJson({
    required String serverTourId,
    int? communityId,
    int version = 1,
    String title = 'Salem Witch Walk',
  }) {
    final m = <String, dynamic>{
      'title': title,
      'path': '/tours/${title}_$serverTourId',
      'tour_id': serverTourId,
      'server_tour_id': serverTourId,
      'version': version,
      'language': 'en',
    };
    if (communityId != null) m['community_id'] = communityId;
    return json.encode(m);
  }

  test('held community tour at v1, server v2 → re-downloads once and messages',
      () async {
    SharedPreferences.setMockInitialValues({
      'user_id': 'u1',
      'saved_tours': [recordJson(serverTourId: '10', communityId: 1)],
    });

    final reDownloaded = <int>[];
    final messages = <String>[];
    CommunityToursSync.fetchServerVersion =
        (tourId) async => (version: 2, updatedAt: '2026-10-23');
    CommunityToursSync.reDownload = (tourId, {required newVersion, updatedAt}) async {
      reDownloaded.add(tourId);
      return const TourDownloadResult(TourDownloadStatus.ok);
    };
    CommunityToursSync.onRefreshMessage = (m, {int? tourId}) => messages.add(m);

    // Force an unmetered connection by stubbing nothing — connectionFromResults
    // reads the real Connectivity plugin, which in a test host returns none.
    // So we exercise the pass directly through the public run() with the plugin
    // channel mocked to Wi-Fi.
    _mockConnectivityWifi();

    final result = await CommunityToursSync.instance.run();

    expect(reDownloaded, [10]);
    expect(result.refreshed, 1);
    expect(messages, ['Salem Witch Walk was updated by the organiser.']);
  });

  test('server version unchanged (v1/v1) → no re-download, no message',
      () async {
    SharedPreferences.setMockInitialValues({
      'user_id': 'u1',
      'saved_tours': [recordJson(serverTourId: '10', communityId: 1)],
    });
    final reDownloaded = <int>[];
    final messages = <String>[];
    CommunityToursSync.fetchServerVersion =
        (tourId) async => (version: 1, updatedAt: null);
    CommunityToursSync.reDownload = (tourId, {required newVersion, updatedAt}) async {
      reDownloaded.add(tourId);
      return const TourDownloadResult(TourDownloadStatus.ok);
    };
    CommunityToursSync.onRefreshMessage = (m, {int? tourId}) => messages.add(m);
    _mockConnectivityWifi();

    final result = await CommunityToursSync.instance.run();

    expect(reDownloaded, isEmpty);
    expect(result.refreshed, 0);
    expect(messages, isEmpty);
  });

  test('ordinary (non-community) tour is never re-downloaded', () async {
    SharedPreferences.setMockInitialValues({
      'user_id': 'u1',
      // No community_id → ordinary tour.
      'saved_tours': [recordJson(serverTourId: '10')],
    });
    final reDownloaded = <int>[];
    CommunityToursSync.fetchServerVersion =
        (tourId) async => (version: 99, updatedAt: null);
    CommunityToursSync.reDownload = (tourId, {required newVersion, updatedAt}) async {
      reDownloaded.add(tourId);
      return const TourDownloadResult(TourDownloadStatus.ok);
    };
    _mockConnectivityWifi();

    final result = await CommunityToursSync.instance.run();

    expect(reDownloaded, isEmpty);
    expect(result.refreshed, 0);
  });

  test('expired membership (community not active) → no re-download', () async {
    SharedPreferences.setMockInitialValues({
      'user_id': 'u1',
      'saved_tours': [recordJson(serverTourId: '10', communityId: 1)],
    });
    final reDownloaded = <int>[];
    CommunityToursSync.fetchActiveCommunityIds = (userId) async => const {};
    CommunityToursSync.fetchServerVersion =
        (tourId) async => (version: 2, updatedAt: null);
    CommunityToursSync.reDownload = (tourId, {required newVersion, updatedAt}) async {
      reDownloaded.add(tourId);
      return const TourDownloadResult(TourDownloadStatus.ok);
    };
    _mockConnectivityWifi();

    final result = await CommunityToursSync.instance.run();

    expect(reDownloaded, isEmpty);
    expect(result.refreshed, 0);
  });

  test('a FAILED re-download keeps the old copy — refreshed=0, no message',
      () async {
    SharedPreferences.setMockInitialValues({
      'user_id': 'u1',
      'saved_tours': [recordJson(serverTourId: '10', communityId: 1)],
    });
    final messages = <String>[];
    CommunityToursSync.fetchServerVersion =
        (tourId) async => (version: 2, updatedAt: null);
    CommunityToursSync.reDownload = (tourId, {required newVersion, updatedAt}) async {
      // The replace-in-place keeps the old copy on failure; here it reports it.
      return const TourDownloadResult(TourDownloadStatus.failed);
    };
    CommunityToursSync.onRefreshMessage = (m, {int? tourId}) => messages.add(m);
    _mockConnectivityWifi();

    final result = await CommunityToursSync.instance.run();

    expect(result.refreshed, 0);
    expect(messages, isEmpty);
  });
}

/// Mock the connectivity_plus platform channel so the sync sees Wi-Fi
/// (unmetered) in the test host (which otherwise reports none → no downloads).
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
