// [LOCAL-781] A save/resolve failure after a successful download must REACH the
// user (naming the tour), and the downloaded ZIP must be kept so a retry does
// not re-download the whole tour.
//
// Evidence (Michael, TestFlight 79, 2026-10-27): Home → search → Download
// trinity 445 / BPL 446. map-delivery served the ZIPs (200), then
// /tour/<id>/resolve answered 404 (the cloud looked for the ZIP on local disk;
// it lives in R2). The app "silently failed" — the rich, tour-naming message
// TourDownloadService built was collapsed by home_screen's catch to the generic
// "Error downloading tour" and never named the tour, and the ZIP was discarded
// so every retry re-downloaded.
//
// These tests pin the PURE pieces of the fix (no network, no emulator):
//   * resolveFailureMessage NAMES the tour and tells the user the download is
//     kept for retry;
//   * the ZIP retry cache keeps the bytes across a failed save and frees them on
//     a successful one.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/tour_download_service.dart';

void main() {
  group('LOCAL-781 — resolve-failure message names the tour', () {
    test('names the tour and keeps-for-retry wording, with the server reason',
        () {
      final msg = TourDownloadService.resolveFailureMessage(
          'Trinity Church', 445, 404, 'zip_filename column points to '
              'non-existent file');
      expect(msg, contains('Trinity Church'));
      expect(msg, contains('445'));
      expect(msg, contains('zip_filename column points to non-existent file'));
      // The listener is told the download is kept so a retry won't re-download.
      expect(msg.toLowerCase(), contains('try again'));
      expect(msg.toLowerCase(), contains('kept'));
    });

    test('falls back to the tour id when no name is known', () {
      final msg = TourDownloadService.resolveFailureMessage(null, 446, 500, null);
      expect(msg, contains('446'));
      expect(msg, contains('500')); // the status code is surfaced
      expect(msg, isNot(contains('Downloaded Tour'))); // never the old placeholder
    });

    test('blank name is treated as no name', () {
      final msg = TourDownloadService.resolveFailureMessage('   ', 1, 404, null);
      expect(msg, contains('Tour (ID: 1)'));
    });
  });

  group('LOCAL-781 — ZIP retry cache keeps bytes across a failed save', () {
    const tourId = 445;
    final zip = List<int>.generate(1024, (i) => i % 256);

    setUp(() => TourDownloadService.clearCachedZip(tourId));

    test('a kept ZIP is available for the same tour id, then can be reused', () {
      expect(TourDownloadService.hasCachedZip(tourId), isFalse);

      TourDownloadService.cacheZipForRetry(tourId, zip);
      expect(TourDownloadService.hasCachedZip(tourId), isTrue);

      // Peek does NOT consume — a retry that also fails keeps the bytes.
      final again = TourDownloadService.peekCachedZip(tourId);
      expect(again, isNotNull);
      expect(again!.length, zip.length);
      expect(TourDownloadService.hasCachedZip(tourId), isTrue);
    });

    test('a successful save frees the kept ZIP', () {
      TourDownloadService.cacheZipForRetry(tourId, zip);
      expect(TourDownloadService.hasCachedZip(tourId), isTrue);

      TourDownloadService.clearCachedZip(tourId);
      expect(TourDownloadService.hasCachedZip(tourId), isFalse);
      expect(TourDownloadService.peekCachedZip(tourId), isNull);
    });

    test('empty or null bytes are not cached', () {
      TourDownloadService.cacheZipForRetry(tourId, <int>[]);
      expect(TourDownloadService.hasCachedZip(tourId), isFalse);
      TourDownloadService.cacheZipForRetry(tourId, null);
      expect(TourDownloadService.hasCachedZip(tourId), isFalse);
    });
  });
}
