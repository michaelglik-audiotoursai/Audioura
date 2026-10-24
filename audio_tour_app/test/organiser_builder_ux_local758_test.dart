// [LOCAL-758] Red tests for the rebuilt organiser-audio tour builder UX.
//
// Michael (2026-10-24): the stops were not obviously editable — an icon-only
// delete with no undo that looked like a rename, a dead up-arrow, and raw
// lat/lng with no map pin or "Use my location". These tests pin the new
// behaviour the builder MUST have, and all FAIL on 9a86e6e8 (the old screen has
// no checklist, no Undo, no "Use episode title", no location picker, and
// numbers it into stops without asking).
//
// They drive the REAL OrganiserAudioTourScreen with:
//   * a MockClient so Import returns a feed of episodes, and
//   * a FakeBuilderLocationProvider so "Use my location" needs no device and
//     address search needs no network.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/organiser_audio_tour_screen.dart';
import 'package:audio_tour_app_dev/services/builder_location_provider.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';

// --- Fixtures ---------------------------------------------------------------

/// A community with NO seeded episodes (the organiser imports a feed instead).
Community _emptyCommunity() => const Community(
      id: 42,
      name: 'Salem TV show funs',
      organiser: Organiser(name: 'Michael'),
      hasWaiver: false,
      isPaid: false,
      visibility: 'listed',
      disabled: false,
      passes: [],
      episodes: [],
      episodeCount: 0,
      isOwner: true,
      myStatus: MyStatus(isMember: true, active: true),
    );

/// A community pre-seeded with three episodes (so we can test the checklist and
/// the stop operations without an import round-trip).
Community _seededCommunity() => const Community(
      id: 42,
      name: 'Salem TV show funs',
      organiser: Organiser(name: 'Michael'),
      hasWaiver: false,
      isPaid: false,
      visibility: 'listed',
      disabled: false,
      passes: [],
      episodes: [
        CommunityEpisode(
            position: 1,
            title: 'The Accusations Begin',
            audioUrl: 'https://feed.example/ep1.mp3',
            source: 'feed',
            date: '12 Oct 2026',
            duration: '41 min'),
        CommunityEpisode(
            position: 2,
            title: 'The Trial of George Jacobs',
            audioUrl: 'https://feed.example/ep2.mp3',
            source: 'feed',
            date: '19 Oct 2026',
            duration: '48 min'),
        CommunityEpisode(
            position: 3,
            title: 'The Aftermath',
            audioUrl: 'https://feed.example/ep3.mp3',
            source: 'feed',
            date: '26 Oct 2026',
            duration: '39 min'),
      ],
      episodeCount: 3,
      isOwner: true,
      myStatus: MyStatus(isMember: true, active: true),
    );

/// MockClient: GET community → the seeded feed; import-feed → 200.
MockClient _client() => MockClient((req) async {
      final path = req.url.path;
      final json = {'content-type': 'application/json'};
      if (path.contains('/import-feed')) {
        return http.Response('{"ok":true}', 200, headers: json);
      }
      if (path.endsWith('/communities/42')) {
        return http.Response(
            '{"id":42,"name":"Salem TV show funs","is_owner":true,'
            '"episodes":['
            '{"position":1,"title":"The Accusations Begin","audio_url":"https://feed.example/ep1.mp3","source":"feed","date":"12 Oct 2026","duration":"41 min"},'
            '{"position":2,"title":"The Trial of George Jacobs","audio_url":"https://feed.example/ep2.mp3","source":"feed","date":"19 Oct 2026","duration":"48 min"}'
            ']}',
            200,
            headers: json);
      }
      return http.Response('{}', 200, headers: json);
    });

Future<void> _pump(WidgetTester tester) async {
  for (var i = 0; i < 6; i++) {
    await tester.pump(const Duration(milliseconds: 120));
  }
}

/// Ensure a widget is built and on-screen. The builder is a lazy ListView, so a
/// widget scrolled far away may be disposed; scroll it back first.
Future<void> _reveal(WidgetTester tester, Finder f) async {
  if (f.evaluate().isEmpty) {
    final scrollable = find.byType(Scrollable).first;
    // Try scrolling up then down to re-materialise the target.
    try {
      await tester.scrollUntilVisible(f, -120, scrollable: scrollable);
    } catch (_) {
      await tester.scrollUntilVisible(f, 120, scrollable: scrollable);
    }
    await tester.pump();
  }
  await tester.ensureVisible(f.first);
  await tester.pump();
}

