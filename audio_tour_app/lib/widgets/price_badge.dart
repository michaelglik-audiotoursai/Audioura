// [LOCAL-677] Curator paid tours — the price badge shown next to the ★ rating.
//
// "$4.99" for a paid tour, "Free" for a free one. Built from a tour map that
// map-delivery returns (price_tier + price_label on /tours-near, /search-tours,
// /tour-info, /tour-by-code). Mirrors TourRatingBadge's compact/full styling so
// the two badges sit together.

import 'package:flutter/material.dart';

class TourPriceBadge extends StatelessWidget {
  /// The dollar label, e.g. '$4.99', or null/'Free' for a free tour.
  final String? priceLabel;

  /// True when the tour is paid (drives colour). When null it is inferred from
  /// priceLabel (anything other than 'Free'/null is treated as paid).
  final bool? isPaid;

  /// Compact variant for list rows (smaller font / tighter padding).
  final bool compact;

  const TourPriceBadge({
    super.key,
    this.priceLabel,
    this.isPaid,
    this.compact = false,
  });

  /// Build from a tour map returned by map-delivery.
  factory TourPriceBadge.fromTour(Map<String, dynamic> tour,
      {bool compact = false}) {
    return TourPriceBadge(
      priceLabel: tour['price_label'] as String?,
      isPaid: tour['is_paid'] == true,
      compact: compact,
    );
  }

  bool get _paid {
    if (isPaid != null) return isPaid!;
    final l = priceLabel;
    return l != null && l.isNotEmpty && l != 'Free';
  }

  @override
  Widget build(BuildContext context) {
    final paid = _paid;
    final text = paid ? (priceLabel ?? '') : 'Free';
    final fontSize = compact ? 11.0 : 13.0;

    // Paid: a green "price" chip. Free: a muted grey chip.
    final bg = paid ? const Color(0xFFE3F4E6) : const Color(0xFFEDEDED);
    final fg = paid ? const Color(0xFF1B6B2E) : const Color(0xFF666666);
    final icon = paid ? Icons.sell : Icons.lock_open;

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 6 : 8,
        vertical: compact ? 2 : 4,
      ),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: fontSize + 2, color: fg),
          const SizedBox(width: 3),
          Text(
            text,
            style: TextStyle(
              fontSize: fontSize,
              fontWeight: FontWeight.w600,
              color: fg,
            ),
          ),
        ],
      ),
    );
  }
}
