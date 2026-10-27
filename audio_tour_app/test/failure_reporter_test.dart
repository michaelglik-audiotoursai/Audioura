// test/failure_reporter_test.dart — LOCAL-785 (RED first).
//
// The app's FailureReporter must:
//   * send a report in the background (via the sendOverride test seam here),
//   * QUEUE a report offline when the send fails, up to 50 (FIFO — oldest
//     dropped), and FLUSH the queue when connectivity returns,
//   * surface a download/save failure as a report (surface 'download').
//
// These assert the queue/flush contract and the download-failure report shape
// without any real network.
//
// Run: flutter test test/failure_reporter_test.dart

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/failure_reporter.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final reporter = FailureReporter.instance;

  setUp(() async {
    SharedPreferences.setMockInitialValues({'user_id': 'USER-TEST'});
    reporter.resetForTest();
  });

  group('LOCAL-785 FailureReporter', () {
    test('a successful send is NOT queued', () async {
      final sent = <Map<String, dynamic>>[];
      reporter.sendOverride = (body) async {
        sent.add(body);
        return true;
      };
      await reporter.reportAndWaitForTest(
        surface: 'download',
        errorCode: 'tour_download_save_failed',
        message: 'boom',
        tourId: '445',
      );
      expect(sent, hasLength(1));
      expect(sent.first['surface'], 'download');
      expect(sent.first['error_code'], 'tour_download_save_failed');
      expect(sent.first['tour_id'], '445');
      expect(sent.first['platform'], isNotNull);
      expect(await reporter.queueLength(), 0);
    });

    test('an offline send is queued, then flushed when back online', () async {
      // First: offline — every send fails, so the report is queued.
      reporter.sendOverride = (body) async => false;
      await reporter.reportAndWaitForTest(
        surface: 'download', message: 'offline one', tourId: '446');
      expect(await reporter.queueLength(), 1);

      // Now back online — flush drains the queue.
      final sent = <Map<String, dynamic>>[];
      reporter.sendOverride = (body) async {
        sent.add(body);
        return true;
      };
      await reporter.flush();
      expect(sent, hasLength(1));
      expect(sent.first['message'], 'offline one');
      expect(await reporter.queueLength(), 0);
    });

    test('the offline queue is capped at 50 (oldest dropped)', () async {
      reporter.sendOverride = (body) async => false; // always offline
      for (var i = 0; i < 60; i++) {
        await reporter.reportAndWaitForTest(
            surface: 'play', message: 'msg $i');
      }
      expect(await reporter.queueLength(), FailureReporter.maxQueue);
    });

    test('a download failure produces a report with surface "download"',
        () async {
      final sent = <Map<String, dynamic>>[];
      reporter.sendOverride = (body) async {
        sent.add(body);
        return true;
      };
      // This is exactly what home_screen's batch-download catch calls.
      await reporter.reportAndWaitForTest(
        surface: 'download',
        errorCode: 'tour_download_save_failed',
        exceptionType: 'Exception',
        message: 'download/save/resolve failed for "Boston Common": 409',
        tourId: '370',
      );
      expect(sent, hasLength(1));
      expect(sent.first['surface'], 'download');
      expect(sent.first['error_code'], 'tour_download_save_failed');
    });

    test('uncaught errors are throttled to 5 per minute', () async {
      final sent = <Map<String, dynamic>>[];
      reporter.sendOverride = (body) async {
        sent.add(body);
        return true;
      };
      for (var i = 0; i < 8; i++) {
        reporter.reportUncaught(StateError('loop $i'), StackTrace.current);
      }
      // Let the fire-and-forget sends settle.
      await Future<void>.delayed(const Duration(milliseconds: 50));
      expect(sent.length, lessThanOrEqualTo(5));
    });
  });
}
