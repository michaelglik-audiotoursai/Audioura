// [LOCAL-759 B] The community page must NOT list the raw imported episodes.
//
// Michael (2026-10-24, community 10): after Import the feed's 42 episodes
// appeared on his community page. Episodes are BUILDER MATERIAL, not tours — the
// page shows TOURS only. These tests pump a community that carries episodes and
// assert NONE of the episode rows render (no "Episodes (N)" header, no episode
// titles, no "From feed" subtitle), while the TOURS section still shows.
//
// Red on d816a251 (the page rendered an episode ListTile per c.episodes entry).
// The episodes stay in the model (the owner-only builder reads them for its
// checklist) — they are just not drawn on the page.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/community_page_screen.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({
      'server_mode': 'local',
      'server_ip': '127.0.0.1',
      'app_mode': 'Tours',
      'user_id': 'local759_test',
    });
  });

  MockClient benignClient() => MockClient((request) async =>
      http.Response('{"ok":true}', 200,
          headers: {'content-type': 'application/json'}));

  List<CommunityEpisode> episodes(int n) => [
        for (var i = 1; i <= n; i++)
          CommunityEpisode(
            position: i,
            title: 'Podcast Episode $i',
            audioUrl: 'https://owner.example/ep$i.mp3',
            source: 'feed',
          ),
      ];

  Community community({
    required bool isOwner,
    required bool active,
    List<CommunityEpisode> eps = const [],
    List<CommunityInviteTourOption> tours = const [],
  }) =>
      Community(
        id: 10,
        name: 'Salem Witches',
        description: 'A friendly Salem community.',
        organiser: const Organiser(name: 'Michael'),
        hasWaiver: false,
        isPaid: false,
        visibility: 'listed',
        disabled: false,
        passes: const [],
        episodes: eps,
        episodeCount: eps.length,
        tours: tours,
        isOwner: isOwner,
        myStatus: MyStatus(isMember: !isOwner, active: active),
      );

  Future<void> pumpPage(WidgetTester tester, Community c) async {
    await tester.binding.setSurfaceSize(const Size(1200, 3000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
      home: CommunityPageScreen(initialCommunity: c),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
  }

  testWidgets('active member: NO episode rows, NO "Episodes" header',
      (tester) async {
    await http.runWithClient(() async {
      await pumpPage(
        tester,
        community(
          isOwner: false,
          active: true,
          eps: episodes(42),
          tours: const [
            CommunityInviteTourOption(
                id: 750, name: 'The Salem Witch Trial', stopCount: 3),
          ],
        ),
      );

      // No episode header and no episode rows.
      expect(find.textContaining('Episodes ('), findsNothing);
      expect(find.text('Podcast Episode 1'), findsNothing);
      expect(find.text('Podcast Episode 42'), findsNothing);
      expect(find.text('From feed'), findsNothing);
      expect(find.text('Join to listen to the episodes.'), findsNothing);

      // The TOURS section still shows the community tour.
      expect(find.textContaining('Tours ('), findsOneWidget);
      expect(find.text('The Salem Witch Trial'), findsOneWidget);
    }, benignClient);
  });

  testWidgets('OWNER view also renders no episode rows on the page',
      (tester) async {
    await http.runWithClient(() async {
      await pumpPage(
        tester,
        community(isOwner: true, active: true, eps: episodes(5)),
      );
      expect(find.textContaining('Episodes ('), findsNothing);
      expect(find.text('Podcast Episode 1'), findsNothing);
      expect(find.text('From feed'), findsNothing);
    }, benignClient);
  });
}
