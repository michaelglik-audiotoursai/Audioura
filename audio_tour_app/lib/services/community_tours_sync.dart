// [LOCAL-713 / D675 §4] Community-tours SYNC ON OPEN — the baseline.
//
// When the app opens (and on resume), call /communities/new-tours with the
// stored `since`, plan the downloads with SyncPlanner (pure), run each via the
// SINGLE download path (TourDownloadService), and store `server_time` as the
// next `since` ONLY after the downloads succeed. LOCAL-714 adds the background
// WorkManager/iOS run; this is the baseline that always works.
//
// The POLICY is the pure SyncPlanner in community_downloads.dart; this file is
// the thin I/O shell (connectivity, prefs, the download loop) around it. The
// `since` advance is deliberately gated on success so a failed download is
// retried next open (never skipped).

import 'dart:convert';
import 'dart:ui' show PlatformDispatcher;

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'communities_service.dart';
import 'community_downloads.dart';
import 'community_tour_service.dart';
import 'tour_download_service.dart';

/// The outcome of one sync run (for logging/tests).
class CommunityToursSyncResult {
  final int planned;
  final int downloaded;
  final int failed;
  final bool sinceAdvanced;

  /// [LOCAL-746] How many HELD community tours were re-downloaded to the
  /// organiser's newer version this run (independent of the new-tours plan).
  final int refreshed;

  const CommunityToursSyncResult({
    required this.planned,
    required this.downloaded,
    required this.failed,
    required this.sinceAdvanced,
    this.refreshed = 0,
  });

  static const CommunityToursSyncResult noop = CommunityToursSyncResult(
      planned: 0, downloaded: 0, failed: 0, sinceAdvanced: false);
}

/// Map a connectivity_plus result list to the planner's SyncConnection. Wi-Fi/
/// ethernet is unmetered; mobile is metered; anything else (none/bluetooth/vpn-
/// only) is treated as none (no auto-download). This is the ONE place the real
/// connectivity enum is interpreted, so the planner stays plugin-free.
SyncConnection connectionFromResults(List<ConnectivityResult> results) {
  final hasWifi = results.contains(ConnectivityResult.wifi) ||
      results.contains(ConnectivityResult.ethernet);
  if (hasWifi) return SyncConnection.unmetered;
  if (results.contains(ConnectivityResult.mobile)) return SyncConnection.metered;
  return SyncConnection.none;
}

class CommunityToursSync {
  CommunityToursSync._();
  static final CommunityToursSync instance = CommunityToursSync._();

  bool _running = false;

  /// Fetch the new tours for a user since [since]. Seam so the background entry
  /// point and tests can stub the HTTP round trip; defaults to the real
  /// endpoint client. ONE planner/downloader is shared either way (D675).
  static Future<NewToursResult?> Function(String userId, {String? since})
      fetchNewTours = CommunityTourService.newTours;

  /// Download + save one tour by server id. Seam so tests can stub the
  /// downloader; defaults to the SINGLE download path (TourDownloadService).
  static Future<TourDownloadResult> Function(int tourId) download =
      TourDownloadService.downloadAndSave;

  // ─── [LOCAL-746] Re-download of a HELD community tour the organiser edited ──

  /// Read the CURRENT server (version, updated_at) of a tour — the LOCAL-657
  /// number the app already shows. Seam for tests; defaults to the real
  /// map-delivery `/tour-info` client. Null on any failure (that tour is simply
  /// not refreshed).
  ///
  /// [LOCAL-755] Also carries `isOrganiserAudio` (source_kind='organiser_audio')
  /// so the refresh pass can SKIP an organiser-audio tour even if its saved
  /// record predates source_kind stamping (members are never pushed updates).
  static Future<({int version, String? updatedAt, bool isOrganiserAudio})?>
      Function(int tourId) fetchServerVersion =
      CommunityTourService.serverTourVersion;

  /// The community ids the member is STILL active in (active membership) PLUS
  /// the ones the member OWNS — the set the refresh planner gates on. Seam for
  /// tests; defaults to merging `/communities/mine` (active flag) with
  /// `/communities/mine-owned`. Empty on any failure (fail closed → nothing is
  /// re-downloaded when membership cannot be confirmed).
  static Future<Set<int>> Function(String userId) fetchActiveCommunityIds =
      _defaultActiveCommunityIds;

