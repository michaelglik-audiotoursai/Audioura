// [LOCAL-757] Community tours stand out on the Home map (green marker) and in
// search / list / sheets (one green CommunityTourChip) BEFORE the listener taps.
//
// Michael, 2026-10-24: a community tour looked exactly like every other tour on
// the map and carried only a small purple line in the lists, so people feared
// "all tours are for community and we are just hassling money from them". This
// suite drives the pure rules + the single chip widget, so it is RED on
// 9a86e6e8 (homeTourChipLabel / homeMarkerKind / homeMarkerColor / homeMarkerIcon
// and CommunityTourChip do not exist yet) and GREEN after the fix.
//
// Run: flutter test test/home_community_marker_chip_local757_test.dart

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/widgets/community_tour_chip.dart';

void main() {
  // The exact /tours-near community-tour shape from the ticket (community 10,
  // "Salem TV show funs", tours 716/733/735).
  Map<String, dynamic> communityTour({String visibility = 'members'}) => {
        'id': 716,
        'name': 'Salem downtown walk',
        'type': 'tour',
        'community_id': 10,
        'community_name': 'Salem TV show funs',
        'community_visibility': visibility,
        'price_label': 'Free',
      };

  Map<String, dynamic> plainTour() => {
        'id': 1,
        'name': 'City walk',
        'type': 'tour',
        'price_label': '\$4.99',
      };

  Map<String, dynamic> treat() => {'id': 9, 'name': 'Cafe', 'type': 'treat'};

  group('LOCAL-757 A — map marker tells a community tour apart (both paths)', () {
    // Both marker paths (cached ~491 and live /tours-near ~814) now build the
    // marker from CommunityRules.homeMarkerKind + homeMarkerColor/homeMarkerIcon,
    // so testing the shared rule covers BOTH paths.
    test('a community tour cluster is the "community" kind', () {
      expect(CommunityRules.homeMarkerKind([communityTour()]), 'community');
    });

    test('a plain single tour is "single", a plain multi is "multiple"', () {
      expect(CommunityRules.homeMarkerKind([plainTour()]), 'single');
      expect(
          CommunityRules.homeMarkerKind([plainTour(), plainTour()]), 'multiple');
    });

    test('a community tour mixed into a cluster still makes the pin community', () {
      expect(
          CommunityRules.homeMarkerKind([plainTour(), communityTour()]),
          'community');
    });

    test('a treat pin keeps its own kind (community does not steal the cup)', () {
      expect(CommunityRules.homeMarkerKind([treat(), communityTour()]), 'treat');
    });

    test('the community marker COLOUR differs from a plain tour marker', () {
      final community = homeMarkerColor(CommunityRules.homeMarkerKind([communityTour()]));
      final plainSingle = homeMarkerColor(CommunityRules.homeMarkerKind([plainTour()]));
      final plainMulti =
          homeMarkerColor(CommunityRules.homeMarkerKind([plainTour(), plainTour()]));
      expect(community, isNot(plainSingle));
      expect(community, isNot(plainMulti));
      expect(community, kCommunityGreen);
    });

    test('the community marker ICON is the groups symbol, not the plain walk', () {
      final community = homeMarkerIcon(CommunityRules.homeMarkerKind([communityTour()]));
      final plain = homeMarkerIcon(CommunityRules.homeMarkerKind([plainTour()]));
      expect(community, Icons.groups);
      expect(community, isNot(plain));
    });
  });

  group('LOCAL-757 B — chip label (pure, carries the community name)', () {
    test('members-only community tour → "Members only · <name>"', () {
      expect(CommunityRules.homeTourChipLabel(communityTour(visibility: 'members')),
          'Members only · Salem TV show funs');
    });

    test('public / listed community tour (D706) → "Community tour · <name>"', () {
      expect(CommunityRules.homeTourChipLabel(communityTour(visibility: 'listed')),
          'Community tour · Salem TV show funs');
    });

    test('the chip label always includes the community name', () {
      expect(CommunityRules.homeTourChipLabel(communityTour()),
          contains('Salem TV show funs'));
    });

    test('a plain Audioura tour has no chip label', () {
      expect(CommunityRules.homeTourChipLabel(plainTour()), '');
    });

    test('isMembersOnlyTour is true for members-only, false for listed/plain', () {
      expect(CommunityRules.isMembersOnlyTour(communityTour(visibility: 'members')),
          isTrue);
      expect(CommunityRules.isMembersOnlyTour(communityTour(visibility: 'listed')),
          isFalse);
      expect(CommunityRules.isMembersOnlyTour(plainTour()), isFalse);
    });
  });

  group('LOCAL-757 B — CommunityTourChip widget (one widget, every surface)', () {
    Future<void> pump(WidgetTester tester, Map<String, dynamic> tour,
        {Brightness brightness = Brightness.light}) async {
      await tester.pumpWidget(MaterialApp(
        theme: ThemeData(brightness: brightness),
        home: Scaffold(
          body: Center(
            child: SizedBox(width: 320, child: CommunityTourChip(tour: tour)),
          ),
        ),
      ));
    }

    testWidgets('shown for a members-only community tour, with name + icon',
        (tester) async {
      await pump(tester, communityTour(visibility: 'members'));
      expect(find.byKey(const Key('community_tour_chip')), findsOneWidget);
      expect(find.text('Members only · Salem TV show funs'), findsOneWidget);
      expect(find.byIcon(Icons.groups), findsOneWidget);
    });

    testWidgets('shown for a PUBLIC community tour (D706)', (tester) async {
      await pump(tester, communityTour(visibility: 'listed'));
      expect(find.byKey(const Key('community_tour_chip')), findsOneWidget);
      expect(find.text('Community tour · Salem TV show funs'), findsOneWidget);
    });

    testWidgets('ABSENT for a plain Audioura tour (no membership implied)',
        (tester) async {
      await pump(tester, plainTour());
      expect(find.byKey(const Key('community_tour_chip')), findsNothing);
      expect(find.byIcon(Icons.groups), findsNothing);
    });

    testWidgets('renders in dark mode too (contrast path exercised)',
        (tester) async {
      await pump(tester, communityTour(), brightness: Brightness.dark);
      expect(find.byKey(const Key('community_tour_chip')), findsOneWidget);
      expect(find.text('Members only · Salem TV show funs'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}
