// [LOCAL-598] Pure decision logic for the app-open renewal flow.
//
// SUBSCRIPTION_LEVELS.md (D613):
//   • At or after the anniversary, the app asks: renew (buy again) or drop to
//     L1. The server sets `renewal_prompt` for this.
//   • A 3-day warning is shown before the anniversary. The server sets
//     `warn_renewal`. It must appear ONCE per anniversary — not on every
//     resume — so we remember the last anniversary we warned for.
//
// This file holds the pure logic (no Flutter, no I/O) so the launch/resume
// handler and the unit tests both use the exact same rules. The handler feeds
// in the server flags + the stored "last warned anniversary" and gets back a
// plan of what to show.

import 'services/entitlements_service.dart';

/// What the app-open handler should do after a /entitlements/app-open call.
class RenewalAction {
  /// Show the modal renew-or-lapse sheet (server said renewal_prompt).
  final bool showRenewalSheet;

  /// Show the one-time 3-day warning banner.
  final bool showWarningBanner;

  /// When [showWarningBanner] is true, this is the anniversary value the caller
  /// must persist as "already warned" so the banner does not reappear on the
  /// next resume. Null when there is nothing new to record.
  final String? markWarnedAnniversary;

  const RenewalAction({
    required this.showRenewalSheet,
    required this.showWarningBanner,
    required this.markWarnedAnniversary,
  });

  static const RenewalAction none = RenewalAction(
    showRenewalSheet: false,
    showWarningBanner: false,
    markWarnedAnniversary: null,
  );

  @override
  bool operator ==(Object other) =>
      other is RenewalAction &&
      other.showRenewalSheet == showRenewalSheet &&
      other.showWarningBanner == showWarningBanner &&
      other.markWarnedAnniversary == markWarnedAnniversary;

  @override
  int get hashCode => Object.hash(
      showRenewalSheet, showWarningBanner, markWarnedAnniversary);

  @override
  String toString() => 'RenewalAction(sheet: $showRenewalSheet, '
      'banner: $showWarningBanner, mark: $markWarnedAnniversary)';
}

/// Decide what to show on app open.
///
/// Rules:
///   1. renewal_prompt wins: when due, show the sheet and nothing else. (The
///      banner is the pre-anniversary heads-up; once we're AT the anniversary
///      the actionable sheet replaces it.)
///   2. warn_renewal shows the banner ONLY if we have not already warned for
///      THIS anniversary. "This anniversary" is keyed on the anniversary
///      timestamp string, so a new pack (new anniversary) warns again.
///   3. Otherwise nothing.
///
/// [lastWarnedAnniversary] is the anniversary string we last showed the banner
/// for (persisted by the caller), or null if we never have.
RenewalAction decideRenewalAction(
  Entitlements ent, {
  required String? lastWarnedAnniversary,
}) {
  if (ent.renewalPrompt) {
    return const RenewalAction(
      showRenewalSheet: true,
      showWarningBanner: false,
      markWarnedAnniversary: null,
    );
  }

  if (ent.warnRenewal) {
    final ann = ent.anniversaryAt;
    // Only warn once per anniversary. If we've already warned for this exact
    // anniversary value, stay silent.
    if (ann != null && ann != lastWarnedAnniversary) {
      return RenewalAction(
        showRenewalSheet: false,
        showWarningBanner: true,
        markWarnedAnniversary: ann,
      );
    }
  }

  return RenewalAction.none;
}