  /// Re-download a held tour and replace it in place. Seam for tests; defaults
  /// to [TourDownloadService.reDownloadAndReplace].
  static Future<TourDownloadResult> Function(int tourId,
          {required int newVersion, String? updatedAt}) reDownload =
      TourDownloadService.reDownloadAndReplace;

  /// Emit the ONE short "<tour> was updated by the organiser." message after a
  /// successful refresh. Defaults to a no-op; main wires it to a snackbar/toast.
  ///
  /// [LOCAL-750 C] Carries the refreshed tour's id so a FOREGROUND in-app
  /// message can offer a "View" action that opens it. The id is optional so the
  /// background wiring (notification only) can ignore it.
  static void Function(String message, {int? tourId}) onRefreshMessage =
      _noopMessage;

  static void _noopMessage(String _, {int? tourId}) {}

  /// [LOCAL-755 / D709 Rule 3] Emit the ONE short in-app message (LOCAL-750
  /// mechanism) when a HELD organiser-audio tour was updated by the organiser:
  /// "<tour> was updated by the organiser. Re-download?" with a Re-download
  /// action. A member is NEVER pushed the update — this only OFFERS it. Carries
  /// the tour id + the server version so the foreground wiring can run the tap
  /// (TourDownloadService.reDownloadAndReplace). Defaults to a no-op; main wires
  /// it to a snackbar/toast with the action.
  static void Function(String message,
          {required int tourId, required int serverVersion, String? updatedAt})
      onOrganiserAudioUpdate = _noopOrganiserAudioUpdate;

  static void _noopOrganiserAudioUpdate(String _,
      {required int tourId, required int serverVersion, String? updatedAt}) {}

  /// [LOCAL-755] Re-download an organiser-audio tour the member OPTED IN to (the
  /// tap on the message/row). Seam for tests; defaults to
  /// [TourDownloadService.reDownloadAndReplace] — the SAME in-place replace a
  /// generated refresh uses (package + MP3s from the organiser host, old copy
  /// replaced only after the new one is complete).
  static Future<TourDownloadResult> Function(int tourId,
          {required int newVersion, String? updatedAt}) reDownloadOrganiserAudio =
      TourDownloadService.reDownloadAndReplace;

  /// [LOCAL-748] The community ids the user OWNS — a tour in one of these is the
  /// user's OWN tour and is NEVER announced to them. Seam for tests; defaults to
  /// `/communities/mine-owned`. Empty on any failure (so a lookup failure never
  /// suppresses a legitimate announcement — the owned check simply matches
  /// nothing).
  static Future<Set<int>> Function(String userId) fetchOwnedCommunityIds =
      _defaultOwnedCommunityIds;

  /// [LOCAL-748] Announce ONE new community tour to the member (D675 part 2 §).
  /// Defaults to a no-op; main wires it to a snackbar/notification. Called once
  /// per new tour (never for the user's own tours), carrying the message plus
  /// the tour id + whether it was auto-downloaded (so the UI can offer View vs
  /// Download).
  static void Function(NewTourAnnouncement announcement, String message)
      onNewTourAnnouncement = _noopAnnouncement;

  static void _noopAnnouncement(NewTourAnnouncement _, String __) {}

  /// [LOCAL-750 C] Fired once after a run that downloaded a new tour or
  /// refreshed a held one, so the Listen page reloads without the user leaving
  /// and coming back. Defaults to a no-op; main wires it to SavedToursRefresh.
  static void Function() onToursChanged = _noopToursChanged;

  static void _noopToursChanged() {}

  static Future<Set<int>> _defaultOwnedCommunityIds(String userId) async {
    final ids = <int>{};
    try {
      final owned = await CommunityTourService.ownedCommunities(userId);
      for (final c in owned) {
        if (c.id != 0) ids.add(c.id);
      }
    } catch (_) {}
    return ids;
  }

  static Future<Set<int>> _defaultActiveCommunityIds(String userId) async {
    final ids = <int>{};
    try {
      final mine = await CommunitiesService.mine(userId);
      for (final c in mine) {
        if (c.active && c.id != 0) ids.add(c.id);
      }
    } catch (_) {}
    try {
      final owned = await CommunityTourService.ownedCommunities(userId);
      for (final c in owned) {
        if (c.id != 0) ids.add(c.id);
      }
    } catch (_) {}
    return ids;
  }

