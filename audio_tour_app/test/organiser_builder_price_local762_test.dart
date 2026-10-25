// [LOCAL-762 / D711 §4] The organiser-audio builder's optional "Price for
// non-members" field is shown ONLY when the tour's visibility is Public (a
// members-only tour is covered by the dues and cannot be priced).
//
// Drives the REAL OrganiserAudioTourScreen with a MockClient (so the /price-
// tiers ladder call and the community GET resolve offline) and a Fake location
// provider, with the map tiles stubbed transparent.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
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
      episodes: [],
      episodeCount: 0,
      isOwner: true,
      myStatus: MyStatus(isMember: true, active: true),
    );

MockClient _client() => MockClient((req) async {
      final json = {'content-type': 'application/json'};
      if (req.url.path.endsWith('/price-tiers')) {
        return http.Response(
            '{"tiers":['
            '{"tier":20,"price_usd":3,"label":"\$3","product_id":"audioura.tour.usd3","in_picker":true},'
            '{"tier":22,"price_usd":5,"label":"\$5","product_id":"audioura.tour.usd5","in_picker":true}'
            ']}',
            200,
            headers: json);
      }
      return http.Response('{}', 200, headers: json);
    });

Widget _host() => MaterialApp(
      home: OrganiserAudioTourScreen(
        community: _community(),
        locationProvider: const FakeBuilderLocationProvider(),
      ),
    );

Future<void> _pump(WidgetTester tester) async {
  for (var i = 0; i < 6; i++) {
    await tester.pump(const Duration(milliseconds: 120));
  }
}

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

  testWidgets('the Price field is HIDDEN for a members-only tour (default)',
      (tester) async {
    await http.runWithClient(() async {
      await tester.pumpWidget(_host());
      await _pump(tester);
      // Default visibility is Members → no price field.
      expect(find.text('Price for non-members: '), findsNothing);
    }, _client);
  });

  testWidgets('switching visibility to Public SHOWS the Price field',
      (tester) async {
    await http.runWithClient(() async {
      await tester.pumpWidget(_host());
      await _pump(tester);

      // Flip the Visibility dropdown to Public.
      await tester.tap(find.byType(DropdownButton<String>).last);
      await _pump(tester);
      await tester.tap(find.text('Public').last);
      await _pump(tester);

      // The price field and a default "Free" chip appear.
      expect(find.text('Price for non-members: '), findsOneWidget);
      expect(find.widgetWithText(ChoiceChip, 'Free'), findsOneWidget);
    }, _client);
  });
}
