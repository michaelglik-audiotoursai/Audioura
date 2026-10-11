import 'package:flutter/material.dart';
import '../services/tour_reviews_service.dart';

/// The "Reviews (n)" section shown in the tour dialog (LOCAL-672).
///
/// It expands to show:
///   * the five-band rating DISTRIBUTION as horizontal bars with percentages
///     (item 8) — tap a bar to FILTER the list to that band (item 10);
///   * a SORT control: Top / Most recent / Critical (item 10);
///   * each approved review with its 1–10 rating, "Verified listener" badge
///     when verified, the date, the text, a "Helpful (n)" button (item 9), and
///     the single curator reply when present (item 3 / §2).
///
/// Reads are best-effort (the service returns empty on failure), so the section
/// degrades to "No reviews yet" rather than erroring.
class ReviewsSection extends StatefulWidget {
  final String tourId;

  /// The count the dialog already knows (from the tour's rating_count), used for
  /// the collapsed header before the list loads.
  final int initialCount;

  const ReviewsSection({
    super.key,
    required this.tourId,
    this.initialCount = 0,
  });

  @override
  State<ReviewsSection> createState() => _ReviewsSectionState();
}

class _ReviewsSectionState extends State<ReviewsSection> {
  bool _expanded = false;
  bool _loading = false;
  List<TourReview> _reviews = const [];
  RatingDistribution _distribution = RatingDistribution.empty;
  ReviewSort _sort = ReviewSort.top;
  String? _bandFilter; // null = all bands

  Future<void> _loadIfNeeded() async {
    if (!_expanded) return;
    setState(() => _loading = true);
    final reviews = await TourReviewsService.fetchReviews(
      widget.tourId,
      sort: _sort,
      band: _bandFilter,
    );
    final dist = await TourReviewsService.fetchDistribution(widget.tourId);
    if (!mounted) return;
    setState(() {
      _reviews = reviews;
      _distribution = dist;
      _loading = false;
    });
  }

  void _toggle() {
    setState(() => _expanded = !_expanded);
    if (_expanded) _loadIfNeeded();
  }

  Future<void> _onSortChanged(ReviewSort s) async {
    setState(() => _sort = s);
    await _loadIfNeeded();
  }

  Future<void> _onBandTapped(String band) async {
    setState(() => _bandFilter = _bandFilter == band ? null : band);
    await _loadIfNeeded();
  }

  Future<void> _onHelpful(TourReview r) async {
    final newCount = await TourReviewsService.voteHelpful(r.id);
    if (!mounted) return;
    if (newCount == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Couldn't record your vote.")),
      );
      return;
    }
    await _loadIfNeeded();
  }

  @override
  Widget build(BuildContext context) {
    final headerCount = _reviews.isNotEmpty ? _reviews.length : widget.initialCount;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: _toggle,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Row(
              children: [
                Text(
                  'Reviews ($headerCount)',
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                ),
                const Spacer(),
                Icon(_expanded ? Icons.expand_less : Icons.expand_more),
              ],
            ),
          ),
        ),
        if (_expanded) ...[
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(12),
              child: Center(
                child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            )
          else ...[
            _buildDistribution(),
            const SizedBox(height: 8),
            _buildSortRow(),
            const SizedBox(height: 4),
            if (_reviews.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text('No reviews yet.',
                    style: TextStyle(color: Color(0xFF777777))),
              )
            else
              ..._reviews.map(_buildReviewTile),
          ],
        ],
      ],
    );
  }

  Widget _buildDistribution() {
    if (_distribution.total == 0) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final b in _distribution.bands)
          _DistributionBar(
            band: b,
            selected: _bandFilter == b.band,
            onTap: () => _onBandTapped(b.band),
          ),
        if (_bandFilter != null)
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              onPressed: () => _onBandTapped(_bandFilter!),
              child: const Text('Clear filter'),
            ),
          ),
      ],
    );
  }

  Widget _buildSortRow() {
    return Row(
      children: [
        const Text('Sort:', style: TextStyle(fontSize: 12, color: Color(0xFF555555))),
        const SizedBox(width: 6),
        for (final s in ReviewSort.values) ...[
          ChoiceChip(
            label: Text(s.label, style: const TextStyle(fontSize: 11)),
            selected: _sort == s,
            onSelected: (_) => _onSortChanged(s),
            visualDensity: VisualDensity.compact,
          ),
          const SizedBox(width: 4),
        ],
      ],
    );
  }

  Widget _buildReviewTile(TourReview r) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: const Color(0xFFF7F7F7),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.star, size: 15, color: Color(0xFFE2A400)),
              const SizedBox(width: 3),
              Text('${r.rating}/10',
                  style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
              const SizedBox(width: 8),
              if (r.verified) const VerifiedListenerBadge(),
              const Spacer(),
              if (r.date != null)
                Text(r.date!,
                    style: const TextStyle(fontSize: 11, color: Color(0xFF999999))),
            ],
          ),
          const SizedBox(height: 4),
          Text(r.text, style: const TextStyle(fontSize: 13)),
          const SizedBox(height: 6),
          Row(
            children: [
              TextButton.icon(
                onPressed: () => _onHelpful(r),
                icon: const Icon(Icons.thumb_up_alt_outlined, size: 15),
                label: Text(
                  r.helpfulCount > 0
                      ? '${r.helpfulCount} ${r.helpfulCount == 1 ? "person" : "people"} found this helpful'
                      : 'Helpful',
                  style: const TextStyle(fontSize: 12),
                ),
                style: TextButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 6),
                  visualDensity: VisualDensity.compact,
                ),
              ),
            ],
          ),
          if (r.replyText != null) ...[
            const SizedBox(height: 4),
            Container(
              margin: const EdgeInsets.only(left: 12),
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: const Color(0xFFEDF3FF),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.reply, size: 14, color: Color(0xFF3A6EA5)),
                      const SizedBox(width: 4),
                      const Text('Curator reply',
                          style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF3A6EA5))),
                      const Spacer(),
                      if (r.replyDate != null)
                        Text(r.replyDate!,
                            style: const TextStyle(
                                fontSize: 10, color: Color(0xFF999999))),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(r.replyText!, style: const TextStyle(fontSize: 12)),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// "Verified listener" pill, shown on verified reviews/ratings (item 1).