  /// Run the sync-on-open baseline — the SAME planner + downloader the Android
  /// background worker runs (LOCAL-714). Safe to call repeatedly (a run in
  /// flight is a no-op). Returns a result for logging/tests. Never throws: any
  /// failure leaves `since` unchanged so the next open retries.
  Future<CommunityToursSyncResult> run() async {
    if (_running) return CommunityToursSyncResult.noop;
    _running = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id') ?? '';
      if (userId.isEmpty) return CommunityToursSyncResult.noop;

      // The connection + cellular allowance gate BOTH the new-tours downloads
      // and the held-tour refreshes, so resolve them once up front. A failure
      // reading connectivity (e.g. no plugin on a test host) must NOT abort the
      // run — treat it as `none` (nothing auto-downloads) and still let the
      // new-tours fetch below run so `since` can advance on an empty result.
      SyncConnection connection;
      try {
        connection =
            connectionFromResults(await Connectivity().checkConnectivity());
      } catch (_) {
        connection = SyncConnection.none;
      }
      final cellularAllowed =
          prefs.getBool(kAutoDownloadCellularPrefKey) ?? false;
      final deleted =
          (prefs.getStringList(kDeletedTourIdsPrefKey) ?? const []).toSet();

      // ── Part A: the LOCAL-713 new-tours baseline (unchanged policy). ──
      int planned = 0;
      int ok = 0;
      int failed = 0;
      bool advanced = false;

      final since = prefs.getString(kNewToursSincePrefKey);
      final result = await fetchNewTours(userId, since: since);
      if (result != null) {
        if (result.tours.isEmpty) {
          // Nothing new. Still advance `since` to server_time so the next sync
          // starts from here (a successful round trip with no work).
          if (result.serverTime != null && result.serverTime!.isNotEmpty) {
            await prefs.setString(kNewToursSincePrefKey, result.serverTime!);
            advanced = true;
          }
        } else {
          final onPhone = _onPhoneTourIds(prefs);
          final autoCommunities =
              _autoDownloadCommunityIds(prefs, result.tours);

          // [LOCAL-715 / D675 addendum 1] The listening language is PER
          // COMMUNITY. Resolve it ONCE per community that has new tours.
          final locale = _localeLanguageCode();
          final languageByCommunity = <int, String>{};
          for (final id in result.tours.map((t) => t.communityId).toSet()) {
            languageByCommunity[id] =
                languageForCommunity(prefs, id, localeLanguageCode: locale);
          }
          final preferred = resolveCommunityLanguage(
            aboutDefault: prefs.getString(kListeningLanguagePrefKey),
            localeLanguageCode: locale,
          );

          final plan = SyncPlanner.plan(
            newTours: result.tours,
            onPhoneTourIds: onPhone,
            deletedTourIds: deleted,
            connection: connection,
            cellularAllowed: cellularAllowed,
            autoDownloadCommunityIds: autoCommunities,
            preferredLanguage: preferred,
            languageByCommunity: languageByCommunity,
          );
          planned = plan.length;

          final autoDownloadedIds = <int>{};
          for (final d in plan) {
            final r = await download(d.tourId);
            if (r.status == TourDownloadStatus.ok ||
                r.status == TourDownloadStatus.alreadyOnPhone) {
              ok++;
              autoDownloadedIds.add(d.tourId);
            } else {
              failed++;
            }
          }

          // [LOCAL-748] Announce the new tours to the member — ONE short message
          // per tour, once per tour, NEVER for the user's own tours. A tour that
          // was auto-downloaded this run offers "View"; one that was not (auto-
          // download off, or on a metered connection) offers "Download".
          await _announceNewTours(
            prefs: prefs,
            userId: userId,
            newTours: result.tours,
            autoDownloadedTourIds: autoDownloadedIds,
          );

          // D675 §: advance `since` only after the downloads SUCCEED.
          final haveServerTime =
              result.serverTime != null && result.serverTime!.isNotEmpty;
          if (shouldAdvanceSince(
              haveServerTime: haveServerTime, failedCount: failed)) {
            await prefs.setString(kNewToursSincePrefKey, result.serverTime!);
            advanced = true;
          }
        }
      }
      // result == null is a transport failure: leave `since` unchanged. The
      // refresh pass below is independent (it has its own per-tour reads), so a
      // new-tours transport failure must not stop it.

      // ── Part B: [LOCAL-746] re-download HELD community tours the organiser
      // edited (version rose). Runs EVERY sync, independent of new-tours — an
      // in-place edit never appears in /communities/new-tours. ──
      final refreshed = await _refreshHeldCommunityTours(
        prefs: prefs,
        userId: userId,
        connection: connection,
        cellularAllowed: cellularAllowed,
        deletedTourIds: deleted,
      );

      // [LOCAL-750 C] If this run downloaded a new tour or refreshed a held one,
      // tell the Listen page to reload so the change appears without the user
      // leaving and coming back. One signal per run (not per tour).
      if (ok > 0 || refreshed > 0) {
        onToursChanged();
      }

      return CommunityToursSyncResult(
        planned: planned,
        downloaded: ok,
        failed: failed,
        sinceAdvanced: advanced,
        refreshed: refreshed,
      );
    } catch (_) {
      return CommunityToursSyncResult.noop;
    } finally {
      _running = false;
    }
  }

  /// [LOCAL-748] Announce the new community tours to the member. ONE short
  /// message per NEW tour, at most once per tour, NEVER for a tour in a
  /// community the user OWNS. The pure [planNewTourAnnouncements] decides which
  /// tours to announce (skipping owned communities + already-announced ids);
  /// this shell reads/writes the announced-ids set and emits each message via
  /// the [onNewTourAnnouncement] seam. [autoDownloadedTourIds] are the ids
  /// actually downloaded this run (so each message offers View vs Download).
  Future<void> _announceNewTours({
    required SharedPreferences prefs,
    required String userId,
    required List<NewCommunityTour> newTours,
    required Set<int> autoDownloadedTourIds,
  }) async {
    if (newTours.isEmpty) return;
    final ownedIds = await fetchOwnedCommunityIds(userId);
    final announced =
        (prefs.getStringList(kAnnouncedNewTourIdsPrefKey) ?? const []).toSet();

    final toAnnounce = planNewTourAnnouncements(
      newTours: newTours,
      ownedCommunityIds: ownedIds,
      announcedTourIds: announced,
      autoDownloadedTourIds: autoDownloadedTourIds,
    );
    if (toAnnounce.isEmpty) return;

    for (final a in toAnnounce) {
      onNewTourAnnouncement(a, newTourMessage(a.communityName, a.tourName));
      announced.add(a.tourId.toString());
    }
    await prefs.setStringList(
        kAnnouncedNewTourIdsPrefKey, announced.toList());
  }

  /// [LOCAL-746] The held-community-tour refresh pass. Gathers the community
  /// tours ALREADY on the phone, reads each one's CURRENT server version, runs
  /// the pure [RefreshPlanner], re-downloads the ones whose version rose (the
  /// member is still active / owner, the tour was not deleted, the connection
  /// allows it), replacing them in place, and emits ONE message per tour that
  /// actually refreshed. A failed re-download keeps the old copy (never leaves
  /// the member with nothing). Returns how many tours were refreshed.
  Future<int> _refreshHeldCommunityTours({
    required SharedPreferences prefs,
    required String userId,
    required SyncConnection connection,
    required bool cellularAllowed,
    required Set<String> deletedTourIds,
  }) async {
    // Cheap connection gate first — avoid the network reads when nothing could
    // be re-downloaded anyway.
    if (connection == SyncConnection.none) return 0;
    if (connection == SyncConnection.metered && !cellularAllowed) return 0;

    final onPhone = _heldCommunityTourRecords(prefs);
    if (onPhone.isEmpty) return 0;

    // The communities the member is still active in (or owns).
    final activeIds = await fetchActiveCommunityIds(userId);

    // Read each held community tour's CURRENT server version. A null read
    // (transport error / missing) is treated as "no change" (savedVersion), so
    // that tour is simply not re-downloaded this run.
    final held = <HeldCommunityTour>[];
    for (final rec in onPhone) {
      final serverVer = await fetchServerVersion(rec.serverTourId);
      held.add(HeldCommunityTour(
        tourId: rec.serverTourId,
        communityId: rec.communityId,
        savedVersion: rec.savedVersion,
        serverVersion: serverVer?.version ?? rec.savedVersion,
        language: rec.language,
        isCommunityTour: true,
        // [LOCAL-755] Organiser-audio tours are never auto-re-downloaded: the
        // marker comes from the saved record (stamped at download, LOCAL-754B)
        // and, when a server read carries it, from the server too (so a record
        // saved before source_kind was stamped is still classified).
        isOrganiserAudio:
            rec.isOrganiserAudio || (serverVer?.isOrganiserAudio ?? false),
        name: rec.name,
      ));
      // Stash the server updated_at alongside, keyed by id, for the label.
      if (serverVer != null) {
        _serverUpdatedAt[rec.serverTourId] = serverVer.updatedAt;
      }
    }

    // [LOCAL-755 / D709 Rule 3] OFFER (never push) the organiser-audio updates.
    // RefreshPlanner (below) SKIPS organiser-audio tours; here we surface ONE
    // in-app message per organiser-audio tour whose version rose, at most once
    // per (tour, server version), so the member can opt in by tapping
    // Re-download. No download happens here — the tap does it.
    await _offerOrganiserAudioUpdates(
      prefs: prefs,
      held: held,
      activeCommunityIds: activeIds,
      deletedTourIds: deletedTourIds,
    );

    final plan = RefreshPlanner.plan(
      held: held,
      activeCommunityIds: activeIds,
      connection: connection,
      cellularAllowed: cellularAllowed,
      deletedTourIds: deletedTourIds,
    );
    if (plan.isEmpty) return 0;

    int refreshed = 0;
    for (final p in plan) {
      final r = await reDownload(
        p.tourId,
        newVersion: p.serverVersion,
        updatedAt: _serverUpdatedAt[p.tourId],
      );
      if (r.status == TourDownloadStatus.ok) {
        refreshed++;
        // Req 3: ONE short message per refreshed tour.
        onRefreshMessage(refreshedMessage(p.name), tourId: p.tourId);
      }
      // A failed re-download keeps the old copy (reDownloadAndReplace never
      // touches the files on failure) — nothing to undo here.
    }
    return refreshed;
  }

  /// [LOCAL-755 / D709 Rule 3] Surface the organiser-audio updates. The pure
  /// [OrganiserAudioUpdatePlanner] picks the organiser-audio tours whose server
  /// version rose (still active/owned, not deleted); this shell emits ONE
  /// in-app message per offer via [onOrganiserAudioUpdate], at most once per
  /// (tour, server version) — tracked in a persisted set so a later sync does
  /// not nag again for the same version. A member is NEVER pushed the update;
  /// the message/row offers a tap that re-downloads it.
  Future<void> _offerOrganiserAudioUpdates({
    required SharedPreferences prefs,
    required List<HeldCommunityTour> held,
    required Set<int> activeCommunityIds,
    required Set<String> deletedTourIds,
  }) async {
    final offers = OrganiserAudioUpdatePlanner.plan(
      held: held,
      activeCommunityIds: activeCommunityIds,
      deletedTourIds: deletedTourIds,
    );
    if (offers.isEmpty) return;
    final offered =
        (prefs.getStringList(kOfferedOrganiserAudioKey) ?? const []).toSet();
    // [LOCAL-755] Stamp the pending server version onto the matching saved
    // record so the Listen/community row can show the "Updated by the organiser
    // — Re-download" affordance (organiserAudioUpdateLabel) even between syncs.
    // This does NOT re-download — it only marks that a newer version exists.
    final savedRaw = prefs.getStringList('saved_tours') ?? const [];
    final byTourId = {for (final o in offers) o.tourId: o.serverVersion};
    var recordsChanged = false;
    final updatedRecords = <String>[];
    for (final s in savedRaw) {
      try {
        final m = Map<String, dynamic>.from(json.decode(s) as Map);
        final sid = int.tryParse((m['server_tour_id'] ?? '').toString());
        final tid = int.tryParse((m['tour_id'] ?? '').toString());
        final serverVer = byTourId[sid] ?? byTourId[tid];
        if (serverVer != null && m['pending_organiser_version'] != serverVer) {
          m['pending_organiser_version'] = serverVer;
          updatedRecords.add(json.encode(m));
          recordsChanged = true;
          continue;
        }
      } catch (_) {}
      updatedRecords.add(s);
    }
    if (recordsChanged) {
      await prefs.setStringList('saved_tours', updatedRecords);
    }
    var changed = false;
    for (final o in offers) {
      // One offer per (tour id, server version) — re-nag only if a NEWER
      // version appears.
      final key = '${o.tourId}:${o.serverVersion}';
      if (offered.contains(key)) continue;
      onOrganiserAudioUpdate(
        organiserAudioUpdateMessage(o.name),
        tourId: o.tourId,
        serverVersion: o.serverVersion,
        updatedAt: _serverUpdatedAt[o.tourId],
      );
      offered.add(key);
      changed = true;
    }
    if (changed) {
      await prefs.setStringList(kOfferedOrganiserAudioKey, offered.toList());
    }
  }

  /// The server updated_at read for each held tour this run (id → ISO date),
  /// used to stamp the "v2 · updated <date>" label on a refreshed record.
  final Map<int, String?> _serverUpdatedAt = {};

  /// [LOCAL-715 / D675 addendum 1] The phone locale's language code, read
  /// without a WidgetsBinding so it also works in the background isolate (the
  /// WorkManager run has no bound widget tree). Null on any failure, which
  /// resolveCommunityLanguage/defaultListeningLanguage treat as "English".
  static String? _localeLanguageCode() {
    try {
      return PlatformDispatcher.instance.locale.languageCode;
    } catch (_) {
      return null;
    }
  }

  /// The server tour ids already on the phone, from the saved_tours records.
  static Set<String> _onPhoneTourIds(SharedPreferences prefs) {
    final out = <String>{};
    for (final s in (prefs.getStringList('saved_tours') ?? const [])) {
      try {
        final map = json.decode(s);
        if (map is Map<String, dynamic>) {
          final tid = map['tour_id'];
          final sid = map['server_tour_id'];
          if (tid is String && tid.isNotEmpty) out.add(tid);
          if (sid is String && sid.isNotEmpty) out.add(sid);
        }
      } catch (_) {}
    }
    return out;
  }

  /// The communities whose auto-download switch is ON, among the ones appearing
  /// in the new tours (default OFF). LOCAL-714 writes the switch at the join
  /// question; LOCAL-713 reads it for the baseline.
  static Set<int> _autoDownloadCommunityIds(
      SharedPreferences prefs, List<NewCommunityTour> tours) {
    final ids = <int>{};
    for (final t in tours) {
      if (prefs.getBool(autoDownloadPrefKey(t.communityId)) ?? false) {
        ids.add(t.communityId);
      }
    }
    return ids;
  }

  /// [LOCAL-746] The COMMUNITY tours already on the phone, with the facts the
  /// refresh pass needs: the numeric server id, the community id, the saved
  /// version, the held language and the display name. An ordinary tour (no
  /// `community_id`) or one with no numeric server id is skipped — the refresh
  /// only touches community tours.
  static List<_HeldRecord> _heldCommunityTourRecords(SharedPreferences prefs) {
    final out = <_HeldRecord>[];
    for (final s in (prefs.getStringList('saved_tours') ?? const [])) {
      try {
        final m = json.decode(s);
        if (m is! Map<String, dynamic>) continue;

        // community_id (int or numeric string); skip ordinary tours.
        final rawCid = m['community_id'];
        int? cid;
        if (rawCid is int) {
          cid = rawCid;
        } else if (rawCid is num) {
          cid = rawCid.toInt();
        } else if (rawCid is String) {
          cid = int.tryParse(rawCid.trim());
        }
        if (cid == null || cid == 0) continue;

        // The numeric server/download id the version endpoints key on.
        final sid = int.tryParse((m['server_tour_id'] ?? '').toString());
        if (sid == null) continue;

        // Saved version (version | tour_version), default 1.
        int savedVersion = 1;
        final rawV = m['version'] ?? m['tour_version'];
        if (rawV is int) {
          savedVersion = rawV;
        } else if (rawV is num) {
          savedVersion = rawV.toInt();
        } else if (rawV is String) {
          savedVersion = int.tryParse(rawV) ?? 1;
        }

        final language =
            (m['language'] ?? m['original_language'] ?? 'en').toString();
        final name = (m['title'] ?? m['original_request'] ?? 'This tour')
            .toString();

        // [LOCAL-755] source_kind stamped at download (LOCAL-754B). An
        // organiser-audio tour is never auto-re-downloaded (members opt in).
        final sk = (m['source_kind'] ?? '').toString().trim();

        out.add(_HeldRecord(
          serverTourId: sid,
          communityId: cid,
          savedVersion: savedVersion,
          language: language.isEmpty ? 'en' : language,
          name: name,
          isOrganiserAudio: sk == 'organiser_audio',
        ));
      } catch (_) {}
    }
    return out;
  }
}

/// [LOCAL-746] A held community tour's facts, gathered from its saved_tours
/// record for the refresh pass.
class _HeldRecord {
  final int serverTourId;
  final int communityId;
  final int savedVersion;
  final String language;
  final String name;

  /// [LOCAL-755] Whether the saved record is an organiser-audio tour
  /// (source_kind='organiser_audio'). Such a tour is never auto-re-downloaded.
  final bool isOrganiserAudio;

  const _HeldRecord({
    required this.serverTourId,
    required this.communityId,
    required this.savedVersion,
    required this.language,
    required this.name,
    this.isOrganiserAudio = false,
  });
}
