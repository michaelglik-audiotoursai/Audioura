import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/screens/edit_stop_screen.dart';
import 'package:audio_tour_app_dev/utils/tour_path_healer.dart';

/// LOCAL-478 — Original audio failed silently in the stop editor.
///
/// Two defects, two guards:
///
///  1. `_loadSelectedAudio` returned silently when the audio WebView
///     controller was null (`00:00 -- 00:00`, no log, no UI, no retry). The
///     null-controller path is now expressed by [planAudioLoad], which MUST
///     map "controller not ready" to [AudioLoadPlan.deferAndLog] — a logged,
///     retryable outcome — never a silent no-op. If someone reintroduces the
///     bare `return` (deleting the plan / defer branch), these tests go red.
///     (AC #4)
///
///  2. Stored tour paths carry a stale iOS container UUID after a reinstall /
///     TestFlight update. [healTourPath] re-anchors them to the current
///     Documents directory — the SAME rule the Listen screen applies to
///     saved_tours. (AC #2)
void main() {
  group('LOCAL-478 planAudioLoad — null-controller path', () {
    test('controller NOT ready defers and logs — never a silent drop (AC #4)', () {
      final plan = planAudioLoad(controllerReady: false);

      // The whole point: a not-ready controller must produce a *visible*,
      // retryable outcome. This is what the original silent `return` failed to
      // do. Deleting the defer branch (restoring the silent return) breaks this.
      expect(plan, equals(AudioLoadPlan.deferAndLog));
      expect(plan, isNot(equals(AudioLoadPlan.proceed)));
    });

    test('controller ready proceeds to load', () {
      expect(planAudioLoad(controllerReady: true), equals(AudioLoadPlan.proceed));
    });

    test('the two outcomes are distinct — defer is not a no-op alias', () {
      expect(AudioLoadPlan.deferAndLog, isNot(equals(AudioLoadPlan.proceed)));
      // Both legitimate outcomes exist; neither is a silent bail.
      expect(AudioLoadPlan.values.length, equals(2));
    });
  });

  group('LOCAL-478 healTourPath — stale container healing (AC #2)', () {
    const docsDir =
        '/var/mobile/Containers/Data/Application/NEW-UUID/Documents';

    test('re-anchors a stale container path onto the current Documents dir', () {
      const stale =
          '/var/mobile/Containers/Data/Application/OLD-UUID/Documents/tours/paris_42/audio_1.mp3';

      final healed = healTourPath(stale, docsDir);

      expect(healed, equals('$docsDir/tours/paris_42/audio_1.mp3'));
    });

    test('leaves a path already rooted at the current Documents dir unchanged', () {
      const current = '$docsDir/tours/paris_42/audio_1.mp3';

      expect(healTourPath(current, docsDir), equals(current));
    });

    test('leaves a path without the /tours/ marker unchanged', () {
      const other = '/somewhere/else/file.mp3';

      expect(healTourPath(other, docsDir), equals(other));
    });

    test('healed path preserves the full /tours/... suffix', () {
      const stale =
          '/old/root/tours/deep/nested/stop_3/audio_3.mp3';

      final healed = healTourPath(stale, docsDir);

      expect(healed, endsWith('/tours/deep/nested/stop_3/audio_3.mp3'));
      expect(healed, startsWith(docsDir));
    });
  });
}
