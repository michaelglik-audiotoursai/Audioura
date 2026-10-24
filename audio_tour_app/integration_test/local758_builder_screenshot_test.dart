// [LOCAL-758] Live screenshot run on the iOS simulator. Renders the REAL
// rebuilt OrganiserAudioTourScreen with a seeded community (three feed
// episodes) and a FakeBuilderLocationProvider, then drives it through the UX
// states Michael asked to see and photographs each:
//   1. checklist      — "Choose episodes" with Select none/all + metadata
//   2. collapsed_cards — the stops after "Add selected" (number, name, status)
//   3. expanded_card   — one stop open: name + Episode/Use episode title +
//                        location buttons + Advanced
//   4. located_card    — after "Use my location" fills the stop (✓ + preview)
//   5. map_picker      — the full-screen "Pick on map" screen
//   6. undo_snackbar   — the Remove-stop Undo SnackBar
//
// No server is involved: the screen is given the community directly and the
// fake provider returns fixed places, so the run is deterministic and $0.
// Map tiles use the real OpenStreetMap network tiles (simulator has internet).
//
// Usage:
//   flutter drive \
//     --driver=test_driver/local758_screenshot_driver.dart \
//     --target=integration_test/local758_builder_screenshot_test.dart \
//     -d <booted-simulator-id>
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/organiser_audio_tour_screen.dart';
import 'package:audio_tour_app_dev/services/builder_location_provider.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';

Community _community() => const Community(
      id: 42,
      name: 'Salem TV show funs',
      organiser: Organiser(name: 'Michael'),
      hasWaiver: false,
      isPaid: false,
      visibility: 'listed',
      disabled: false,
      passes: [],
      episodeCount: 3,
      isOwner: true,
      myStatus: MyStatus(isMember: true, active: true),
      episodes: [
        CommunityEpisode(
            position: 1,
            title: 'The Accusations Begin',
            audioUrl: 'https://feed.example/ep1.mp3',
            source: 'feed',
            date: '12 Oct 2026',
            duration: '41 min',
            sizeBytes: 39845000,
            description: 'How the first accusations spread through Salem.'),
        CommunityEpisode(
            position: 2,
            title: 'The Trial of George Jacobs',
            audioUrl: 'https://feed.example/ep2.mp3',
            source: 'feed',
            date: '19 Oct 2026',
            duration: '48 min',
            sizeBytes: 46710000),
        CommunityEpisode(
            position: 3,
            title: 'The Aftermath',
            audioUrl: 'https://feed.example/ep3.mp3',
            source: 'feed',
            date: '26 Oct 2026',
            duration: '39 min',
            sizeBytes: 37120000),
      ],
    );

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  Future<void> settle(WidgetTester tester) async {
    for (var i = 0; i < 8; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }
  }

  Future<void> shot(WidgetTester tester, String name) async {
    await settle(tester);
    await binding.convertFlutterSurfaceToImage();
    await settle(tester);
    await binding.takeScreenshot(name);
  }

  Future<void> reveal(WidgetTester tester, Finder f) async {
    if (f.evaluate().isEmpty) {
      final s = find.byType(Scrollable).first;
      try {
        await tester.scrollUntilVisible(f, -140, scrollable: s);
      } catch (_) {
        await tester.scrollUntilVisible(f, 140, scrollable: s);
      }
    }
    await tester.ensureVisible(f.first);
    await settle(tester);
  }

  Future<void> tap(WidgetTester tester, Finder f) async {
    await reveal(tester, f);
    await tester.tap(f.first);
    await settle(tester);
  }

  testWidgets('organiser builder UX — all states', (tester) async {
    SharedPreferences.setMockInitialValues({'user_id': 'owner-1'});
    await tester.pumpWidget(MaterialApp(
      home: OrganiserAudioTourScreen(
        community: _community(),
        locationProvider: const FakeBuilderLocationProvider(
          myLocation: ResolvedPlace(42.5195, -70.8967,
              label: 'My location (Salem, MA)'),
          geocodeResult: ResolvedPlace(42.5281, -70.9009,
              label: 'Salem Witch Museum, Salem, MA'),
        ),
      ),
    ));
    await settle(tester);

    // 1. The import checklist.
    await shot(tester, '01_checklist');

    // 2. Add all episodes as stops → collapsed cards.
    await tap(tester, find.textContaining('Select all'));
    await tap(tester, find.widgetWithText(ElevatedButton, 'Add selected'));
    await shot(tester, '02_collapsed_cards');

    // 3. Expand the first stop.
    await tap(tester, find.text('The Accusations Begin'));
    await shot(tester, '03_expanded_card');

    // 4. Fill the location via the fake "Use my location".
    await tap(tester, find.widgetWithText(OutlinedButton, 'Use my location'));
    await shot(tester, '04_located_card');

    // 5. Open the full-screen map picker, drop a pin, photograph it.
    await tap(tester, find.widgetWithText(OutlinedButton, 'Pick on map'));
    // Tap near the centre of the map to drop a pin.
    await tester.tapAt(tester.getCenter(find.byType(Scaffold).last));
    await settle(tester);
    await shot(tester, '05_map_picker');
    // Return from the picker.
    await tap(tester, find.text('Use this pin'));

    // 6. Remove a stop → the Undo SnackBar.
    await tap(tester, find.widgetWithText(TextButton, 'Remove stop'));
    await shot(tester, '06_undo_snackbar');
  });
}
