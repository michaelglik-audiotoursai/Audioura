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

/// The display names for the listening languages, mirroring the names in
/// widgets/language_selector. Kept here (dependency-free) so both About and the
/// community page show identical names from ONE source.
const Map<String, String> kListeningLanguageNames = {
  'en': 'English',
  'ru': 'Русский',
  'es': 'Español',
  'fr': 'Français',
  'de': 'Deutsch',
  'zh': '中文',
};

/// The display name for a listening-language [code], falling back to the code
/// itself for an unknown one.
String listeningLanguageName(String code) =>
    kListeningLanguageNames[code] ?? code;

/// The fallback listening language when the phone's language is not one
/// Audioura offers (D675 §1: "otherwise English"; "maybe start with English").
const String kDefaultListeningLanguage = 'en';

/// The saved-setting key for the chosen listening language. This is About's
/// "Listening language" — the DEFAULT for every community (D675 addendum 1).
const String kListeningLanguagePrefKey = 'listening_language';

/// [LOCAL-715 / D675 addendum 1] The per-community listening-language key:
/// `listening_language_<community_id>`. When set, this community's tours
/// download in this language; when absent, the page falls back to About's
/// `listening_language` (then the phone locale, then English). A member can
/// hear the Book Club in Russian and the Boston Walkers in English.
String communityLanguagePrefKey(int communityId) =>
    'listening_language_$communityId';

/// [LOCAL-715 / D675 addendum 1] PURE precedence resolver for the language a
/// given community's tours download in. Total, dependency-free, so all four
/// cases are unit-tested without a running app:
///   1. [communityChoice] — the per-community key, when set (non-empty);
///   2. else [aboutDefault] — About's saved Listening language, when set;
///   3. else the phone's [localeLanguageCode] when Audioura offers it;
///   4. else English.
/// (3) + (4) are exactly About's own default (defaultListeningLanguage), so a
/// community with no choice and no About setting resolves the same way About
/// would — the phone's language, else English.
String resolveCommunityLanguage({
  String? communityChoice,
  String? aboutDefault,
  String? localeLanguageCode,
}) {
  final chosen = (communityChoice ?? '').trim();
  if (chosen.isNotEmpty) return chosen;
  final about = (aboutDefault ?? '').trim();
  if (about.isNotEmpty) return about;
  return defaultListeningLanguage(localeLanguageCode);
}

/// The per-community auto-download switch key (default OFF). LOCAL-714 writes it
/// at the join question; LOCAL-713 reads it for the sync-on-open baseline.
String autoDownloadPrefKey(int communityId) => 'auto_download_$communityId';

