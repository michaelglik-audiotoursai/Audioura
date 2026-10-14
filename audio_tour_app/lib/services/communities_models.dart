// [LOCAL-690] Communities model + pure helpers (D657 / D658 + addenda).
//
// This file is DEPENDENCY-FREE on purpose: no Endpoints, no plugins, no Flutter
// — only Dart. It holds the JSON models and the pure UI rules so they can be
// unit-tested directly (test/communities_service_test.dart) without a running
// app. The networked client lives in communities_service.dart and imports this.
//
// Parsing is defensive: a missing or malformed field never throws (the UI must
// degrade gracefully if the user-api is briefly unreachable or older-shaped).

/// The organiser card shown on a community page (D658 (c)).
class Organiser {
  final String? name;
  final String? photoUrl;
  final String? bio;
  final String? contact;

  const Organiser({this.name, this.photoUrl, this.bio, this.contact});

  factory Organiser.fromJson(Map<String, dynamic>? j) {
    if (j == null) return const Organiser();
    return Organiser(
      name: j['name'] as String?,
      photoUrl: j['photo_url'] as String?,
      bio: j['bio'] as String?,
      contact: j['contact'] as String?,
    );
  }
}

/// A pass option a community offers (price × length). The `label` is server-
/// supplied ("$5 / month"); the app never computes a price.
class CommunityPass {
  final String productId;
  final String length; // day | week | month | year
  final int durationDays;
  final double priceUsd;
  final String label;

  const CommunityPass({
    required this.productId,
    required this.length,
    required this.durationDays,
    required this.priceUsd,
    required this.label,
  });

  factory CommunityPass.fromJson(Map<String, dynamic> j) => CommunityPass(
        productId: (j['product_id'] ?? '') as String,
        length: (j['length'] ?? '') as String,
        durationDays: (j['duration_days'] is num)
            ? (j['duration_days'] as num).toInt()
            : 0,
        priceUsd: (j['price_usd'] is num) ? (j['price_usd'] as num).toDouble() : 0.0,
        label: (j['label'] ?? '') as String,
      );
}

/// One episode (a tour stop): owner-hosted audio metadata only.
class CommunityEpisode {
  final int position;
  final String title;
  final String audioUrl;
  final String? guid;
  final String source; // link | feed

  const CommunityEpisode({
    required this.position,
    required this.title,
    required this.audioUrl,
    this.guid,
    required this.source,
  });

  factory CommunityEpisode.fromJson(Map<String, dynamic> j) => CommunityEpisode(
        position: (j['position'] is num) ? (j['position'] as num).toInt() : 0,
        title: (j['title'] ?? '') as String,
        audioUrl: (j['audio_url'] ?? '') as String,
        guid: j['guid'] as String?,
        source: (j['source'] ?? 'link') as String,
      );
}

/// The member's own status on a community (D658 (c): "the member's own status
/// and expiry").
class MyStatus {
  final bool isMember;
  final bool active;
  final String? expiresAt;

  const MyStatus({required this.isMember, required this.active, this.expiresAt});

  factory MyStatus.fromJson(Map<String, dynamic>? j) {
    if (j == null) return const MyStatus(isMember: false, active: false);
    return MyStatus(
      isMember: j['is_member'] == true,
      active: j['active'] == true,
      expiresAt: j['expires_at'] as String?,
    );
  }
}

/// The full community page payload.
class Community {
  final int id;
  final String name;
  final String? description;
  final Organiser organiser;
  final String? rulesText;
  final String? waiverText;
  final bool hasWaiver;
  final bool isPaid;
  final String visibility; // listed | private
  final bool disabled;
  final double? latitude;
  final double? longitude;
  final List<CommunityPass> passes;
  final List<CommunityEpisode> episodes;
  final int episodeCount;
  final bool isOwner;
  final MyStatus myStatus;
  final String? joinCode; // present on create / to the owner
  final String? inviteMessage; // present on create
  final String? joinMessage; // present on resolve-by-code

  const Community({
    required this.id,
    required this.name,
    this.description,
    required this.organiser,
    this.rulesText,
    this.waiverText,
    required this.hasWaiver,
    required this.isPaid,
    required this.visibility,
    required this.disabled,
    this.latitude,
    this.longitude,
    required this.passes,
    required this.episodes,
    required this.episodeCount,
    required this.isOwner,
    required this.myStatus,
    this.joinCode,
    this.inviteMessage,
    this.joinMessage,
  });

