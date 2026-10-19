import 'package:shared_preferences/shared_preferences.dart';
// [LOCAL-713 / D675] Community-tour download foundation — PURE helpers.
//
// DEPENDENCY-FREE on purpose (no Flutter, no SharedPreferences, no http): the
// listening-language rules, the community-page row status, and the sync-on-open
// planner are plain functions here so they are unit-tested directly
// (test/community_downloads_test.dart) with no running app. The networked
// pieces (the About setting store, the Download button, the sync runner) live
// in the widgets/services that import this and call these functions.
//
// D675 recap:
//   * A saved LISTENING LANGUAGE (About → Listening language). Default = the
//     phone's language when Audioura supports it, else English.
//   * An auto-download takes that language if the tour already has it, otherwise
//     the tour's ORIGINAL language. v1 never requests a NEW translation.
//   * The community page shows each tour as Download / On this phone ✓ /
//     Join to download (non-member).
//   * Sync on open: for communities with auto-download ON, download each NEW
//     tour that is not already on the phone and was not deleted by the user,
//     only on an unmetered connection unless mobile data was allowed. Advance
//     the stored `since` only after the downloads succeed.

/// The languages Audioura offers — the SAME set as widgets/language_selector
/// (en, ru, es, fr, de, zh). Kept here as the dependency-free source of truth so
/// the listening-language default can be computed without importing a widget.
const List<String> kListeningLanguages = ['en', 'ru', 'es', 'fr', 'de', 'zh'];

/// The fallback listening language when the phone's language is not one
/// Audioura offers (D675 §1: "otherwise English"; "maybe start with English").
const String kDefaultListeningLanguage = 'en';

/// The saved-setting key for the chosen listening language.
const String kListeningLanguagePrefKey = 'listening_language';

/// The per-community auto-download switch key (default OFF). LOCAL-714 writes it
/// at the join question; LOCAL-713 reads it for the sync-on-open baseline.
String autoDownloadPrefKey(int communityId) => 'auto_download_$communityId';

/// Whether the member allowed auto-downloads on mobile data (default false —
/// Wi-Fi/unmetered only). One switch for the whole app (D675 §2/§3).
const String kAutoDownloadCellularPrefKey = 'auto_download_cellular';

/// The stored `since` for the new-tours sync (the server_time of the last
/// successful sync). Blank/absent means "from the beginning".
const String kNewToursSincePrefKey = 'community_tours_since';

/// The local set of tour ids the user DELETED, so a deleted tour is never
/// re-downloaded automatically (D675 §6). Stored as a string list of tour ids.
const String kDeletedTourIdsPrefKey = 'deleted_tour_ids';

/// [LEAD review of LOCAL-713] Record a tour the listener deleted from Listen so
/// the community sync never brings it back (D675 §6). Records both ids the
/// on-phone check uses (`tour_id`, `server_tour_id`).
Future<void> recordDeletedTours(
    SharedPreferences prefs, Iterable<Map<String, dynamic>> tours) async {
  final set = (prefs.getStringList(kDeletedTourIdsPrefKey) ?? const []).toSet();
  for (final t in tours) {
    for (final k in const ['tour_id', 'server_tour_id']) {
      final v = t[k];
      if (v != null && v.toString().isNotEmpty) set.add(v.toString());
    }
  }
  await prefs.setStringList(kDeletedTourIdsPrefKey, set.toList());
}

/// Pick the language to download a tour in (D675 §1). The listener's [preferred]
/// language wins when the tour already HAS it; otherwise the tour's [original]
/// language is used (v1 never requests a new translation). [available] is the
/// tour's language list from the server (original first, then finished
/// translations). Pure + total:
///   * preferred is available        → preferred
///   * preferred not available       → original (when original is non-empty)
///   * original blank but available  → original is derived from available[0]
///   * nothing available             → preferred (last resort; the caller's
///                                     download will 404 harmlessly rather than
///                                     this returning an empty string)
String pickDownloadLanguage(
  List<String> available,
  String preferred,
  String original,
) {
  if (preferred.isNotEmpty && available.contains(preferred)) {
    return preferred;
  }
  if (original.isNotEmpty) return original;
  if (available.isNotEmpty) return available.first;
  return preferred;
}

