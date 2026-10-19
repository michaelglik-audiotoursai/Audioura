/// [LOCAL-716] The ONE place that builds the "downloaded" snackbar text, with
/// correct singular/plural agreement for every count it mentions. Michael, on
/// the Pixel-7 (2026-10-19), hit "1 tour downloaded and now are available" —
/// a count that disagreed with its verb. Every number here agrees with its
/// noun and verb.
///
/// PURE: no BuildContext, no plugins, no I/O — just counts in, a String out, so
/// a golden test can pin every wording directly.
///
/// The three Home snackbar sites and the community-page Download all call this,
/// so the wording can never drift between them again.
library;

/// Build the user-facing "downloaded" message.
///
/// [downloaded]        number of NEW tours saved to the phone this run.
/// [translations]      number of extra-language translations saved alongside
///                     them (0 when English-only).
/// [alreadyDownloaded] number of selected tours that were already on the phone
///                     and so were skipped.
/// [failures]          per-tour translation failures: tour name → the list of
///                     language labels that failed. Empty when nothing failed.
///
/// Agreement rules (D-wording):
///   • 1 tour → "1 tour downloaded and is now on your Listen page"
///     N tours → "N tours downloaded and are now on your Listen page"
///   • "1 translation" / "N translations"
///   • "(1 was already downloaded)" / "(N were already downloaded)"
///   • downloaded == 0 → "No new tours downloaded - all selected tours were
///     already on your phone".
String downloadedMessage({
  required int downloaded,
  int translations = 0,
  int alreadyDownloaded = 0,
  Map<String, List<String>> failures = const {},
}) {
  final buffer = StringBuffer();

  if (downloaded <= 0) {
    // Nothing new. If some were skipped it is because they were already here;
    // if the caller somehow passed zero of everything we still say something
    // sensible rather than an empty snackbar.
    buffer.write(
        'No new tours downloaded - all selected tours were already on your phone');
    _appendFailures(buffer, failures);
    return buffer.toString();
  }

  // "N tour(s) downloaded and is/are now on your Listen page".
  final tourWord = downloaded == 1 ? 'tour' : 'tours';
  final tourVerb = downloaded == 1 ? 'is' : 'are';

  if (translations > 0) {
    // When translations were saved too, the sentence names both counts. The
    // tour clause keeps its own agreement; the translation count gets its own.
    final translationWord = translations == 1 ? 'translation' : 'translations';
    buffer.write(
        '$downloaded $tourWord downloaded with $translations $translationWord '
        'and $tourVerb now on your Listen page');
  } else {
    buffer.write(
        '$downloaded $tourWord downloaded and $tourVerb now on your Listen page');
  }

  if (alreadyDownloaded > 0) {
    final alreadyVerb = alreadyDownloaded == 1 ? 'was' : 'were';
    buffer.write(' ($alreadyDownloaded $alreadyVerb already downloaded)');
  }

  _appendFailures(buffer, failures);
  return buffer.toString();
}

/// Append a human list of per-tour translation failures, when any. Shared by
/// both the success and the no-new-tours branches so a partial failure is
/// always reported the same way.
void _appendFailures(StringBuffer buffer, Map<String, List<String>> failures) {
  if (failures.isEmpty) return;
  final parts = failures.entries
      .map((e) => '${e.key}: ${e.value.join(", ")}')
      .join('; ');
  buffer.write('. Some translations failed: $parts');
}
