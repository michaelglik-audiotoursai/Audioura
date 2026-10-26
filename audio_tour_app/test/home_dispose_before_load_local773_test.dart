// [LOCAL-773] First launch crashes in Home's _loadAppMode (setState after
// dispose); stale startup banner.
//
// Found by GCloud_Storied on Play build 2.4.31+77 (emulator, API 36):
//   Unhandled Exception: Null check operator used on a null value
//   at State.setState  (_HomeScreenState._loadAppMode, home_screen.dart ~325)
//
// _loadAppMode() awaits SharedPreferences, DeviceService.getUserId,
// _loadLocationHistory and _loadCustomLocation, then calls setState with no
// `mounted` check. On a FRESH install the root (_AudioTourAppState) renders
// MainScreen -> HomeScreen optimistically, then _checkOnboarding() reads
// SharedPreferences and, finding onboarding_complete=false, swaps `home` to
// OnboardingScreen — DISPOSING the in-flight HomeScreen while _loadAppMode's
// awaits are still pending. When they resolve, setState fires on a disposed
// State and throws. In release/profile that is "Null check operator used on a
// null value" (the null `_element`); in a debug build (what this test runs) it
// is the equivalent assertion "setState() called after dispose()". Every fresh
// tester install hits this.
//
// This test reproduces the race deterministically. On a fresh install there is
// no cached `user_id`, so _loadAppMode suspends at `await
// DeviceService.getUserId()`, which crosses the device_info_plus platform
// channel — a real async gap. We hold that channel reply open with a Completer,
// dispose HomeScreen while the await is parked, then release the reply so the
// _loadAppMode continuation (its setState) runs against the disposed State —
// exactly the production ordering. runAsync lets the real channel replies and
// the resumed continuation actually run.
//
// We collect every error routed through FlutterError.onError during the window:
//   * RED on base (85af16c4): the unguarded setState throws "setState() called
//     after dispose()" (release: "Null check operator…"), captured here.
//   * GREEN on the branch: the `if (!mounted) return;` guard makes _loadAppMode
//     bail out quietly — no such error — AND the load never reaches
//     _initializeMap (its first line logs "HOME: Starting map initialization"
//     to the persisted debug_logs, which therefore stays absent).
//
// Offline: SharedPreferences is mocked; path_provider is stubbed; the
// community/map HTTP calls started in initState fail transport-side and are
// swallowed by their own try/catch.
//
// Run: flutter test test/home_dispose_before_load_local773_test.dart

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/home_screen.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const deviceInfoChannel =
      MethodChannel('dev.fluttercommunity.plus/device_info');
  const pathProviderChannel = MethodChannel('plugins.flutter.io/path_provider');

  late Completer<Map<String, dynamic>> deviceInfoGate;

  setUp(() {
    // Fresh install: default Tours mode, and crucially NO cached user_id — so
    // _loadAppMode must call DeviceService.getUserId(), which crosses the
    // device_info channel and parks the await there.
    SharedPreferences.setMockInitialValues(<String, Object>{
      'app_mode': 'Tours',
    });

    // Hold the device_info reply open until we choose to release it, so the
    // _loadAppMode await stays suspended across the dispose.
    deviceInfoGate = Completer<Map<String, dynamic>>();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(deviceInfoChannel, (call) async {
      return await deviceInfoGate.future;
    });
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
            pathProviderChannel, (call) async => '/tmp');
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(deviceInfoChannel, null);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(pathProviderChannel, null);
  });

  testWidgets(
    '[LOCAL-773] disposing Home before its async load finishes throws no '
    'setState-after-dispose error and never reaches _initializeMap',
    (tester) async {
      // Capture everything routed through FlutterError.onError during the
      // window, so the setState-after-dispose error (base) is observable and a
      // clean absence (branch) is assertable. We deliberately do NOT rethrow,
      // so the harness does not fail before our explicit expectations run.
      final flutterErrors = <FlutterErrorDetails>[];
      final previousOnError = FlutterError.onError;
      FlutterError.onError = (details) => flutterErrors.add(details);
      addTearDown(() => FlutterError.onError = previousOnError);

      // 1. Build Home. initState fires _loadAppMode(); it runs until
      //    `await DeviceService.getUserId()`, which blocks on the held
      //    device_info channel reply.
      await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
      await tester.pump();

      // Home is in its loading state — proof it built and began loading.
      expect(find.byType(CircularProgressIndicator), findsOneWidget,
          reason: 'Home should be loading while _loadAppMode is suspended.');

      // 2. Dispose Home BEFORE the async load completes — exactly as the root
      //    does on a fresh install when it swaps in OnboardingScreen.
      await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: Text('onboarding'))),
      );
      expect(find.byType(HomeScreen), findsNothing);

      // 3. Release the device_info reply, then let the real channel replies and
      //    the resumed _loadAppMode continuation run to completion.
      deviceInfoGate.complete(<String, dynamic>{
        'brand': 'test',
        'model': 'test',
        'id': 'test-id',
      });
      await tester.runAsync(() async {
        await Future<void>.delayed(const Duration(milliseconds: 300));
      });
      await tester.pump();

      // Restore the handler BEFORE any expect(), so the harness sees a clean
      // FlutterError.onError and we do not trip its end-of-test assertion.
      FlutterError.onError = previousOnError;

      // 4a. No setState-after-dispose crash. RED on base: _loadAppMode's
      //     unguarded setState throws here (debug: "setState() called after
      //     dispose()"; release: "Null check operator used on a null value").
      final setStateAfterDispose = flutterErrors.where((d) {
        final s = d.exceptionAsString();
        return s.contains('setState() called after dispose()') ||
            s.contains('Null check operator used on a null value');
      }).toList();
      expect(
        setStateAfterDispose,
        isEmpty,
        reason:
            'Disposing Home mid-load must not throw a setState-after-dispose '
            'error from _loadAppMode (LOCAL-773 mounted guard). Captured: '
            '${setStateAfterDispose.map((d) => d.exceptionAsString()).toList()}',
      );

      // 4b. The aborted load never reached _initializeMap — its first line logs
      //     this marker to the persisted debug_logs, so the marker is absent.
      final prefs = await SharedPreferences.getInstance();
      final logs = prefs.getStringList('debug_logs') ?? const <String>[];
      expect(
        logs.any((l) => l.contains('HOME: Starting map initialization')),
        isFalse,
        reason:
            '_initializeMap must not run after Home is disposed mid-load; the '
            'mounted guard in _loadAppMode returns before calling it.',
      );
    },
  );
}
