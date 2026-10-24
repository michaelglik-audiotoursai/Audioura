// [LOCAL-750 C] Members must SEE community messages.
//
// Before this change, a new/updated community tour produced ONLY a
// low-importance, silent system notification (channel `community_new_tours`,
// Importance.low). It never popped up and nothing appeared in the app, so
// Michael saw nothing while using the app (2026-10-23 retest).
//
// This service routes every community message through ONE decision:
//   * app in the FOREGROUND  → show it IN THE APP (a SnackBar via the global
//     [communityScaffoldMessengerKey]) with a "View" action that opens the tour
//     (reusing PendingListenOpen), and SKIP the system notification;
//   * app in the BACKGROUND  → keep the quiet system notification.
//
// The routing decision ([CommunityMessageRouter.target]) is a pure function so
// the "foreground → in-app, background → system" policy is unit-testable
// without a widget tree or a notification plugin.

import 'package:flutter/material.dart';

import 'deep_link_service.dart' show PendingListenOpen;

/// The global messenger used to show an in-app community message from anywhere
/// (the sync runs outside any particular screen's context). Wired onto the
/// MaterialApp as `scaffoldMessengerKey`. Null-safe: if the app has not built a
/// messenger yet, [ForegroundCommunityMessages.show] reports "not shown" and the
/// caller falls back to the system notification.
final GlobalKey<ScaffoldMessengerState> communityScaffoldMessengerKey =
    GlobalKey<ScaffoldMessengerState>();

/// Where a community message should be delivered.
enum CommunityMessageTarget {
  /// Show it inside the app (SnackBar) — the app is in the foreground.
  inApp,

  /// Post the quiet system notification — the app is in the background.
  systemNotification,
}

/// PURE routing policy (LOCAL-750 C): a foreground app shows the message in the
/// app; a backgrounded app gets the system notification. Kept separate from the
/// widget layer so the policy is unit-testable.
class CommunityMessageRouter {
  const CommunityMessageRouter._();

  static CommunityMessageTarget target({required bool isForeground}) =>
      isForeground
          ? CommunityMessageTarget.inApp
          : CommunityMessageTarget.systemNotification;
}

/// Tracks whether the app is currently in the foreground, and shows in-app
/// community messages. The lifecycle flag is updated by [AppSyncCoordinator]'s
/// lifecycle observer (the one place already watching lifecycle), so there is a
/// single source of truth.
class ForegroundCommunityMessages {
  ForegroundCommunityMessages._();
  static final ForegroundCommunityMessages instance =
      ForegroundCommunityMessages._();

  /// Assume foreground at startup: the app is on screen when `main()` runs its
  /// first sync, and a pause event flips this to false.
  bool _isForeground = true;

  bool get isForeground => _isForeground;

  /// Called by the lifecycle observer. `resumed` → foreground; anything else
  /// (paused/inactive/detached/hidden) → background.
  void setForeground(bool value) {
    _isForeground = value;
  }

  /// Show the community message IN THE APP, with a "View" action that opens the
  /// tour when [tourId] is known. Returns true when the SnackBar was actually
  /// shown (a messenger exists); false otherwise, so the caller can fall back to
  /// the system notification. Never throws.
  bool show(String message, {int? tourId, String? language}) {
    final messenger = communityScaffoldMessengerKey.currentState;
    if (messenger == null) return false;
    try {
      messenger.showSnackBar(
        buildCommunityMessageSnackBar(
          message,
          tourId: tourId,
          language: language,
        ),
      );
      return true;
    } catch (_) {
      return false;
    }
  }
}

/// Build the in-app SnackBar for a community message. When [tourId] is known it
/// carries a "View" action that asks to open that tour on the Listen tab
/// (reusing PendingListenOpen — the same path a download "View" uses). Exposed
/// for the widget test.
SnackBar buildCommunityMessageSnackBar(
  String message, {
  int? tourId,
  String? language,
}) {
  return SnackBar(
    content: Text(message),
    duration: const Duration(seconds: 6),
    action: (tourId != null)
        ? SnackBarAction(
            label: 'View',
            onPressed: () => PendingListenOpen.instance
                .offer(tourId.toString(), language),
          )
        : null,
  );
}

/// [LOCAL-755 / D709 Rule 3] Build the in-app SnackBar for an ORGANISER-AUDIO
/// update offer. Unlike a generated tour's "View", this offers a "Re-download"
/// action (members opt in — organiser-audio updates are never pushed), running
/// [onReDownload] when tapped. Exposed for the widget test.
SnackBar buildOrganiserAudioUpdateSnackBar(
  String message, {
  required void Function() onReDownload,
}) {
  return SnackBar(
    content: Text(message),
    duration: const Duration(seconds: 8),
    action: SnackBarAction(
      label: 'Re-download',
      onPressed: onReDownload,
    ),
  );
}

/// [LOCAL-755] Show the organiser-audio update offer IN THE APP, with a
/// "Re-download" action. Returns true when the SnackBar was shown (a messenger
/// exists); false otherwise so the caller can fall back to a system
/// notification. Never throws.
bool showOrganiserAudioUpdateInApp(
  String message, {
  required void Function() onReDownload,
}) {
  final messenger = communityScaffoldMessengerKey.currentState;
  if (messenger == null) return false;
  try {
    messenger.showSnackBar(
      buildOrganiserAudioUpdateSnackBar(message, onReDownload: onReDownload),
    );
    return true;
  } catch (_) {
    return false;
  }
}

/// Route ONE community message to the right place (LOCAL-750 C). Tries the
/// in-app SnackBar when the app is in the foreground; returns the target that
/// was actually used so the caller posts the system notification only when the
/// message did NOT go in-app (background, or no messenger yet). [postSystem] is
/// the system-notification fallback (the quiet CommunityNotifications post).
CommunityMessageTarget routeCommunityMessage(
  String message, {
  int? tourId,
  String? language,
  required bool isForeground,
  required void Function() postSystem,
}) {
  final target = CommunityMessageRouter.target(isForeground: isForeground);
  if (target == CommunityMessageTarget.inApp) {
    final shown = ForegroundCommunityMessages.instance
        .show(message, tourId: tourId, language: language);
    if (shown) return CommunityMessageTarget.inApp;
    // No messenger available yet — fall back to the system notification so the
    // message is never silently dropped.
  }
  postSystem();
  return CommunityMessageTarget.systemNotification;
}
