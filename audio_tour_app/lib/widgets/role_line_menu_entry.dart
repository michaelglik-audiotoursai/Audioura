// [LOCAL-763 / D711 §2] The Listen ⋮ menu's FIRST line — the "role line" — as a
// bright, coloured, wrapping, closable strip.
//
// Michael's retest 2026-10-25 on the LOCAL-762 menu:
//   * "The first line is grey and invisible, that makes the whole dialog sad:
//      make it in colour and bright; colours may depend on what it says."
//   * "For the first item on Listen the title goes into multiple lines and the
//      last lines are hidden behind the options." → it must GROW to fit.
//   * "There is no ✕ or close button; one has to find a place behind the dialog
//      for it to disappear." → a ✕ on this row closes the menu.
//
// This is a custom [PopupMenuEntry] (not a [PopupMenuItem]) so that:
//   1. It is NOT selectable (`represents` returns false) — tapping the strip
//      does nothing, exactly like the old disabled role line.
//   2. Its rendered height follows its content (the text [Wrap]s / wraps to as
//      many lines as it needs), so nothing is ever hidden behind the next item,
//      even for the longest label on the narrowest (320 px) phone.
//   3. It can host a real, tappable ✕ button that closes the whole menu via
//      Navigator.pop — the menu route is the top route while it is open.
//
// The colour is chosen by [TourRoleKind] and tuned for BOTH light and dark mode
// (filled strips use white text; the outline + grey variants use a readable
// on-surface tone). See [kCommunityGreen] (LOCAL-757) so the organiser green
// here is the SAME green the community chip and map markers use.

import 'package:flutter/material.dart';

import '../utils/tour_role_label.dart';
import 'community_tour_chip.dart' show kCommunityGreen, kCommunityGreenLight;

/// Visual key on the ✕ close button, for tests and tooling.
const Key kRoleLineCloseKey = Key('role_line_close');

/// Visual key on the role-line strip container, for tests.
const Key kRoleLineStripKey = Key('role_line_strip');

/// Visual key on the bright, tappable ⓘ of a disabled ⋮-menu row, for tests.
const Key kDisabledInfoIconKey = Key('disabled_info_icon');

/// [LOCAL-763 / D711] The CHILD of a ⋮-menu row that LOOKS disabled (grey
/// leading icon + grey title) but whose trailing ⓘ is in the PRIMARY colour and
/// is tappable.
///
/// Michael 2026-10-25: "The (i) mark is grey as an option one cannot click —
/// confusing. If (i) is clickable it should NOT be greyed out." So the action
/// (Edit / Translate / Price) reads as unavailable (grey), while the ⓘ — which
/// IS tappable and shows the reason — is bright. Wrap this in a
/// `PopupMenuItem(value: …)` so the menu selection fires the notice.
Widget disabledMenuInfoChild(
  BuildContext context, {
  required IconData icon,
  required String title,
}) {
  final primary = Theme.of(context).colorScheme.primary;
  return ListTile(
    leading: Icon(icon, color: Colors.grey),
    title: Text(title, style: const TextStyle(color: Colors.grey)),
    trailing: Tooltip(
      message: 'Why is this unavailable?',
      child: Icon(Icons.info_outline,
          key: kDisabledInfoIconKey, size: 20, color: primary),
    ),
    dense: true,
  );
}

/// The resolved colours for one [TourRoleKind] in one [Brightness].
class _RoleLineColors {
  final Color fill; // strip background
  final Color fg; // text + icon colour
  final Color? border; // non-null → an OUTLINE style (transparent-ish fill)
  const _RoleLineColors(this.fill, this.fg, {this.border});
}

