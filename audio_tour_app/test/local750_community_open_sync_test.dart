import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/community_page_screen.dart';
import 'package:audio_tour_app_dev/services/communities_service.dart';

/// LOCAL-750 (C2) — opening a community page must kick a sync.
///
/// Michael stayed in the app; tour 735 (created 21:34) was never fetched because
/// the sync ran only on app start / resume. Now opening the Communities hub or a
/// community page triggers a community sync. This pins the community-page open:
/// its initState calls [CommunityPageScreen.onOpenSync] exactly once.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({'user_id': 'local750_test'});
  });

  MockClient benignClient() => MockClient((request) async =>
      http.Response('{"ok":true}', 200,
          headers: {'content-type': 'application/json'}));

  Community community() => const Community(
        id: 55,
        name: 'Salem',
        description: 'A friendly Salem community.',
        organiser: Organiser(name: 'Michael'),
        hasWaiver: false,
        isPaid: false,
        visibility: 'listed',
        disabled: false,
        passes: [],
        episodes: [],
        episodeCount: 0,
        tours: [],
        isOwner: false,
        myStatus: MyStatus(isMember: true, active: true),
      );

  testWidgets('opening a community page triggers exactly one sync',
      (tester) async {
    var syncs = 0;
    final original = CommunityPageScreen.onOpenSync;
    CommunityPageScreen.onOpenSync = () => syncs++;
    addTearDown(() => CommunityPageScreen.onOpenSync = original);

    await http.runWithClient(() async {
      await tester.binding.setSurfaceSize(const Size(1200, 2600));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(MaterialApp(
        home: CommunityPageScreen(initialCommunity: community()),
      ));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
    }, benignClient);

    expect(syncs, 1);
  });
}
