// [LOCAL-807] Unit tests for the subscription product mapping in IapService:
// the store ids match the StoreKit config / migration 060, autoRenews is true
// for Week/Month/Year and false for the Day pass, and isSubscriptionProduct
// recognises exactly the four subscription ids (and not the packs/tours).

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/iap_service.dart';

void main() {
  test('subscription store ids match the server/StoreKit ids', () {
    expect(IapSubscription.day.storeId, 'audioura.sub.day');
    expect(IapSubscription.weekly.storeId, 'audioura.sub.weekly');
    expect(IapSubscription.monthly.storeId, 'audioura.sub.monthly');
    expect(IapSubscription.annual.storeId, 'audioura.sub.annual');
  });

  test('autoRenews is true for week/month/year, false for the day pass', () {
    expect(IapSubscription.day.autoRenews, isFalse);
    expect(IapSubscription.weekly.autoRenews, isTrue);
    expect(IapSubscription.monthly.autoRenews, isTrue);
    expect(IapSubscription.annual.autoRenews, isTrue);
  });

  test('isSubscriptionProduct recognises exactly the four subscription ids', () {
    for (final s in IapSubscription.values) {
      expect(isSubscriptionProduct(s.storeId), isTrue, reason: s.storeId);
    }
    // Not the one-time pack / tour products.
    expect(isSubscriptionProduct('audioura.pack.l3'), isFalse);
    expect(isSubscriptionProduct('audioura.round.l4'), isFalse);
    expect(isSubscriptionProduct('audioura.tour.usd5'), isFalse);
    expect(isSubscriptionProduct('audioura.pass.usd5'), isFalse);
  });

  test('kSubscriptionStoreIds contains all four ids', () {
    expect(kSubscriptionStoreIds, {
      'audioura.sub.day',
      'audioura.sub.weekly',
      'audioura.sub.monthly',
      'audioura.sub.annual',
    });
  });
}