/// The default listening language for a phone whose locale language code is
/// [localeLanguageCode] (e.g. 'de', 'EN', 'pt'). The phone's language when
/// Audioura offers it (case-insensitively), else English (D675 §1).
String defaultListeningLanguage(String? localeLanguageCode) {
  final code = (localeLanguageCode ?? '').trim().toLowerCase();
  if (code.isNotEmpty && kListeningLanguages.contains(code)) return code;
  return kDefaultListeningLanguage;
}

/// The status of one community tour row on the community page (D675 §5).
enum CommunityTourRowStatus {
  /// A non-member: the row shows "Join to download" (D663).
  joinToDownload,

  /// Already in Listen (any language): "On this phone ✓".
  onThisPhone,

  /// A member, not yet on the phone: a "Download" button that runs the SAME
  /// download path a Home/Listen download uses.
  download,
}

/// Decide the row status for a community tour (D675 §5). PURE.
///   * not a member (and not the owner)    → joinToDownload
///   * the tour id is already on the phone  → onThisPhone  (any language counts)
///   * otherwise                            → download
///
/// [onPhoneTourIds] is the set of server tour ids already saved on the device
/// (from the `saved_tours` records' tour_id). A member (or the owner — the
/// organiser has full access) who does not have the tour sees Download.
CommunityTourRowStatus rowStatusFor({
  required int tourId,
  required bool isMember,
  required bool isOwner,
  required Set<String> onPhoneTourIds,
}) {
  final canDownload = isMember || isOwner;
  if (!canDownload) return CommunityTourRowStatus.joinToDownload;
  if (onPhoneTourIds.contains(tourId.toString())) {
    return CommunityTourRowStatus.onThisPhone;
  }
  return CommunityTourRowStatus.download;
}

/// A new community tour as returned by GET /communities/new-tours — the minimal
/// shape the pure planner needs. DEPENDENCY-FREE (no JSON decode here; the
/// service builds these from the response).
class NewCommunityTour {
  final int communityId;
  final int tourId;

  /// The tour's languages, original first (used to pick the download language).
  final List<String> languages;

  /// The tour's original language (languages.first on the server, but carried
  /// explicitly so the planner does not have to assume).
  final String originalLanguage;

  /// The community name + the tour's short title (for UI/notifications). Not
  /// needed by the planner, but carried for the caller.
  final String communityName;
  final String shortTitle;
  final int stopCount;
  final String? createdAt;

  const NewCommunityTour({
    required this.communityId,
    required this.tourId,
    required this.languages,
    required this.originalLanguage,
    this.communityName = '',
    this.shortTitle = '',
    this.stopCount = 0,
    this.createdAt,
  });

  /// Build from one /communities/new-tours row. `languages` leads with the
  /// original language, so originalLanguage is languages.first (en when empty).
  factory NewCommunityTour.fromJson(Map<String, dynamic> j) {
    final rawLangs = (j['languages'] as List?) ?? const [];
    final langs = rawLangs.whereType<String>().toList(growable: false);
    return NewCommunityTour(
      communityId:
          (j['community_id'] is num) ? (j['community_id'] as num).toInt() : 0,
      tourId: (j['tour_id'] is num) ? (j['tour_id'] as num).toInt() : 0,
      languages: langs,
      originalLanguage: langs.isNotEmpty ? langs.first : kDefaultListeningLanguage,
      communityName: (j['community_name'] ?? '') as String,
      shortTitle: (j['short_title'] ?? '') as String,
      stopCount: (j['stop_count'] is num) ? (j['stop_count'] as num).toInt() : 0,
      createdAt: j['created_at'] as String?,
    );
  }
}

/// The full result of GET /communities/new-tours: the tours plus the
/// `server_time` to store as the next `since` AFTER the downloads succeed.
class NewToursResult {
  final List<NewCommunityTour> tours;
  final String? serverTime;

  const NewToursResult({required this.tours, this.serverTime});

  static const NewToursResult empty = NewToursResult(tours: [], serverTime: null);

