// test/local745_error_message_test.dart — LOCAL-745 requirement 4 (RED first).
//
// Michael saw "Save failed: Exception: Save Failed" — the generic fallback —
// when the server actually returned a structured body with a `message` (e.g. a
// 404 TOUR_NOT_FOUND, or the 403 organiser-only refusal). The edit service read
// only body['error'] (which the server does not send) and fell back to the
// generic string, hiding the real reason.
//
// tourEditErrorMessage(body) is the pure extractor the service uses to pick the
// human message out of a server error body, preferring 'message' then 'error',
// with a last-resort fallback.
//
// Run: flutter test test/local745_error_message_test.dart

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/tour_editing_service.dart';

void main() {
  group('LOCAL-745 tourEditErrorMessage — surface the server message', () {
    test('prefers the server message field (404 TOUR_NOT_FOUND)', () {
      final body = {
        'status': 'error',
        'error_code': 'TOUR_NOT_FOUND',
        'message': "Tour with ID '716' could not be found for bulk save operation",
      };
      expect(
        tourEditErrorMessage(body),
        "Tour with ID '716' could not be found for bulk save operation",
      );
    });

    test('surfaces the organiser-only 403 message', () {
      final body = {
        'status': 'error',
        'error_code': 'NOT_COMMUNITY_OWNER',
        'message': 'Only the community organiser can edit this tour.',
      };
      expect(
        tourEditErrorMessage(body),
        'Only the community organiser can edit this tour.',
      );
    });

    test('falls back to error when message is absent', () {
      final body = {'error': 'legacy error text'};
      expect(tourEditErrorMessage(body), 'legacy error text');
    });

    test('last-resort generic only when nothing usable is present', () {
      expect(tourEditErrorMessage(const {}), 'Save failed');
    });
  });
}
