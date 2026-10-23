// [LOCAL-714 / D675 part 2] Community tours in the BACKGROUND.
//
// LOCAL-713 gave the new-tours endpoint, the listening language, the
// community-page Download, and the sync WHEN THE APP OPENS. This file makes the
// SAME sync run when the app is CLOSED, with the member's permission:
//
//   * Android — a WorkManager periodic task (every 6 h) runs the SAME shared
//     planner + downloader as the sync on open (CommunityToursSync.run()).
//     ONE implementation, called from both. Constraints (network / battery /
//     storage) are set at registration; the worker also skips when <1 GB is
//     free (D675 part 2 §2).
//   * iOS — a BGTaskScheduler app-refresh that only CHECKS /communities/new-
//     tours and, if there is anything new, posts ONE quiet local notification
//     ("2 new tours from Demo Boston Walkers"). The DOWNLOAD happens at the
//     next app open (713's sync). Quiet hours (23:00–07:30 local) are respected
//     — a check that finds new tours during quiet hours queues the single
//     notification for the morning (D675 part 2 §3).
//
// The policy pieces here are PURE and dependency-free so they are unit-tested
// with no device:
//   * quietHoursGate       — may we notify now, or must we wait until morning?
//   * newToursNotificationText — the "N new tours from X" text (1 vs N).
//   * hasEnoughFreeStorage — the <1 GB skip, given a measured free-byte count.
//
// The WorkManager dispatcher (callbackDispatcher) is the Android/iOS entry
// point the OS calls with the app CLOSED; it is annotated `vm:entry-point` so
// tree-shaking keeps it. It is a thin shell: Android → CommunityToursSync.run()
// (the shared planner+downloader); iOS → the check-only notification path.

import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:workmanager/workmanager.dart';

import 'community_downloads.dart';
import 'community_tours_sync.dart';
import 'community_notifications.dart';

/// The unique WorkManager task name + the iOS BGTaskScheduler identifier. The
/// iOS id MUST also be listed under BGTaskSchedulerPermittedIdentifiers in
/// Info.plist, or iOS refuses to schedule it.
const String kCommunitySyncTaskName = 'com.audioura.community_tours_sync';
const String kCommunitySyncTaskTag = 'community_tours_sync';

/// The minimum free storage to run an auto-download: 1 GB (D675 part 2 §2 —
/// "It skips when less than 1 GB is free"). Exposed for the test.
const int kMinFreeStorageBytes = 1024 * 1024 * 1024; // 1 GiB

/// Quiet hours (local): no notifications 23:00–07:30 (D675 part 2 §3). A check
/// that finds new tours inside this window queues the one notification for the
/// morning instead of buzzing the phone at night.
const int kQuietStartMinutes = 23 * 60; // 23:00
const int kQuietEndMinutes = 7 * 60 + 30; // 07:30

/// PURE. Whether [freeBytes] clears the 1 GB floor. Below the floor, an
/// auto-download is skipped (the next run, with more space or on Wi-Fi + idle,
/// tries again). Total: a negative/unknown measurement (-1) is treated as "not
/// enough" so we never download when we could not measure.
bool hasEnoughFreeStorage(int freeBytes) =>
    freeBytes >= kMinFreeStorageBytes;

/// PURE. The minutes-since-midnight for a local [now]. Helper for the gate.
int minutesOfDay(DateTime now) => now.hour * 60 + now.minute;

/// PURE. Is [now] (local) inside the quiet-hours window 23:00–07:30? The window
/// wraps midnight, so it is "after 23:00 OR before 07:30".
bool isQuietHours(DateTime now) {
  final m = minutesOfDay(now);
  return m >= kQuietStartMinutes || m < kQuietEndMinutes;
}

/// The outcome of the quiet-hours gate: notify now, or hold until a local
/// morning time.
class QuietHoursDecision {
  /// May we post the notification right now?
  final bool mayNotifyNow;

  /// When [mayNotifyNow] is false, the local DateTime to (re)schedule the
  /// single notification for — the next 07:30. Null when notifying now.
  final DateTime? deferUntil;

  const QuietHoursDecision({required this.mayNotifyNow, this.deferUntil});
}

/// PURE. Decide whether the one "new tours" notification may fire at [now]
/// (local), or must be queued for the morning (D675 part 2 §3). Outside quiet
/// hours → notify now. Inside quiet hours → defer to the NEXT 07:30 (today if
/// it is still before 07:30, tomorrow if it is after 23:00).
QuietHoursDecision quietHoursGate(DateTime now) {
  if (!isQuietHours(now)) {
    return const QuietHoursDecision(mayNotifyNow: true);
  }
  // Inside the window. The next 07:30 is today when it is currently after
  // midnight but before 07:30, otherwise tomorrow (we are after 23:00).
  final todayMorning =
      DateTime(now.year, now.month, now.day, 7, 30);
  final deferUntil = now.isBefore(todayMorning)
      ? todayMorning
      : todayMorning.add(const Duration(days: 1));
  return QuietHoursDecision(mayNotifyNow: false, deferUntil: deferUntil);
}

