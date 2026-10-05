// [LOCAL-581] Unit tests for the pure tour-error resolver.
//
// These cover the decision logic that fixes Michael's two defects:
//   • the server's actionable message must be shown (not the generic string);
//   • the generic fallback only when the server sent nothing;
//   • the LOCAL-580 suggestion {label, request, tour_type} is parsed safely;
//   • error_code venue_no_verifiable_content is NOT plain-retryable.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/tour_error_resolver.dart';

void main() {
  group('resolveTourError — message precedence', () {
    test('shows the server error text verbatim (Michael defect #1)', () {
      const griffin =
          'We could not find enough verified material about "Griffin Museum '
          'of Photography" to build a tour. Try a broader request — for '
          'example a walking tour of the surrounding neighbourhood.';
      final r = resolveTourError({
        'status': 'error',
        'error': griffin,
      });
      expect(r.message, griffin);
      expect(r.isServerMessage, isTrue);
    });

    test('falls back to the generic text ONLY when server sent nothing', () {
      final r = resolveTourError({'status': 'failed'});
      expect(r.message, kGenericTourError);
      expect(r.isServerMessage, isFalse);
    });

    test('ignores a blank error string and falls through to message', () {
      final r = resolveTourError({
        'error': '   ',
        'message': 'Server-side user message',
      });
      expect(r.message, 'Server-side user message');
      expect(r.isServerMessage, isTrue);
    });

    test('error wins over message/user_message when both present', () {
      final r = resolveTourError({
        'error': 'specific error',
        'message': 'less specific',
        'user_message': 'least specific',
      });
      expect(r.message, 'specific error');
    });

    test('LOCAL-580 top-level message used when no error field', () {
      final r = resolveTourError({'message': 'LOCAL-580 message'});
      expect(r.message, 'LOCAL-580 message');
      expect(r.isServerMessage, isTrue);
    });

    test('legacy user_error.message honoured', () {
      final r = resolveTourError({
        'user_error': {'message': 'legacy structured message'},
      });
      expect(r.message, 'legacy structured message');
    });
  });

  group('resolveTourError — suggestion {label,request,tour_type}', () {
    test('parses a full LOCAL-580 suggestion', () {
      final r = resolveTourError({
        'error': 'no verified material',
        'suggestion': {
          'label': 'Walking tour of the neighbourhood',
          'request': 'walking tour of Winchester, MA',
          'tour_type': 'walking',
        },
      });
      expect(r.suggestion, isNotNull);
      expect(r.suggestion!.label, 'Walking tour of the neighbourhood');
      expect(r.suggestion!.request, 'walking tour of Winchester, MA');
      expect(r.suggestion!.tourType, 'walking');
    });

    test('no suggestion field → null (button hidden, no crash)', () {
      final r = resolveTourError({'error': 'x'});
      expect(r.suggestion, isNull);
    });

    test('malformed suggestion (missing request) → null', () {
      final r = resolveTourError({
        'error': 'x',
        'suggestion': {'label': 'Only a label'},
      });
      expect(r.suggestion, isNull);
    });

    test('suggestion without label → sensible default label', () {
      final r = resolveTourError({
        'error': 'x',
        'suggestion': {'request': 'a broader walking tour'},
      });
      expect(r.suggestion, isNotNull);
      expect(r.suggestion!.label, isNotEmpty);
      expect(r.suggestion!.request, 'a broader walking tour');
      expect(r.suggestion!.tourType, isNull);
    });

    test('suggestion that is not a map → null', () {
      final r = resolveTourError({'error': 'x', 'suggestion': 'nope'});
      expect(r.suggestion, isNull);
    });
  });

  group('resolveTourError — retryability from error_code', () {
    test('venue_no_verifiable_content is NOT plain-retryable (Edit request)',
        () {
      final r = resolveTourError({
        'error': 'no verified material',
        'error_code': 'venue_no_verifiable_content',
      });
      expect(r.canRetry, isFalse);
      expect(r.errorCode, 'venue_no_verifiable_content');
    });

    test('unknown/absent error_code is retryable', () {
      expect(resolveTourError({'error': 'transient'}).canRetry, isTrue);
      expect(
        resolveTourError({'error': 'x', 'error_code': 'something_else'})
            .canRetry,
        isTrue,
      );
    });
  });

  group('resolveTourError — legacy suggestion lines', () {
    test('collects user_error.suggestions list', () {
      final r = resolveTourError({
        'user_error': {
          'message': 'm',
          'suggestions': ['Try a larger city', 'Check spelling'],
        },
      });
      expect(r.suggestions, ['Try a larger city', 'Check spelling']);
    });
  });
}
