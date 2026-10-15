// [LOCAL-693 / D660] Delete-confirmation copy for a downloaded tour (pure,
// testable).
//
// D660: every download of a PAID tour is paid. What is on the phone is the
// listener's forever, but deleting it means buying again to get it back. So the
// delete confirmation for a PAID tour uses the SAME warning sentence the Buy
// dialog showed ("Delete and lose it?" + "Deleting it or changing phones means
// buying again"); a FREE tour keeps the plain "Delete Tour" confirmation (it can
// be downloaded again at no cost).
//
// Pure data (no Flutter, no I/O) so a unit test asserts the exact copy and the
// "paid only" rule without a widget tree. The screen renders the dialog from it.

/// The title + body for the delete confirmation of one downloaded tour.
class DeleteTourPrompt {
  /// Dialog title.
  final String title;

  /// Dialog body.
  final String body;

  /// Whether this is the PAID warning variant (carries the D660 sentence).
  final bool isPaidWarning;

  const DeleteTourPrompt({
    required this.title,
    required this.body,
    required this.isPaidWarning,
  });

  /// The exact D660 sentence shared with the Buy dialog.
  static const String warningSentence =
      'Deleting it or changing phones means buying again.';

  /// Decide the prompt from the tour's title and whether it is PAID.
  ///
  ///   * [isPaid] — the saved tour carried a price at download time
  ///     (is_paid == true, or price_tier > 0).
  ///
  /// A paid tour gets the "Delete and lose it?" warning with the shared
  /// sentence; a free tour gets the plain "Delete Tour".
  factory DeleteTourPrompt.decide({
    required String tourTitle,
    required bool isPaid,
  }) {
    if (isPaid) {
      return DeleteTourPrompt(
        title: 'Delete and lose it?',
        body: 'Delete "$tourTitle"?\n\nThis tour downloaded to this phone. '
            '$warningSentence',
        isPaidWarning: true,
      );
    }
    return DeleteTourPrompt(
      title: 'Delete Tour',
      body: 'Delete "$tourTitle"?',
      isPaidWarning: false,
    );
  }

  /// Detect "paid" from a saved tour map (is_paid flag or a positive
  /// price_tier captured at download time).
  static bool isPaidTour(Map<String, dynamic> tour) {
    if (tour['is_paid'] == true) return true;
    final t = tour['price_tier'];
    return t is num && t > 0;
  }
}
