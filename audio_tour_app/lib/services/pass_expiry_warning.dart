// [LOCAL-732] The once-on-entry warning that a community pass ends within 3
// days (72 h). Michael (2026-10-22): "warn member that their subscription to a
// community is about to expire, maybe 3 days before, and only once upon entry
// to Audioura." The server already flags a 3-day reminder (run_reminders in
// user-tracking/communities_api.py, D657/D658) but nothing delivered it; this
// delivers it IN THE APP from data the app already loads (My communities).
//
// This file has two parts:
//   • PassExpiryWarning — a PURE (Flutter-free) selector over the
//     JoinedCommunity list the app already fetches. Unit-tested directly.
//   • PassWarnedStore    — a thin SharedPreferences layer that remembers which
//     (community, expires_at) pairs have already warned, so the SAME pass
//     period never warns twice. A renewal changes expires_at (D701), so the
//     next period warns again. Keeps only the last 50 keys.
//
// Nothing on the server changes (the task is app-only).

import 'package:shared_preferences/shared_preferences.dart';
import 'communities_models.dart';

/// The warning window: a pass warns when it ends within this long.
const Duration kPassWarningWindow = Duration(hours: 72);

/// One community that qualifies for the 3-day pass-expiry warning: it is an
/// active membership whose expiry falls inside the warning window.
class ExpiringPass {
  final JoinedCommunity community;

  const ExpiringPass(this.community);

  int get id => community.id;
  String get name => community.name;

  /// The raw server `expires_at` for this membership. Non-null for a qualifying
  /// pass (a free/no-expiry membership never qualifies). Used both to format
  /// the line and to build the once-key.
  String get expiresAt => community.expiresAt!;

  /// The SharedPreferences once-key for THIS pass period:
  /// `pass_warned_<community_id>_<expires_at>`. A renewal moves expires_at, so
  /// the next period gets a fresh key and warns again (D701).
  String get warnedKey => PassWarnedStore.keyFor(id, expiresAt);
}

/// Pure (Flutter-free) selection of the memberships that should warn.
class PassExpiryWarning {
  const PassExpiryWarning._();

  /// From the member's joined communities, the ones that qualify for the 3-day
  /// warning: ACTIVE, with an expiry that is still in the future and no more
  /// than [window] away (0 < time left ≤ 72 h).
  ///
  /// Skips:
  ///   • free / no-expiry memberships (expires_at null/blank — nothing to
  ///     renew, and `is_membership_active` keeps them active forever);
  ///   • already-expired passes (time left ≤ 0 — that is the AT-expiry case the
  ///     server's own reminder owns, not this 3-day heads-up);
  ///   • passes more than the window away (plenty of time left).
  ///
  /// The owner's own community is already absent: `/communities/mine` lists
  /// MEMBERSHIPS (community_memberships rows), and the owner is not a member of
  /// their own community (D665 addendum), so no owner row is ever returned.
  ///
  /// [now] is injectable for deterministic tests; defaults to DateTime.now().
  static List<ExpiringPass> select(
    List<JoinedCommunity> communities, {
    DateTime? now,
    Duration window = kPassWarningWindow,
  }) {
    final current = (now ?? DateTime.now()).toLocal();
    final out = <ExpiringPass>[];
    for (final c in communities) {
      if (!c.active) continue; // expired/lapsed → not this warning
      final raw = c.expiresAt;
      if (raw == null || raw.trim().isEmpty) continue; // free / no expiry
      final expiry = _parse(raw);
      if (expiry == null) continue; // unparseable → skip rather than guess
      final remaining = expiry.difference(current);
      if (remaining <= Duration.zero) continue; // already expired
      if (remaining > window) continue; // more than 3 days left
      out.add(ExpiringPass(c));
    }
    return out;
  }

  /// Parse the server `expires_at`, treating a zone-less string as UTC (the
  /// server stores UTC). Mirrors PassExpiryFormat.parse but kept local so this
  /// selector stays independent of the Flutter-free formatter's surface.
  static DateTime? _parse(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) return null;
    final hasZone = trimmed.endsWith('Z') ||
        RegExp(r'[+\-]\d{2}:?\d{2}$').hasMatch(trimmed);
    final normalised = hasZone ? trimmed : '${trimmed}Z';
    final parsed = DateTime.tryParse(normalised);
    return parsed?.toLocal();
  }
}

/// Remembers which pass periods have already warned, in SharedPreferences, so
/// the warning fires ONCE per pass period (Michael: "only once upon entry").
///
/// Key shape: `pass_warned_<community_id>_<expires_at>`. The expires_at makes a
/// renewal (new expiry, D701) a new key — the next period warns again. We cap
/// the stored set at [maxKeys] (the 50 most-recently-written) so the list never
/// grows without bound; a member in dozens of communities over years would
/// otherwise accumulate stale keys.
class PassWarnedStore {
  PassWarnedStore._();

  /// The ordered list of already-warned keys, newest last. One SharedPreferences
  /// entry so the 50-key cap is trivial to enforce.
  static const String _prefsKey = 'pass_warned_keys';
  static const int maxKeys = 50;

  /// The once-key for a (community, expires_at) pair.
  static String keyFor(int communityId, String expiresAt) =>
      'pass_warned_${communityId}_$expiresAt';

  /// The currently-remembered keys (order preserved, oldest first).
  static Future<List<String>> _load(SharedPreferences prefs) async =>
      prefs.getStringList(_prefsKey) ?? const <String>[];

  /// Has this pass period already warned?
  static Future<bool> hasWarned(String key) async {
    final prefs = await SharedPreferences.getInstance();
    return (await _load(prefs)).contains(key);
  }

  /// Keep only the passes that have NOT yet warned (from a freshly-selected
  /// set). Pure except for the SharedPreferences read, so callers get the
  /// final to-show list in one step.
  static Future<List<ExpiringPass>> unwarned(List<ExpiringPass> passes) async {
    if (passes.isEmpty) return passes;
    final prefs = await SharedPreferences.getInstance();
    final seen = (await _load(prefs)).toSet();
    return passes.where((p) => !seen.contains(p.warnedKey)).toList();
  }

  /// Record that these pass periods have now warned. Adds each key (skipping
  /// duplicates), then trims to the newest [maxKeys].
  static Future<void> markWarned(Iterable<String> keys) async {
    final prefs = await SharedPreferences.getInstance();
    final list = List<String>.from(await _load(prefs));
    for (final k in keys) {
      list.remove(k); // move an existing key to the "newest" end
      list.add(k);
    }
    // Trim to the most-recent maxKeys (drop from the front — the oldest).
    final trimmed = list.length > maxKeys
        ? list.sublist(list.length - maxKeys)
        : list;
    await prefs.setStringList(_prefsKey, trimmed);
  }
}
