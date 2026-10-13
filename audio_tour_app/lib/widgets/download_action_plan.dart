// [LOCAL-677C / D654] Pay-before-download dialog logic (pure, testable).
//
// Decides what the shared download / language dialog offers for a tour:
//   * a FREE tour (or an already-unlocked paid tour) → a plain "Download Tour"
//     button, unchanged from before;
//   * an UNBOUGHT PAID tour → "▶ Preview Stop 1" + "Buy & Download — $X", and
//     NO plain Download button. Buying runs the purchase first; the download
//     starts only after the server confirms the unlock.
//
// The decision is pure data (no Flutter, no I/O) so a widget/unit test can
// assert the exact buttons without a server. The dialog widget renders from it.

/// How the dialog should present download actions for a tour.
class DownloadActionPlan {
  /// Show the plain "Download Tour" button (free, or an unlocked paid tour).
  final bool showPlainDownload;

  /// Show "▶ Preview Stop 1" (an unbought paid tour only).
  final bool showPreview;

  /// Show "Buy & Download — $X" (an unbought paid tour only).
  final bool showBuyAndDownload;

  /// The price label for the Buy button, e.g. '$4.99' (null when free).
  final String? priceLabel;

  /// The price tier for the purchase, e.g. 3 (null when free).
  final int? priceTier;

  const DownloadActionPlan({
    required this.showPlainDownload,
    required this.showPreview,
    required this.showBuyAndDownload,
    this.priceLabel,
    this.priceTier,
  });

  /// Decide the plan from a tour's paid state and whether THIS language row is
  /// already unlocked for the device.
  ///
  ///   * [isPaid]    — the row carries a price (price_tier > 0).
  ///   * [unlocked]  — the device already owns THIS language row (per-language,
  ///                   D653). A paid-but-unlocked tour downloads plainly.
  ///   * [priceTier] / [priceLabel] — the row's price for the Buy button.
  ///
  /// A free tour: plain Download only. A paid+unlocked tour: plain Download
  /// only (it is already bought). A paid+not-unlocked tour: Preview + Buy, and
  /// NO plain Download.
  factory DownloadActionPlan.decide({
    required bool isPaid,
    required bool unlocked,
    int? priceTier,
    String? priceLabel,
  }) {
    final bool lockedPaid = isPaid && !unlocked;
    if (!lockedPaid) {
      return const DownloadActionPlan(
        showPlainDownload: true,
        showPreview: false,
        showBuyAndDownload: false,
      );
    }
    return DownloadActionPlan(
      showPlainDownload: false,
      showPreview: true,
      showBuyAndDownload: true,
      priceTier: priceTier,
      priceLabel: priceLabel,
    );
  }
}

/// One paid language the listener selected to buy & download. Each selected
/// paid language is bought SEPARATELY (D653: 2 × $4.99 for two languages), each
/// at the row's own price.
class PaidLanguagePurchase {
  /// The language code, e.g. 'en', 'ru'.
  final String language;

  /// The audio_tours id for THAT language row (the id the unlock keys on).
  final String tourId;

  /// The price tier for the purchase.
  final int priceTier;

  /// The price label, e.g. '$4.99'.
  final String priceLabel;

  const PaidLanguagePurchase({
    required this.language,
    required this.tourId,
    required this.priceTier,
    required this.priceLabel,
  });
}
