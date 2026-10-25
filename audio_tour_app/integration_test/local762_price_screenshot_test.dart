// [LOCAL-762 / D711 §4] Live screenshot run on the iOS simulator. Renders the
// REAL OrganiserAudioTourScreen and photographs the optional "Price for
// non-members" control appearing ONLY when visibility is Public:
//   1. members_no_price — default (Members) visibility: no price control
//   2. public_price     — after switching to Public: Free + $ chips + the
//                         "Members get it included; non-members pay this price"
//                         grandfather note
//
// A MockClient answers /price-tiers so the $ chips render; no other server is
// involved and the location provider is faked, so the run is deterministic and
// $0. (The map tiles are stubbed transparent.)
//
// Usage:
//   flutter drive \
//     --driver=test_driver/local762_screenshot_driver.dart \
//     --target=integration_test/local762_price_screenshot_test.dart \
//     -d <booted-simulator-id>
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/organiser_audio_tour_screen.dart';
import 'package:audio_tour_app_dev/services/builder_location_provider.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/utils/tour_role_label.dart';

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
            '{"tier":22,"price_usd":5,"label":"\$5","product_id":"audioura.tour.usd5","in_picker":true},'
            '{"tier":25,"price_usd":10,"label":"\$10","product_id":"audioura.tour.usd10","in_picker":true},'
            '{"tier":28,"price_usd":20,"label":"\$20","product_id":"audioura.tour.usd20","in_picker":true}'
            ']}',
            200,
            headers: json);
      }
      return http.Response('{}', 200, headers: json);
    });

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

  testWidgets('builder price field: members (hidden) → public (shown)',
      (tester) async {
    debugBuilderTileProviderOverride = TransparentTileProvider();
    SharedPreferences.setMockInitialValues({
      'server_mode': 'cloud',
      'user_id': 'owner-1',
    });

    await http.runWithClient(() async {
      await tester.pumpWidget(MaterialApp(
        home: OrganiserAudioTourScreen(
          community: _community(),
          locationProvider: const FakeBuilderLocationProvider(),
        ),
      ));
      await settle(tester);

      // 1. Default visibility = Members → NO price control.
      await shot(tester, '01_members_no_price');

      // 2. Switch Visibility → Public, revealing the price control.
      await tester.tap(find.byType(DropdownButton<String>).last);
      await settle(tester);
      await tester.tap(find.text('Public').last);
      await shot(tester, '02_public_price');
    }, _client);
  });

  // [LOCAL-762 / D711 §2] The Listen ⋮ menu role line, rendered with the REAL
  // tourRoleLabel function for the three cases Michael asked to see, plus the
  // owner-only Price/Re-score gating they govern. Rendered in a representative
  // menu so the role line + gated items are visible together (the full
  // MyToursScreen needs a live backend; the menu structure here mirrors it).
  testWidgets('Listen menu role line: member / organiser / broadcast',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: _RoleMenuDemo()));
    await settle(tester);
    await shot(tester, '03_role_lines');
  });
}

/// A static demo of the three role-line cases side by side, each above the
/// owner-only items it governs, built with the real tourRoleLabel + the real
/// icon mapping — exactly what the Listen ⋮ menu renders.
class _RoleMenuDemo extends StatelessWidget {
  const _RoleMenuDemo();

  Widget _case(Map<String, dynamic> record, List<String> items) {
    final line = tourRoleLabel(record, 'me');
    final icon = {
      TourRoleIcon.person: Icons.person_outline,
      TourRoleIcon.group: Icons.groups_outlined,
      TourRoleIcon.broadcast: Icons.podcasts,
      TourRoleIcon.audioura: Icons.headphones_outlined,
    }[line.icon]!;
    return Card(
      margin: const EdgeInsets.all(8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            leading: Icon(icon, size: 16, color: Colors.grey),
            title: Text(line.text,
                style: const TextStyle(fontSize: 12, color: Colors.grey)),
            dense: true,
          ),
          const Divider(height: 1),
          for (final it in items)
            ListTile(dense: true, title: Text(it)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Listen ⋮ menu — role line (D711 §2)')),
      body: ListView(
        children: [
          // Owner of a public community tour: role line + live Price + Re-score.
          _case({
            'is_owner': true,
            'is_community': true,
            'is_organiser': true,
            'community_name': 'Salem TV show funs',
            'community_visibility': 'public',
          }, const ['Price', 'Request re-score']),
          // Member on a community tour: role line, NO Price/Re-score.
          _case({
            'is_owner': false,
            'is_community': true,
            'community_id': 10,
            'community_name': 'Salem TV show funs',
            'community_visibility': 'members',
          }, const ['(no Price · no Re-score — not the owner)']),
          // Broadcast tour, you are the organiser: role line, NO Re-score.
          _case({
            'is_owner': true,
            'is_community': true,
            'is_organiser': true,
            'is_broadcast': true,
            'source_kind': 'organiser_audio',
            'community_name': 'Salem TV show funs',
          }, const ['(no Re-score — broadcast tour)']),
        ],
      ),
    );
  }
}

