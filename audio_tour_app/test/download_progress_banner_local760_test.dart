// test/download_progress_banner_local760_test.dart — LOCAL-760 (build item 1).
//
// Michael (iPhone, 2026-10-24): "the status message appeared and disappeared and
// then appeared, etc. The status message is good, but it should not disappear."
// The old code showed each progress tick as a fresh SnackBar (clearSnackBars +
// showSnackBar), so it flashed. The replacement is ONE persistent widget driven
// by a DownloadProgressController: it stays mounted across every stop/byte tick,
// shows the shared downloadingAudioLabel line and a Cancel, and is dismissed only
// on success/cancel/failure.
//
// RED on 127cd384: lib/widgets/download_progress_banner.dart does not exist yet.
//
// Run: flutter test test/download_progress_banner_local760_test.dart

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/remote_audio_fetcher.dart';
import 'package:audio_tour_app_dev/widgets/download_progress_banner.dart';

void main() {
  testWidgets('one persistent banner across many progress ticks (no flashing)',
      (tester) async {
    final controller = DownloadProgressController();
    var cancelled = false;

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: DownloadProgressBanner(
          controller: controller,
          onCancel: () => cancelled = true,
        ),
      ),
    ));

    // Idle → nothing shown.
    expect(find.byType(LinearProgressIndicator), findsNothing);

    // Start → the banner appears exactly once.
    controller.start();
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);

    // Many ticks across two stops — the SAME widget stays; it must never be a
    // SnackBar (the flashing mechanism) and there is still exactly one bar.
    for (var i = 1; i <= 20; i++) {
      controller.update(RemoteAudioProgress(
        stopNumber: i <= 10 ? 1 : 2,
        receivedBytes: i * 1024 * 1024,
        totalBytes: 40 * 1024 * 1024,
      ));
      await tester.pump();
      expect(find.byType(LinearProgressIndicator), findsOneWidget);
      expect(find.byType(SnackBar), findsNothing,
          reason: 'progress must not be a flashing SnackBar');
    }

    // The shared label text is shown and names the current stop.
    expect(find.textContaining('Downloading audio'), findsOneWidget);
    expect(find.textContaining('stop 2 of 2'), findsOneWidget);

    // Cancel is offered and wired.
    await tester.tap(find.text('Cancel'));
    await tester.pump();
    expect(cancelled, isTrue);
  });

  testWidgets('banner disappears on finish()', (tester) async {
    final controller = DownloadProgressController();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: DownloadProgressBanner(controller: controller, onCancel: () {}),
      ),
    ));
    controller.start();
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);

    controller.finish();
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsNothing);
  });

  test('controller exposes the shared downloadingAudioLabel line', () {
    final controller = DownloadProgressController();
    controller.start();
    controller.update(const RemoteAudioProgress(
        stopNumber: 2, receivedBytes: 45 * 1024 * 1024, totalBytes: 81 * 1024 * 1024));
    // maxStop tracks the highest stop seen so the "of N" is monotonic.
    expect(controller.label, contains('Downloading audio'));
    expect(controller.label, contains('stop 2 of 2'));
    expect(controller.visible, isTrue);
    controller.finish();
    expect(controller.visible, isFalse);
  });
}
