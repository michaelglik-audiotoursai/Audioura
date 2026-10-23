// [LOCAL-748] Community-page behaviour on the phone (Michael's test, 2026-10-23):
//   1. "On this phone ✓" is a LINK — tapping it opens the player for that tour
//      (no back → Listen → find → open). Proven by the open_tour_<id> row
//      firing PendingListenOpen with the tour id.
//   2. A community-page Download stamps community_id (and version) onto the
//      saved record — without it CommunityToursSync's refresh skipped the tour
//      and the organiser's edit never reached the member. Proven by driving the
//      SINGLE download path (TourDownloadService.downloadAndSave) with the
//      community-page sourceItem and reading the saved record back.
//   3. After a community-page download the tour is on the Listen page WITHOUT a
//      second action — PendingListenOpen is offered on success.
//
// These FAIL on 7332bfb5: the row had no onTap/key (1), the community-page
// download passed no sourceItem so the record had no community_id (2), and the
// success path did not offer PendingListenOpen (3).

import 'dart:convert';

import 'package:archive/archive.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/community_page_screen.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/services/community_downloads.dart';
import 'package:audio_tour_app_dev/services/deep_link_service.dart';
import 'package:audio_tour_app_dev/services/tour_download_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Community communityWithTour({
    required bool isOwner,
    required bool isMember,
    bool active = true,
    required List<CommunityInviteTourOption> tours,
  }) =>
      Community(
        id: 10,
        name: 'Salem TV show funs',
        description: 'A friendly Salem community.',
        organiser: const Organiser(name: 'Michael'),
        hasWaiver: false,
        isPaid: false,
        visibility: 'listed',
        disabled: false,
        passes: const [],
        episodes: const [],
        episodeCount: 0,
        tours: tours,
        isOwner: isOwner,
        myStatus: MyStatus(isMember: isMember, active: active),
      );

  MockClient benignClient() => MockClient((request) async =>
      http.Response('{"ok":true}', 200,
          headers: {'content-type': 'application/json'}));

  group('[LOCAL-748] "On this phone" is a link that opens the player', () {
    setUp(() {
      PendingListenOpen.instance.consume();
      SharedPreferences.setMockInitialValues({
        'app_mode': 'Tours',
        'user_id': 'local748_test',
        // Tour 716 is already on the phone → status onThisPhone.
        'saved_tours': [
          jsonEncode({
            'title': 'Salem Witch Walk',
            'path': '/tmp/salem_716',
            'tour_id': '716',
            'server_tour_id': '716',
          }),
        ],
      });
    });

    testWidgets('tapping the open_tour row offers the tour to Listen',
        (tester) async {
      await tester.binding.setSurfaceSize(const Size(1200, 2600));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final c = communityWithTour(
        isOwner: false,
        isMember: true,
        tours: const [
          CommunityInviteTourOption(id: 716, name: 'Salem Witch Walk'),
        ],
      );

      await http.runWithClient(() async {
        await tester.pumpWidget(MaterialApp(
          home: CommunityPageScreen(initialCommunity: c),
        ));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 50));

        // The row is rendered as "On this phone" and carries the open key.
        final openRow = find.byKey(const Key('open_tour_716'));
        expect(openRow, findsOneWidget);
        expect(find.text('On this phone'), findsOneWidget);

        PendingListenOpen.instance.consume();
        await tester.tap(openRow);
        await tester.pump();

        final req = PendingListenOpen.instance.request.value;
        expect(req, isNotNull);
        expect(req!.tourId, '716');
      }, benignClient);
    });
  });

  group('[LOCAL-748] community-page download stamps community_id + Listen', () {
    setUp(() {
      PendingListenOpen.instance.consume();
      // path_provider → write the extracted tour under /tmp.
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (call) async => '/tmp/local748_dl',
      );
    });
    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        null,
      );
    });

    // A minimal valid tour ZIP: one tour.json with two stops.
    List<int> tourZip() {
      final archive = Archive();
      final body = utf8.encode(jsonEncode({
        'stops': [
          {'id': 1},
          {'id': 2},
        ],
      }));
      archive.addFile(ArchiveFile('tour.json', body.length, body));
      return ZipEncoder().encode(archive)!;
    }

    // A MockClient that answers the two endpoints the single download path hits:
    //   GET /download-tour/716   → 200 ZIP bytes
    //   GET /tour/716/resolve    → 200 resolution JSON
    // Anything else (unlock-state etc.) → benign 200 so the save never throws.
    MockClient downloadClient() => MockClient((request) async {
          final path = request.url.path;
          if (path.contains('/download-tour/')) {
            return http.Response.bytes(tourZip(), 200);
          }
          if (path.contains('/resolve')) {
            return http.Response(
              jsonEncode({
                'status': 'success',
                'edit_tour_id': '716',
                'tour_name': 'Salem Witch Walk',
                'editable': false,
                'stops_count': 2,
              }),
              200,
              headers: {'content-type': 'application/json'},
            );
          }
          return http.Response('{"ok":true}', 200,
              headers: {'content-type': 'application/json'});
        });

    test('downloadAndSave with the community-page sourceItem stamps the record',
        () async {
      SharedPreferences.setMockInitialValues({
        'server_mode': 'local',
        'server_ip': '127.0.0.1',
        'user_id': 'local748_test',
      });

      await http.runWithClient(() async {
        final result = await TourDownloadService.downloadAndSave(
          716,
          sourceItem: communityTourSourceItem(
            communityId: 10,
            version: 2,
            updatedAt: '2026-10-23',
          ),
        );
        expect(result.status, TourDownloadStatus.ok);

        final prefs = await SharedPreferences.getInstance();
        final saved = prefs.getStringList('saved_tours') ?? const [];
        expect(saved, isNotEmpty);
        final rec = jsonDecode(saved.single) as Map<String, dynamic>;
        // The record now carries community_id + version — what the held-tour
        // refresh needs. On 7332bfb5 the community-page download passed no
        // sourceItem, so these were absent.
        expect(rec['community_id'], 10);
        expect(rec['version'], 2);
        expect(rec['server_tour_id'], '716');
      }, downloadClient);
    });
  });
}
