import 'package:flutter_test/flutter_test.dart';
import '../lib/services/tour_share_service.dart';

/// [LOCAL-579] Error-handling tests for TourShareService that need no network.
///
/// The one branch fully exercisable without a live server is the local guard:
/// POST /tour/share keys on the numeric audio_tours.id, so a tour whose only
/// id is a non-numeric job-id string (freshly generated / some translations)
/// must be rejected locally with a clear, non-crashing message rather than a
/// doomed round trip. The network branches (404/5xx/offline) are proven by the
/// scripted LOCAL round trip in SUBMISSION_LOCAL-579.md.
///
/// These tests can FAIL — make share() return success for a null id and the
/// expectations below go red.
void main() {
  group('TourShareService rejects un-shareable ids locally', () {
    test('null id → failure with a message, never throws', () async {
      final r = await TourShareService.share(null);
      expect(r.ok, isFalse);
      expect(r.code, isNull);
      expect(r.errorMessage, isNotNull);
      expect(r.errorMessage, contains('tour ID'));
    });

    test('non-numeric job-id string → failure, never throws', () async {
      final r = await TourShareService.share('job_abc123-def');
      expect(r.ok, isFalse);
      expect(r.errorMessage, isNotNull);
    });

    test('empty string → failure', () async {
      final r = await TourShareService.share('');
      expect(r.ok, isFalse);
    });
  });

  group('ShareResult factory invariants', () {
    test('success exposes code and ok==true', () {
      final r = ShareResult.success('FFush25U', 'https://audioura.io/tour/FFush25U');
      expect(r.ok, isTrue);
      expect(r.code, 'FFush25U');
      expect(r.shareUrl, 'https://audioura.io/tour/FFush25U');
      expect(r.errorMessage, isNull);
    });

    test('failure exposes message and ok==false', () {
      final r = ShareResult.failure('Tour not found.');
      expect(r.ok, isFalse);
      expect(r.code, isNull);
      expect(r.errorMessage, 'Tour not found.');
    });
  });
}
