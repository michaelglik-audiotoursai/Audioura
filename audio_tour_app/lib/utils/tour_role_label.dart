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

/// The role line result: the [text] to show and an [icon] hint.
class TourRoleLine {
  final String text;
  final TourRoleIcon icon;
  const TourRoleLine(this.text, this.icon);

  @override
  bool operator ==(Object other) =>
      other is TourRoleLine && other.text == text && other.icon == icon;

  @override
  int get hashCode => Object.hash(text, icon);

  @override
  String toString() => 'TourRoleLine($text, $icon)';
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
    );
  }

  // Your own tour.
  if (isOwner) {
    if (isCommunity && isOrganiser) {
      return const TourRoleLine(
        'Your community tour — you are the organiser',
        TourRoleIcon.group,
      );
    }
    // Your own community tour where you are NOT the organiser is still "your
    // tour" from your side (you created it); name the community so it is clear.
    if (isCommunity && communityName != null) {
      return TourRoleLine('Your tour · $communityName', TourRoleIcon.group);
    }
    return const TourRoleLine('Your tour', TourRoleIcon.person);
  }

  // A generated community tour you did not create.
  if (isCommunity) {
    final base = communityName != null
        ? 'Community tour · $communityName'
        : 'Community tour';
    return TourRoleLine(
      isOrganiser ? '$base — you are the organiser' : base,
      TourRoleIcon.group,
    );
  }

  // Anything else: a plain Audioura tour.
  return const TourRoleLine('Audioura tour', TourRoleIcon.audioura);
}
