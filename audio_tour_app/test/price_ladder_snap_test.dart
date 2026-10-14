// [LOCAL-686] Price-ladder snapping — unit tests for the client-side helper
// TourPricingService.snapToLadder (mirrors price_tiers.snap_to_ladder on the
// server). The guide's Custom price field calls this on every keystroke to show
// "Your price: $X" = the nearest ladder step.
//
// Pure/sync — no network, no WebView. The ladder is the 34 round-dollar steps.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/tour_pricing_service.dart';

/// Build the 34-step round-dollar ladder as PriceTier rows (tiers 8..41),
/// exactly as /price-tiers would return for the in_picker set.
List<PriceTier> _ladder() {
  final dollars = <int>[
    for (var d = 2; d <= 20; d++) d, // $2..$20 /$1
    25, 30, 35, 40, 45, 50, // /$5
    60, 70, 80, 90, 100, // /$10
    125, 150, 175, 200, // /$25
  ];
  var tier = 8;
  return [
    for (final d in dollars)
      PriceTier(
        tier: tier++,
        priceUsd: d.toDouble(),
        label: '\$$d',
        productId: 'audioura.tour.usd$d',
        inPicker: true,
      ),
  ];
}

void main() {
  final ladder = _ladder();

  test('ladder has 34 round-dollar steps, tiers 8..41', () {
    expect(ladder.length, 34);
    expect(ladder.first.tier, 8);
    expect(ladder.last.tier, 41);
    expect(ladder.first.priceUsd, 2.0);
    expect(ladder.last.priceUsd, 200.0);
  });

  group('snapToLadder — the ticket cases', () {
    final cases = <double, int>{
      37: 35, // Michael's headline example
      1: 2, // below the floor → $2
      2.4: 2,
      2.5: 2, // tie → round DOWN
      22: 20,
      23: 25,
      199: 200,
      250: 200, // above the ceiling → $200
      112.5: 100, // tie → round DOWN
      113: 125,
    };
    cases.forEach((amount, expected) {
      test('$amount → \$$expected', () {
        final snapped = TourPricingService.snapToLadder(amount, ladder);
        expect(snapped, isNotNull);
        expect(snapped!.priceUsd, expected.toDouble());
        expect(snapped.label, '\$$expected');
      });
    });
  });

  test('empty ladder → null', () {
    expect(TourPricingService.snapToLadder(10, const []), isNull);
  });

  test('exact step snaps to itself', () {
    expect(TourPricingService.snapToLadder(50, ladder)!.priceUsd, 50.0);
    expect(TourPricingService.snapToLadder(2, ladder)!.priceUsd, 2.0);
    expect(TourPricingService.snapToLadder(200, ladder)!.priceUsd, 200.0);
  });
}
