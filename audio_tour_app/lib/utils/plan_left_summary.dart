// [LOCAL-733 / D703] One Flutter-free place that phrases "what is left" for a
// member, so the plan card, the post-purchase message and the Generate-screen
// line all read the same way and can be unit-tested without a widget.
//
// D703 shows members what is left on their pack now that a new pack ADDS to
// the old one (same level) or converts 1:1 (different level):
//   • $10 Pack (l3):  "8 new tours and 6 stop-adding edits left"
//   • Curator (l4):   "29 operations (new tours or edits) left"
//   • Free (l2):      "1 new tour left today" / "3 new tours left this month"
//   • Introduction (l1) / hidden / admin: nothing (null).
//
// The date is formatted by the caller with PassExpiryFormat.formatDate
// (LOCAL-731) so this file stays date-library-free and Flutter-free.

import '../services/entitlements_service.dart';

class PlanLeftSummary {
  const PlanLeftSummary._();

  static String _tours(int n) => n == 1 ? '1 new tour' : '$n new tours';
  static String _edits(int n) => n == 1 ? '1 edit' : '$n edits';
  static String _ops(int n) => n == 1 ? '1 operation' : '$n operations';

  /// The core "what is left" phrase for the CURRENT level, WITHOUT any date —
  /// e.g. "8 new tours and 6 stop-adding edits", "29 operations (new tours or
  /// edits)", "1 new tour left today", "3 new tours left this month". Returns
  /// null when there is nothing to show for the level (Introduction, an
  /// unknown/hidden level, or no applicable allowance present).
  ///
  /// The pack phrasings (l3/l4) describe the balance only; the day/month
  /// phrasings (Free) carry their own "today"/"this month" because the cadence
  /// is part of the sentence.
  static String? phrase(Entitlements ent) {
    final a = ent.allowances;
    switch (ent.level) {
      case 'l3': // $10 Pack: fresh tours + stop-adding edits.
        final fresh = a.freshLeft;
        final edits = a.editsLeft;
        if (fresh == null && edits == null) return null;
        final parts = <String>[];
        if (fresh != null) parts.add(_tours(fresh));
        if (edits != null) {
          parts.add(edits == 1
              ? '1 stop-adding edit'
              : '$edits stop-adding edits');
        }
        return parts.join(' and ');
      case 'l4': // Curator: a single pool of operations.
        final ops = a.opsLeft;
        if (ops == null) return null;
        return '${_ops(ops)} (new tours or edits)';
      case 'l2': // Free: a daily cadence, with a monthly cap behind it.
        final today = a.toursTodayLeft;
        if (today != null) {
          return '${_tours(today)} left today';
        }
        final month = a.toursThisMonthLeft;
        if (month != null) {
          return '${_tours(month)} left this month';
        }
        return null;
      default: // l1 (Introduction), tester, admin, unknown: nothing extra.
        return null;
    }
  }

  /// The current-plan card headline block, e.g.
  ///   "$10 Pack · 8 new tours and 6 stop-adding edits left · until 22 Nov 2026"
  /// [displayName] is the server display name; [endDate] is the already-
  /// formatted anniversary date (PassExpiryFormat.formatDate) or null.
  /// Returns null when there is nothing to show for the level, so the caller
  /// renders no line (Introduction).
  static String? cardLine(Entitlements ent, {String? endDate}) {
    final p = phrase(ent);
    if (p == null) return null;
    // Free already says "left today/this month"; packs need the "left" word.
    final withLeft = ent.level == 'l2' ? p : '$p left';
    final sb = StringBuffer('${ent.displayName} · $withLeft');
    if (endDate != null) sb.write(' · until $endDate');
    return sb.toString();
  }

  /// The short grey line near the Generate button, e.g.
  ///   "3 new tours left in your pack" (paid), "1 new tour left today" (Free).
  /// Returns null on Introduction / hidden / admin (which the caller hides).
  static String? generateLine(Entitlements ent) {
    switch (ent.level) {
      case 'l3':
        final fresh = ent.allowances.freshLeft;
        if (fresh == null) return null;
        return '${_tours(fresh)} left in your pack';
      case 'l4':
        final ops = ent.allowances.opsLeft;
        if (ops == null) return null;
        return '${_ops(ops)} left in your pack';
      case 'l2':
        final today = ent.allowances.toursTodayLeft;
        if (today != null) return '${_tours(today)} left today';
        final month = ent.allowances.toursThisMonthLeft;
        if (month != null) return '${_tours(month)} left this month';
        return null;
      default:
        return null;
    }
  }

  /// The post-purchase success message, e.g.
  ///   "You now have 8 new tours and 6 edits until 22 Nov 2026."
  /// Uses the short "edits" word (not "stop-adding edits") to keep the snackbar
  /// compact. [endDate] is the formatted anniversary or null.
  static String purchaseMessage(Entitlements ent, {String? endDate}) {
    final a = ent.allowances;
    String? body;
    switch (ent.level) {
      case 'l3':
        final parts = <String>[];
        if (a.freshLeft != null) parts.add(_tours(a.freshLeft!));
        if (a.editsLeft != null) parts.add(_edits(a.editsLeft!));
        if (parts.isNotEmpty) body = parts.join(' and ');
        break;
      case 'l4':
        if (a.opsLeft != null) {
          body = '${_ops(a.opsLeft!)} (new tours or edits)';
        }
        break;
    }
    if (body == null) {
      // A level with no pack balance to report (shouldn't happen after a pack
      // buy, but degrade gracefully).
      return 'Your plan is updated.';
    }
    final tail = endDate != null ? ' until $endDate' : '';
    return 'You now have $body$tail.';
  }
}