  factory Community.fromJson(Map<String, dynamic> j) {
    List<T> list<T>(dynamic v, T Function(Map<String, dynamic>) f) =>
        (v is List)
            ? v
                .whereType<Map<String, dynamic>>()
                .map(f)
                .toList(growable: false)
            : <T>[];
    return Community(
      id: (j['id'] is num) ? (j['id'] as num).toInt() : 0,
      name: (j['name'] ?? '') as String,
      description: j['description'] as String?,
      organiser: Organiser.fromJson(j['organiser'] as Map<String, dynamic>?),
      rulesText: j['rules_text'] as String?,
      waiverText: j['waiver_text'] as String?,
      hasWaiver: j['has_waiver'] == true,
      isPaid: j['is_paid'] == true,
      visibility: (j['visibility'] ?? 'private') as String,
      disabled: j['disabled'] == true,
      latitude: (j['latitude'] is num) ? (j['latitude'] as num).toDouble() : null,
      longitude:
          (j['longitude'] is num) ? (j['longitude'] as num).toDouble() : null,
      passes: list(j['passes'], CommunityPass.fromJson),
      episodes: list(j['episodes'], CommunityEpisode.fromJson),
      episodeCount:
          (j['episode_count'] is num) ? (j['episode_count'] as num).toInt() : 0,
      isOwner: j['is_owner'] == true,
      myStatus: MyStatus.fromJson(j['my_status'] as Map<String, dynamic>?),
      joinCode: j['join_code'] as String?,
      inviteMessage: j['invite_message'] as String?,
      joinMessage: j['join_message'] as String?,
    );
  }
}

/// A Listed community pin for the Home map (community badge).
class CommunityMapPin {
  final int id;
  final String name;
  final double latitude;
  final double longitude;
  final bool isPaid;
  final String badge; // 'community'

  const CommunityMapPin({
    required this.id,
    required this.name,
    required this.latitude,
    required this.longitude,
    required this.isPaid,
    required this.badge,
  });

  factory CommunityMapPin.fromJson(Map<String, dynamic> j) => CommunityMapPin(
        id: (j['id'] is num) ? (j['id'] as num).toInt() : 0,
        name: (j['name'] ?? '') as String,
        latitude: (j['latitude'] is num) ? (j['latitude'] as num).toDouble() : 0,
        longitude:
            (j['longitude'] is num) ? (j['longitude'] as num).toDouble() : 0,
        isPaid: j['is_paid'] == true,
        badge: (j['badge'] ?? 'community') as String,
      );
}

/// A joined community for the Listen tab origin label (⋯ → Origin).
class JoinedCommunity {
  final int id;
  final String name;
  final String? organiserName;
  final bool active;
  final String? expiresAt;

  const JoinedCommunity({
    required this.id,
    required this.name,
    this.organiserName,
    required this.active,
    this.expiresAt,
  });

  factory JoinedCommunity.fromJson(Map<String, dynamic> j) => JoinedCommunity(
        id: (j['id'] is num) ? (j['id'] as num).toInt() : 0,
        name: (j['name'] ?? '') as String,
        organiserName: j['organiser_name'] as String?,
        active: j['active'] == true,
        expiresAt: j['expires_at'] as String?,
      );
}

/// Pure, Flutter-free helpers for the Communities UI. The heart of the
/// app-side unit tests (no network, no widgets).
class CommunityRules {
  /// The origin label shown on a Listen-tab row and in the ⋯ → Origin menu.
  /// "Audioura" for the app's own tours; the community name (and organiser)
  /// for a joined community tour (D658 addendum 2 §3).
  static String originLabel({String? communityName, String? organiserName}) {
    if (communityName == null || communityName.isEmpty) return 'Audioura';
    if (organiserName != null && organiserName.isNotEmpty) {
      return '$communityName — $organiserName';
    }
    return communityName;
  }

  /// The non-member join framing shown when a code resolves to a community the
  /// listener has not joined (D658 addendum 2 §3). Exactly the server wording.
  static String joinFraming(String communityName) =>
      'This tour belongs to $communityName. Join to listen.';

  /// Whether a community may be Listed. A waiver community is ALWAYS Private
  /// (D658/D656); a Listed community needs a location. Returns the forced
  /// visibility so the Generate form cannot submit an illegal combination.
  static String forcedVisibility({
    required bool hasWaiver,
    required String requested,
  }) =>
      hasWaiver ? 'private' : requested;

  /// Community tours DOWNLOAD by default (D658 addendum §: not stream) so an
  /// owner-host outage only affects people joining later. Always true for a
  /// community tour.
  static bool downloadByDefault() => true;
}
