// [LOCAL-759 A5 / A6] The named stop-failure message must REACH the UI.
//
// On d816a251, _fetchRemoteAudioDevice threw "Audio for stop N could not be
// downloaded." but downloadAndSave caught everything and returned a bare
// TourDownloadStatus.failed with NO message — so the community page could only
// show the generic "Download failed. Please try again." These tests pin:
//   * TourDownloadResult carries an `errorMessage` so the community page can
//     show the named message instead of the generic one (A5);
//   * the web path refuses an episode over 50 MB with a clear message (A6);
//   * the pure helper that chooses the SnackBar text prefers the named message.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/tour_download_service.dart';
import 'package:audio_tour_app_dev/services/remote_audio_fetcher.dart';

void main() {
  group('A5 — named message reaches the result/UI', () {
    test('TourDownloadResult can carry an errorMessage', () {
      const r = TourDownloadResult(
        TourDownloadStatus.failed,
        errorMessage: "Audio for stop 2 'The Accusations Begin' could not be "
            "downloaded.",
      );
      expect(r.status, TourDownloadStatus.failed);
      expect(r.errorMessage,
          contains("Audio for stop 2 'The Accusations Begin'"));
    });

    test('download failure SnackBar text prefers the named message', () {
      // The pure chooser the community page uses: a named message wins over the
      // generic fallback; a null/blank message falls back to the generic text.
      expect(
        TourDownloadService.failureMessage(
            "Audio for stop 2 'The Accusations Begin' could not be downloaded."),
        "Audio for stop 2 'The Accusations Begin' could not be downloaded.",
      );
      expect(TourDownloadService.failureMessage(null),
          'Download failed. Please try again.');
      expect(TourDownloadService.failureMessage('   '),
          'Download failed. Please try again.');
    });

    test('remoteAudioStopFailureMessage names the stop', () {
      expect(remoteAudioStopFailureMessage(2, 'The Accusations Begin'),
          "Audio for stop 2 'The Accusations Begin' could not be downloaded.");
      expect(remoteAudioStopFailureMessage(3, ''),
          'Audio for stop 3 could not be downloaded.');
    });
  });

  group('A6 — web refuses an episode over 50 MB', () {
    test('webSizeLimitMessage names the stop and the limit', () {
      final msg = TourDownloadService.webSizeLimitMessage(2, 'Big Episode');
      expect(msg, contains('stop 2'));
      expect(msg, contains('Big Episode'));
      expect(msg.toLowerCase(), contains('50'));
    });

    test('exceedsWebLimit is true above 50 MB, false at/below', () {
      const limit = TourDownloadService.webMaxBytesPerStop;
      expect(limit, 50 * 1024 * 1024);
      expect(TourDownloadService.exceedsWebLimit(limit + 1), isTrue);
      expect(TourDownloadService.exceedsWebLimit(limit), isFalse);
      expect(TourDownloadService.exceedsWebLimit(0), isFalse);
    });
  });

  group('A3 — progress label', () {
    test('shows stop X of Y and a / b MB', () {
      expect(
        downloadingAudioLabel(
          stopIndex: 2,
          stopCount: 3,
          receivedBytes: 45 * 1024 * 1024,
          totalBytes: 81 * 1024 * 1024,
        ),
        'Downloading audio — stop 2 of 3 · 45 / 81 MB',
      );
    });
    test('drops the total when unknown', () {
      expect(
        downloadingAudioLabel(
          stopIndex: 1,
          stopCount: 1,
          receivedBytes: 3 * 1024 * 1024,
        ),
        'Downloading audio — stop 1 of 1 · 3.0 MB',
      );
    });
  });

  group('A4 — mobile-data size prompt', () {
    test('names the tour size and asks for Wi-Fi', () {
      final msg =
          TourDownloadService.mobileDataSizePrompt(285 * 1024 * 1024);
      expect(msg, contains('285 MB'));
      expect(msg.toLowerCase(), contains('wi-fi'));
      expect(msg.toLowerCase(), contains('mobile data'));
    });
    test('drops the size clause when unknown', () {
      final msg = TourDownloadService.mobileDataSizePrompt(0);
      expect(msg, isNot(contains('MB')));
      expect(msg.toLowerCase(), contains('wi-fi'));
    });
  });
}
