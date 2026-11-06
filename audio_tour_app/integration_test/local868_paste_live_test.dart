// LOCAL-868 — LIVE simulator/emulator run of "Paste a list of places" and
// Share → Audioura. Talks to the task's OWN stack (docker-compose.local868-proof.yml,
// ports 15000/15002) — never the shared :5000/:5002 containers.
//
// The shell drives and photographs (the LOCAL-841 pattern): this test renders
// the REAL screens, prints `LOCAL868SHOT <NAME>_BEGIN` and holds so the host can
// run `xcrun simctl io <sim> screenshot` / `adb exec-out screencap -p`.
//
//   LOCAL868_MODE=paste   Create Tour -> Paste a list -> Preview -> Use ->
//                         (LOCAL868_GENERATE=true) Generate Now -> wait.
//   LOCAL868_MODE=share   MainScreen + the real share plumbing; waits for the
//                         shell to deliver text (adb ACTION_SEND intent on
//                         Android, `simctl openurl audioura://paste?...` on iOS)
//                         and photographs the pre-filled paste box.
//
// Run:
//   flutter test integration_test/local868_paste_live_test.dart -d <device-id> \
//     --dart-define=DEBUG_SERVER_IP=127.0.0.1 --dart-define=DEBUG_PORT_OFFSET=10000 \
//     --dart-define=LOCAL868_MODE=paste --dart-define=LOCAL868_GENERATE=true
//   (Android emulator: `adb reverse tcp:15000 tcp:15000` etc. first, so the
//   emulator's 127.0.0.1:150xx reaches the host stack.)
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/main_screen.dart';
import 'package:audio_tour_app_dev/screens/paste_list_screen.dart';
import 'package:audio_tour_app_dev/screens/tour_generator_screen.dart';
import 'package:audio_tour_app_dev/services/deep_link_service.dart';
import 'package:audio_tour_app_dev/services/shared_text_service.dart';

const String _mode = String.fromEnvironment('LOCAL868_MODE', defaultValue: 'paste');
const bool _generate = bool.fromEnvironment('LOCAL868_GENERATE');
const String _michael = 'Cathedral → Post Office → Book Street → '
    'Independence Palace → War Remnants Museum → Opera House/Đồng Khởi → '
    'City Hall & Nguyễn Huệ → Café Apartments 42 → '
    'Bạch Đằng Pier (tour-bus + waterbus) → Thi Bar';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  Future<void> hold(WidgetTester tester, int seconds) async {
    final end = DateTime.now().add(Duration(seconds: seconds));
    while (DateTime.now().isBefore(end)) {
      await tester.pump(const Duration(milliseconds: 100));
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
  }

  Future<void> shot(WidgetTester tester, String name, {int seconds = 8}) async {
    debugPrint('LOCAL868SHOT ${name}_BEGIN');
    await hold(tester, seconds);
    debugPrint('LOCAL868SHOT ${name}_END');
  }

  Future<bool> waitFor(WidgetTester tester, Finder f, int seconds) async {
    final end = DateTime.now().add(Duration(seconds: seconds));
    while (DateTime.now().isBefore(end)) {
      await tester.pump(const Duration(milliseconds: 100));
      if (f.evaluate().isNotEmpty) return true;
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
    return f.evaluate().isNotEmpty;
  }

  setUp(() {
    SharedPreferences.setMockInitialValues({
      'user_id': 'local821-tester',
      'app_mode': 'Tours',
      'narrative_tone': 'general',
      'onboarding_complete': true,
    });
  });

  testWidgets('LOCAL-868 paste a list: preview, review, use, generate',
      (tester) async {
    if (_mode != 'paste') return;
    await tester.pumpWidget(const MaterialApp(home: TourGeneratorScreen()));
    await hold(tester, 3);
    await shot(tester, 'CREATE_TOUR', seconds: 5);

    await tester.tap(find.byKey(const Key('paste_list_entry')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(kPasteTextKey), _michael);
    await tester.enterText(find.byKey(kPasteCityKey), 'Ho Chi Minh City');
    await tester.pump();
    await shot(tester, 'PASTE_BOX', seconds: 8);

    await tester.tap(find.byKey(kPastePreviewButtonKey));
    final got = await waitFor(tester, find.byKey(kPasteUseButtonKey), 120);
    debugPrint('LOCAL868 preview_arrived=$got');
    expect(got, isTrue, reason: 'preview did not arrive');
    await waitFor(tester, find.byKey(const ValueKey('paste-pin-10')), 30);
    final pins = List.generate(10, (i) => i + 1)
        .where((n) => find.byKey(ValueKey('paste-pin-$n')).evaluate().isNotEmpty)
        .length;
    debugPrint('LOCAL868 pins_on_map=$pins');
    await shot(tester, 'PREVIEW_TOP', seconds: 14);
    // Scroll the list so the lower stops are photographed too.
    await tester.drag(find.byType(ReorderableListView), const Offset(0, -700));
    await tester.pump();
    await shot(tester, 'PREVIEW_LIST_LOWER', seconds: 6);
    expect(pins, 10, reason: 'expected 10 numbered pins');

    await tester.tap(find.byKey(kPasteUseButtonKey));
    await tester.pumpAndSettle();
    await shot(tester, 'CREATE_TOUR_WITH_STOPS', seconds: 8);

    if (!_generate) return;
    await tester.ensureVisible(find.text('🎯 Generate Now'));
    await tester.pump(const Duration(milliseconds: 500));
    await shot(tester, 'GENERATE_BUTTON', seconds: 5);
    await tester.tap(find.text('🎯 Generate Now'));
    await tester.pump(const Duration(seconds: 1));
    debugPrint('LOCAL868 generate_tapped');
    final start = DateTime.now();
    var shots = 0;
    final doneFinder = find.text('🎯 Generate Now');
    while (DateTime.now().difference(start) < const Duration(minutes: 16)) {
      await hold(tester, 20);
      shots++;
      debugPrint('LOCAL868SHOT PROGRESS_${shots}_BEGIN');
      await hold(tester, 4);
      debugPrint('LOCAL868SHOT PROGRESS_${shots}_END');
      if (doneFinder.evaluate().isNotEmpty && shots > 1) break;
    }
    debugPrint('LOCAL868 generate_loop_exit after '
        '${DateTime.now().difference(start).inSeconds}s');
    await shot(tester, 'GENERATE_DONE', seconds: 10);
  });

  testWidgets('LOCAL-868 Share -> Audioura opens the pre-filled paste box',
      (tester) async {
    if (_mode != 'share') return;
    await SharedTextService.instance.init();
    await DeepLinkService.instance.init();
    await tester.pumpWidget(const MaterialApp(home: MainScreen()));
    await hold(tester, 4);
    debugPrint('LOCAL868 WAITING_FOR_SHARE');
    final got = await waitFor(tester, find.byKey(kPasteTextKey), 180);
    debugPrint('LOCAL868 share_box_opened=$got');
    expect(got, isTrue, reason: 'shared text did not open the paste box');
    final t = tester.widget<TextField>(find.byKey(kPasteTextKey));
    debugPrint('LOCAL868 box_text=${t.controller!.text}');
    await shot(tester, 'SHARE_BOX', seconds: 12);
    expect(t.controller!.text, contains('Cathedral'));
  });
}
