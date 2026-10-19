// [LOCAL-716B / D358] PURE planner for the download snackbar's "View" button.
//
// Michael tested 2.4.30+72 on the Pixel-4: he downloaded ONE tour with its
// Russian translation. The message was right ("1 tour downloaded with 1
// translation … is"), but "View" opened nothing — it showed the Listen list
// and stopped. Two faults fed that:
//   * Home offered a tour id only when exactly one FILE was downloaded; a
//     translation is a second file, so it offered null and View just showed
//     the list.
//   * My Tours matched the offered id against a saved entry's `tour_id` /
//     `server_tour_id` and, on a miss, returned silently — a translation's
//     saved entry keys differently from the English original, so even a
//     correct offer could miss with no trace.
//
// This file is the ONE place that decides, from the saved entries alone, WHICH
// copy "View" opens for a single downloaded tour, and otherwise says "highlight
// the newest". It is dependency-free (no Flutter, no SharedPreferences, no
// http) so every branch is unit-tested directly (test/view_after_download_test
// .dart) with plain maps — the same style as community_downloads.dart.
//
// The rule (D358 required behaviour):
//   1. A tour is ONE tour even with translations — we match on the SERVER tour
//      id the snackbar offers, across the original and every translation of it.
//   2. For exactly one tour, open the copy in the language just downloaded:
//        * exactly one translation  → that translation;
//        * several translations      → the one matching the listening language
//          if present, else the first one downloaded (oldest `created`);
//        * no translation            → the original.
//   3. For several tours, there is no single id to open: highlight the newest.
//   4. No silent miss: when nothing matches the offered id, the caller logs it
//      and falls back to the highlight path — this planner returns
//      [ViewAfterDownloadPlan.highlightNewest] for that case too.
library;

/// What "View" should do once the Listen list has loaded.
enum ViewAfterDownloadAction {
  /// Open a specific saved entry's player (the index into the list passed in).
  openEntry,

  /// Do not open anything; scroll to and briefly highlight the newest entry.
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

/// Decide what "View" does after a download, given the loaded saved [entries]
/// (in ANY order — this reads `created` to order them), the number of distinct
/// tours downloaded this run ([downloadedTourCount]), the SERVER tour id the
/// snackbar offered ([wantedServerId], null when several tours were
/// downloaded), and the resolved [listeningLanguage] (About / per-community, or
/// null — defaults to English).
///
/// Returns [ViewAfterDownloadPlan.openEntry] with the index of the entry to
/// open for a single tour that has a match, or
/// [ViewAfterDownloadPlan.highlightNewest] when several tours were downloaded,
/// no id was offered, or no saved entry matches the offered id.
ViewAfterDownloadPlan planViewAfterDownload({
  required List<Map<String, dynamic>> entries,
  required int downloadedTourCount,
  String? wantedServerId,
  String? listeningLanguage,
}) {
  // Several tours (or none identifiable) → highlight the newest, never open.
  if (downloadedTourCount != 1 ||
      wantedServerId == null ||
      wantedServerId.isEmpty) {
    return const ViewAfterDownloadPlan.highlightNewest();
  }

  // Gather every saved entry that belongs to the offered tour, keeping each
  // one's original index so we can return a stable pointer into `entries`.
  final matches = <int>[];
  for (var i = 0; i < entries.length; i++) {
    if (_belongsToTour(entries[i], wantedServerId)) matches.add(i);
  }
  if (matches.isEmpty) {
    // No silent miss: the caller logs and falls back to the highlight path.
    return const ViewAfterDownloadPlan.highlightNewest();
  }

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
