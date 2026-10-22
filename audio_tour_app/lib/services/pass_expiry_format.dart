// [LOCAL-731 / D701] One shared, Flutter-free formatter that turns the
// server's `expires_at` into a readable pass-expiry line for members.
//
// The server sends `expires_at` as a UTC ISO-8601 string that MAY lack a zone
// designator, e.g. `2026-11-21T15:16:15.422467`. We treat a zone-less string as
// UTC, then show the member LOCAL time. Nothing on the server changes
// (LOCAL-731): this is a pure presentation helper.
//
// We format the date by hand (day, month name, year, 24-h time) rather than add
// the `intl` package — LOCAL-731 forbids new packages, and `intl` is not a
// dependency of this project.
//
// Outputs (D701: a member must see the expiry, and that renewing ADDS days):
//   active, > 1 day left:   "Member until 21 Nov 2026 · 30 days left"
//   active, < 24 h left:    "Member until today 15:16 · ends in 5 hours"
//   expired:                "Expired on 21 Nov 2026"
//   null (free / owner):    null  — the caller renders no line.

class PassExpiryFormat {
  const PassExpiryFormat._();

  static const List<String> _months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];

  // Dart's DateTime.weekday is 1 (Mon) .. 7 (Sun).
  static const List<String> _weekdays = [
    'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun',
  ];

  /// Parse the server's `expires_at`. A zone-less string is treated as UTC
  /// (the server stores UTC). Returns a LOCAL-time [DateTime], or null when the
  /// input is null/blank/unparseable.
  static DateTime? parse(String? expiresAt) {
    if (expiresAt == null) return null;
    final raw = expiresAt.trim();
    if (raw.isEmpty) return null;
    // If the string carries no explicit zone (no trailing Z and no ±hh:mm
    // offset after the time), append Z so DateTime.parse reads it as UTC.
    final hasZone = raw.endsWith('Z') ||
        RegExp(r'[+\-]\d{2}:?\d{2}$').hasMatch(raw);
    final normalised = hasZone ? raw : '${raw}Z';
    final parsed = DateTime.tryParse(normalised);
    if (parsed == null) return null;
    return parsed.toLocal();
  }

  /// `21 Nov 2026`
  static String formatDate(DateTime local) =>
      '${local.day} ${_months[local.month - 1]} ${local.year}';

  /// `15:16` (24-hour, zero-padded).
  static String formatTime(DateTime local) {
    final h = local.hour.toString().padLeft(2, '0');
    final m = local.minute.toString().padLeft(2, '0');
    return '$h:$m';
  }

  /// The one-line expiry text for a member, or null when there is no expiry
  /// (a free community or the owner — the caller then renders no line).
  ///
  /// [now] is injectable for deterministic tests; it defaults to DateTime.now().
  static String? format(String? expiresAt, {DateTime? now}) {
    final local = parse(expiresAt);
    if (local == null) return null;
    final current = (now ?? DateTime.now()).toLocal();
    final remaining = local.difference(current);

    // Expired: the expiry instant is now or in the past (nothing left).
    if (remaining <= Duration.zero) {
      return 'Expired on ${formatDate(local)}';
    }

    // Under 24 hours left: show the clock time and an hour countdown.
    if (remaining.inHours < 24) {
      final hours = remaining.inHours;
      final hourWord = hours == 1 ? 'hour' : 'hours';
      final endsIn = hours >= 1
          ? 'ends in $hours $hourWord'
          : 'ends soon';
      final sameDay = local.year == current.year &&
          local.month == current.month &&
          local.day == current.day;
      final whenLabel =
          sameDay ? 'today ${formatTime(local)}' : '${formatDate(local)} ${formatTime(local)}';
      return 'Member until $whenLabel · $endsIn';
    }

    // More than a day left: whole days remaining, rounded down.
    final days = remaining.inDays;
    final dayWord = days == 1 ? 'day' : 'days';
    return 'Member until ${formatDate(local)} · $days $dayWord left';
  }

  /// `Fri 24 Oct` — weekday, day and short month, no year. Used by the short
  /// countdown variant [formatShort] that the 3-day pass-expiry WARNING shows
  /// (LOCAL-732). The year is dropped because the warning only fires inside a
  /// 72-hour window, so the year is never ambiguous.
  static String formatWeekdayDate(DateTime local) =>
      '${_weekdays[local.weekday - 1]} ${local.day} ${_months[local.month - 1]}';

  /// [LOCAL-732] The short expiry line for the 3-day warning dialog, e.g.
  /// `Fri 24 Oct · in 2 days` or `Sat 25 Oct · in 5 hours`. Returns null when
  /// there is no expiry (free community / owner) or the pass has already
  /// expired — the warning only concerns an ACTIVE pass that ends soon, and the
  /// caller filters those out, but we return null defensively so a caller can
  /// never render a nonsensical "in 0 days" line for a lapsed pass.
  ///
  /// [now] is injectable for deterministic tests; it defaults to DateTime.now().
  static String? formatShort(String? expiresAt, {DateTime? now}) {
    final local = parse(expiresAt);
    if (local == null) return null;
    final current = (now ?? DateTime.now()).toLocal();
    final remaining = local.difference(current);

    // Already expired (or exactly now): nothing left to warn about.
    if (remaining <= Duration.zero) return null;

    final when = formatWeekdayDate(local);

    // Under 24 hours left: count down in hours (a "days" count would read 0).
    if (remaining.inHours < 24) {
      final hours = remaining.inHours;
      if (hours < 1) return '$when · ends soon';
      final hourWord = hours == 1 ? 'hour' : 'hours';
      return '$when · in $hours $hourWord';
    }

    // A day or more left: whole days, rounded down.
    final days = remaining.inDays;
    final dayWord = days == 1 ? 'day' : 'days';
    return '$when · in $days $dayWord';
  }
}