/// Scroll a widget into view (the builder is a long ListView) and tap it.
Future<void> _tap(WidgetTester tester, Finder f) async {
  await _reveal(tester, f);
  await tester.tap(f.first);
  await _pump(tester);
}

/// Scroll a field into view and enter text.
Future<void> _enter(WidgetTester tester, Finder f, String text) async {
  await _reveal(tester, f);
  await tester.enterText(f.first, text);
  await tester.pump();
}

Widget _host(Community c, {BuilderLocationProvider? loc}) => MaterialApp(
      home: OrganiserAudioTourScreen(
        community: c,
        locationProvider: loc ?? const FakeBuilderLocationProvider(),
      ),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    debugBuilderTileProviderOverride = TransparentTileProvider();
    SharedPreferences.setMockInitialValues({
      'server_mode': 'cloud',
      'user_id': 'owner-1',
    });
  });

  tearDown(() {
    debugBuilderTileProviderOverride = null;
  });

  testWidgets('seeded episodes appear as a CHECKLIST, nothing is a stop yet',
      (tester) async {
    await tester.pumpWidget(_host(_seededCommunity()));
    await _pump(tester);

    // The three episodes are shown as checkboxes (the checklist), with titles.
    expect(find.text('The Accusations Begin'), findsOneWidget);
    expect(find.text('The Trial of George Jacobs'), findsOneWidget);
    expect(find.byType(CheckboxListTile), findsWidgets);

    // "Select none / all" controls exist.
    expect(find.textContaining('Select all'), findsOneWidget);

    // Nothing has become a stop yet: no stop card / "Stop 1" header.
    expect(find.textContaining('Stop 1'), findsNothing);
  });

  testWidgets('importing a feed adds its episodes to the CHECKLIST, not stops',
      (tester) async {
    await http.runWithClient(() async {
      await tester.pumpWidget(_host(_emptyCommunity()));
      await _pump(tester);

      // Empty to start: no episodes yet.
      expect(find.text('The Accusations Begin'), findsNothing);

      // Type a feed URL and import.
      await _enter(
          tester, find.widgetWithText(TextField, 'RSS feed URL'), 'https://f');
      await _tap(tester, find.widgetWithText(TextButton, 'Import'));

      // The imported episodes appear as a CHECKLIST (checkboxes), not as stops.
      expect(find.text('The Accusations Begin'), findsOneWidget);
      expect(find.byType(CheckboxListTile), findsWidgets);
      expect(find.textContaining('Stop 1'), findsNothing);
    }, _client);
  });

  testWidgets('only TICKED episodes become stops, in feed order',
      (tester) async {
    await tester.pumpWidget(_host(_seededCommunity()));
    await _pump(tester);

    // Tick the first and third episodes only (index 0 and 2).
    final boxes = find.byType(CheckboxListTile);
    await _tap(tester, boxes.at(0));
    await _tap(tester, boxes.at(2));

    // Add the ticked episodes as stops.
    await _tap(tester, find.widgetWithText(ElevatedButton, 'Add selected'));

    // Two stops were created, from the TICKED episodes, in feed order.
    expect(find.textContaining('Stop 1'), findsOneWidget);
    expect(find.textContaining('Stop 2'), findsOneWidget);
    expect(find.textContaining('Stop 3'), findsNothing);
  });

  testWidgets('Remove shows a labelled button and an Undo that restores the '
      'same stop at the same position', (tester) async {
    await tester.pumpWidget(_host(_seededCommunity()));
    await _pump(tester);

    // Select all, add them all as stops.
    await _tap(tester, find.textContaining('Select all'));
    await _tap(tester, find.widgetWithText(ElevatedButton, 'Add selected'));

    // Expand stop 2 so its Remove button is visible, then remove it.
    await _tap(tester, find.text('The Trial of George Jacobs'));
    final remove = find.widgetWithText(TextButton, 'Remove stop');
    expect(remove, findsWidgets); // labelled, not an icon-only button
    await _tap(tester, remove);

    // An Undo SnackBar appears.
    expect(find.widgetWithText(SnackBarAction, 'Undo'), findsOneWidget);

    // Undo restores the removed stop.
    await _tap(tester, find.widgetWithText(SnackBarAction, 'Undo'));
    expect(find.text('The Trial of George Jacobs'), findsWidgets);
  });

  testWidgets('"Use episode title" restores the stop name after an edit',
      (tester) async {
    await tester.pumpWidget(_host(_seededCommunity()));
    await _pump(tester);

    await _tap(tester, find.textContaining('Select all'));
    await _tap(tester, find.widgetWithText(ElevatedButton, 'Add selected'));

    // Expand stop 1.
    await _tap(tester, find.text('The Accusations Begin'));

    // The episode title is shown under the name field.
    expect(find.textContaining('Episode:'), findsWidgets);

    // Overwrite the name, then restore it with "Use episode title".
    await _enter(
        tester, find.widgetWithText(TextField, 'Stop name'), 'Something else');
    await _tap(tester, find.widgetWithText(TextButton, 'Use episode title'));
    expect(find.text('The Accusations Begin'), findsWidgets);
  });

  testWidgets('"Use my location" fills the stop from the (fake) provider',
      (tester) async {
    await tester.pumpWidget(_host(
      _seededCommunity(),
      loc: const FakeBuilderLocationProvider(
          myLocation: ResolvedPlace(42.52, -70.9, label: 'My location')),
    ));
    await _pump(tester);

    await _tap(tester, find.textContaining('Select all'));
    await _tap(tester, find.widgetWithText(ElevatedButton, 'Add selected'));

    await _tap(tester, find.text('The Accusations Begin'));
    await _tap(tester, find.widgetWithText(OutlinedButton, 'Use my location'));

    // The chosen location is shown as text (a label), not just raw numbers.
    expect(find.textContaining('My location'), findsWidgets);
  });

  testWidgets('address search fills the stop from the (fake) geocoder',
      (tester) async {
    await tester.pumpWidget(_host(
      _seededCommunity(),
      loc: const FakeBuilderLocationProvider(
          geocodeResult:
              ResolvedPlace(42.51, -70.89, label: 'Salem, Massachusetts')),
    ));
    await _pump(tester);

    await _tap(tester, find.textContaining('Select all'));
    await _tap(tester, find.widgetWithText(ElevatedButton, 'Add selected'));

    await _tap(tester, find.text('The Accusations Begin'));

    await _enter(
        tester, find.widgetWithText(TextField, 'Search address'), 'Salem');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await _pump(tester);

    expect(find.textContaining('Salem, Massachusetts'), findsWidgets);
  });

  testWidgets('publish validation NAMES the stop that needs a location',
      (tester) async {
    await tester.pumpWidget(_host(_seededCommunity()));
    await _pump(tester);

    // Give the tour a name while the field is at the top and on-screen.
    await _enter(tester,
        find.widgetWithText(TextField, 'Tour name'), 'Salem Witch Trials');

    await _tap(tester, find.textContaining('Select all'));
    await _tap(tester, find.widgetWithText(ElevatedButton, 'Add selected'));

    // Accept rights, but leave locations empty — a walking tour needs every
    // stop located.
    await _tap(tester, find.textContaining('I have the right'));

    // Scroll the Publish button into view and tap it.
    await _tap(tester, find.widgetWithText(FilledButton, 'Publish'));

    // The message names the specific stop (number + title).
    expect(
        find.textContaining("Stop 1 'The Accusations Begin'"), findsWidgets);
  });

  testWidgets('drag reorder is available (ReorderableListView)',
      (tester) async {
    await tester.pumpWidget(_host(_seededCommunity()));
    await _pump(tester);

    await _tap(tester, find.textContaining('Select all'));
    await _tap(tester, find.widgetWithText(ElevatedButton, 'Add selected'));

    // The stops are hosted in a ReorderableListView with drag handles.
    expect(find.byType(ReorderableListView), findsOneWidget);
    expect(find.byIcon(Icons.drag_handle), findsWidgets);
  });
}
