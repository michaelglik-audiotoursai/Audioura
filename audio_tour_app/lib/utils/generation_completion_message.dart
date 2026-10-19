/// [LOCAL-717 / D677 §2] The ONE place that builds the generation-completed
/// message, so a regeneration that REPLACED an existing tour tells the listener
/// so instead of looking like a brand-new tour.
///
/// Michael (D677, 2026-10-19) regenerated "restaurant tour, Boston, MA". The
/// server did exactly what D622 asks — it replaced tour 370 and bumped it to
/// version 2 — but the app said only "Tour ready! Opening now...", so Michael
/// went looking for a SECOND tour that never existed. When the job-status
/// payload reports a replacement (`replaced: true`, `version_no >= 2`), the
/// completion message must name the update: "Updated your tour '<short title>'
/// — now version N".
///
/// PURE: a job-status map in, a String out — no BuildContext, no I/O — so a
/// unit test can pin the wording for "updated to version 2" directly.
library;

/// Build the generation-completion snackbar text from a job-status map (the
/// body of GET /status/:id when status == 'completed').
///
/// [status] is the decoded job-status JSON. The fields this reads
/// (all optional, server-provided by [tour_orchestrator_service.py]):
///   • replaced   (bool)  — true when this generation replaced an existing tour.
///   • version_no (int)   — the version of the delivered tour (>= 2 on replace).
///   • tour_title (String)— the tour's short title for the message.
///
/// [fallbackTitle] is used when the payload carries no tour_title (e.g. the
/// location the user typed).
///
/// Returns:
///   • "Updated your tour '<title>' — now version N" when the generation was a
///     NEW VERSION of an existing tour (replaced == true AND version_no >= 2).
///   • [defaultMessage] ("Tour ready! Opening now...") for a brand-new tour.
String generationCompletionMessage(
  Map<String, dynamic> status, {
  String? fallbackTitle,
  String defaultMessage = 'Tour ready! Opening now...',
}) {
  final replaced = status['replaced'] == true;
  final versionNo = _asInt(status['version_no']);

  // Only an actual replacement to version >= 2 is an "update". A fresh insert
  // (version 1) or a payload with no version info is a new tour.
  if (replaced && versionNo != null && versionNo >= 2) {
    final rawTitle = status['tour_title'];
    final title = (rawTitle is String && rawTitle.trim().isNotEmpty)
        ? rawTitle.trim()
        : ((fallbackTitle != null && fallbackTitle.trim().isNotEmpty)
            ? fallbackTitle.trim()
            : 'your tour');
    return "Updated your tour '$title' — now version $versionNo";
  }

  return defaultMessage;
}

int? _asInt(dynamic v) {
  if (v is int) return v;
  if (v is num) return v.toInt();
  if (v is String) return int.tryParse(v);
  return null;
}
