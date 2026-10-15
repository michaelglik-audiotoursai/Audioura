// [LOCAL-701] Community tour models + pure helpers (D663 §3).
//
// A tour made with Audioura FOR a community. DEPENDENCY-FREE on purpose (no
// Endpoints, no Flutter): the JSON models and the pure Generate-tab selector
// rules live here so they can be unit-tested directly without a running app
// (test/community_tour_test.dart). The networked client lives in
// community_tour_service.dart and imports this.

/// One tour listed on a community page (the episode-like tour list, D663 §3).
class CommunityTour {
  final int id;
  final String name;
  final String requestString;
  final double? lat;
  final double? lng;
  final String visibility; // members | public
  final String contentRating; // general | mature | not_allowed

  const CommunityTour({
    required this.id,
    required this.name,
    required this.requestString,
    this.lat,
    this.lng,
    required this.visibility,
    required this.contentRating,
  });

  bool get isPublic => visibility == 'public';

  factory CommunityTour.fromJson(Map<String, dynamic> j) => CommunityTour(
        id: (j['id'] is num) ? (j['id'] as num).toInt() : 0,
        name: (j['name'] ?? '') as String,
        requestString: (j['request_string'] ?? '') as String,
        lat: (j['lat'] is num) ? (j['lat'] as num).toDouble() : null,
        lng: (j['lng'] is num) ? (j['lng'] as num).toDouble() : null,
        visibility: (j['visibility'] ?? 'members') as String,
        contentRating: (j['content_rating'] ?? 'general') as String,
      );
}

/// The result of GET /communities/<id>/tours: the member-gated tour list.
class CommunityTourList {
  final int communityId;
  final bool isMember;
  final List<CommunityTour> tours;

  const CommunityTourList({
    required this.communityId,
    required this.isMember,
    required this.tours,
  });

  factory CommunityTourList.fromJson(Map<String, dynamic> j) {
    final raw = (j['tours'] as List?) ?? const [];
    return CommunityTourList(
      communityId:
          (j['community_id'] is num) ? (j['community_id'] as num).toInt() : 0,
      isMember: j['is_member'] == true,
      tours: raw
          .whereType<Map<String, dynamic>>()
          .map(CommunityTour.fromJson)
          .toList(growable: false),
    );
  }
}

/// A community an organiser owns, offered as a target on the Generate tab's
/// "For:" selector. Minimal shape (id + name) — the selector only needs those.
class OwnedCommunity {
  final int id;
  final String name;

  const OwnedCommunity({required this.id, required this.name});
}

/// The chosen "For:" target on the Generate tab. Either "Just me / public as
/// usual" (community == null) or a specific owned community with a visibility.
class CommunityTourTarget {
  /// null means "Just me / public as usual" — an ordinary tour, no community.
  final OwnedCommunity? community;

  /// 'members' (default) | 'public'. Ignored when [community] is null.
  final String visibility;

  const CommunityTourTarget({this.community, this.visibility = 'members'});

  /// The default selection on the Generate tab (D663 §3): "Just me / public".
  static const CommunityTourTarget justMe = CommunityTourTarget();

  bool get isCommunity => community != null;
  bool get isPublic => isCommunity && visibility == 'public';

  /// The extra request fields to merge into the generate body. Empty for the
  /// "Just me" default — an ordinary generation, unchanged. For a community
  /// target it adds community_id + community_visibility, which the orchestrator
  /// uses to tag the stored tour (and charges the organiser as normal).
  Map<String, dynamic> generateFields() {
    if (community == null) return const {};
    return {
      'community_id': community!.id,
      'community_visibility':
          (visibility == 'public') ? 'public' : 'members',
    };
  }
}

/// Pure, Flutter-free helpers for the Generate-tab community selector so the
/// options and labels are unit-testable without a widget.
class CommunityTourRules {
  /// The two visibility choices offered when a community is selected (D663 §3):
  ///   members — community page only, members download (DEFAULT).
  ///   public  — on the map with the community badge; download needs a pass.
  static const List<String> visibilityChoices = ['members', 'public'];
  static const String defaultVisibility = 'members';

  /// The label for the "Just me" default option on the selector.
  static const String justMeLabel = 'Just me / public as usual';

  /// The label for a community option, e.g. 'For: my community The Owls'.
  static String communityLabel(String communityName) =>
      'For: my community $communityName';

  /// A one-line explanation of a visibility choice, shown under the selector.
  static String visibilityHint(String visibility) {
    switch (visibility) {
      case 'public':
        return 'Shown on the map with the community badge. Members download it; '
            'a non-member is asked to join.';
      case 'members':
      default:
        return 'Shown only on the community page. Only members download it.';
    }
  }

  /// Whether the "Generate" button may proceed for the chosen target. A PUBLIC
  /// community tour must have coordinates (it goes on the map) — the server
  /// enforces this too (public_needs_location), but the app can warn early.
  /// `hasLocation` is whether the generation request will carry coordinates.
  static bool canGenerate(CommunityTourTarget target, {required bool hasLocation}) {
    if (!target.isCommunity) return true;
    if (target.isPublic && !hasLocation) return false;
    return true;
  }

  /// Only an organiser (owner of ≥ 1 community) sees the "For:" selector at all
  /// (D663 §3). Returns true when the owned-communities list is non-empty.
  static bool selectorVisible(List<OwnedCommunity> ownedCommunities) =>
      ownedCommunities.isNotEmpty;
}