/// PURE. The single notification's text for [count] new tours from
/// [communityName] (D675 part 2 §3 example: "2 new tours from Demo Boston
/// Walkers"). 1 tour reads "1 new tour from X" (singular). When more than one
/// community has new tours, [communityName] is the one with the most new tours
/// and [otherCommunities] (>0) adds "and N other communities".
///   * 1 tour, 1 community    → "1 new tour from Demo Boston Walkers"
///   * N tours, 1 community    → "N new tours from Demo Boston Walkers"
///   * tours across M commun.  → "… and 2 other communities"
String newToursNotificationText({
  required int count,
  required String communityName,
  int otherCommunities = 0,
}) {
  final noun = count == 1 ? 'tour' : 'tours';
  final base = '$count new $noun from $communityName';
  if (otherCommunities <= 0) return base;
  final others = otherCommunities == 1
      ? '1 other community'
      : '$otherCommunities other communities';
  return '$base and $others';
}

/// PURE. The notification TITLE (short, constant).
const String kNewToursNotificationTitle = 'New community tours';

/// The free bytes on the directory backing app storage, or -1 when it cannot be
/// measured (treated as "not enough" by [hasEnoughFreeStorage]). Isolated here
/// (the only `dart:io` storage probe) so the gate stays pure/testable.
Future<int> measureFreeStorageBytes() async {
  try {
    // `df -k <tmp>` → the app's volume free space. Works on Android and iOS
    // (both ship a busybox/toybox `df`). Column 4 (1K-blocks available) × 1024.
    final dir = Directory.systemTemp.path;
    final res = await Process.run('df', ['-k', dir]);
    if (res.exitCode != 0) return -1;
    final lines = (res.stdout as String).trim().split('\n');
    if (lines.length < 2) return -1;
    // The last line is the mount row; split on whitespace. `Available` is the
    // 4th numeric column on both platforms' df output.
    final cols =
        lines.last.trim().split(RegExp(r'\s+')).where((s) => s.isNotEmpty).toList();
    // Find the first parseable KB value after the filesystem name; use the
    // Available column by position (index 3) when present, else scan.
    if (cols.length >= 4) {
      final availKb = int.tryParse(cols[3]);
      if (availKb != null) return availKb * 1024;
    }
    return -1;
  } catch (_) {
    return -1;
  }
}

/// [Android] Run the background community-tours sync with the app CLOSED. This
/// is the SAME planner + downloader as the sync on open — it simply calls
/// CommunityToursSync.run(). It first applies the <1 GB storage skip (the OS
/// constraints already gate network/battery/storage-low, this adds the explicit
/// 1 GB floor from D675 part 2 §2). Returns true on a clean run (no failures).
Future<bool> runAndroidBackgroundSync() async {
  // The <1 GB skip. The OS "storage not low" constraint is coarse; D675 asks
  // for an explicit 1 GB floor.
  final free = await measureFreeStorageBytes();
  if (!hasEnoughFreeStorage(free)) {
    return true; // Not an error — just nothing to do this cycle.
  }
  // [LOCAL-746] With the app CLOSED there is no main() to set the hook, so wire
  // the "<tour> was updated by the organiser." heads-up here too (a quiet local
  // notification). Harmless when nothing is refreshed.
  CommunityToursSync.onRefreshMessage = (message, {int? tourId}) {
    CommunityNotifications.postTourUpdated(message);
  };
  // [LOCAL-748] Announce a new community tour from the background sync too.
  CommunityToursSync.onNewTourAnnouncement = (announcement, message) {
    CommunityNotifications.postNewTourAvailable(message);
  };
  final result = await CommunityToursSync.instance.run();
  return result.failed == 0;
}

