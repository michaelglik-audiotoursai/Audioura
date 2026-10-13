// [LOCAL-677C / D654] Pay-before-download — unit tests for the download-dialog
// decision and the refund-lock snapshot.
//
// These exercise the testable core of the app side:
//   * DownloadActionPlan.decide — a FREE or already-UNLOCKED tour offers a plain
//     "Download Tour"; an UNBOUGHT PAID tour offers "▶ Preview Stop 1" +
//     "Buy & Download" and NO plain Download (the ticket's §3 rule);
//   * DownloadedTourStore.markLockedForPath — a refund (the quiet online
//     re-check) persists is_paid:true + unlocked:false so the lock holds on a
//     later offline open, while markUnlockedForPath lifts it.
//
// Pure model + SharedPreferences — no WebView, no live server.

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/widgets/download_action_plan.dart';
import 'package:audio_tour_app_dev/services/downloaded_tour_meta.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DownloadActionPlan.decide (D654 §3)', () {
    test('a FREE tour shows plain Download, no Preview/Buy', () {
      final p = DownloadActionPlan.decide(isPaid: false, unlocked: true);
      expect(p.showPlainDownload, isTrue);
      expect(p.showPreview, isFalse);
      expect(p.showBuyAndDownload, isFalse);
    });

    test('an UNBOUGHT PAID tour shows Preview + Buy and NO plain Download', () {
      final p = DownloadActionPlan.decide(
        isPaid: true,
        unlocked: false,
        priceTier: 3,
        priceLabel: '\$4.99',
      );
      expect(p.showPlainDownload, isFalse); // the key rule: NO plain Download
      expect(p.showPreview, isTrue);
      expect(p.showBuyAndDownload, isTrue);
      expect(p.priceLabel, '\$4.99');
      expect(p.priceTier, 3);
    });

    test('a PAID but already-UNLOCKED tour shows plain Download (it is bought)',
        () {
      final p = DownloadActionPlan.decide(
        isPaid: true,
        unlocked: true,
        priceTier: 3,
        priceLabel: '\$4.99',
      );
      expect(p.showPlainDownload, isTrue);
      expect(p.showPreview, isFalse);
      expect(p.showBuyAndDownload, isFalse);
    });
  });

  group('PaidLanguagePurchase (per-language, D653)', () {
    test('each selected paid language is its own priced purchase', () {
      const en = PaidLanguagePurchase(
          language: 'en', tourId: '557', priceTier: 3, priceLabel: '\$4.99');
      const ru = PaidLanguagePurchase(
          language: 'ru', tourId: '615', priceTier: 3, priceLabel: '\$4.99');
      // Two languages → two separate purchases, each priced (2 × $4.99).
      expect(en.tourId, '557');
      expect(ru.tourId, '615');
      expect(en.priceLabel, ru.priceLabel);
      expect(en.tourId == ru.tourId, isFalse);
    });
  });

  group('refund lock snapshot (D654 online re-check)', () {
    const path = '/local/tours/paid_tour';

    setUp(() {
      SharedPreferences.setMockInitialValues({
        'saved_tours': [
          // A bought paid tour: paid, unlocked at download.
          '{"path":"$path","server_tour_id":"557","price_tier":3,'
              '"is_paid":true,"unlocked":true,"price_label":"\$4.99"}',
        ],
      });
    });

    test('markLockedForPath flips a bought tour to paid + NOT unlocked', () async {
      // Before: the local snapshot says unlocked.
      var meta = await DownloadedTourStore.metaForPath(path);
      expect(meta.isPaid, isTrue);
      expect(meta.unlocked, isTrue);
      expect(meta.lockedOffline, isFalse);

      // A refund: the quiet online re-check reports paid + not unlocked.
      await DownloadedTourStore.markLockedForPath(path);

      // After: the snapshot locks, so a later OFFLINE open stays locked.
      meta = await DownloadedTourStore.metaForPath(path);
      expect(meta.isPaid, isTrue);
      expect(meta.unlocked, isFalse);
      expect(meta.lockedOffline, isTrue);
    });

    test('markUnlockedForPath lifts the lock again', () async {
      await DownloadedTourStore.markLockedForPath(path);
      await DownloadedTourStore.markUnlockedForPath(path);
      final meta = await DownloadedTourStore.metaForPath(path);
      expect(meta.unlocked, isTrue);
      expect(meta.lockedOffline, isFalse);
    });
  });
}
