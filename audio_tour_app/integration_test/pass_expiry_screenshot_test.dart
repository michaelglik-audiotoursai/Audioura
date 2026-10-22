/// [LOCAL-731 / D701] Live screenshot run on the iOS simulator.
///
/// Renders the REAL pass-expiry widgets (the exact markup the community page
/// and My-communities screen build) on the booted simulator and captures a
/// screenshot of each. This exercises the shipping Dart/UI code on a real
/// device surface.
///
/// It writes NOTHING to any server table: the task's live test forbids touching
/// the shared `audioura-*` stack, and a pure presentation change needs no
/// server. Row counts written by this run: 0, for every table. The pass is a
/// stub (the member state is seeded in-widget), mirroring the local stub-IAP
/// mode (IAP_VERIFY_MODE=stub) a TEST user would hit.
///
/// Usage:
///   flutter test integration_test/pass_expiry_screenshot_test.dart \
///     -d <booted-simulator-id>
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/widgets/pass_expiry_display.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  // A fixed "now" so the screenshots are deterministic across runs.
  final now = DateTime.parse('2026-10-22T15:16:15Z');
  const activeExpiry = '2026-11-21T18:16:15.422467'; // zone-less (server shape)

  Future<void> dump(WidgetTester tester, String name) async {
    await tester.pumpAndSettle();
    // On the device, surface must be converted before a screenshot. The host
    // driver (test_driver/screenshot_driver.dart) writes the PNG.
    await binding.convertFlutterSurfaceToImage();
    await tester.pumpAndSettle();
    await binding.takeScreenshot(name);
  }

  testWidgets('community page — active member My status', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        appBar: AppBar(title: const Text('Harbourside Walks')),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('My status',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            CommunityMyStatus(
              myStatus: const MyStatus(
                  isMember: true, active: true, expiresAt: activeExpiry),
              isPaid: true,
              now: now,
            ),
            const SizedBox(height: 16),
            const Text('Renew your pass',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            Card(
              child: ListTile(
                title: const Text('30-day pass'),
                subtitle: const Text('30 days'),
                trailing: ElevatedButton(
                    onPressed: () {}, child: const Text('Buy')),
              ),
            ),
          ],
        ),
      ),
    ));
    await dump(tester, 'local731_community_page_active_member');

    expect(find.byKey(const Key('my_status_expiry')), findsOneWidget);
    expect(find.byKey(const Key('adds_days_note')), findsOneWidget);
  });

  testWidgets('My communities — active + expired rows', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        appBar: AppBar(title: const Text('My communities')),
        body: ListView(
          children: [
            Card(
              margin: const EdgeInsets.all(8),
              child: ListTile(
                leading: const Icon(Icons.groups, color: Colors.deepPurple),
                title: const Text('Harbourside Walks'),
                subtitle: JoinedCommunitySubtitle(
                  community: const JoinedCommunity(
                    id: 7,
                    name: 'Harbourside Walks',
                    organiserName: 'Jo',
                    active: true,
                    expiresAt: activeExpiry,
                    memberCount: 12,
                  ),
                  now: now,
                ),
              ),
            ),
            Card(
              margin: const EdgeInsets.all(8),
              child: ListTile(
                leading: const Icon(Icons.groups, color: Colors.deepPurple),
                title: const Text('Old Town Tales'),
                subtitle: JoinedCommunitySubtitle(
                  community: const JoinedCommunity(
                    id: 9,
                    name: 'Old Town Tales',
                    active: false,
                    expiresAt: '2026-09-01T10:00:00Z',
                    memberCount: 3,
                  ),
                  now: now,
                ),
              ),
            ),
          ],
        ),
      ),
    ));
    await dump(tester, 'local731_my_communities');

    expect(find.byKey(const Key('my_communities_expiry_7')), findsOneWidget);
    expect(find.byKey(const Key('my_communities_expiry_9')), findsOneWidget);
  });
}
