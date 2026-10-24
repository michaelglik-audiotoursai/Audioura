// [LOCAL-757 B] The ONE green chip that marks a community tour wherever Home
// surfaces it BEFORE the listener taps — search results, list rows, the map
// carousel, the detail sheet and the multi-tour dialog all use THIS widget, no
// per-screen copies (ticket: "Put the colour and chip in ONE widget").
//
// Michael, 2026-10-24: a community tour looked like every other tour until
// tapped, so people feared "all tours are for community and we are just
// hassling money from them". The chip says, in green, which community a tour
// belongs to and whether it is members-only — e.g.
//   👥 Members only · Salem TV show funs
//   👥 Community tour · Salem TV show funs   (public community tour, D706)
// so the choice to join is informed, not a surprise after the tap.
//
// The green (and the groups icon) also drive the MAP MARKERS via
// [homeMarkerColor] / [homeMarkerIcon], so the marker and the chip read as one
// colour language. The label text is the pure CommunityRules.homeTourChipLabel
// so it can be unit-tested without a widget.

import 'package:flutter/material.dart';

import '../services/communities_models.dart';

/// The community green used by BOTH the chip and the map markers. A single
/// source so the marker and the chip can never drift apart. Chosen for contrast
/// against the map and against both light and dark sheets.
const Color kCommunityGreen = Color(0xFF2E7D32); // Colors.green.shade800
const Color kCommunityGreenLight = Color(0xFF66BB6A); // Colors.green.shade400

/// [LOCAL-757 A] The fill colour for a Home map marker of the given
/// [CommunityRules.homeMarkerKind]. Community pins are green; every other kind
/// keeps exactly its pre-LOCAL-757 colour.
Color homeMarkerColor(String kind) {
  switch (kind) {
    case 'treat':
      return Colors.orange;
    case 'community':
      return kCommunityGreen;
    case 'multiple':
      return Colors.purple;
    case 'single':
    default:
      return Colors.blue;
  }
}

/// [LOCAL-757 A] The icon for a Home map marker of the given
/// [CommunityRules.homeMarkerKind]. A community pin carries the groups (👥)
/// symbol so it reads as "a community's tour"; the others are unchanged.
IconData homeMarkerIcon(String kind) {
  switch (kind) {
    case 'treat':
      return Icons.local_cafe;
    case 'community':
      return Icons.groups;
    case 'multiple':
      return Icons.layers;
    case 'single':
    default:
      return Icons.directions_walk;
  }
}

/// The green community chip. Builds nothing (returns [SizedBox.shrink]) for a
/// plain Audioura tour, so a caller can drop it in unconditionally and a
/// non-community tour never shows it. Pass the tour map straight from
/// `/tours-near` / search results.
class CommunityTourChip extends StatelessWidget {
  const CommunityTourChip({super.key, required this.tour});

  final Map<String, dynamic> tour;

  @override
  Widget build(BuildContext context) {
    final label = CommunityRules.homeTourChipLabel(tour);
    if (label.isEmpty) return const SizedBox.shrink();

    final dark = Theme.of(context).brightness == Brightness.dark;
    // Light mode: solid green fill, white text (high contrast on a white sheet).
    // Dark mode: a lighter-green outline + tinted fill with light-green text, so
    // the chip stays legible and does not glare on a dark sheet. Both pass
    // WCAG AA for the 13-px text used here.
    final Color fill = dark ? kCommunityGreen.withValues(alpha: 0.22) : kCommunityGreen;
    final Color border = dark ? kCommunityGreenLight : kCommunityGreen;
    final Color fg = dark ? kCommunityGreenLight : Colors.white;

    return Container(
      key: const Key('community_tour_chip'),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: border, width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.groups, size: 16, color: fg),
          const SizedBox(width: 5),
          Flexible(
            child: Text(
              label,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: fg,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
