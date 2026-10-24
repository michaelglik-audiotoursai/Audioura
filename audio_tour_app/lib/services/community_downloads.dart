import 'dart:convert';

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

/// [LOCAL-752 C] PURE: remove the given tour [ids] from a [deleted] set of tour
/// ids. Returns a NEW set (the input is not mutated). Ids may be int or String —
/// both are compared as their string form (the deleted set stores strings, the
/// same way `recordDeletedTours` writes them). Removing an id that was not in the
/// set is a harmless no-op.
Set<String> removeFromDeletedTourIds(Set<String> deleted, Iterable<Object> ids) {
  final out = deleted.toSet();
  for (final id in ids) {
    out.remove(id.toString());
  }
  return out;
}

/// [LOCAL-752 C] Clear the given tour [ids] from the persisted `deleted_tour_ids`
/// so an EXPLICIT download/re-download lets the tour sync again.
///
/// Michael's history (2026-10-23): he deleted community tour 716 on the Pixel
/// (the deleted set held "716"), then re-downloaded it from the community page.
/// The organiser's edit took the server to v3, but RefreshPlanner skips any id in
/// `deleted_tour_ids`, so "716" was skipped forever and the edit never arrived.
/// Any explicit download/re-download (TourDownloadService.saveTourToMyTours /
/// reDownloadAndReplace) now calls this, removing the id so the next sync refresh
/// picks up the organiser's version and shows the "… was updated by the
/// organiser." message. A no-op when the list is absent or the id was not there.
Future<void> clearDeletedTourIds(
    SharedPreferences prefs, Iterable<Object> ids) async {
  final current = prefs.getStringList(kDeletedTourIdsPrefKey);
  if (current == null || current.isEmpty) return;
  final after = removeFromDeletedTourIds(current.toSet(), ids);
  if (after.length != current.toSet().length) {
    await prefs.setStringList(kDeletedTourIdsPrefKey, after.toList());
  }
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

  /// [LOCAL-755 / D709] Whether this is an ORGANISER-AUDIO tour (source_kind =
  /// 'organiser_audio', built from the organiser's own hosted audio). A member
  /// is NEVER pushed an organiser-audio update (even with auto-download on): the
  /// planner SKIPS it so it is never auto-re-downloaded. Instead the member opts
  /// in by tapping "Re-download" on the Listen/community row. A generated
  /// community tour (false) keeps today's auto-refresh behaviour (Rule 4).
  final bool isOrganiserAudio;

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
    this.isOrganiserAudio = false,
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
      // [LOCAL-755 / D709] Rule 3: a member is NEVER pushed an organiser-audio
      // update (even with auto-download on). Skip organiser-audio tours here —
      // the member opts in by tapping "Re-download" on the Listen/community row.
      // A generated community tour (isOrganiserAudio false) keeps today's
      // auto-refresh (Rule 4).
      if (t.isOrganiserAudio) continue;
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

/// [LOCAL-755 / D709 Rule 3] One organiser-audio update to OFFER the member —
/// never pushed. The member opts in by tapping "Re-download"; this value feeds
/// the one in-app message and the row affordance.
class PlannedOrganiserAudioUpdate {
  final int tourId;
  final int communityId;
  final int serverVersion;
  final String language;
  final String name;

  const PlannedOrganiserAudioUpdate({
    required this.tourId,
    required this.communityId,
    required this.serverVersion,
    required this.language,
    required this.name,
  });

  @override
  bool operator ==(Object other) =>
      other is PlannedOrganiserAudioUpdate &&
      other.tourId == tourId &&
      other.communityId == communityId &&
      other.serverVersion == serverVersion &&
      other.language == language &&
      other.name == name;

  @override
  int get hashCode =>
      Object.hash(tourId, communityId, serverVersion, language, name);

  @override
  String toString() => 'PlannedOrganiserAudioUpdate(t:$tourId, c:$communityId, '
      'v:$serverVersion, lang:$language, name:$name)';
}

/// [LOCAL-755 / D709 Rule 3] The PURE policy for ORGANISER-AUDIO updates. A
/// member is NEVER pushed an organiser-audio update (even with auto-download
/// on): RefreshPlanner skips these. Instead, for the organiser-audio tours
/// ALREADY on the phone whose server version rose above the saved one, this
/// returns the ones to OFFER — one in-app message ("… was updated by the
/// organiser. Re-download?") and a Listen/community row affordance. The member
/// taps to re-download (package + MP3s from the organiser host).
///
/// Unlike RefreshPlanner there is NO connection gate: nothing is downloaded
/// here, only offered. The tap performs the download (TourDownloadService), and
/// that call is where connectivity matters.
///
/// Rules, in order, per held tour:
///   * it must be an organiser-audio COMMUNITY tour (isOrganiserAudio &&
///     isCommunityTour);
///   * the server version must be STRICTLY GREATER than the saved one;
///   * its community must be active/owned ([activeCommunityIds]);
///   * it must NOT be in [deletedTourIds] (a deleted tour is never resurfaced).
///
/// The result preserves the input order of [held].
class OrganiserAudioUpdatePlanner {
  static List<PlannedOrganiserAudioUpdate> plan({
    required List<HeldCommunityTour> held,
    required Set<int> activeCommunityIds,
    required Set<String> deletedTourIds,
  }) {
    final out = <PlannedOrganiserAudioUpdate>[];
    for (final t in held) {
      if (!t.isCommunityTour || !t.isOrganiserAudio) continue;
      if (t.serverVersion <= t.savedVersion) continue;
      if (!activeCommunityIds.contains(t.communityId)) continue;
      if (deletedTourIds.contains(t.tourId.toString())) continue;
      out.add(PlannedOrganiserAudioUpdate(
        tourId: t.tourId,
        communityId: t.communityId,
        serverVersion: t.serverVersion,
        language: t.language,
        name: t.name,
      ));
    }
    return out;
  }
}

/// [LOCAL-755 Rule 3] The ONE short in-app message (LOCAL-750 mechanism) shown
/// when an organiser-audio tour the member holds was updated by the organiser.
/// PURE so the wording is a single source of truth. Unlike a generated tour
/// (refreshedMessage, past tense — it already re-downloaded), this ASKS: the
/// member opts in by tapping Re-download.
String organiserAudioUpdateMessage(String tourName) =>
    '$tourName was updated by the organiser. Re-download?';

/// [LOCAL-755 / D709 Rule 3] The Listen/community-page ROW label for an
/// ORGANISER-AUDIO tour the organiser has updated — a member opts in by tapping
/// it (members are never pushed an organiser-audio update). PURE so the wording
/// and the "when to show it" rule are a single source of truth, unit-tested
/// without a running app.
///
/// Returns the label "Updated by the organiser — Re-download" ONLY when the
/// server version is STRICTLY GREATER than the saved one (the organiser ticked
/// "I changed this tour — tell my members", bumping the version). Returns null
/// when the versions match (nothing new) or the server is lower (never a
/// downgrade) — so the row shows the ordinary version label instead.
String? organiserAudioUpdateLabel({
  required int savedVersion,
  required int serverVersion,
}) {
  if (serverVersion > savedVersion) {
    return 'Updated by the organiser — Re-download';
  }
  return null;
}

// ─── [LOCAL-748] Community-page download sourceItem + record stamping ────────
//
// Michael's test (2026-10-23): the organiser's edit never reached the member
// because the community-page Download saved the record with NO community_id and
// NO version — so CommunityToursSync._heldCommunityTourRecords skipped it and
// RefreshPlanner never saw it. The fix is two parts, both PURE here so they are
// unit-tested without a running app:
//   1. communityTourSourceItem — the sourceItem the community-page Download
//      passes to TourDownloadService.saveTourToMyTours, carrying the row's
//      community_id/version/updated_at so the saved record is stamped at
//      download time (saveTourToMyTours already reads these keys).
//   2. stampCommunityIdOnSavedRecords — repair records ALREADY on phones: when
//      the community page loads, stamp community_id (and version 1 when missing)
//      onto saved records whose server_tour_id matches one of that community's
//      tours. No re-download needed.

/// The sourceItem a community-page Download passes so the saved record carries
/// the community id, the tour's version and its updated_at (the keys
/// saveTourToMyTours reads). [version] defaults to 1 for a tour never edited;
/// [updatedAt] may be null. PURE.
Map<String, dynamic> communityTourSourceItem({
  required int communityId,
  int version = 1,
  String? updatedAt,
  // [LOCAL-760 build item 2 / D708] The tour's source_kind, when the community
  // page row carries one ('organiser_audio' for a broadcast tour). Passed
  // through so TourDownloadService.saveTourToMyTours stamps it on the saved
  // record at DOWNLOAD time — the root cause Michael hit was a member's
  // download record with no source_kind, so Listen kept Edit/Translate enabled.
  String? sourceKind,
}) {
  final m = <String, dynamic>{
    'community_id': communityId,
    'version': version,
  };
  if (updatedAt != null && updatedAt.isNotEmpty) m['updated_at'] = updatedAt;
  if (sourceKind != null && sourceKind.trim().isNotEmpty) {
    m['source_kind'] = sourceKind.trim();
  }
  return m;
}

/// [LOCAL-748] Repair the saved_tours records already on the phone so a tour
/// downloaded BEFORE this fix (no community_id, no version) becomes visible to
/// the held-tour refresh. Given the raw saved_tours JSON strings, the community
/// id, and the set of that community's server tour ids (as strings), it returns
/// a NEW list with community_id (and version 1 when missing) stamped onto every
/// record whose `server_tour_id` or `tour_id` matches one of the community's
/// tours AND does not already carry a community_id. Returns null when nothing
/// changed (so the caller can skip the write). PURE (JSON in, JSON out).
List<String>? stampCommunityIdOnSavedRecords({
  required List<String> savedToursJson,
  required int communityId,
  required Set<String> communityTourIds,
}) {
  if (communityTourIds.isEmpty) return null;
  var changed = false;
  final out = <String>[];
  for (final s in savedToursJson) {
    Map<String, dynamic>? m;
    try {
      final decoded = jsonDecode(s);
      if (decoded is Map<String, dynamic>) m = decoded;
    } catch (_) {}
    if (m == null) {
      out.add(s);
      continue;
    }
    final sid = (m['server_tour_id'] ?? '').toString();
    final tid = (m['tour_id'] ?? '').toString();
    final matches = (sid.isNotEmpty && communityTourIds.contains(sid)) ||
        (tid.isNotEmpty && communityTourIds.contains(tid));
    // Already carries a (non-zero) community_id → leave it alone.
    final rawCid = m['community_id'];
    final hasCid = rawCid is num
        ? rawCid.toInt() != 0
        : (rawCid is String && (int.tryParse(rawCid.trim()) ?? 0) != 0);
    if (matches && !hasCid) {
      m['community_id'] = communityId;
      // Stamp version 1 only when the record has no version at all, so the
      // refresh has a baseline to compare the server version against. Never
      // overwrite a real version.
      if (m['version'] == null && m['tour_version'] == null) {
        m['version'] = 1;
      }
      out.add(jsonEncode(m));
      changed = true;
    } else {
      out.add(s);
    }
  }
  return changed ? out : null;
}

/// [LOCAL-760 build item 2 / D708] True iff a downloaded tour FOLDER is an
/// organiser-audio tour, judged from its file list: an organiser-audio package
/// carries a `remote_audio.json` (stop N → the organiser's URL) and NO MP3 in
/// the ZIP (the phone fetches the audio on download). The repair below is
/// driven by this: a tour whose folder has remote_audio.json is stamped
/// source_kind='organiser_audio'. PURE (file names in, bool out).
bool isOrganiserAudioFromFiles(List<String> fileNames) {
  for (final f in fileNames) {
    final name = f.trim();
    // Match the bare file name whether or not the caller passed a path.
    final base = name.contains('/') ? name.split('/').last : name;
    if (base == 'remote_audio.json') return true;
  }
  return false;
}

/// [LOCAL-760 build item 2 / D708] Repair saved_tours records ALREADY on the
/// phone so a broadcast tour downloaded BEFORE source_kind was stamped (the
/// root cause Michael hit) becomes recognised — the Listen ⋮ menu then disables
/// Edit/Translate with an ⓘ. Given the set of this community's ORGANISER-AUDIO
/// tour ids (as strings — the caller derives them from the server listing's
/// source_kind, or from a folder's remote_audio.json via
/// [isOrganiserAudioFromFiles]), it stamps source_kind='organiser_audio' onto
/// every matching record that does not already carry it. Returns a NEW list, or
/// null when nothing changed (so the caller can skip the write). PURE.
List<String>? stampSourceKindOnSavedRecords({
  required List<String> savedToursJson,
  required Set<String> organiserAudioTourIds,
}) {
  if (organiserAudioTourIds.isEmpty) return null;
  var changed = false;
  final out = <String>[];
  for (final s in savedToursJson) {
    Map<String, dynamic>? m;
    try {
      final decoded = jsonDecode(s);
      if (decoded is Map<String, dynamic>) m = decoded;
    } catch (_) {}
    if (m == null) {
      out.add(s);
      continue;
    }
    final sid = (m['server_tour_id'] ?? '').toString();
    final tid = (m['tour_id'] ?? '').toString();
    final matches = (sid.isNotEmpty && organiserAudioTourIds.contains(sid)) ||
        (tid.isNotEmpty && organiserAudioTourIds.contains(tid));
    final already =
        (m['source_kind'] is String) && (m['source_kind'] as String).trim() ==
            'organiser_audio';
    if (matches && !already) {
      m['source_kind'] = 'organiser_audio';
      out.add(jsonEncode(m));
      changed = true;
    } else {
      out.add(s);
    }
  }
  return changed ? out : null;
}

// ─── [LOCAL-748] New-tour announcement policy (member's phone) ───────────────
//
// Michael's test: no announcement on the member's phone when the organiser adds
// a tour. When the sync finds a new tour in a community the user belongs to,
// show ONE short message. Once per tour; NEVER for the user's own tours (the
// owner made it). The pure policy here decides WHICH new tours to announce; the
// sync shell emits the message and records the announced ids.

/// One new-tour announcement the sync should surface: the tour id, its
/// community name and the tour's display title, plus whether it was
/// auto-downloaded (so the shell shows "View" vs "Download"). PURE value.
class NewTourAnnouncement {
  final int tourId;
  final String communityName;
  final String tourName;
  final bool autoDownloaded;

  const NewTourAnnouncement({
    required this.tourId,
    required this.communityName,
    required this.tourName,
    required this.autoDownloaded,
  });

  @override
  bool operator ==(Object other) =>
      other is NewTourAnnouncement &&
      other.tourId == tourId &&
      other.communityName == communityName &&
      other.tourName == tourName &&
      other.autoDownloaded == autoDownloaded;

  @override
  int get hashCode =>
      Object.hash(tourId, communityName, tourName, autoDownloaded);

  @override
  String toString() => 'NewTourAnnouncement(t:$tourId, c:$communityName, '
      'name:$tourName, auto:$autoDownloaded)';
}

/// The ONE short message for a new community tour (D675 part 2 §). PURE so the
/// wording is a single source of truth and unit-tested.
String newTourMessage(String communityName, String tourName) =>
    'New tour in $communityName: $tourName';

/// [LOCAL-748] PURE policy: which new tours to ANNOUNCE on the member's phone.
/// Given the new tours from /communities/new-tours, the ids of communities this
/// user OWNS (the user's own tours live there — never announced), the set of
/// ids ALREADY announced (announce once per tour), and the ids that were
/// auto-downloaded this run (so the message offers View rather than Download),
/// it returns EXACTLY the announcements to show, in the input order.
///
/// Rules, in order, per new tour:
///   * skip a tour in a community the user OWNS ([ownedCommunityIds]) — the
///     organiser made it, so the member is never told about their own tour;
///   * skip a tour already announced ([announcedTourIds]) — once per tour;
///   * otherwise announce it; autoDownloaded is true when its id is in
///     [autoDownloadedTourIds].
List<NewTourAnnouncement> planNewTourAnnouncements({
  required List<NewCommunityTour> newTours,
  required Set<int> ownedCommunityIds,
  required Set<String> announcedTourIds,
  required Set<int> autoDownloadedTourIds,
}) {
  final out = <NewTourAnnouncement>[];
  for (final t in newTours) {
    if (ownedCommunityIds.contains(t.communityId)) continue;
    if (announcedTourIds.contains(t.tourId.toString())) continue;
    final name =
        t.shortTitle.trim().isNotEmpty ? t.shortTitle.trim() : 'a new tour';
    out.add(NewTourAnnouncement(
      tourId: t.tourId,
      communityName: t.communityName,
      tourName: name,
      autoDownloaded: autoDownloadedTourIds.contains(t.tourId),
    ));
  }
  return out;
}

/// The SharedPreferences key for the set of new-tour ids already announced to
/// the member, so each is announced at most once (D675 part 2 §).
const String kAnnouncedNewTourIdsPrefKey = 'announced_new_tour_ids';

/// [LOCAL-755 / D709 Rule 3] The SharedPreferences key for the set of
/// organiser-audio updates already OFFERED to the member, keyed "<tourId>:<ver>"
/// so the one in-app "… was updated by the organiser. Re-download?" message
/// fires at most once per (tour, server version) — a later sync re-nags only if
/// a NEWER version appears. A member is never pushed the update, only offered.
const String kOfferedOrganiserAudioKey = 'offered_organiser_audio_updates';
