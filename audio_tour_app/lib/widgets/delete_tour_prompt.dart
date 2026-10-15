// [LOCAL-693 / D660 + LOCAL-693B / D660 addendum] Delete-confirmation copy for
// a downloaded tour (pure, testable).
//
// D660: every download of a PAID tour is paid; what is on the phone is the
// listener's forever, but deleting it means buying again to get it back.
//
// D660 addendum (Michael, 2026-10-14): no warning at purchase time — a bought
// tour is like a bought bag. The one confirmation lives at DELETION, in a calm
// voice. For a PAID tour the dialog is exactly:
//     title   "Delete paid tour?"
//     text    "Are you sure you want to delete this paid tour? Downloading it
//              again will require another purchase."
//     buttons "Cancel" (default) and "Delete".
// A FREE tour keeps the plain "Delete Tour" confirmation and no warning (it can
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

  /// Label of the confirming (destructive) button.
  final String confirmLabel;

  /// Label of the dismissing (default) button.
  final String cancelLabel;

  /// Whether this is the PAID variant (carries the D660 addendum sentence).
  final bool isPaidWarning;

  const DeleteTourPrompt({
    required this.title,
    required this.body,
    required this.confirmLabel,
    required this.cancelLabel,
    required this.isPaidWarning,
  });

  /// The exact D660-addendum paid-tour title.
  static const String paidTitle = 'Delete paid tour?';

  /// The exact D660-addendum paid-tour body sentence.
  static const String paidBody =
      'Are you sure you want to delete this paid tour? Downloading it again '
      'will require another purchase.';

  /// Decide the prompt from whether the tour is PAID.
  ///
  ///   * [isPaid] — the saved tour carried a price at download time
  ///     (is_paid == true, or price_tier > 0).
  ///
  /// A paid tour gets the calm D660-addendum confirmation; a free tour gets the
  /// plain "Delete Tour".
  factory DeleteTourPrompt.decide({
    required String tourTitle,
    required bool isPaid,
  }) {
    if (isPaid) {
      return const DeleteTourPrompt(
        title: paidTitle,
        body: paidBody,
        confirmLabel: 'Delete',
        cancelLabel: 'Cancel',
        isPaidWarning: true,
      );
    }
    return DeleteTourPrompt(
      title: 'Delete Tour',
      body: 'Delete "$tourTitle"?',
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
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