/// [LOCAL-715 / D675 addendum 1] The ONE place that resolves the language a
/// community's tours download in, from SharedPreferences. Reads the
/// per-community key (`listening_language_<id>`) and About's `listening_language`,
/// then applies [resolveCommunityLanguage]. The sync on open, the background
/// worker and the community-page Download button ALL call this — no other place
/// may read `listening_language` for community tours (D675 addendum 1).
///
/// [localeLanguageCode] is the phone locale's language code (e.g. from
/// `WidgetsBinding.instance.platformDispatcher.locale.languageCode`); passed in
/// so this helper stays free of Flutter bindings and is testable.
String languageForCommunity(
  SharedPreferences prefs,
  int communityId, {
  String? localeLanguageCode,
}) {
  return resolveCommunityLanguage(
    communityChoice: prefs.getString(communityLanguagePrefKey(communityId)),
    aboutDefault: prefs.getString(kListeningLanguagePrefKey),
    localeLanguageCode: localeLanguageCode,
  );
}

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
///      then plan it, in the listener's language FOR THAT COMMUNITY when the
///      tour has it, else the original (pickDownloadLanguage).
///
/// [LOCAL-715 / D675 addendum 1] The listening language is PER COMMUNITY: the
/// caller passes [languageByCommunity] (community id → the resolved language
/// from languageForCommunity). [preferredLanguage] is the fallback used only
/// for a community not present in the map (and keeps older callers/tests
/// working). So two communities with different per-community languages produce
/// two different download languages from one sync.
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
    Map<int, String> languageByCommunity = const {},
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
      // The listener's language FOR THIS COMMUNITY (D675 addendum 1), falling
      // back to the global preferred for a community not in the map.
      final preferredForCommunity =
          languageByCommunity[t.communityId] ?? preferredLanguage;
      final lang = pickDownloadLanguage(
        t.languages,
        preferredForCommunity,
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

// ─── [LOCAL-746 / D675 §4 addendum] Version-aware RE-DOWNLOAD of a held tour ──
//
// Why this exists (Michael, 2026-10-23): an organiser edits the Salem community
// tour on the iPhone; the member's Pixel-4 must get the change. LOCAL-745 made
// the server side work — the edit replaces the tour in place, archives the old
// content and the version RISES (map-delivery reports it, LOCAL-657). But the
// app's sync-on-open never re-downloads a tour already on the phone: SyncPlanner
// skips held ids and the edit never appears in /communities/new-tours (that
// endpoint filters created_at > since, and an in-place edit keeps created_at).
// So the member kept the old audio (SUBMISSION_LOCAL-745 §Req 3).
//
// RefreshPlanner is the PURE policy for the OTHER half of the sync: for the
// community tours ALREADY on the phone, re-download the ones whose server
// version rose above the saved one — and nothing else. Kept here, dependency-
// free, alongside SyncPlanner so it is unit-tested without a running app.

/// A community tour ALREADY on the phone, with the facts the refresh planner
/// needs. [savedVersion] is the LOCAL-657 version stamped on the saved record
/// at download (absent → 1); [serverVersion] is the tour's CURRENT version read
/// from the server now (the same LOCAL-657 number map-delivery reports).
/// [isCommunityTour] is false for an ordinary tour (no community_id) — such a
/// tour is NEVER re-downloaded, so the member's own generations are untouched.
class HeldCommunityTour {
  final int tourId;
  final int communityId;
  final int savedVersion;
  final int serverVersion;

  /// The language the held copy is in, so the re-download pulls the SAME
  /// language the member already had (not a surprise switch to the original).
  final String language;

  /// Whether this is a community tour (carries a community_id). An ordinary
  /// tour is false and is excluded by the planner.
  final bool isCommunityTour;

  /// The tour's display name, for the "<name> was updated by the organiser."
  /// message after a successful refresh.
  final String name;

  const HeldCommunityTour({
    required this.tourId,
    required this.communityId,
    required this.savedVersion,
    required this.serverVersion,
    required this.language,
    required this.isCommunityTour,
    required this.name,
  });
}

/// One re-download the refresh planner decided to perform: WHICH held tour, in
/// WHICH language, to WHICH server version (for the new "v2 · updated" label and
/// the message).
class PlannedRefresh {
  final int tourId;
  final int communityId;
  final int serverVersion;
  final String language;
  final String name;

  const PlannedRefresh({
    required this.tourId,
    required this.communityId,
    required this.serverVersion,
    required this.language,
    required this.name,
  });

  @override
  bool operator ==(Object other) =>
      other is PlannedRefresh &&
      other.tourId == tourId &&
      other.communityId == communityId &&
      other.serverVersion == serverVersion &&
      other.language == language &&
      other.name == name;

  @override
  int get hashCode =>
      Object.hash(tourId, communityId, serverVersion, language, name);

  @override
  String toString() =>
      'PlannedRefresh(t:$tourId, c:$communityId, v:$serverVersion, '
      'lang:$language, name:$name)';
}

/// The PURE re-download planner (LOCAL-746). Given the community tours already
/// on the phone — each with its saved version and the server's CURRENT version
/// — plus the communities the member is still active in (or owns), the deleted
/// set, the connectivity and the cellular allowance, it returns EXACTLY the
/// re-downloads to perform. No I/O.
///
/// Rules, in order:
///   1. offline (none)                      → re-download nothing.
///   2. metered + cellular not allowed      → re-download nothing.
///   3. for each held tour:
///        * it must be a COMMUNITY tour (isCommunityTour) — an ordinary tour is
///          never re-downloaded;
///        * the server version must be STRICTLY GREATER than the saved one
///          (an unchanged tour, or a stale/lower server read, is skipped — never
///          a downgrade);
///        * its community must be in [activeCommunityIds] — the member is still
///          active, or owns it (an expired membership contributes nothing);
///        * it must NOT be in the user's [deletedTourIds] (a tour the member
///          deleted is never brought back, D675 §6).
///
/// The result preserves the input order of [held].
class RefreshPlanner {
  static List<PlannedRefresh> plan({
    required List<HeldCommunityTour> held,
    required Set<int> activeCommunityIds,
    required SyncConnection connection,
    required bool cellularAllowed,
    required Set<String> deletedTourIds,
  }) {
    // 1 + 2: the SAME connection gate as SyncPlanner. Nothing offline, and
    // nothing on a metered connection unless mobile data was explicitly allowed.
    if (connection == SyncConnection.none) return const [];
    if (connection == SyncConnection.metered && !cellularAllowed) {
      return const [];
    }

    final planned = <PlannedRefresh>[];
    for (final t in held) {
      // Only community tours (an ordinary tour is never re-downloaded).
      if (!t.isCommunityTour) continue;
      // The server version must have risen above the saved one.
      if (t.serverVersion <= t.savedVersion) continue;
      // The member must still be active in (or own) the community.
      if (!activeCommunityIds.contains(t.communityId)) continue;
      // Never re-download a tour the user deleted.
      if (deletedTourIds.contains(t.tourId.toString())) continue;
      planned.add(PlannedRefresh(
        tourId: t.tourId,
        communityId: t.communityId,
        serverVersion: t.serverVersion,
        language: t.language,
        name: t.name,
      ));
    }
    return planned;
  }
}

/// [LOCAL-746 Req 3] The ONE short message shown after a held tour is refreshed
/// to the organiser's new version. Kept here (dependency-free) so the wording is
/// unit-tested and comes from a single source.
String refreshedMessage(String tourName) =>
    '$tourName was updated by the organiser.';
