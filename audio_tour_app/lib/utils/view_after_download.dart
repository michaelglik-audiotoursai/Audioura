// [LOCAL-719 / D677 addendum 1] PURE planner for the download snackbar's
// "View" button. View ALWAYS opens a player.
//
// Michael (2026-10-19): "if we start playing when one tour with a translation
// is downloaded, we should start playing when multiple tours are downloaded
// too, maybe the first one; in any case the behaviour should be consistent."
//
// LOCAL-716B (D358) made "View" open a player for a SINGLE downloaded tour
// (picking the right language copy across the original and its translations),
// but for SEVERAL tours it only highlighted the newest in Listen and opened
// nothing — the inconsistency Michael is pointing at. This file now makes the
// decision uniform:
//   * one tour   → open that tour, in the language just downloaded
//                  (the LOCAL-716B logic, unchanged);
//   * several    → open the FIRST tour in the order the user selected them,
//                  in the language just downloaded. "First" is the first id in
//                  the ordered list the caller passes; the caller only adds a
//                  tour's id AFTER it saved, so a tour that failed to download
//                  is simply absent and the first that SUCCEEDED is opened.
//
// (The other tours from the batch are highlighted when the user goes back to
// Listen — that is the caller's amber-highlight path, unchanged. This planner
// only decides which ONE player to open.)
//
// This is the ONE place that decides, from the saved entries alone, WHICH copy
// "View" opens. It is dependency-free (no Flutter, no SharedPreferences, no
// http) so every branch is unit-tested directly (test/view_after_download_test
// .dart) with plain maps — the same style as community_downloads.dart.
//
// The rule:
//   1. A tour is ONE tour even with translations — we match on the SERVER tour
//      id across the original and every translation of it.
//   2. The tour to open is the FIRST id in [downloadedTourIds] that has a
//      matching saved entry. For one downloaded tour that is simply that tour;
//      for several it is the first the user selected (that succeeded). Ids with
//      no matching saved entry are skipped (a save that silently vanished must
//      not strand "View").
//   3. For the chosen tour, open the copy in the language just downloaded:
//        * exactly one translation  → that translation;
//        * several translations      → the one matching the listening language
//          if present, else the first one downloaded (oldest `created`);
//        * no translation            → the original.
//   4. No silent miss: when NO offered id matches any saved entry (and when no
//      id was offered at all), the caller logs it and falls back to the
//      highlight path — this planner returns
//      [ViewAfterDownloadPlan.highlightNewest] for that case too.
library;

/// What "View" should do once the Listen list has loaded.
enum ViewAfterDownloadAction {
  /// Open a specific saved entry's player (the index into the list passed in).
  openEntry,

  /// Do not open anything; scroll to and briefly highlight the newest entry.
  /// Reached only when nothing could be opened (no ids offered, or none of the
  /// offered ids matched a saved entry).
  highlightNewest,
}

/// The decision produced by [planViewAfterDownload]. Immutable and comparable
/// so tests can assert it directly.
class ViewAfterDownloadPlan {
  const ViewAfterDownloadPlan.openEntry(this.entryIndex)
      : action = ViewAfterDownloadAction.openEntry;

  const ViewAfterDownloadPlan.highlightNewest()
      : action = ViewAfterDownloadAction.highlightNewest,
        entryIndex = null;

  final ViewAfterDownloadAction action;

  /// Index into the `entries` list of the entry to open. Null when
  /// [action] is [ViewAfterDownloadAction.highlightNewest].
  final int? entryIndex;

  @override
  bool operator ==(Object other) =>
      other is ViewAfterDownloadPlan &&
      other.action == action &&
      other.entryIndex == entryIndex;

  @override
  int get hashCode => Object.hash(action, entryIndex);

  @override
  String toString() => action == ViewAfterDownloadAction.openEntry
      ? 'ViewAfterDownloadPlan.openEntry($entryIndex)'
      : 'ViewAfterDownloadPlan.highlightNewest()';
}

/// True when [entry] is a translation (saved with `is_translation: true`).
bool _isTranslation(Map<String, dynamic> entry) {
  final v = entry['is_translation'];
  return v == true || v == 'true';
}

/// The target language of a translation entry (e.g. 'ru'), or null. Originals
/// have no `language` field; [LOCAL-716B] stamps it onto every translation.
String? _entryLanguage(Map<String, dynamic> entry) {
  final raw = entry['language']?.toString().trim();
  if (raw == null || raw.isEmpty) return null;
  return raw;
}

/// Does [entry] belong to the tour whose server id is [wantedServerId]? An
/// entry matches when ANY of its id keys equals the offered id:
///   * `server_tour_id` / `tour_id` — the original's own ids, and (for a
///     translation) its OWN translated id;
///   * `parent_server_tour_id` — [LOCAL-716B] the ORIGINAL server id stamped
///     onto a translation at save time. The snackbar offers the ORIGINAL id
///     (e.g. 117), but a translation's own ids are its translated id (e.g.
///     437) with a non-numeric / null `parent_tour_id`; without this key the
///     Russian copy could not be tied to the offered 117 — the Pixel-4 miss.
bool _belongsToTour(Map<String, dynamic> entry, String wantedServerId) {
  for (final key in const [
    'server_tour_id',
    'tour_id',
    'parent_server_tour_id',
  ]) {
    final raw = entry[key]?.toString();
    if (raw != null && raw == wantedServerId) return true;
  }
  return false;
}