class VerifiedListenerBadge extends StatelessWidget {
  const VerifiedListenerBadge({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0xFFE3F5E8),
        borderRadius: BorderRadius.circular(10),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.verified, size: 13, color: Color(0xFF2E8B57)),
          SizedBox(width: 3),
          Text('Verified listener',
              style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF2E8B57))),
        ],
      ),
    );
  }
}

/// One tappable distribution bar (item 8 + the item 10 band filter).
class _DistributionBar extends StatelessWidget {
  final RatingBand band;
  final bool selected;
  final VoidCallback onTap;

  const _DistributionBar({
    required this.band,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(
          children: [
            SizedBox(
              width: 34,
              child: Text(band.band,
                  style: TextStyle(
                      fontSize: 11,
                      fontWeight: selected ? FontWeight.w700 : FontWeight.w400)),
            ),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: band.percent / 100.0,
                  minHeight: 10,
                  backgroundColor: const Color(0xFFE8E8E8),
                  valueColor: AlwaysStoppedAnimation<Color>(
                    selected ? const Color(0xFFE2A400) : const Color(0xFFBFA14A),
                  ),
                ),
              ),
            ),
            SizedBox(
              width: 38,
              child: Text('${band.percent}%',
                  textAlign: TextAlign.right,
                  style: const TextStyle(fontSize: 11, color: Color(0xFF666666))),
            ),
          ],
        ),
      ),
    );
  }
}

/// The optional "Add a short review" dialog, offered after a rating (item 6).
/// <= 500 chars; the server auto-checks it. Returns the server status string
/// ('approved' | 'pending') if submitted, else null.
Future<String?> showAddReviewDialog(
  BuildContext context, {
  required String tourId,
  required String tourTitle,
}) {
  final controller = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (ctx) {
      bool submitting = false;
      return StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: const Text('Add a short review'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(tourTitle, style: const TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              TextField(
                controller: controller,
                maxLength: 500,
                maxLines: 4,
                decoration: const InputDecoration(
                  hintText: 'What did you think? (optional)',
                  border: OutlineInputBorder(),
                ),
              ),
              const Text(
                'Reviews are checked before they appear.',
                style: TextStyle(fontSize: 11, color: Color(0xFF777777)),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: submitting ? null : () => Navigator.of(ctx).pop(null),
              child: const Text('Skip'),
            ),
            ElevatedButton(
              onPressed: submitting
                  ? null
                  : () async {
                      final text = controller.text.trim();
                      if (text.isEmpty) {
                        Navigator.of(ctx).pop(null);
                        return;
                      }
                      setLocal(() => submitting = true);
                      final status = await TourReviewsService.submitReview(
                        tourId: tourId,
                        reviewText: text,
                      );
                      if (!ctx.mounted) return;
                      Navigator.of(ctx).pop(status);
                    },
              child: submitting
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Submit'),
            ),
          ],
        ),
      );
    },
  );
}
