// [LOCAL-693 / D660 + LOCAL-693B / D660 addendum] Delete-confirmation copy —
// unit tests.
//
// Proves the ticket's rule "the delete-confirmation warning is shown for PAID
// tours only", with the exact D660-addendum copy:
//   paid  → title "Delete paid tour?", body "Are you sure you want to delete
//           this paid tour? Downloading it again will require another
//           purchase.", buttons "Cancel" (default) + "Delete".
//   free  → plain "Delete Tour", no warning sentence.
// Pure model (DeleteTourPrompt) — no widget tree, no server.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/widgets/delete_tour_prompt.dart';

void main() {
  group('DeleteTourPrompt.decide (D660 addendum)', () {
    test('a PAID tour gets the exact addendum title, body and buttons', () {
      final p = DeleteTourPrompt.decide(tourTitle: 'Old Nice', isPaid: true);
      expect(p.isPaidWarning, isTrue);
      // Exact title.
      expect(p.title, 'Delete paid tour?');
      // Exact body — one calm sentence, no "lose it", no phone-change alarm.
      expect(p.body,
          'Are you sure you want to delete this paid tour? Downloading it '
          'again will require another purchase.');
      // Buttons: Cancel (default) + Delete.
      expect(p.cancelLabel, 'Cancel');
      expect(p.confirmLabel, 'Delete');
      // The withdrawn LEAD wording must be gone.
      expect(p.body.contains('lose it'), isFalse);
      expect(p.body.contains('changing phones'), isFalse);
      expect(p.title.contains('lose it'), isFalse);
    });

    test('a FREE tour gets the plain confirmation and skips the warning', () {
      final p = DeleteTourPrompt.decide(tourTitle: 'Free Walk', isPaid: false);
      expect(p.isPaidWarning, isFalse);
      expect(p.title, 'Delete Tour');
      expect(p.body, contains('Free Walk'));
      // No paid-tour language anywhere in a free prompt.
      expect(p.body.contains('another purchase'), isFalse);
      expect(p.body.contains('paid tour'), isFalse);
      expect(p.cancelLabel, 'Cancel');
      expect(p.confirmLabel, 'Delete');
    });
  });

  group('DeleteTourPrompt.isPaidTour', () {
    test('is_paid flag true → paid', () {
      expect(DeleteTourPrompt.isPaidTour({'is_paid': true}), isTrue);
    });
    test('price_tier > 0 → paid', () {
      expect(DeleteTourPrompt.isPaidTour({'price_tier': 3}), isTrue);
    });
    test('price_tier 0 or null → free', () {
      expect(DeleteTourPrompt.isPaidTour({'price_tier': 0}), isFalse);
      expect(DeleteTourPrompt.isPaidTour({'price_tier': null}), isFalse);
      expect(DeleteTourPrompt.isPaidTour({}), isFalse);
    });
    test('is_paid false + no tier → free', () {
      expect(DeleteTourPrompt.isPaidTour({'is_paid': false}), isFalse);
    });
  });
}
