import 'dart:async';

import 'package:flutter/material.dart';

import 'foreground_community_messages.dart'
    show communityScaffoldMessengerKey, ForegroundCommunityMessages;
import 'notification_service.dart';
import 'pending_tour_requests_store.dart';

/// [LOCAL-841] Surface for the "Your tour is ready" message a resumed download
/// produces.
///
/// Mirrors the community-message policy (LOCAL-750 C): when the app is in the
/// FOREGROUND show it IN THE APP (a SnackBar via the global
/// [communityScaffoldMessengerKey], with a "View" action that jumps to the
/// Listen tab), and when it is in the BACKGROUND post the quiet system
/// notification that already exists (NotificationService — Android only; a no-op
/// on iOS without new permissions, exactly as LOCAL-841 allows). The tour is
/// already saved by the time this runs, so the user finds it on Listen either
/// way; this message just tells them it arrived.
///
/// The banner text builder is a pure function so it is unit-testable without a
/// widget tree.
class TourReadyMessage {
  const TourReadyMessage._();

  /// The user-facing "ready" line. Uses the tour title when known.
  static String text(PendingTourRequest req) {
    final title = req.title.trim();
    if (title.isEmpty) return 'Your tour is ready — find it on Listen.';
    return 'Your tour "$title" is ready — find it on Listen.';
  }

  /// Build the in-app SnackBar for a ready tour. [onView] runs when the user
  /// taps "View" (wired to switch to the Listen tab). Exposed for the test.
  static SnackBar buildSnackBar(PendingTourRequest req,
      {required VoidCallback onView}) {
    return SnackBar(
      key: const Key('tour_ready_snackbar'),
      content: Text(text(req)),
      duration: const Duration(seconds: 6),
      action: SnackBarAction(label: 'View', onPressed: onView),
    );
  }
}

/// Route ONE "tour ready" message to the right place. Returns true when it went
/// in-app (a messenger exists and the app is foreground), false when the system
/// notification fallback was used. [onView] is the Listen-tab jump for the in-app
/// action; [isForeground]/[postSystem]/[showInApp] are injectable for tests.
bool routeTourReadyMessage(
  PendingTourRequest req, {
  required VoidCallback onView,
  bool? isForeground,
  bool Function(SnackBar snackBar)? showInApp,
  void Function()? postSystem,
}) {
  final fg = isForeground ?? ForegroundCommunityMessages.instance.isForeground;
  if (fg) {
    final shown = (showInApp ?? _defaultShowInApp)(
      TourReadyMessage.buildSnackBar(req, onView: onView),
    );
    if (shown) return true;
    // No messenger yet — fall through to the system notification so it is never
    // silently dropped.
  }
  (postSystem ?? () => unawaited(NotificationService.showTourReadyNotification(req.title)))();
  return false;
}

bool _defaultShowInApp(SnackBar snackBar) {
  final messenger = communityScaffoldMessengerKey.currentState;
  if (messenger == null) return false;
  try {
    messenger.showSnackBar(snackBar);
    return true;
  } catch (_) {
    return false;
  }
}
