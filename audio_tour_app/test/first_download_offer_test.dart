// [LOCAL-740 / B5b] Unit tests for the first-download recovery-offer rule.
//
// Proves the ticket's behaviour precisely: show ONCE on the first download;
// if the listener tapped "Later", ask AGAIN after the 3rd download; then NEVER;
// and never on the same day a recovery offer already showed (the first-purchase
// offer coordinates through the same lastOfferDay).

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/first_download_offer.dart';

void main() {
  const today = '2026-10-22';
  const tomorrow = '2026-10-23';

  FirstDownloadOfferState state({
    required int downloadCount,
    int timesShown = 0,
    bool choseLater = false,
    bool done = false,
    String? lastOfferDay,
  }) =>
      FirstDownloadOfferState(
        downloadCount: downloadCount,
        timesShown: timesShown,
        choseLater: choseLater,
        done: done,
        lastOfferDay: lastOfferDay,
      );

  group('decideFirstDownloadOffer', () {
    test('shows once on the very first download', () {
      final d = decideFirstDownloadOffer(state(downloadCount: 1), today: today);
      expect(d.show, isTrue);
      expect(d.timesShown, 1);
      expect(d.lastOfferDay, today);
    });

    test('does NOT show again on the 2nd download after it was already shown',
        () {
      final d = decideFirstDownloadOffer(
        state(downloadCount: 2, timesShown: 1, choseLater: true),
        // A later day, so the same-day rule is not what blocks it.
        today: tomorrow,
      );
      expect(d.show, isFalse);
      expect(d.timesShown, 1);
    });

    test('asks AGAIN after the 3rd download if the listener chose "Later"', () {
      final d = decideFirstDownloadOffer(
        state(downloadCount: 3, timesShown: 1, choseLater: true),
        today: tomorrow,
      );
      expect(d.show, isTrue);
      expect(d.timesShown, 2);
      // Two showings is the whole budget.
      expect(firstDownloadOfferExhausted(d.timesShown), isTrue);
    });

    test('does NOT ask again after the 3rd download if they did NOT choose Later',
        () {
      // timesShown 1 but choseLater false means they created a code / opted in
      // (the caller would also mark done); the rule itself refuses a 2nd show.
      final d = decideFirstDownloadOffer(
        state(downloadCount: 5, timesShown: 1, choseLater: false),
        today: tomorrow,
      );
      expect(d.show, isFalse);
    });

    test('NEVER shows a third time', () {
      final d = decideFirstDownloadOffer(
        state(downloadCount: 9, timesShown: 2, choseLater: true),
        today: tomorrow,
      );
      expect(d.show, isFalse);
    });

    test('never shows once the offer is done (code created / exhausted)', () {
      final d = decideFirstDownloadOffer(
        state(downloadCount: 1, done: true),
        today: today,
      );
      expect(d.show, isFalse);
    });

    test('never shows on the SAME DAY as another recovery offer', () {
      // First download, would normally show — but a recovery offer (e.g. the
      // first-purchase one) already showed today.
      final d = decideFirstDownloadOffer(
        state(downloadCount: 1, lastOfferDay: today),
        today: today,
      );
      expect(d.show, isFalse);
      expect(d.timesShown, 0);
    });

    test('the same-day block lifts on a later day', () {
      final d = decideFirstDownloadOffer(
        state(downloadCount: 1, lastOfferDay: today),
        today: tomorrow,
      );
      expect(d.show, isTrue);
      expect(d.lastOfferDay, tomorrow);
    });

    test('the "Later" second showing is also same-day blocked', () {
      final d = decideFirstDownloadOffer(
        state(
            downloadCount: 3,
            timesShown: 1,
            choseLater: true,
            lastOfferDay: today),
        today: today,
      );
      expect(d.show, isFalse);
    });
  });
}
