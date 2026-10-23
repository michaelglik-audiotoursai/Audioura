// [LOCAL-742] Widget tests for the organiser's community-page "Add a tour"
// entry point and the Generate-tab preselect it opens.
//
// Michael (his new "Salem" community): "When I come to my community I see no
// ability to create a tour." The only path was Generate → the "For:" selector.
// LOCAL-742 puts a prominent "Add a tour" button on the organiser's OWN
// community page (top, above the tour list, and as the empty-state action) that
// opens TourGeneratorScreen with that community PRESELECTED.
//
// These run OFFLINE via test seams — CommunityPageScreen(initialCommunity:) and
// TourGeneratorScreen(initialOwnedCommunities:/initialCommunityId:) — so no
// user-api is touched. http is intercepted with a benign MockClient so the
// generator's background/entitlement loads never reach a real server.
//
// Covered:
//   • an OWNER sees "Add a tour" (top button + empty-state button);
//   • a MEMBER does NOT (the RED test — a member shown the button fails);
//   • a NON-MEMBER does NOT;
//   • TourGeneratorScreen(initialCommunityId: X) preselects "For: my community
//     X" with 'members' visibility; without it, "Just me".

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/community_page_screen.dart';
import 'package:audio_tour_app_dev/screens/tour_generator_screen.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/services/community_tour_models.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({
      'server_mode': 'local',
      'server_ip': '127.0.0.1',
      'app_mode': 'Tours',
      'user_id': 'local742_test',
    });
  });

  /// A benign client so any stray HTTP the screens attempt resolves quietly.
  MockClient benignClient() => MockClient((request) async =>
      http.Response('{"ok":true}', 200,
          headers: {'content-type': 'application/json'}));

  /// Build a community page payload. [isOwner]/[isMember]/[active] set the
  /// viewer's relationship to the community. No tours → the empty-state path.
  Community community({
    required bool isOwner,
    required bool isMember,
    bool active = false,
    List<CommunityInviteTourOption> tours = const [],
  }) =>
      Community(
        id: 55,
        name: 'Salem',
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

  Future<void> pumpPage(WidgetTester tester, Community c) async {
    await tester.binding.setSurfaceSize(const Size(1200, 2600));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
      home: CommunityPageScreen(initialCommunity: c),
    ));
    // _load() is async (reads prefs); let it settle.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
  }

  group('community page "Add a tour" visibility', () {
    testWidgets('OWNER sees the top button AND the empty-state button',
        (tester) async {
      await http.runWithClient(() async {
        await pumpPage(tester, community(isOwner: true, isMember: false));

        expect(find.byKey(const Key('add_a_tour_button')), findsOneWidget);
        // No tours → the owner empty-state call to action is shown too.
        expect(find.byKey(const Key('add_first_tour_button')), findsOneWidget);
        expect(find.text('No tours yet. Add the first one.'), findsOneWidget);
        expect(find.text('Add a tour'), findsWidgets);
      }, benignClient);
    });

    // RED TEST: a MEMBER must NOT see the "Add a tour" button. If the button
    // were shown to members (the bug this guards against), this fails.
    testWidgets('MEMBER does NOT see the "Add a tour" button (red test)',
        (tester) async {
      await http.runWithClient(() async {
        await pumpPage(
            tester, community(isOwner: false, isMember: true, active: true));

        expect(find.byKey(const Key('add_a_tour_button')), findsNothing);
        expect(find.byKey(const Key('add_first_tour_button')), findsNothing);
        expect(find.text('Add a tour'), findsNothing);
      }, benignClient);
    });

    testWidgets('NON-MEMBER does NOT see the "Add a tour" button',
        (tester) async {
      await http.runWithClient(() async {
        await pumpPage(tester, community(isOwner: false, isMember: false));

        expect(find.byKey(const Key('add_a_tour_button')), findsNothing);
        expect(find.byKey(const Key('add_first_tour_button')), findsNothing);
        expect(find.text('Add a tour'), findsNothing);
      }, benignClient);
    });
  });

  group('TourGeneratorScreen initialCommunityId preselect', () {
    const owned = [
      OwnedCommunity(id: 55, name: 'Salem'),
      OwnedCommunity(id: 77, name: 'The Owls'),
    ];

    Future<void> pumpGen(WidgetTester tester, {int? initialCommunityId}) async {
      await tester.binding.setSurfaceSize(const Size(1200, 2600));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(MaterialApp(
        home: TourGeneratorScreen(
          initialOwnedCommunities: owned,
          initialCommunityId: initialCommunityId,
        ),
      ));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
    }

    testWidgets('with initialCommunityId: "For: my community X" is selected',
        (tester) async {
      await http.runWithClient(() async {
        await pumpGen(tester, initialCommunityId: 55);

        // The selector shows the chosen community as the Dropdown's value.
        expect(find.text('For: my community Salem'), findsOneWidget);
        // Its members-default visibility choice is revealed and selected.
        final members = tester.widget<RadioListTile<String>>(
            find.widgetWithText(RadioListTile<String>, 'Members'));
        expect(members.groupValue, 'members');
        // "Just me" is NOT the current value.
        expect(find.text('Just me / public as usual'), findsNothing);
      }, benignClient);
    });

    testWidgets('without initialCommunityId: defaults to "Just me"',
        (tester) async {
      await http.runWithClient(() async {
        await pumpGen(tester);

        // Default selection: the "Just me" option is the Dropdown's value, and
        // the per-community visibility radios are NOT shown.
        expect(find.text('Just me / public as usual'), findsOneWidget);
        expect(find.text('For: my community Salem'), findsNothing);
        expect(find.widgetWithText(RadioListTile<String>, 'Members'),
            findsNothing);
      }, benignClient);
    });

    testWidgets('an unknown initialCommunityId falls back to "Just me"',
        (tester) async {
      await http.runWithClient(() async {
        await pumpGen(tester, initialCommunityId: 9999);

        expect(find.text('Just me / public as usual'), findsOneWidget);
        expect(find.textContaining('For: my community'), findsNothing);
      }, benignClient);
    });
  });
}
