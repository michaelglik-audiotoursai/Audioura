import 'package:flutter/material.dart';
import '../services/tour_rating_service.dart';
import '../services/tour_listen_service.dart';

/// A small "★ 8.3 · 2 ratings" / "★ 7.5 · New" badge, shown on home-page tour
/// list items and in tour dialogs (LOCAL-670).
///
/// Pass whatever the map-delivery record already carries (rating_score /
/// rating_count / rating_label). When those are absent (older server), it
/// falls back to the 7.5 "New" default so the badge is never blank.
class TourRatingBadge extends StatelessWidget {
  final double? score;
  final int? count;
  final String? label;

  /// Compact variant uses a smaller font / tighter padding for list rows.
  final bool compact;

  const TourRatingBadge({
    super.key,
    this.score,
    this.count,
    this.label,
    this.compact = false,
  });

  /// Build from a tour map returned by map-delivery (/tours-near etc.).
  factory TourRatingBadge.fromTour(Map<String, dynamic> tour, {bool compact = false}) {
    return TourRatingBadge(
      score: (tour['rating_score'] as num?)?.toDouble(),
      count: (tour['rating_count'] as num?)?.toInt(),
      label: tour['rating_label'] as String?,
      compact: compact,
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = score ?? 7.5;
    final c = count ?? 0;
    final l = label ?? (c == 0 ? 'New' : (c == 1 ? '1 rating' : '$c ratings'));
    final text = '${s.toStringAsFixed(1)} · $l';
    final fontSize = compact ? 11.0 : 13.0;

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 6 : 8,
        vertical: compact ? 2 : 4,
      ),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF4D6),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.star, size: fontSize + 2, color: const Color(0xFFE2A400)),
          const SizedBox(width: 3),
          Text(
            text,
            style: TextStyle(
              fontSize: fontSize,
              fontWeight: FontWeight.w600,
              color: const Color(0xFF7A5C00),
            ),
          ),
        ],
      ),
    );
  }
}

/// A 1–10 "Rate this tour" dialog (LOCAL-670).
///
/// Offered at the end of a tour (after the last stop) and from the downloaded
/// tour's menu. Whole numbers only (10 selectable chips). On submit it POSTs to
/// the orchestrator and returns the recomputed [TourRating] (or null on
/// failure) via [showRateTourDialog].
class RateTourDialog extends StatefulWidget {
  final String tourId;
  final String tourTitle;

  /// The user's existing rating for this tour, if known, so the dialog opens
  /// pre-selected (re-rating replaces the previous value).
  final int? initialRating;

  const RateTourDialog({
    super.key,
    required this.tourId,
    required this.tourTitle,
    this.initialRating,
  });

  @override
  State<RateTourDialog> createState() => _RateTourDialogState();
}

class _RateTourDialogState extends State<RateTourDialog> {
  int? _selected;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    _selected = widget.initialRating;
  }

  Future<void> _submit() async {
    if (_selected == null || _submitting) return;
    setState(() => _submitting = true);

    final result = await TourRatingService.submitRating(
      tourId: widget.tourId,
      rating: _selected!,
    );

    if (!mounted) return;

    if (result != null) {
      Navigator.of(context).pop(result);
    } else {
      setState(() => _submitting = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text("Couldn't save your rating — please try again."),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Rate this tour'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            widget.tourTitle,
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          const Text(
            'How would you rate it, 1 (poor) to 10 (excellent)?',
            style: TextStyle(fontSize: 13, color: Color(0xFF555555)),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (int n = 1; n <= 10; n++)
                ChoiceChip(
                  label: Text('$n'),
                  selected: _selected == n,
                  onSelected: _submitting
                      ? null
                      : (_) => setState(() => _selected = n),
                ),
            ],
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: _submitting ? null : () => Navigator.of(context).pop(null),
          child: const Text('Not now'),
        ),
        ElevatedButton(
          onPressed: (_selected == null || _submitting) ? null : _submit,
          child: _submitting
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Submit'),
        ),
      ],
    );
  }
}

/// Show the rate-tour dialog. Returns the recomputed [TourRating] if the user
/// submitted, or null if they dismissed it (or submission failed).
///
/// [LOCAL-670B] The per-TOUR rating is gated behind "heard at least 2 stops"
/// (or all stops on a short tour). If the listener opens this before that
/// threshold, we DON'T show the 1–10 picker — we show the polite Audible-style
/// message with the running count and return null. Callers should also hide the
/// entry point until [TourListenService.hasListenedEnough], but gating here as
/// well guarantees the message is consistent wherever rating is triggered.
Future<TourRating?> showRateTourDialog(
  BuildContext context, {
  required String tourId,
  required String tourTitle,
  int? initialRating,
  int? totalStops,
}) async {
  final enough = await TourListenService.hasListenedEnough(
    tourId,
    totalStops: totalStops,
  );
  if (!enough) {
    if (!context.mounted) return null;
    final heard = await TourListenService.listenedCount(tourId);
    final required = TourListenService.requiredThreshold(totalStops);
    if (!context.mounted) return null;
    await showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Rate this tour'),
        content: Text(
          'Listen to at least $required stops to rate this tour. '
          "You've heard $heard so far.",
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
    return null;
  }

  if (!context.mounted) return null;
  return showDialog<TourRating>(
    context: context,
    builder: (_) => RateTourDialog(
      tourId: tourId,
      tourTitle: tourTitle,
      initialRating: initialRating,
    ),
  );
}
