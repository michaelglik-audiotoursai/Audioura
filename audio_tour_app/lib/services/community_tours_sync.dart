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

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'community_downloads.dart';
import 'community_tour_service.dart';
import 'tour_download_service.dart';

/// The outcome of one sync run (for logging/tests).
class CommunityToursSyncResult {
  final int planned;
  final int downloaded;
  final int failed;
  final bool sinceAdvanced;

  const CommunityToursSyncResult({
    required this.planned,
    required this.downloaded,
    required this.failed,
    required this.sinceAdvanced,
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

  /// Run the sync-on-open baseline. Safe to call repeatedly (a run in flight is
  /// a no-op). Returns a result for logging/tests. Never throws: any failure
  /// leaves `since` unchanged so the next open retries.
  Future<CommunityToursSyncResult> run() async {
    if (_running) return CommunityToursSyncResult.noop;
    _running = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id') ?? '';
      if (userId.isEmpty) return CommunityToursSyncResult.noop;

      final since = prefs.getString(kNewToursSincePrefKey);
      final result =
          await CommunityTourService.newTours(userId, since: since);
      if (result == null) {
        // Transport failure — leave `since` unchanged (never advance on
        // failure).
        return CommunityToursSyncResult.noop;
      }
      if (result.tours.isEmpty) {
        // Nothing new. Still advance `since` to server_time so the next sync
        // starts from here (there was a successful round trip with no work).
        if (result.serverTime != null && result.serverTime!.isNotEmpty) {
          await prefs.setString(kNewToursSincePrefKey, result.serverTime!);
          return const CommunityToursSyncResult(
              planned: 0, downloaded: 0, failed: 0, sinceAdvanced: true);
        }
        return CommunityToursSyncResult.noop;
      }

      // Gather the inputs the pure planner needs.
      final connection =
          connectionFromResults(await Connectivity().checkConnectivity());
      final cellularAllowed =
          prefs.getBool(kAutoDownloadCellularPrefKey) ?? false;
      final preferred = prefs.getString(kListeningLanguagePrefKey) ??
          kDefaultListeningLanguage;
      final onPhone = _onPhoneTourIds(prefs);
      final deleted =
          (prefs.getStringList(kDeletedTourIdsPrefKey) ?? const []).toSet();
      final autoCommunities = _autoDownloadCommunityIds(prefs, result.tours);

      final plan = SyncPlanner.plan(
        newTours: result.tours,
        onPhoneTourIds: onPhone,
        deletedTourIds: deleted,
        connection: connection,
        cellularAllowed: cellularAllowed,
        autoDownloadCommunityIds: autoCommunities,
        preferredLanguage: preferred,
      );

      if (plan.isEmpty) {
        // Nothing to download under the current switches/connection, but the
        // round trip succeeded — advance `since` so we do not re-evaluate the
        // same tours forever.
        if (result.serverTime != null && result.serverTime!.isNotEmpty) {
          await prefs.setString(kNewToursSincePrefKey, result.serverTime!);
          return const CommunityToursSyncResult(
              planned: 0, downloaded: 0, failed: 0, sinceAdvanced: true);
        }
        return CommunityToursSyncResult.noop;
      }

      // Perform the planned downloads via the SINGLE download path. The planner
      // chose the language; the download pulls that tour id. (v1: the language
      // tour id is the planned tour id — a translation is downloaded by the
      // planner picking the original when the preferred is not available.)
      int ok = 0;
      int failed = 0;
      for (final d in plan) {
        final r = await TourDownloadService.downloadAndSave(d.tourId);
        if (r.status == TourDownloadStatus.ok ||
            r.status == TourDownloadStatus.alreadyOnPhone) {
          ok++;
        } else {
          failed++;
        }
      }

      // D675 §: store server_time as the next `since` only after the downloads
      // SUCCEED — if any failed, leave `since` so the next open retries.
      final haveServerTime =
          result.serverTime != null && result.serverTime!.isNotEmpty;
      bool advanced = false;
      if (shouldAdvanceSince(haveServerTime: haveServerTime, failedCount: failed)) {
        await prefs.setString(kNewToursSincePrefKey, result.serverTime!);
        advanced = true;
      }
      return CommunityToursSyncResult(
          planned: plan.length,
          downloaded: ok,
          failed: failed,
          sinceAdvanced: advanced);
    } catch (_) {
      return CommunityToursSyncResult.noop;
    } finally {
      _running = false;
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
}
