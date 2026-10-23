import 'package:flutter_test/flutter_test.dart';

import 'package:audio_tour_app_dev/services/app_sync_coordinator.dart';
import 'package:audio_tour_app_dev/services/community_tours_sync.dart';
import 'package:audio_tour_app_dev/services/foreground_community_messages.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// LOCAL-750 (C3) — the 5-minute foreground sync must:
///   * run ONLY while the app is in the foreground, and
///   * never overlap a sync already running.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('foreground tick gating (pure)', () {
    test('runs a sync only in the foreground', () {
      expect(AppSyncCoordinator.shouldRunForegroundTick(isForeground: true),
          isTrue);
      expect(AppSyncCoordinator.shouldRunForegroundTick(isForeground: false),
          isFalse);
    });

    test('the interval is 5 minutes', () {
      expect(AppSyncCoordinator.foregroundSyncInterval,
          const Duration(minutes: 5));
    });
  });

  group('foreground flag', () {
    test('setForeground flips the shared flag the tick reads', () {
      ForegroundCommunityMessages.instance.setForeground(false);
      expect(ForegroundCommunityMessages.instance.isForeground, isFalse);
      expect(
          AppSyncCoordinator.shouldRunForegroundTick(
              isForeground:
                  ForegroundCommunityMessages.instance.isForeground),
          isFalse);

      ForegroundCommunityMessages.instance.setForeground(true);
      expect(ForegroundCommunityMessages.instance.isForeground, isTrue);
    });
  });

  group('no overlap: CommunityToursSync.run self-guards', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({'user_id': 'local750_overlap'});
      // Make a run take a beat so a second call lands while it is in flight.
      CommunityToursSync.fetchNewTours = (userId, {since}) async {
        await Future<void>.delayed(const Duration(milliseconds: 40));
        return null; // no new tours → run completes cleanly
      };
    });

    test('a second run() while one is in flight is a no-op', () async {
      final first = CommunityToursSync.instance.run();
      // Fire a second run immediately — it must short-circuit to noop.
      final second = await CommunityToursSync.instance.run();
      expect(identical(second, CommunityToursSyncResult.noop), isTrue,
          reason: 'overlapping run must return the noop result');
      await first; // let the first finish so _running resets
    });
  });
}
