// LOCAL-705 (D661) — per-screen device-like proof that each NEW screen stays
// usable when the backend is Storied (Stable) and answers the GCloud API
// gateway's 404 for a route it does not host:
//
//     {"error":"endpoint not found","service":"api-gateway"}   (HTTP 404)
//
// Each test swaps the app's top-level http client for a MockClient that returns
// that exact 404 (via http.runWithClient — http 1.x routes Endpoints.get/post
// and bare http.get/post through the zone-local client), pumps the real screen,
// and asserts it shows the Preview message / its empty state and NO crash, NO
// red error widget, NO stuck spinner.
//
// Screens covered (the task's five new ones):
//   1. My communities           -> empty state, join bar still usable
//   2. Community page (by id)    -> "Community not found." message, usable
//   2b.Community page (by code)  -> "No community with that code." message
//   3. Your plan (buy buttons)   -> buy buttons still visible (no crash)
//   4. Recovery code             -> tapping Create shows "Preview only"
//   5. Generate "for my community" selector feed -> ownedCommunities() == []
//      (the selector hides; CommunityTourList stays null) — the device-like
//      proof for the Generate-tab community path without pumping the 111 KB
//      generator screen.
//
// A regression (e.g. a screen that rethrows the gateway 404, or shows a raw
// "(404)") turns these red.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/config/endpoints.dart';
import 'package:audio_tour_app_dev/screens/my_communities_screen.dart';
import 'package:audio_tour_app_dev/screens/community_page_screen.dart';
import 'package:audio_tour_app_dev/screens/communities_about_screen.dart';
import 'package:audio_tour_app_dev/screens/plan_screen.dart';
import 'package:audio_tour_app_dev/screens/recovery_code_screen.dart';
import 'package:audio_tour_app_dev/services/community_tour_service.dart';

/// The exact GCloud API gateway 404 envelope for an unknown route.
const _gateway404 = '{"error":"endpoint not found","service":"api-gateway"}';

/// A client that answers EVERY request with the gateway's JSON 404.
MockClient _gatewayClient() => MockClient((req) async => http.Response(
      _gateway404,
      404,
      headers: {'content-type': 'application/json'},
    ));

