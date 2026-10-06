// [LOCAL-598 D8] Unit tests for the refusal -> UI action mapping.
//
// The subscription-levels refusals (subscription_levels.py) come back as
// 429/401 with an error_code; refusalActionFor maps each to the button the UI
// should show. These tests pin that mapping so a future server code change (or
// a typo) is caught here, not in the field.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/tour_error_resolver.dart';

void main() {
  group('refusalActionFor — subscription error_codes', () {
    test('out-of-allowance codes -> Buy a pack', () {
      for (final code in [
        'plan_limit_daily',
        'plan_limit_monthly',
        'pack_exhausted',
        'level_cannot_generate',
      ]) {
        expect(refusalActionFor({'error_code': code}), TourRefusalAction.buyPack,
            reason: code);
      }
    });

    test('request-shape codes -> Edit request', () {
      for (final code in ['stops_over_plan', 'by_reference_unavailable']) {
        expect(refusalActionFor({'error_code': code}),
            TourRefusalAction.editRequest,
            reason: code);
      }
    });

    test('plan-state codes -> Your plan', () {
      for (final code in ['renewal_due', 'user_id_required']) {
        expect(refusalActionFor({'error_code': code}),
            TourRefusalAction.yourPlan,
            reason: code);
      }
    });

    test('unknown or absent error_code -> none', () {
      expect(refusalActionFor({'error_code': 'something_new'}),
          TourRefusalAction.none);
      expect(refusalActionFor({}), TourRefusalAction.none);
      expect(refusalActionFor({'error_code': ''}), TourRefusalAction.none);
    });

    test('generation-failure codes are NOT subscription actions', () {
      // These are handled by the suggestion/canRetry path, not a plan button.
      expect(refusalActionFor({'error_code': 'venue_no_verifiable_content'}),
          TourRefusalAction.none);
      expect(refusalActionFor({'error_code': 'generation_failed'}),
          TourRefusalAction.none);
    });
  });

  group('refusalActionLabel', () {
    test('each action has a non-empty label except none', () {
      expect(refusalActionLabel(TourRefusalAction.buyPack), 'Buy a pack');
      expect(refusalActionLabel(TourRefusalAction.yourPlan), 'Your plan');
      expect(refusalActionLabel(TourRefusalAction.editRequest), 'Edit request');
      expect(refusalActionLabel(TourRefusalAction.joinQueue), 'Join the queue');
      expect(refusalActionLabel(TourRefusalAction.none), '');
    });
  });

  group('resolveTourError carries the server message for a refusal', () {
    test('message + suggestion survive for a plan refusal', () {
      final r = resolveTourError({
        'error_code': 'pack_exhausted',
        'message': 'Your pack is used up. Buy another to make more tours.',
        'suggestion': {
          'label': 'Buy a \$10 pack',
          'request': 'buy_l3',
        },
      });
      expect(r.message, 'Your pack is used up. Buy another to make more tours.');
      expect(r.isServerMessage, isTrue);
      // The resolver never shows the generic string when the server spoke.
      expect(r.message, isNot(kGenericTourError));
      // And the action is the Buy-a-pack button.
      expect(
          refusalActionFor({'error_code': 'pack_exhausted'}),
          TourRefusalAction.buyPack);
    });
  });
}
