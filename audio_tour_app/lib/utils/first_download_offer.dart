// [LOCAL-740 / B5b] When to offer the recovery code after a DOWNLOAD finishes.
//
// Michael's review (2026-10-22): the recovery code only saves a listener after
// a lost phone if it was kept off the phone beforehand — so prompt proactively.
// The first-PURCHASE offer already exists (maybeOfferRecoveryCode). B5b adds a
// first-DOWNLOAD offer for anyone who downloads before they ever buy:
//
//   * The FIRST time a download finishes (any tour or article, not only a
//     purchase), offer once: "Save your recovery code…" with
//     [Create my code] and [Later].
//   * "Later" → ask again after the 3rd download, then NEVER.
//   * "Create my code" (or the listener already made one) → never again.
//   * Never show this on the SAME DAY as the first-purchase offer — one nudge a
//     day at most.
//
// This module is PURE (no Flutter, no I/O): it decides from a small immutable
// state, and returns the next state to persist. The SharedPreferences glue is a
// thin wrapper (firstDownloadOffer...) kept beside it. Pure → unit-testable
// without a widget tree or a clock.

/// Immutable inputs to the decision, read from storage before a download's
/// completion is handled.
class FirstDownloadOfferState {
  /// Total downloads FINISHED so far, INCLUDING the one that just completed.
  /// (1 on the very first download.)
  final int downloadCount;

  /// How many times the first-download offer has already been shown (0, 1, 2).
  final int timesShown;

  /// The listener tapped "Later" on a previous showing.
  final bool choseLater;

  /// The offer is finished for good: they created a code, or we exhausted the
  /// one-then-after-3rd budget, or any other path that closes it.
  final bool done;

  /// A recovery-code offer (purchase OR download) was last shown on this day,
  /// as 'yyyy-mm-dd', or null if never. Used for the "not twice in a day" rule.
  final String? lastOfferDay;

  const FirstDownloadOfferState({
    required this.downloadCount,
    required this.timesShown,
    required this.choseLater,
    required this.done,
    required this.lastOfferDay,
  });
}

/// The decision: whether to show the offer now, and the fields to persist.
class FirstDownloadOfferDecision {
  final bool show;

  /// New value for timesShown to persist (unchanged when not showing).
  final int timesShown;

  /// New value for lastOfferDay to persist (set to [today] only when showing).
  final String? lastOfferDay;

  const FirstDownloadOfferDecision({
    required this.show,
    required this.timesShown,
    required this.lastOfferDay,
  });
}

/// Decide whether to show the first-download recovery offer now.
///
/// [today] is the current day as 'yyyy-mm-dd' (passed in so the rule is
/// testable without a real clock).
///
/// Rules, in order:
///   1. Never once [done] (code created, or budget exhausted).
///   2. Never twice in a day: if a recovery offer already showed [today], skip.
///   3. First showing: on the 1st download, when it has never been shown.
///   4. Second (final) showing: only if they chose "Later" AND this is at least
///      the 3rd download AND it was shown exactly once. After this it is done
///      (the caller marks done when timesShown reaches 2).
FirstDownloadOfferDecision decideFirstDownloadOffer(
  FirstDownloadOfferState s, {
  required String today,
}) {
  FirstDownloadOfferDecision skip() => FirstDownloadOfferDecision(
        show: false,
        timesShown: s.timesShown,
        lastOfferDay: s.lastOfferDay,
      );

  if (s.done) return skip();
  if (s.timesShown >= 2) return skip();
  // Not twice on the same day as any recovery offer (purchase or download).
  if (s.lastOfferDay == today) return skip();

  // First showing: the very first download, never shown before.
  final firstShowing = s.timesShown == 0 && s.downloadCount >= 1;
  // Second (final) showing: they said Later, shown once, now ≥3rd download.
  final secondShowing =
      s.timesShown == 1 && s.choseLater && s.downloadCount >= 3;

  if (firstShowing || secondShowing) {
    return FirstDownloadOfferDecision(
      show: true,
      timesShown: s.timesShown + 1,
      lastOfferDay: today,
    );
  }
  return skip();
}

/// Whether, after a showing, the offer is now DONE for good: shown twice is the
/// whole budget (first, then once more after the 3rd download).
bool firstDownloadOfferExhausted(int timesShownAfter) => timesShownAfter >= 2;
