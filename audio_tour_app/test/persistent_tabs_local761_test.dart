// [LOCAL-761 / D710 as amended] Red-first tests for the persistent tab bar.
//
// What D710 (amended by Michael 2026-10-24) requires and these tests pin:
//   1. The tabs are EXACTLY Home · Generate Tour · Listen · Treats · About, in
//      that order — no Communities tab, no Settings move.
//   2. Each tab owns its own Navigator, so a screen pushed INSIDE a tab keeps
//      the bottom bar visible (the bar lives above the per-tab Navigators).
//   3. Re-tapping the active tab pops that tab back to its first screen.
//   4. Android Back pops inside the current tab; at a tab's first screen it
//      goes to Home; at Home it leaves the app (handled by the system).
//   5. A "go to Listen" request (notification View / PendingListenOpen) opens
//      the Listen tab with the bar visible.
//   6. The bar auto-hides while scrolling content down and returns on scroll
//      up / at the top.
//
// These are RED against the pre-LOCAL-761 MainScreen (a single body + one
// BottomNavigationBar, no per-tab Navigators, no auto-hide). The testing hooks
// (MainScreen.tabNavigatorKeyForTest, kMainBottomBarKey, kMainBottomBarSlideKey)
// are part of the new public surface.

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollDirection;
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/main_screen.dart';
import 'package:audio_tour_app_dev/services/deep_link_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Several hosted screens (My Tours) heal paths via path_provider on load.
  // Give it a temp dir so building the Listen tab never throws in the test VM.
  setUp(() {
    SharedPreferences.setMockInitialValues({'app_mode': 'Tours'});
    PendingListenOpen.instance.consume();
    PendingShareSearch.instance.code.value = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => '/tmp',
    );
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
  });

  group('[LOCAL-761] tab order and labels are unchanged', () {
    testWidgets('exactly five tabs: Home · Generate Tour · Listen · Treats · '
        'About, in order', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: MainScreen()));
      await tester.pump();

      final bar = tester.widget<BottomNavigationBar>(
        find.byType(BottomNavigationBar),
      );
      final labels = bar.items.map((i) => i.label).toList();
      expect(labels, ['Home', 'Generate Tour', 'Listen', 'Treats', 'About']);

      // No Communities tab was added.
      expect(labels.contains('Communities'), isFalse);
    });
  });

  group('[LOCAL-761] a tab\'s heavy content is built lazily on first visit', () {
    testWidgets('starting on Treats does not mount the Home tab Navigator '
        'until Home is visited', (tester) async {
      // initialTab 3 = Treats. Home's content must not be built yet.
      await tester.pumpWidget(
          const MaterialApp(home: MainScreen(initialTab: kTreatsTab)));
      await tester.pump();

      final state = tester.state<MainScreenState>(find.byType(MainScreen));
      expect(state.currentIndexForTest, kTreatsTab);
      // The Home tab's Navigator has not been created yet (lazy) — so its
      // GlobalKey has no live NavigatorState.
      expect(state.tabNavigatorKeyForTest(kHomeTab).currentState, isNull);
      // The visited (Treats) tab's Navigator IS live.
      expect(state.tabNavigatorKeyForTest(kTreatsTab).currentState, isNotNull);

      // Visiting Home builds it.
      await tester.tap(find.byIcon(Icons.home));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(state.currentIndexForTest, kHomeTab);
      expect(state.tabNavigatorKeyForTest(kHomeTab).currentState, isNotNull);
    });
  });

  group('[LOCAL-761] per-tab Navigators keep the bar visible', () {
    testWidgets('each of the five tabs has its own NavigatorState key',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: MainScreen()));
      await tester.pump();

      final state = tester.state<MainScreenState>(find.byType(MainScreen));
      for (var i = 0; i < 5; i++) {
        expect(state.tabNavigatorKeyForTest(i), isA<GlobalKey<NavigatorState>>());
      }
      // The keys are distinct per tab.
      final keys = List.generate(5, (i) => state.tabNavigatorKeyForTest(i));
      expect(keys.toSet().length, 5);
    });

    testWidgets('pushing a screen inside the current tab keeps the bottom bar',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: MainScreen()));
      await tester.pump();

      // The bar is present on the first screen.
      expect(find.byKey(kMainBottomBarKey), findsOneWidget);

      // Push a deep screen INTO the Home tab's own Navigator.
      final state = tester.state<MainScreenState>(find.byType(MainScreen));
      state.tabNavigatorKeyForTest(0).currentState!.push(
            MaterialPageRoute(
              builder: (_) => const Scaffold(
                body: Center(child: Text('DEEP SCREEN')),
              ),
            ),
          );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // The deep screen is on top AND the persistent bar is still there.
      expect(find.text('DEEP SCREEN'), findsOneWidget);
      expect(find.byKey(kMainBottomBarKey), findsOneWidget);
    });
  });

  group('[LOCAL-761] re-tap the active tab pops it to its first screen', () {
    testWidgets('re-tapping the current tab pops its Navigator to root',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: MainScreen()));
      await tester.pump();

      final state = tester.state<MainScreenState>(find.byType(MainScreen));
      state.tabNavigatorKeyForTest(0).currentState!.push(
            MaterialPageRoute(
              builder: (_) => const Scaffold(
                body: Center(child: Text('PUSHED IN HOME')),
              ),
            ),
          );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text('PUSHED IN HOME'), findsOneWidget);
      expect(state.tabNavigatorKeyForTest(0).currentState!.canPop(), isTrue);

      // Re-tap the already-selected Home tab.
      await tester.tap(find.byIcon(Icons.home));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pump(const Duration(milliseconds: 400));

      // Home's Navigator was popped back to its first screen.
      expect(find.text('PUSHED IN HOME'), findsNothing);
      expect(state.tabNavigatorKeyForTest(0).currentState!.canPop(), isFalse);
    });
  });

  group('[LOCAL-761] Android back pops within the tab, then to Home', () {
    testWidgets('back pops the current tab stack before leaving the app',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: MainScreen()));
      await tester.pump();

      // On the Generate tab, push a screen, then press system Back.
      final state = tester.state<MainScreenState>(find.byType(MainScreen));
      await tester.tap(find.byIcon(Icons.add));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(state.currentIndexForTest, 1);
      state.tabNavigatorKeyForTest(1).currentState!.push(
            MaterialPageRoute(
              builder: (_) => const Scaffold(
                body: Center(child: Text('GEN DEEP')),
              ),
            ),
          );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text('GEN DEEP'), findsOneWidget);

      // System back: pops within the Generate tab (does NOT leave the app).
      final didPop = await state.handleBackForTest();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pump(const Duration(milliseconds: 400));
      expect(didPop, isTrue, reason: 'back was handled inside the tab');
      expect(find.text('GEN DEEP'), findsNothing);
    });

    testWidgets('at a non-Home tab root, back goes to the Home tab',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: MainScreen()));
      await tester.pump();

      final state = tester.state<MainScreenState>(find.byType(MainScreen));
      await tester.tap(find.byIcon(Icons.local_cafe));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(state.currentIndexForTest, 3);

      // At the Treats root (nothing to pop), back selects Home.
      final didPop = await state.handleBackForTest();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(didPop, isTrue, reason: 'back switched to Home instead of exiting');
      expect(state.currentIndexForTest, 0);
    });

    testWidgets('at the Home tab root, back is NOT consumed (app may exit)',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: MainScreen()));
      await tester.pump();

      final state = tester.state<MainScreenState>(find.byType(MainScreen));
      expect(state.currentIndexForTest, 0);

      // Nothing to pop on Home and we are already Home → back is not consumed,
      // so the system is free to background/exit the app (current behaviour).
      final didPop = await state.handleBackForTest();
      await tester.pump();
      expect(didPop, isFalse);
      expect(state.currentIndexForTest, 0);
    });
  });

  group('[LOCAL-761] PendingListenOpen opens the Listen tab with the bar', () {
    testWidgets('firing PendingListenOpen selects Listen and keeps the bar',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: MainScreen()));
      await tester.pump();

      expect(find.text('Home'), findsOneWidget); // on Home to start
      final state = tester.state<MainScreenState>(find.byType(MainScreen));
      expect(state.currentIndexForTest, 0);

      PendingListenOpen.instance.offer('123');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      expect(state.currentIndexForTest, 2); // Listen tab
      expect(find.byKey(kMainBottomBarKey), findsOneWidget);
    });
  });

  group('[LOCAL-761] bar auto-hides on scroll down, returns on scroll up', () {
    testWidgets('scrolling content down hides the bar; scrolling up shows it',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: MainScreen()));
      await tester.pump();

      final state = tester.state<MainScreenState>(find.byType(MainScreen));

      // Visible with no scrolling.
      expect(state.barVisibleForTest, isTrue);

      // A downward content scroll (finger up) hides the bar.
      state.onScrollForTest(ScrollDirection.reverse);
      await tester.pump(const Duration(milliseconds: 300));
      expect(state.barVisibleForTest, isFalse);

      // Scrolling back up shows it again.
      state.onScrollForTest(ScrollDirection.forward);
      await tester.pump(const Duration(milliseconds: 300));
      expect(state.barVisibleForTest, isTrue);
    });

    testWidgets('the animated slide wrapper exists so the bar can slide away',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: MainScreen()));
      await tester.pump();
      expect(find.byKey(kMainBottomBarSlideKey), findsOneWidget);
    });
  });
}