/// A client that refuses every connection (the whole service absent on Storied).
MockClient _refusedClient() =>
    MockClient((req) async => throw const SocketException('Connection refused'));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    // A real-user cloud profile on the Storied track, with a user id so the
    // screens take their normal (networked) path — which the MockClient then
    // answers with the gateway 404.
    SharedPreferences.setMockInitialValues({
      'server_mode': 'cloud',
      'cloud_track': 'storied',
      'user_id': 'local705-widget-user',
      'use_mock_wallet': false,
    });
  });

  // ───────────────────────────── 1. My communities ───────────────────────────
  group('My communities on a Storied gateway 404', () {
    testWidgets('shows the empty state and the join bar stays usable',
        (tester) async {
      await http.runWithClient(() async {
        await tester.pumpWidget(const MaterialApp(home: MyCommunitiesScreen()));
        await tester.pumpAndSettle();
      }, _gatewayClient);

      // A 404 is a REACHABLE server (isAvailable -> true), so the join bar and
      // the "no communities yet" empty state show — not a crash, not a spinner.
      expect(find.byType(CircularProgressIndicator), findsNothing);
      expect(find.text('Have an invite code?'), findsOneWidget);
      expect(find.widgetWithText(ElevatedButton, 'Join'), findsOneWidget);
      expect(find.textContaining('not joined any communities'), findsOneWidget);
      expect(find.byType(ErrorWidget), findsNothing);
      expect(TestWidgetsFlutterBinding.instance.takeException(), isNull);
    });

    testWidgets('on connection-refused shows the Preview-only empty state',
        (tester) async {
      await http.runWithClient(() async {
        await tester.pumpWidget(const MaterialApp(home: MyCommunitiesScreen()));
        await tester.pumpAndSettle();
      }, _refusedClient);

      expect(find.byType(CircularProgressIndicator), findsNothing);
      expect(find.textContaining('Preview only'), findsOneWidget);
      expect(TestWidgetsFlutterBinding.instance.takeException(), isNull);
    });
  });

  // ───────────────────────────── 2. Community page ───────────────────────────
  group('Community page on a Storied gateway 404', () {
    testWidgets('by id -> "Community not found.", no crash', (tester) async {
      await http.runWithClient(() async {
        await tester.pumpWidget(
            const MaterialApp(home: CommunityPageScreen(communityId: 7)));
        await tester.pumpAndSettle();
      }, _gatewayClient);

      expect(find.byType(CircularProgressIndicator), findsNothing);
      expect(find.text('Community not found.'), findsOneWidget);
      expect(find.byType(ErrorWidget), findsNothing);
      expect(TestWidgetsFlutterBinding.instance.takeException(), isNull);
    });

    testWidgets('by invite code -> "No community with that code.", no crash',
        (tester) async {
      await http.runWithClient(() async {
        await tester.pumpWidget(
            const MaterialApp(home: CommunityPageScreen(joinCode: 'AB12CD34')));
        await tester.pumpAndSettle();
      }, _gatewayClient);

      expect(find.byType(CircularProgressIndicator), findsNothing);
      expect(find.text('No community with that code.'), findsOneWidget);
      expect(TestWidgetsFlutterBinding.instance.takeException(), isNull);
    });
  });

  // ───────────────────────── 2c. Communities About (join) ────────────────────
  group('Communities About on a Storied gateway 404', () {
    testWidgets('still renders the join field + Create button (usable)',
        (tester) async {
      await http.runWithClient(() async {
        await tester
            .pumpWidget(const MaterialApp(home: CommunitiesAboutScreen()));
        await tester.pumpAndSettle();
      }, _gatewayClient);

      await tester.scrollUntilVisible(
        find.widgetWithText(TextField, 'Invite code'),
        200,
        scrollable: find.byType(Scrollable),
      );
      expect(find.widgetWithText(TextField, 'Invite code'), findsOneWidget);
      expect(find.widgetWithText(ElevatedButton, 'Join'), findsOneWidget);
      expect(TestWidgetsFlutterBinding.instance.takeException(), isNull);
    });
  });

  // ───────────────────────────── 3. Your plan ────────────────────────────────
  group('Your plan on a Storied gateway 404', () {
    testWidgets('buy buttons still visible; no crash, no stuck spinner',
        (tester) async {
      await http.runWithClient(() async {
        // No test seams: entitlements + /purchases/mode both answer 404, so the
        // screen must still build its buy card from its defaults.
        await tester.pumpWidget(const MaterialApp(home: PlanScreen()));
        await tester.pumpAndSettle();
      }, _gatewayClient);

      expect(find.byType(ErrorWidget), findsNothing);
      expect(TestWidgetsFlutterBinding.instance.takeException(), isNull);
      // The $10 Pack and Curator buy buttons are always visible (LOCAL-699).
      expect(
          find.text('\$10 Pack — 5 new tours + 5 edits, up to 10 stops'),
          findsOneWidget);
      expect(
          find.text(
              'Curator (\$25) — 25 tours or edits, up to 25 stops, sell your tours'),
          findsOneWidget);
    });
  });

  // ───────────────────────────── 4. Recovery code ────────────────────────────
  group('Recovery code on a Storied gateway 404', () {
    testWidgets('Create my recovery code -> shows the Preview-only message',
        (tester) async {
      await http.runWithClient(() async {
        await tester
            .pumpWidget(const MaterialApp(home: RecoveryCodeScreen()));
        await tester.pumpAndSettle();

        await tester.tap(find.widgetWithText(ElevatedButton,
            'Create my recovery code'));
        await tester.pump(); // start the request
        await tester.pump(const Duration(milliseconds: 50)); // 404 comes back
      }, _gatewayClient);
      await tester.pumpAndSettle();

      // The helper turns the gateway 404 into the Preview-only line, shown in a
      // SnackBar — never a raw "(404)" and never an uncaught exception.
      expect(find.text(Endpoints.featureUnavailableMessage), findsOneWidget);
      expect(find.textContaining('(404)'), findsNothing);
      expect(TestWidgetsFlutterBinding.instance.takeException(), isNull);
    });
  });

  // ─────────────────── 5. Generate "for my community" selector ────────────────
  group('Generate "for my community" selector on a Storied gateway 404', () {
    test('ownedCommunities() -> [] (selector hides), communityTours() -> null',
        () async {
      await http.runWithClient(() async {
        final owned =
            await CommunityTourService.ownedCommunities('local705-widget-user');
        expect(owned, isEmpty); // CommunityTourRules.selectorVisible([]) == false
        expect(CommunityTourRules.selectorVisible(owned), isFalse);

        final list = await CommunityTourService.communityTours(7,
            userId: 'local705-widget-user');
        expect(list, isNull); // the community page shows its own empty state
      }, _gatewayClient);
    });

    test('on connection-refused the selector also hides (no throw)', () async {
      await http.runWithClient(() async {
        final owned =
            await CommunityTourService.ownedCommunities('local705-widget-user');
        expect(owned, isEmpty);
        expect(CommunityTourRules.selectorVisible(owned), isFalse);
      }, _refusedClient);
    });
  });
}
