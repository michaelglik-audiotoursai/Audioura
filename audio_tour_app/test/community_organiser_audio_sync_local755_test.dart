// [LOCAL-755 / D709 Rule 3] The GLUE test for the organiser-audio UPDATE pass of
// CommunityToursSync. The pure policy (OrganiserAudioUpdatePlanner) is proven in
// community_organiser_audio_updates_local755_test.dart; here we prove the shell:
// an organiser-audio held tour whose server version rose is NEVER auto-
// re-downloaded (members are never pushed it), is OFFERED via exactly ONE in-app
// message with a Re-download action, the pending version is stamped on the saved
// record (for the Listen-row affordance), and the same tour is not nagged twice.
//
// A GENERATED community tour at a higher version still auto-refreshes (Rule 4).

import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/community_tours_sync.dart';
import 'package:audio_tour_app_dev/services/tour_download_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    CommunityToursSync.fetchNewTours = (userId, {since}) async => null;
    CommunityToursSync.fetchActiveCommunityIds = (userId) async => const {1};
    CommunityToursSync.onRefreshMessage = (_, {int? tourId}) {};
    CommunityToursSync.onOrganiserAudioUpdate =
        (_, {required tourId, required serverVersion, updatedAt}) {};
  });

  String recordJson({
    required String serverTourId,
    int communityId = 1,
    int version = 1,
    String? sourceKind,
    String title = 'Salem Audio Walk',
  }) {
    final m = <String, dynamic>{
      'title': title,
      'path': '/tours/${title}_$serverTourId',
      'tour_id': serverTourId,
      'server_tour_id': serverTourId,
      'version': version,
      'language': 'en',
      'community_id': communityId,
    };
    if (sourceKind != null) m['source_kind'] = sourceKind;
    return json.encode(m);
  }

  test('organiser-audio held tour v1→v2: OFFERED once, never auto-downloaded',
      () async {
    SharedPreferences.setMockInitialValues({
      'user_id': 'u1',
      'saved_tours': [
        recordJson(serverTourId: '10', sourceKind: 'organiser_audio'),
      ],
    });
    final reDownloaded = <int>[];
    final offers = <String>[];
    final offerIds = <int>[];
    CommunityToursSync.fetchServerVersion = (tourId) async =>
        (version: 2, updatedAt: '2026-10-24', isOrganiserAudio: true);
    CommunityToursSync.reDownload = (tourId, {required newVersion, updatedAt}) async {
      reDownloaded.add(tourId);
      return const TourDownloadResult(TourDownloadStatus.ok);
    };
    CommunityToursSync.onOrganiserAudioUpdate = (m,
        {required tourId, required serverVersion, updatedAt}) {
      offers.add(m);
      offerIds.add(tourId);
    };
    _mockConnectivityWifi();

    final result = await CommunityToursSync.instance.run();

    // Never auto-re-downloaded (Rule 3: members are never pushed).
    expect(reDownloaded, isEmpty);
    expect(result.refreshed, 0);
    // Offered exactly once, with the ask-to-re-download wording.
    expect(offers, ['Salem Audio Walk was updated by the organiser. Re-download?']);
    expect(offerIds, [10]);

    // The pending server version is stamped on the saved record for the row.
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getStringList('saved_tours')!;
    final m = json.decode(saved.single) as Map<String, dynamic>;
    expect(m['pending_organiser_version'], 2);
  });

  test('a GENERATED community tour v1→v2 still auto-refreshes (Rule 4)',
      () async {
    SharedPreferences.setMockInitialValues({
      'user_id': 'u1',
      'saved_tours': [recordJson(serverTourId: '20')], // no source_kind
    });
    final reDownloaded = <int>[];
    final offers = <String>[];
    CommunityToursSync.fetchServerVersion = (tourId) async =>
        (version: 2, updatedAt: null, isOrganiserAudio: false);
    CommunityToursSync.reDownload = (tourId, {required newVersion, updatedAt}) async {
      reDownloaded.add(tourId);
      return const TourDownloadResult(TourDownloadStatus.ok);
    };
    CommunityToursSync.onOrganiserAudioUpdate = (m,
        {required tourId, required serverVersion, updatedAt}) => offers.add(m);
    _mockConnectivityWifi();

    final result = await CommunityToursSync.instance.run();

    expect(reDownloaded, [20], reason: 'a generated tour auto-refreshes');
    expect(result.refreshed, 1);
    expect(offers, isEmpty, reason: 'no organiser-audio offer for a generated tour');
  });

  test('the same organiser-audio update is offered at most once across runs',
      () async {
    SharedPreferences.setMockInitialValues({
      'user_id': 'u1',
      'saved_tours': [
        recordJson(serverTourId: '10', sourceKind: 'organiser_audio'),
      ],
    });
    var offerCount = 0;
    CommunityToursSync.fetchServerVersion = (tourId) async =>
        (version: 2, updatedAt: null, isOrganiserAudio: true);
    CommunityToursSync.reDownload =
        (tourId, {required newVersion, updatedAt}) async =>
            const TourDownloadResult(TourDownloadStatus.ok);
    CommunityToursSync.onOrganiserAudioUpdate = (m,
        {required tourId, required serverVersion, updatedAt}) => offerCount++;
    _mockConnectivityWifi();

    await CommunityToursSync.instance.run();
    await CommunityToursSync.instance.run();

    expect(offerCount, 1, reason: 'one message per (tour, server version)');
  });
}

/// Mock connectivity_plus so the sync sees Wi-Fi in the test host.
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