/// Decide what "View" does after a download. View ALWAYS opens a player when
/// anything can be opened.
///
/// Given the loaded saved [entries] (in ANY order — this reads `created` to
/// order them), the SERVER tour ids downloaded this run IN THE ORDER THE USER
/// SELECTED THEM ([downloadedTourIds]; one element for a single tour, several
/// for a batch — a tour that failed to download is simply absent), and the
/// resolved [listeningLanguage] (About / per-community, or null — defaults to
/// English):
///
///   * opens the FIRST id in [downloadedTourIds] that has a matching saved
///     entry, choosing the copy in the language just downloaded (the single
///     translation, the listening-language translation when there are several,
///     or the original when there are none);
///   * returns [ViewAfterDownloadPlan.highlightNewest] only when
///     [downloadedTourIds] is empty or NONE of its ids matches any saved entry
///     (the caller logs the miss and falls back to highlighting the newest).
ViewAfterDownloadPlan planViewAfterDownload({
  required List<Map<String, dynamic>> entries,
  required List<String> downloadedTourIds,
  String? listeningLanguage,
}) {
  // Walk the offered ids in selection order and open the first one that has a
  // saved entry. A tour the caller lists but that saved no entry (should not
  // happen — ids are added only after a successful save) is skipped rather
  // than stranding "View" on it.
  for (final rawId in downloadedTourIds) {
    final wantedServerId = rawId.trim();
    if (wantedServerId.isEmpty) continue;

    // Gather every saved entry that belongs to this tour, keeping each one's
    // original index so we can return a stable pointer into `entries`.
    final matches = <int>[];
    for (var i = 0; i < entries.length; i++) {
      if (_belongsToTour(entries[i], wantedServerId)) matches.add(i);
    }
    if (matches.isEmpty) continue; // try the next selected tour

    return _planForTour(entries, matches, listeningLanguage);
  }

  // Nothing could be opened (no ids, or no id matched a saved entry). No silent
  // miss: the caller logs and falls back to the highlight path.
  return const ViewAfterDownloadPlan.highlightNewest();
}

/// Pick the copy of ONE tour to open, from the indices [matches] of its saved
/// entries, applying the "language just downloaded" rule.
ViewAfterDownloadPlan _planForTour(
  List<Map<String, dynamic>> entries,
  List<int> matches,
  String? listeningLanguage,
) {
  final translations =
      matches.where((i) => _isTranslation(entries[i])).toList();
  final originals =
      matches.where((i) => !_isTranslation(entries[i])).toList();

  // No translation downloaded → open the original.
  if (translations.isEmpty) {
    return ViewAfterDownloadPlan.openEntry(originals.first);
  }

  // Exactly one translation → open it (the single language just downloaded).
  if (translations.length == 1) {
    return ViewAfterDownloadPlan.openEntry(translations.first);
  }

  // Several translations → prefer the one in the listening language; else the
  // first one downloaded (oldest `created`).
  final wantedLang = (listeningLanguage ?? '').trim().toLowerCase();
  if (wantedLang.isNotEmpty) {
    for (final i in translations) {
      final lang = _entryLanguage(entries[i])?.toLowerCase();
      if (lang == wantedLang) return ViewAfterDownloadPlan.openEntry(i);
    }
  }

  // Fall back to the first translation downloaded (oldest `created`).
  final firstDownloaded = _oldestByCreated(entries, translations);
  return ViewAfterDownloadPlan.openEntry(firstDownloaded);
}

/// The index (from [candidates]) of the entry with the EARLIEST `created`
/// timestamp — "the first one downloaded". Entries with an unparseable or
/// missing `created` sort last so a real timestamp always wins. Ties keep the
/// earliest index in [candidates] (stable).
int _oldestByCreated(
    List<Map<String, dynamic>> entries, List<int> candidates) {
  int best = candidates.first;
  DateTime? bestTime = _created(entries[best]);
  for (final i in candidates.skip(1)) {
    final t = _created(entries[i]);
    if (bestTime == null) {
      // Current best has no time; any entry with a time beats it.
      if (t != null) {
        best = i;
        bestTime = t;
      }
      continue;
    }
    if (t != null && t.isBefore(bestTime)) {
      best = i;
      bestTime = t;
    }
  }
  return best;
}

DateTime? _created(Map<String, dynamic> entry) {
  final raw = entry['created']?.toString();
  if (raw == null || raw.isEmpty) return null;
  return DateTime.tryParse(raw);
}

/// The index of the NEWEST saved entry (latest `created`) in [entries], for the
/// highlight path. Returns null for an empty list. Entries with no parseable
/// `created` are treated as oldest. Ties keep the LATER index (so a freshly
/// appended entry wins over an equally-timestamped earlier one).
///
/// NOTE: MyToursScreen displays `_tours` as `reversed` (newest first), so the
/// list the user sees is newest-at-top. This returns the index into the
/// UNREVERSED saved order; the caller maps it to the displayed position.
int? newestEntryIndex(List<Map<String, dynamic>> entries) {
  if (entries.isEmpty) return null;
  int best = 0;
  DateTime? bestTime = _created(entries[0]);
  for (var i = 1; i < entries.length; i++) {
    final t = _created(entries[i]);
    if (t == null) continue;
    if (bestTime == null || !t.isBefore(bestTime)) {
      best = i;
      bestTime = t;
    }
  }
  return best;
}