/// [iOS] The CHECK-ONLY background path: fetch /communities/new-tours, and if
/// there is anything new, post the ONE quiet notification (respecting quiet
/// hours). iOS does NOT download in the background — the download happens at the
/// next app open (713's sync on open). Does NOT advance `since` (the app-open
/// sync owns that), so the notification keeps surfacing until the member opens
/// the app and the real sync runs. Returns true when new tours were found.
Future<bool> runIosBackgroundCheck({DateTime? nowOverride}) async {
  final prefs = await SharedPreferences.getInstance();
  final userId = prefs.getString('user_id') ?? '';
  if (userId.isEmpty) return false;

  // Only notify communities the member opted into auto-download for (the join
  // question's switch) — a check is pointless for communities they never opted
  // into. iOS respects the same per-community switch as Android.
  final since = prefs.getString(kNewToursSincePrefKey);
  final result = await CommunityToursSync.fetchNewTours(userId, since: since);
  if (result == null || result.tours.isEmpty) return false;

  // Keep only tours from communities whose auto-download switch is ON.
  final opted = result.tours
      .where((t) => prefs.getBool(autoDownloadPrefKey(t.communityId)) ?? false)
      .toList(growable: false);
  if (opted.isEmpty) return false;

  final summary = summariseNewTours(opted);
  final now = nowOverride ?? DateTime.now();
  final gate = quietHoursGate(now);
  final text = newToursNotificationText(
    count: summary.totalCount,
    communityName: summary.topCommunityName,
    otherCommunities: summary.otherCommunities,
  );
  await CommunityNotifications.postOrScheduleNewTours(
    body: text,
    mayNotifyNow: gate.mayNotifyNow,
    deferUntil: gate.deferUntil,
  );
  return true;
}

/// A compact summary of the new tours for the notification: the total count,
/// the community with the MOST new tours (named in the text) and how many OTHER
/// communities also have new tours.
class NewToursSummary {
  final int totalCount;
  final String topCommunityName;
  final int otherCommunities;

  const NewToursSummary({
    required this.totalCount,
    required this.topCommunityName,
    required this.otherCommunities,
  });
}

/// PURE. Summarise new-tour rows for the notification. Groups by community,
/// picks the one with the most new tours as the named community, counts the
/// rest as "other communities".
NewToursSummary summariseNewTours(List<NewCommunityTour> tours) {
  final byCommunity = <int, int>{};
  final names = <int, String>{};
  for (final t in tours) {
    byCommunity[t.communityId] = (byCommunity[t.communityId] ?? 0) + 1;
    names[t.communityId] = t.communityName;
  }
  // The community with the most new tours (ties broken by lowest id for
  // determinism).
  int topId = tours.first.communityId;
  int topCount = -1;
  for (final e in byCommunity.entries) {
    if (e.value > topCount || (e.value == topCount && e.key < topId)) {
      topId = e.key;
      topCount = e.value;
    }
  }
  return NewToursSummary(
    totalCount: tours.length,
    topCommunityName: names[topId] ?? '',
    otherCommunities: byCommunity.length - 1,
  );
}

/// The WorkManager entry point the OS invokes with the app CLOSED. Annotated
/// `vm:entry-point` so AOT tree-shaking keeps it. On Android it runs the shared
/// sync (download); on iOS it runs the check-only notification path. Any throw
/// is swallowed into a failure result so the OS simply retries next cycle.
@pragma('vm:entry-point')
void callbackDispatcher() {
  Workmanager().executeTask((task, inputData) async {
    try {
      if (Platform.isIOS) {
        await runIosBackgroundCheck();
        return true;
      }
      return await runAndroidBackgroundSync();
    } catch (_) {
      return false; // Let the OS retry on the next scheduled cycle.
    }
  });
}

/// Register the periodic background task (every 6 h) with the OS constraints
/// (D675 part 2 §2): network connected (unmetered unless the member allowed
/// mobile data), battery not low, storage not low. Idempotent — WorkManager
/// replaces an existing periodic task of the same unique name. Called from
/// main() after Workmanager().initialize(callbackDispatcher). Never throws.
Future<void> registerCommunitySyncTask() async {
  try {
    final prefs = await SharedPreferences.getInstance();
    final cellularAllowed =
        prefs.getBool(kAutoDownloadCellularPrefKey) ?? false;
    await Workmanager().registerPeriodicTask(
      kCommunitySyncTaskName,
      kCommunitySyncTaskTag,
      frequency: const Duration(hours: 6),
      constraints: Constraints(
        // Unmetered (Wi-Fi/ethernet) unless the member allowed mobile data, in
        // which case any connected network. The pure planner re-checks the live
        // connection too, so this is defence-in-depth, not the only gate.
        networkType:
            cellularAllowed ? NetworkType.connected : NetworkType.unmetered,
        requiresBatteryNotLow: true,
        requiresStorageNotLow: true,
      ),
      existingWorkPolicy: ExistingPeriodicWorkPolicy.update,
    );
  } catch (_) {
    // A platform without WorkManager (e.g. a test host) simply gets no task.
  }
}

/// Cancel the periodic task (e.g. when the member turns OFF the last auto-
/// download switch). Never throws.
Future<void> cancelCommunitySyncTask() async {
  try {
    await Workmanager().cancelByUniqueName(kCommunitySyncTaskName);
  } catch (_) {}
}
