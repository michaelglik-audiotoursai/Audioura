import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/score_explanation_service.dart';

/// [LOCAL-688] "Why this score" bottom sheet.
///
/// Opened by tapping a tour's rating badge (in the tour dialog and the home
/// List view). It fetches the editor's evaluation and shows:
///   * the Audioura score (and, when the tour has listener ratings, BOTH the
///     listeners' score and the Audioura score, with the rule that from the
///     fourth rating on the listeners decide);
///   * the five rubric criteria as bars with their grade and the one-sentence
///     evidence;
///   * the editor's one-line summary;
///   * a link to the public "How Audioura scores tours" page.
///
/// Everything here is public and free. [tour] is the map-delivery record so the
/// sheet can read the listener rating_score / rating_count already loaded.
Future<void> showWhyThisScoreSheet(
  BuildContext context, {
  required String tourId,
  Map<String, dynamic>? tour,
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (ctx) => _WhyThisScoreSheet(tourId: tourId, tour: tour),
  );
}

class _WhyThisScoreSheet extends StatefulWidget {
  final String tourId;
  final Map<String, dynamic>? tour;
  const _WhyThisScoreSheet({required this.tourId, this.tour});

  @override
  State<_WhyThisScoreSheet> createState() => _WhyThisScoreSheetState();
}

class _WhyThisScoreSheetState extends State<_WhyThisScoreSheet> {
  late Future<ScoreExplanation?> _future;

  @override
  void initState() {
    super.initState();
    _future = ScoreExplanationService.fetch(widget.tourId);
  }

  int get _listenerCount =>
      (widget.tour?['rating_count'] as num?)?.toInt() ?? 0;

  double? get _listenerScore =>
      (widget.tour?['rating_score'] as num?)?.toDouble();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
        top: 4,
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.82,
        ),
        child: FutureBuilder<ScoreExplanation?>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState != ConnectionState.done) {
              return const Padding(
                padding: EdgeInsets.symmetric(vertical: 48),
                child: Center(child: CircularProgressIndicator()),
              );
            }
            final exp = snap.data;
            if (exp == null) {
              return _unavailable(context);
            }
            return _content(context, exp);
          },
        ),
      ),
    );
  }

  Widget _unavailable(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Why this score',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
        const SizedBox(height: 12),
        const Text(
          'This tour does not have an Audioura score yet. New tours are scored '
          'within a few minutes of appearing.',
        ),
        const SizedBox(height: 16),
        _howWeScoreLink(context),
        const SizedBox(height: 8),
      ],
    );
  }

  Widget _content(BuildContext context, ScoreExplanation exp) {
    final hasListeners = _listenerCount > 0 && _listenerScore != null;
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Why this score',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 12),

          // Dual display when the tour has listener ratings; otherwise the
          // Audioura score alone.
          if (hasListeners)
            _dualScore(exp)
          else
            _singleScore(exp),
          const SizedBox(height: 16),

          if (exp.summary.isNotEmpty) ...[
            Text(
              exp.summary,
              style: const TextStyle(
                  fontStyle: FontStyle.italic, fontSize: 14.5, height: 1.35),
            ),
            const SizedBox(height: 16),
          ],

          // The five criteria.
          ...exp.criteria.map(_criterionTile),

          const SizedBox(height: 8),
          if (exp.scoredAt != null)
            Text('Scored ${exp.scoredAt}'
                '${exp.rubricVersion != null ? ' · rubric v${exp.rubricVersion}' : ''}',
                style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600)),
          const SizedBox(height: 12),
          _howWeScoreLink(context),
          const SizedBox(height: 8),
        ],
      ),
    );
  }

  Widget _singleScore(ScoreExplanation exp) {
    return Row(
      children: [
        const Icon(Icons.star, color: Color(0xFFE2A400), size: 22),
        const SizedBox(width: 6),
        Text(exp.score.toStringAsFixed(1),
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
        const SizedBox(width: 8),
        const Text('Audioura score',
            style: TextStyle(fontSize: 14, color: Color(0xFF7A5C00))),
      ],
    );
  }

  Widget _dualScore(ScoreExplanation exp) {
    final count = _listenerCount;
    final ratingsWord = count == 1 ? '1 rating' : '$count ratings';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.people, color: Color(0xFF2E7D32), size: 20),
            const SizedBox(width: 6),
            Text('Listeners: ${_listenerScore!.toStringAsFixed(1)}',
                style: const TextStyle(
                    fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(width: 6),
            Text('($ratingsWord)',
                style: TextStyle(fontSize: 13, color: Colors.grey.shade700)),
            const SizedBox(width: 12),
            const Icon(Icons.star, color: Color(0xFFE2A400), size: 18),
            const SizedBox(width: 4),
            Text('Audioura: ${exp.score.toStringAsFixed(1)}',
                style: const TextStyle(
                    fontSize: 15, fontWeight: FontWeight.w600)),
          ],
        ),
        const SizedBox(height: 6),
        Text(
          count >= 4
              ? 'This tour has enough ratings — the listeners\' score is what '
                  'you see on the tour.'
              : 'From the fourth rating on, the listeners\' score decides and '
                  'the Audioura score steps aside.',
          style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700),
        ),
      ],
    );
  }

  Widget _criterionTile(ScoreCriterion c) {
    final grade = c.grade ?? 0;
    final frac = (grade / 10.0).clamp(0.0, 1.0);
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(c.label,
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, fontSize: 14)),
              ),
              Text(c.grade != null ? c.grade!.toStringAsFixed(1) : '—',
                  style: const TextStyle(
                      fontWeight: FontWeight.bold, fontSize: 14)),
              const Text(' / 10',
                  style: TextStyle(fontSize: 11, color: Colors.grey)),
            ],
          ),
          const SizedBox(height: 4),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: frac,
              minHeight: 7,
              backgroundColor: const Color(0xFFEEEEEE),
              valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFFE2A400)),
            ),
          ),
          if (c.evidence.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(c.evidence,
                style: TextStyle(
                    fontSize: 12.5, color: Colors.grey.shade800, height: 1.3)),
          ],
        ],
      ),
    );
  }

  Widget _howWeScoreLink(BuildContext context) {
    return InkWell(
      onTap: () async {
        final uri = await ScoreExplanationService.howWeScoreUrl();
        if (await canLaunchUrl(uri)) {
          await launchUrl(uri, mode: LaunchMode.externalApplication);
        }
      },
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.open_in_new, size: 16, color: Color(0xFF1565C0)),
          SizedBox(width: 6),
          Text('How Audioura scores tours',
              style: TextStyle(
                  color: Color(0xFF1565C0),
                  fontWeight: FontWeight.w600,
                  decoration: TextDecoration.underline)),
        ],
      ),
    );
  }
}