  factory NewToursResult.fromJson(Map<String, dynamic> j) {
    final raw = (j['tours'] as List?) ?? const [];
    return NewToursResult(
      tours: raw
          .whereType<Map<String, dynamic>>()
          .map(NewCommunityTour.fromJson)
          .toList(growable: false),
      serverTime: j['server_time'] as String?,
    );
  }
}

/// One download the planner decided to perform: WHICH tour, in WHICH language.
class PlannedDownload {
  final int communityId;
  final int tourId;
  final String language;

  const PlannedDownload({
    required this.communityId,
    required this.tourId,
    required this.language,
  });

  @override
  bool operator ==(Object other) =>
      other is PlannedDownload &&
      other.communityId == communityId &&
      other.tourId == tourId &&
      other.language == language;

  @override
  int get hashCode => Object.hash(communityId, tourId, language);

  @override
  String toString() =>
      'PlannedDownload(c:$communityId, t:$tourId, lang:$language)';
}

/// The connection kind the planner gates on. `unmetered` is Wi-Fi/ethernet;
/// `metered` is mobile data; `none` is offline.
enum SyncConnection { none, unmetered, metered }

/// Whether to advance the stored `since` to the server_time after a sync run
/// (D675 §: advance only on success). PURE. We advance when there was a
/// successful round trip ([haveServerTime]) AND no planned download FAILED
/// ([failedCount] == 0) — a partial failure leaves `since` so the next open
/// retries the ones that failed (never skipped). A run that planned nothing
/// (everything already on phone / switches off) still advances, because the
/// round trip succeeded and re-evaluating the same tours forever is pointless.
bool shouldAdvanceSince({
  required bool haveServerTime,
  required int failedCount,
}) {
  if (!haveServerTime) return false;
  return failedCount == 0;
}

/// The PURE sync-on-open planner (D675 §4). Given the new tours, what is on the
/// phone, what the user deleted, the connectivity, the per-community switches
/// and the cellular allowance, it returns EXACTLY the downloads to perform —
/// and NOTHING on a metered connection unless the member allowed mobile data.
/// No I/O: the caller performs the returned downloads via the existing path and
/// only then advances `since`.
///
/// Rules, in order:
///   1. offline (none)                     → download nothing.
///   2. metered + cellular not allowed      → download nothing.
///   3. for each new tour:
///        * its community's auto-download switch must be ON;
///        * the tour id must NOT already be on the phone;
///        * the tour id must NOT be in the user's deleted set (never re-download
///          automatically, D675 §6);
///      then plan it, in the listener's language when available else the
///      original (pickDownloadLanguage).
///
/// The result preserves the input order of [newTours] (newest first from the
/// server), so the caller downloads newest first.
class SyncPlanner {
  static List<PlannedDownload> plan({
    required List<NewCommunityTour> newTours,
    required Set<String> onPhoneTourIds,
    required Set<String> deletedTourIds,
    required SyncConnection connection,
    required bool cellularAllowed,
    required Set<int> autoDownloadCommunityIds,
    required String preferredLanguage,
  }) {
    // 1 + 2: the connection gate. Nothing downloads offline, and nothing on a
    // metered connection unless mobile data was explicitly allowed.
    if (connection == SyncConnection.none) return const [];
    if (connection == SyncConnection.metered && !cellularAllowed) {
      return const [];
    }

    final planned = <PlannedDownload>[];
    for (final t in newTours) {
      // The per-community auto-download switch must be ON.
      if (!autoDownloadCommunityIds.contains(t.communityId)) continue;
      final idStr = t.tourId.toString();
      // Already on the phone → skip.
      if (onPhoneTourIds.contains(idStr)) continue;
      // Deleted by the user → never re-download automatically.
      if (deletedTourIds.contains(idStr)) continue;
      final lang = pickDownloadLanguage(
        t.languages,
        preferredLanguage,
        t.originalLanguage,
      );
      planned.add(PlannedDownload(
        communityId: t.communityId,
        tourId: t.tourId,
        language: lang,
      ));
    }
    return planned;
  }
}