/// Pure colour mapping: role kind + brightness → strip colours. Kept here (not
/// in the pure label util) because it needs Material [Color]s; still a plain
/// function so a widget test can reason about it via the rendered strip.
_RoleLineColors _colorsFor(TourRoleKind kind, Brightness b) {
  final dark = b == Brightness.dark;
  switch (kind) {
    case TourRoleKind.ownBlue:
      // Brand blue, filled, white text (same blue family as the app's primary).
      return _RoleLineColors(
          dark ? const Color(0xFF1565C0) : const Color(0xFF1976D2),
          Colors.white);
    case TourRoleKind.organiserGreen:
      // The LOCAL-757 community green, filled, white text.
      return _RoleLineColors(
          dark ? const Color(0xFF2E7D32) : kCommunityGreen, Colors.white);
    case TourRoleKind.communityGreen:
      // A member's community tour: GREEN OUTLINE (not filled) so the organiser's
      // filled green and the member's outline green read as related but
      // distinct. Text is the green itself for contrast on the sheet.
      final green = dark ? kCommunityGreenLight : kCommunityGreen;
      return _RoleLineColors(
          green.withValues(alpha: dark ? 0.18 : 0.10), green,
          border: green);
    case TourRoleKind.broadcastPurple:
      // A podcast/broadcast tone, filled, white text.
      return _RoleLineColors(
          dark ? const Color(0xFF7E57C2) : const Color(0xFF6A3FB5),
          Colors.white);
    case TourRoleKind.audiouraGrey:
      // Neutral blue-grey, filled, white text.
      return _RoleLineColors(
          dark ? const Color(0xFF546E7A) : const Color(0xFF607D8B),
          Colors.white);
  }
}

/// The bright role-line strip, used as the first entry of the Listen ⋮ menu.
/// Generic over the menu's value type [T] so it drops into a
/// `PopupMenuButton<T>`; it never represents a value, so it is non-selectable.
class RoleLineMenuEntry<T> extends PopupMenuEntry<T> {
  const RoleLineMenuEntry({
    super.key,
    required this.line,
    required this.icon,
    this.onClose,
  });

  /// The role line (text + colour kind) from [tourRoleLabel].
  final TourRoleLine line;

  /// The leading icon to show (resolved by the caller from [line.icon]).
  final IconData icon;

  /// Called when the ✕ is tapped. The caller closes the menu (Navigator.pop);
  /// if null, the entry pops its own route.
  final VoidCallback? onClose;

  // Only used by showMenu for initialValue alignment; the real height follows
  // the content. A sensible non-zero estimate for a one/two-line strip.
  @override
  double get height => 44;

  @override
  bool represents(T? value) => false;

  @override
  State<RoleLineMenuEntry<T>> createState() => _RoleLineMenuEntryState<T>();
}

class _RoleLineMenuEntryState<T> extends State<RoleLineMenuEntry<T>> {
  @override
  Widget build(BuildContext context) {
    final colors = _colorsFor(widget.line.kind, Theme.of(context).brightness);
    return Padding(
      // Matches the menu's horizontal insets; a little vertical breathing room.
      padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
      child: Container(
        key: kRoleLineStripKey,
        decoration: BoxDecoration(
          color: colors.fill,
          borderRadius: BorderRadius.circular(8),
          border: colors.border != null
              ? Border.all(color: colors.border!, width: 1.5)
              : null,
        ),
        padding: const EdgeInsets.fromLTRB(10, 6, 4, 6),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Icon(widget.icon, size: 18, color: colors.fg),
            const SizedBox(width: 8),
            // Expanded + a wrapping Text: the strip grows to as many lines as
            // the label needs; nothing is clipped or hidden behind the next
            // item. softWrap true + no maxLines → full text always visible.
            Expanded(
              child: Text(
                widget.line.text,
                softWrap: true,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: colors.fg,
                ),
              ),
            ),
            const SizedBox(width: 4),
            // The ✕ close button. Tooltip "Close"; closes the whole menu.
            Tooltip(
              message: 'Close',
              child: InkWell(
                key: kRoleLineCloseKey,
                customBorder: const CircleBorder(),
                onTap: () {
                  if (widget.onClose != null) {
                    widget.onClose!();
                  } else {
                    Navigator.of(context).pop();
                  }
                },
                child: Padding(
                  padding: const EdgeInsets.all(4),
                  child: Icon(Icons.close, size: 18, color: colors.fg),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
