// [LOCAL-762 / D711 §2] The Listen ⋮ menu's role line: one short grey line that
// tells the listener what the tour is and their relationship to it. It is the
// FIRST, non-tappable entry of the ⋮ menu.
//
// `tourRoleLabel` is a PURE function of the cached role fields on a Listen
// record plus the current user id, so every case is unit-testable without the
// widget. The role fields are stamped on the record from GET /tour/<id>/role
// (TourRole.toRecordJson) and refreshed on Listen open.
//
// Cases (D711 §2):
//   * "Your tour"                                     — you created it, no community
//   * "Your community tour — you are the organiser"   — you created it, your community
//   * "Community tour · <name>"                       — a generated community tour
//   * "Broadcast tour · <name>"                       — an organiser-audio tour
//   * "Broadcast tour · <name> — you are the organiser"
//   * "Audioura tour"                                 — anything else (a plain Audioura tour)
//
// Every read is defensive (bool/num/String or missing) and never throws, so a
// record with no role fields (older payload / offline) reads as "Audioura tour".

/// Icon hint for the role line, so the caller can pick a matching leading icon
/// without re-deriving the case. Kept alongside the label as a small enum.
enum TourRoleIcon { person, group, broadcast, audioura }

/// [LOCAL-763 / D711 §2] Colour family for the role line's bright chip. One per
/// relationship so the ⋮ menu's first line reads its meaning by colour at a
/// glance (Michael 2026-10-25: "make it in colour and bright; colours may
/// depend on what it says"). The widget maps each kind to a fill/text/border
/// that passes contrast in BOTH light and dark mode:
///   * ownBlue        — your own (non-community) tour: brand blue, filled.
///   * organiserGreen — your community tour, you are the organiser: the
///                      LOCAL-757 community green, filled.
///   * communityGreen — a community tour you did NOT create: green OUTLINE.
///   * broadcastPurple— a broadcast (organiser-audio/podcast) tour: purple.
///   * audiouraGrey   — a plain Audioura tour: neutral blue-grey.
enum TourRoleKind {
  ownBlue,
  organiserGreen,
  communityGreen,
  broadcastPurple,
  audiouraGrey,
}

/// The role line result: the [text] to show, an [icon] hint and a colour
/// [kind] for the bright chip.
class TourRoleLine {
  final String text;
  final TourRoleIcon icon;
  final TourRoleKind kind;
  const TourRoleLine(this.text, this.icon, this.kind);

  @override
  bool operator ==(Object other) =>
      other is TourRoleLine &&
      other.text == text &&
      other.icon == icon &&
      other.kind == kind;

  @override
  int get hashCode => Object.hash(text, icon, kind);

  @override
  String toString() => 'TourRoleLine($text, $icon, $kind)';
}

bool _b(dynamic v) => v == true;

String? _s(dynamic v) {
  if (v is String) {
    final t = v.trim();
    return t.isEmpty ? null : t;
  }
  return null;
}

/// Build the role line for a Listen [record] as seen by [userId].
///
/// [record] carries the role fields stamped from the server (is_owner,
/// is_community, is_organiser, is_broadcast / source_kind, community_name).
/// [userId] is accepted for API symmetry and future per-viewer nuance; the
/// owner/organiser flags are already resolved per-viewer on the server, so the
/// function relies on them and treats a missing flag as false.
TourRoleLine tourRoleLabel(Map<String, dynamic> record, String? userId) {
  final isOwner = _b(record['is_owner']);
  final isOrganiser = _b(record['is_organiser']);
  final isBroadcast =
      _b(record['is_broadcast']) || _s(record['source_kind']) == 'organiser_audio';
  final isCommunity = _b(record['is_community']) || record['community_id'] is num;
  final communityName = _s(record['community_name']);

  // A broadcast (organiser-audio) tour, named by its community.
  if (isBroadcast) {
    final base = communityName != null
        ? 'Broadcast tour · $communityName'
        : 'Broadcast tour';
    return TourRoleLine(
      isOrganiser ? '$base — you are the organiser' : base,
      TourRoleIcon.broadcast,
      TourRoleKind.broadcastPurple,
    );
  }

  // Your own tour.
  if (isOwner) {
    if (isCommunity && isOrganiser) {
      return const TourRoleLine(
        'Your community tour — you are the organiser',
        TourRoleIcon.group,
        TourRoleKind.organiserGreen,
      );
    }
    // Your own community tour where you are NOT the organiser is still "your
    // tour" from your side (you created it); name the community so it is clear.
    if (isCommunity && communityName != null) {
      return TourRoleLine('Your tour · $communityName', TourRoleIcon.group,
          TourRoleKind.communityGreen);
    }
    return const TourRoleLine(
        'Your tour', TourRoleIcon.person, TourRoleKind.ownBlue);
  }

  // A generated community tour you did not create.
  if (isCommunity) {
    final base = communityName != null
        ? 'Community tour · $communityName'
        : 'Community tour';
    return TourRoleLine(
      isOrganiser ? '$base — you are the organiser' : base,
      TourRoleIcon.group,
      // Organiser of a community tour → filled green; a plain member → outline.
      isOrganiser ? TourRoleKind.organiserGreen : TourRoleKind.communityGreen,
    );
  }

  // Anything else: a plain Audioura tour.
  return const TourRoleLine(
      'Audioura tour', TourRoleIcon.audioura, TourRoleKind.audiouraGrey);
}
