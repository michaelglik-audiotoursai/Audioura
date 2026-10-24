// [LOCAL-690] Communities model + pure helpers (D657 / D658 + addenda).
//
// This file is DEPENDENCY-FREE on purpose: no Endpoints, no plugins, no Flutter
// — only Dart. It holds the JSON models and the pure UI rules so they can be
// unit-tested directly (test/communities_service_test.dart) without a running
// app. The networked client lives in communities_service.dart and imports this.
// (share_code.dart is itself pure Dart, so importing it keeps this file
// Flutter-free — it is the ONE place a share link is built, D671.)
//
// Parsing is defensive: a missing or malformed field never throws (the UI must
// degrade gracefully if the user-api is briefly unreachable or older-shaped).

import '../utils/share_code.dart';

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

/// [LOCAL-710B / D672 addendum 1] A tour MADE WITH Audioura for the community
/// (`audio_tours.community_id = <id>`), newest first. These — never owner
/// MP3/RSS episodes — fill the invite's optional tour line and the invite
/// screen's "Tour to include" picker. The share CODE is NOT stored here: it is
/// fetched on demand via TourShareService.share([id]) (the one share-code
/// system, D671). [stopCount] feeds the "<N> stops" clause; [name] is the raw
/// tour name (shorten with shortTourTitle before display).
class CommunityInviteTourOption {
  final int id;
  final String name;
  final int stopCount;
  final String? createdAt;
  // [LOCAL-711 / D673] The server short title, when the listing carries one.
  final String? shortTitle;
  // [LOCAL-748] The tour's current server version (LOCAL-657) and the ISO date
  // it was last updated, when the listing carries them. Carried so the
  // community-page Download stamps them onto the saved record as its sourceItem
  // (community_id/version/updated_at), which is what CommunityToursSync's
  // held-tour refresh and RefreshPlanner read. Default version 1 (an edit bumps
  // it); updatedAt null when the server omits it.
  final int version;
  final String? updatedAt;

  const CommunityInviteTourOption({
    required this.id,
    required this.name,
    this.stopCount = 0,
    this.createdAt,
    this.shortTitle,
    this.version = 1,
    this.updatedAt,
  });

  factory CommunityInviteTourOption.fromJson(Map<String, dynamic> j) =>
      CommunityInviteTourOption(
        id: (j['id'] is num) ? (j['id'] as num).toInt() : 0,
        name: (j['name'] ?? j['tour_name'] ?? '') as String,
        stopCount: (j['stop_count'] is num)
            ? (j['stop_count'] as num).toInt()
            : (j['stops_count'] is num)
                ? (j['stops_count'] as num).toInt()
                : 0,
        createdAt: (j['created_at'] ?? j['createdAt']) as String?,
        shortTitle: ((j['short_title'] as String?)?.trim().isEmpty ?? true)
            ? null
            : (j['short_title'] as String).trim(),
        version: (j['version'] is num) ? (j['version'] as num).toInt() : 1,
        updatedAt: (j['updated_at'] ?? j['updatedAt']) as String?,
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

/// [LOCAL-702 / D663 §1] A hand-over volunteer the OWNER sees while picking a
/// new organiser. One per member who volunteered.
class OrganiserOffer {
  final String memberUserId;
  final String status; // offered | picked | accepted
  final String? pickedAt;
  final String? acceptedAt;
  final String? offeredAt;

  const OrganiserOffer({
    required this.memberUserId,
    required this.status,
    this.pickedAt,
    this.acceptedAt,
    this.offeredAt,
  });

  bool get isPicked => status == 'picked';

  factory OrganiserOffer.fromJson(Map<String, dynamic> j) => OrganiserOffer(
        memberUserId: (j['member_user_id'] ?? '') as String,
        status: (j['status'] ?? 'offered') as String,
        pickedAt: j['picked_at'] as String?,
        acceptedAt: j['accepted_at'] as String?,
        offeredAt: j['offered_at'] as String?,
      );
}

/// [LOCAL-702 / D663 §1] The CALLER's own hand-over offer, so the app can show
/// "You volunteered" and, when picked, the "Accept" action. Null when the
/// caller has not volunteered.
class MyOffer {
  final String status; // offered | picked | accepted | withdrawn
  final bool picked;
  final String? pickedAt;
  final String? acceptedAt;

  const MyOffer({
    required this.status,
    required this.picked,
    this.pickedAt,
    this.acceptedAt,
  });

  factory MyOffer.fromJson(Map<String, dynamic>? j) {
    if (j == null) return const MyOffer(status: 'none', picked: false);
    return MyOffer(
      status: (j['status'] ?? 'none') as String,
      picked: j['picked'] == true,
      pickedAt: j['picked_at'] as String?,
      acceptedAt: j['accepted_at'] as String?,
    );
  }
}

/// [LOCAL-703 / D664] The launch window: a new community must win its first two
/// QUALIFYING members (excluding the owner) within the window, or it is
/// archived and its invite code stops working. The organiser sees a live
/// countdown that turns into "Launched 🎉" once met.
class CommunityLaunch {
  final String? deadline; // ISO8601, when the window closes
  final int hoursLeft; // whole hours remaining, never negative
  final int membersNeeded; // the bar (2)
  final int membersSoFar; // qualifying members so far (owner excluded)
  final bool launched; // true once the bar is met — countdown gone for good
  final String? launchedAt;

  const CommunityLaunch({
    this.deadline,
    required this.hoursLeft,
    required this.membersNeeded,
    required this.membersSoFar,
    required this.launched,
    this.launchedAt,
  });

  factory CommunityLaunch.fromJson(Map<String, dynamic>? j) {
    if (j == null) {
      return const CommunityLaunch(
          hoursLeft: 0, membersNeeded: 2, membersSoFar: 0, launched: false);
    }
    return CommunityLaunch(
      deadline: j['deadline'] as String?,
      hoursLeft: (j['hours_left'] is num) ? (j['hours_left'] as num).toInt() : 0,
      membersNeeded:
          (j['members_needed'] is num) ? (j['members_needed'] as num).toInt() : 2,
      membersSoFar:
          (j['members_so_far'] is num) ? (j['members_so_far'] as num).toInt() : 0,
      launched: j['launched'] == true,
      launchedAt: j['launched_at'] as String?,
    );
  }
}

/// The full community page payload.
class Community {
  final int id;
  final String name;
  final String? description;
  // [LOCAL-726 item 10] The organiser's user_id — the target when a member
  // blocks the organiser from the community page. May be null on older payloads.
  final String? ownerUserId;
  final Organiser organiser;
  final String? rulesText;
  final String? waiverText;
  final bool hasWaiver;
  final bool isPaid;
  final String visibility; // listed | private
  final bool disabled;
  final double? latitude;
  final double? longitude;
  // [LOCAL-738 / C2c] How often members get new tours (day|week|month|year).
  final String releaseCadence;
  final List<CommunityPass> passes;
  final List<CommunityEpisode> episodes;
  final int episodeCount;
  // [LOCAL-710B / D672 addendum 1] The community's own tours (audio_tours.
  // community_id = id), newest first. Fills the invite tour line + the invite
  // screen's "Tour to include" picker. Empty → no picker, no tour line.
  final List<CommunityInviteTourOption> tours;
  // [LOCAL-704 / D665] The community's member count: active members (unexpired
  // paid passes), owner excluded. Shown on the community page, My communities,
  // search/code results, the map pin sheet and the invite email.
  final int memberCount;
  final bool isOwner;
  final MyStatus myStatus;
  final String? joinCode; // present on create / to the owner
  final String? inviteMessage; // present on create
  final String? joinMessage; // present on resolve-by-code
  // [LOCAL-702 / D663 §1] The organiser step-down state machine.
  final String status; // active | handover | archived
  final bool lookingForOrganiser; // true while in hand-over
  final bool archived; // true once archived
  final bool acceptsNewMembers; // false in handover/archived
  final String? steppedDownAt;
  final String? archivedAt;
  final List<OrganiserOffer> organiserOffers; // owner view, during hand-over
  final MyOffer? myOffer; // the caller's own offer, during hand-over
  // [LOCAL-703 / D664] The launch window / countdown.
  final CommunityLaunch launch;

  const Community({
    required this.id,
    required this.name,
    this.description,
    this.ownerUserId,
    required this.organiser,
    this.rulesText,
    this.waiverText,
    required this.hasWaiver,
    required this.isPaid,
    required this.visibility,
    required this.disabled,
    this.latitude,
    this.longitude,
    this.releaseCadence = 'week',
    required this.passes,
    required this.episodes,
    required this.episodeCount,
    this.tours = const [],
    this.memberCount = 0,
    required this.isOwner,
    required this.myStatus,
    this.joinCode,
    this.inviteMessage,
    this.joinMessage,
    this.status = 'active',
    this.lookingForOrganiser = false,
    this.archived = false,
    this.acceptsNewMembers = true,
    this.steppedDownAt,
    this.archivedAt,
    this.organiserOffers = const [],
    this.myOffer,
    this.launch = const CommunityLaunch(
        hoursLeft: 0, membersNeeded: 2, membersSoFar: 0, launched: false),
  });

  /// [LOCAL-710B / D672 addendum 1] The cheapest pass this community offers, or
  /// null when it offers none. The server returns [passes] ordered by price
  /// ascending, so the first is the cheapest. Quotes "a pass starts at $5 for
  /// week" in the invite.
  CommunityPass? get cheapestPass => passes.isEmpty ? null : passes.first;

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
      ownerUserId: j['owner_user_id'] as String?,
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
      releaseCadence: (j['release_cadence'] ?? 'week') as String,
      passes: list(j['passes'], CommunityPass.fromJson),
      episodes: list(j['episodes'], CommunityEpisode.fromJson),
      tours: list(j['tours'], CommunityInviteTourOption.fromJson),
      episodeCount:
          (j['episode_count'] is num) ? (j['episode_count'] as num).toInt() : 0,
      memberCount:
          (j['member_count'] is num) ? (j['member_count'] as num).toInt() : 0,
      isOwner: j['is_owner'] == true,
      myStatus: MyStatus.fromJson(j['my_status'] as Map<String, dynamic>?),
      joinCode: j['join_code'] as String?,
      inviteMessage: j['invite_message'] as String?,
      joinMessage: j['join_message'] as String?,
      status: (j['status'] ?? 'active') as String,
      lookingForOrganiser: j['looking_for_organiser'] == true,
      archived: j['archived'] == true,
      // Default TRUE when the server omits the field (older shape = active).
      acceptsNewMembers: j['accepts_new_members'] != false,
      steppedDownAt: j['stepped_down_at'] as String?,
      archivedAt: j['archived_at'] as String?,
      organiserOffers: list(j['organiser_offers'], OrganiserOffer.fromJson),
      myOffer: j['my_offer'] is Map<String, dynamic>
          ? MyOffer.fromJson(j['my_offer'] as Map<String, dynamic>)
          : null,
      launch: CommunityLaunch.fromJson(j['launch'] as Map<String, dynamic>?),
    );
  }
}

/// [LOCAL-738 §2 / Michael's review C2b] One allowed pass PRICE the organiser
/// may offer, from the SERVER (GET /communities/pass-prices, built from the
/// single APPLE_LIVE_PASS_PRODUCTS list). The create form fills its price chips
/// from these — never a second hard-coded copy in the app. [label] is the
/// server's display price ('$5'); [priceUsd] orders them.
class PassPrice {
  final String productId;
  final double priceUsd;
  final String label;

  const PassPrice({
    required this.productId,
    required this.priceUsd,
    required this.label,
  });

  factory PassPrice.fromJson(Map<String, dynamic> j) => PassPrice(
        productId: (j['product_id'] ?? '') as String,
        priceUsd: (j['price_usd'] is num) ? (j['price_usd'] as num).toDouble() : 0.0,
        label: (j['label'] ?? '') as String,
      );
}

/// [LOCAL-738 §3 / Michael's review C2] The outcome of a create attempt. On
/// success [community] is non-null; on failure it is null and [error] +
/// [message] carry the SERVER's own words (e.g. error 'name_taken', message
/// "That community name is taken.") so the form shows the real reason — never
/// the generic "the name may be taken, or you may need a plan" guess that
/// hid every failure on Michael's iPhone. A transport failure (no HTTP answer)
/// leaves both null and sets [message] to a short connection note.
class CreateResult {
  final Community? community;
  final String? error;
  final String? message;

  const CreateResult({this.community, this.error, this.message});

  bool get ok => community != null;
}

/// [LOCAL-754B / D658 addendum 2] The outcome of building an organiser-audio
/// tour. On success [tourId] + [sourceKind] ('organiser_audio') + [communityId]
/// are set; on a validation failure [error] (e.g. 'audio_unreachable'),
/// [message] and [stopName] (the failing stop, when the server named one) carry
/// the server's own words so the builder screen can point at the exact stop; a
/// transport failure leaves them null with a short connection [message].
class BuildAudioTourResult {
  final int? tourId;
  final String? sourceKind;
  final int? communityId;
  final String? error;
  final String? stopName;
  final String? message;

  const BuildAudioTourResult({
    this.tourId,
    this.sourceKind,
    this.communityId,
    this.error,
    this.stopName,
    this.message,
  });

  bool get ok => tourId != null;
}

/// [LOCAL-703 / D664] The outcome of resolving an invite code. Exactly one of
/// three states: a resolved [community] (200), [closed] = true when the code
/// belongs to an archived community (410 community_closed → "This community has
/// closed."), or neither (not found / unreachable → the generic message).
class CodeResolution {
  final Community? community;
  final bool closed;

  const CodeResolution({this.community, this.closed = false});

  bool get found => community != null;
}

/// A Listed community pin for the Home map (community badge).
class CommunityMapPin {
  final int id;
  final String name;
  final double latitude;
  final double longitude;
  final bool isPaid;
  final String badge; // 'community'
  // [LOCAL-704 / D665] Member count shown on the map pin sheet.
  final int memberCount;

  const CommunityMapPin({
    required this.id,
    required this.name,
    required this.latitude,
    required this.longitude,
    required this.isPaid,
    required this.badge,
    this.memberCount = 0,
  });

  factory CommunityMapPin.fromJson(Map<String, dynamic> j) => CommunityMapPin(
        id: (j['id'] is num) ? (j['id'] as num).toInt() : 0,
        name: (j['name'] ?? '') as String,
        latitude: (j['latitude'] is num) ? (j['latitude'] as num).toDouble() : 0,
        longitude:
            (j['longitude'] is num) ? (j['longitude'] as num).toDouble() : 0,
        isPaid: j['is_paid'] == true,
        badge: (j['badge'] ?? 'community') as String,
        memberCount:
            (j['member_count'] is num) ? (j['member_count'] as num).toInt() : 0,
      );
}

/// A joined community for the Listen tab origin label (⋯ → Origin).
class JoinedCommunity {
  final int id;
  final String name;
  final String? organiserName;
  final bool active;
  final String? expiresAt;
  // [LOCAL-704 / D665] Member count shown on each My communities row.
  final int memberCount;

  const JoinedCommunity({
    required this.id,
    required this.name,
    this.organiserName,
    required this.active,
    this.expiresAt,
    this.memberCount = 0,
  });

  factory JoinedCommunity.fromJson(Map<String, dynamic> j) => JoinedCommunity(
        id: (j['id'] is num) ? (j['id'] as num).toInt() : 0,
        name: (j['name'] ?? '') as String,
        organiserName: j['organiser_name'] as String?,
        active: j['active'] == true,
        expiresAt: j['expires_at'] as String?,
        memberCount:
            (j['member_count'] is num) ? (j['member_count'] as num).toInt() : 0,
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

  /// [LOCAL-739 §2] Whether this user BELONGS TO or ORGANISES at least one
  /// community. This is the single gate for the three members-only entry points
  /// (the Home map chip, the Generate link, the Listen "My communities (N)"
  /// row): non-members see none of them, members see all three. A user counts
  /// as a member when the joined list (/communities/mine) is non-empty OR the
  /// owned list (/communities/mine-owned) is non-empty — an organiser whose own
  /// community has no membership row still qualifies.
  static bool hasAnyCommunity({
    required int joinedCount,
    required int ownedCount,
  }) =>
      joinedCount > 0 || ownedCount > 0;

  /// [LOCAL-739 §3] The gate shown when a NON-MEMBER taps Download on a
  /// members-only community tour (found on Home or opened from an emailed
  /// link): "This tour is for members of <community>", with a Join action that
  /// opens the community page and its passes. Falls back to a generic wording
  /// when the community name is not known yet.
  static String membersOnlyTourGate(String? communityName) =>
      (communityName == null || communityName.isEmpty)
          ? 'This tour is for members of a community.'
          : 'This tour is for members of $communityName.';

  /// [LOCAL-739 §2] The count shown in the Listen "My communities (N)" row and
  /// anywhere a single combined total is needed: the DISTINCT communities a
  /// user belongs to or organises. An owned community that also has a
  /// membership row for the same user is counted once.
  static int yourCommunitiesCount({
    required Iterable<int> joinedIds,
    required Iterable<int> ownedIds,
  }) =>
      <int>{...joinedIds, ...ownedIds}.length;
}

/// [LOCAL-739 §1 (1)] One row of the "Your communities" section of the single
/// Communities page: a community the user BELONGS TO (a [JoinedCommunity] from
/// /communities/mine) or ORGANISES (an owned community from
/// /communities/mine-owned), merged so the page shows ONE list with no second
/// copy. [joined] carries the member status/expiry for a member row; it is null
/// for an organiser-only row, which shows "You are the organizer" instead.
class YourCommunity {
  final int id;
  final String name;

  /// True when the user organises this community (owns it). An organiser row
  /// shows "You are the organizer" rather than a membership/expiry line.
  final bool isOrganiser;

  /// The membership row for a community the user is a member of; null for an
  /// organiser-only row. When the user both owns AND is a member, the member
  /// row is kept so the expiry can still show, with [isOrganiser] true.
  final JoinedCommunity? joined;

  const YourCommunity({
    required this.id,
    required this.name,
    required this.isOrganiser,
    this.joined,
  });

  /// [LOCAL-739 §1] Merge the joined list (/communities/mine) and the owned
  /// list (/communities/mine-owned) into ONE ordered "Your communities" list,
  /// de-duplicated by community id. Organiser-owned communities come first
  /// (the user runs them), then the communities they are only a member of; each
  /// group keeps the input order. A community in BOTH lists appears once, as an
  /// organiser row that still carries its membership expiry.
  static List<YourCommunity> merge({
    required List<JoinedCommunity> joined,
    required List<OwnedCommunityRef> owned,
  }) {
    final joinedById = {for (final j in joined) j.id: j};
    final ownedIds = {for (final o in owned) o.id};
    final out = <YourCommunity>[];
    // Organiser rows first, in the owned-list order.
    for (final o in owned) {
      out.add(YourCommunity(
        id: o.id,
        name: o.name,
        isOrganiser: true,
        joined: joinedById[o.id],
      ));
    }
    // Then member-only rows, in the joined-list order.
    for (final j in joined) {
      if (ownedIds.contains(j.id)) continue; // already shown as an organiser row
      out.add(YourCommunity(
        id: j.id,
        name: j.name,
        isOrganiser: false,
        joined: j,
      ));
    }
    return out;
  }
}

/// [LOCAL-739 §1] The minimal {id, name} an owner's community needs for the
/// "Your communities" merge. This mirrors the OwnedCommunity model that lives
/// in community_tour_models.dart, but communities_models.dart stays
/// dependency-free (it must not import the community-tour layer), so the merge
/// takes this tiny local shape instead. The screen adapts OwnedCommunity into
/// this with [OwnedCommunityRef.fromIdName].
class OwnedCommunityRef {
  final int id;
  final String name;
  const OwnedCommunityRef({required this.id, required this.name});
}

/// [LOCAL-700] Flutter-free COPY + form helpers for the Communities UI, so the
/// wording and the create-form logic are unit-testable without a running app.
class CommunityCopy {
  /// §1: The plain description of BOTH kinds of community content, shown on the
  /// About → Communities screen and (shorter) as the Create intro. Covers:
  ///   • the organiser's OWN audio (MP3 links / an RSS feed they host) —
  ///     Audioura plays it, never stores or checks it; it is theirs;
  ///   • tours MADE WITH Audioura for the community — generated on the Generate
  ///     tab, checked by Audioura (content rating, same as any tour), shown
  ///     only to members. (The feature itself is a later task; only the TEXT
  ///     ships now.)
  static const String aboutContent =
      'A community is a group an organiser runs inside Audioura. There are two '
      'kinds of audio a community can offer its members:\n\n'
      '• Your own audio — MP3 links, or an RSS feed you host. Audioura plays it '
      'to your members. It stays yours: Audioura does not store it and does not '
      'check it.\n\n'
      '• Tours made with Audioura for your community — generated on the Generate '
      'tab like any other tour, and checked by Audioura (content rating, the '
      'same as every generated or edited tour). These are shown only to your '
      'members.\n\n'
      'Communities are paid: a membership is a pass you buy — a day, a week, a '
      'month, or a year — and every member pays at least \$1 to join. Nothing '
      'renews automatically: when a pass ends we remind you, and you can buy '
      'again. Audio you have already downloaded stays with you.';

  /// §1: The shorter intro shown at the top of the Create form.
  static const String createIntro =
      'Your community can offer two kinds of audio: your OWN audio (MP3 links or '
      'an RSS feed you host — Audioura plays it, never stores or checks it), and '
      'tours MADE WITH Audioura for your members (generated on the Generate tab '
      'and checked by Audioura, like any tour).';

  /// §1: The close warning, shown on both About and the Create form (above the
  /// button). A community cannot be closed once members have joined; the
  /// organiser can step down instead.
  static const String closeWarning =
      'Once members have joined, a community cannot be closed. You can step down '
      'as organiser.';

  /// §2: The message when an invite code resolves to no community.
  static const String noCommunityForCode = 'No community with that code.';

  // ── §4: friendly, lightly-humorous prefill pools (≥ 8 variants each) ────────

  /// Name stems — combined with a place to make "The Wandering Owls of Lisbon".
  static const List<String> namePrefixes = [
    'The Wandering Owls',
    'The Curious Pigeons',
    'The Midnight Ramblers',
    'The Lost Umbrella Society',
    'The Slightly Lost Explorers',
    'The Cobblestone Collective',
    'The Rooftop Dreamers',
    'The Backstreet Historians',
    'The Caffeinated Cartographers',
    'The Unhurried Wanderers',
  ];

  static const List<String> descriptions = [
    'We wander, we point at buildings, we make up facts (then correct them). '
        'Mostly we have a good time.',
    'A friendly circle for people who like stories about the places they walk '
        'past every day.',
    'Short audio strolls for the perpetually curious. Comfortable shoes '
        'recommended, strong opinions optional.',
    'We turn ordinary streets into little adventures. No prior wandering '
        'experience required.',
    'For folks who read every plaque and still want to know more. You are '
        'among friends here.',
    'Half history club, half excuse to go for a walk. We regret nothing.',
    'A cosy group that believes every corner has a tale, and most of them are '
        'even true.',
    'We explore slowly, listen closely, and never, ever skip the snack break.',
  ];

  static const List<String> organiserNames = [
    'Alex Rambler',
    'Sam Cobblestone',
    'Jamie Wayfarer',
    'Riley Milestone',
    'Casey Lamplight',
    'Morgan Backstreet',
    'Jordan Fieldnote',
    'Taylor Breadcrumb',
  ];

  static const List<String> bios = [
    'Chief wanderer, amateur historian, professional snack enthusiast.',
    'I have gotten lost in more cities than I can count, and loved every one.',
    'Local guide by day, map-hoarder by night. Ask me about shortcuts.',
    'I collect stories the way other people collect fridge magnets.',
    'Twenty years of walking the same streets and still finding new corners.',
    'Reformed tour-bus skeptic. Now I just point at things and smile.',
    'Equal parts curiosity and comfortable footwear.',
    'I promise the detours are worth it. Usually.',
  ];

  static const List<String> rules = [
    'Be kind, be curious, and keep the volume reasonable near the ducks.',
    'Respect the neighbours, mind the traffic, and share the good spots.',
    'No heckling the statues. Questions always welcome.',
    'Walk at your own pace, look after each other, and have fun.',
    'Leave places better than you found them. Take only photos.',
    'Be on time-ish, be friendly, and never block a doorway.',
    'Curiosity encouraged, littering forbidden, laughter mandatory.',
    'Stay safe, stay together, and tip your local baker.',
  ];

  static const List<String> contacts = [
    'hello@example.com',
    'organiser@example.com',
    'walks@example.com',
    'say-hi@example.com',
  ];

  /// Where to get Audioura. Store links do not exist yet (D658 era), so use the
  /// marketing site until they do.
  static const String installUrl = 'https://audioura.com';

  /// §4: A UNIQUE community name from a chosen stem + place, with a short
  /// numeric suffix only when the plain name is already taken. [attempt] 0 is
  /// the plain name; attempt ≥ 1 appends a 2-digit suffix. Deterministic given
  /// [stem], [place] and [attempt] so a test can assert it.
  static String uniqueName(String stem, String place, {int attempt = 0}) {
    final base = place.trim().isEmpty ? stem : '$stem of ${place.trim()}';
    if (attempt <= 0) return base;
    // A short, friendly suffix (01..99) wrapped so it reads deliberately.
    final suffix = (attempt % 99) + 1;
    return '$base (${suffix.toString().padLeft(2, '0')})';
  }

  /// [LOCAL-704 / D665] A short "N members" label shown on the community page,
  /// My communities, search/code results and the map pin sheet. Pure so the
  /// exact wording ("1 member" vs "12 members") is unit-testable. The organiser
  /// is never counted (D665 addendum).
  static String memberCountLabel(int count) =>
      count == 1 ? '1 member' : '$count members';

  /// §4 + [LOCAL-710 / D672 → LOCAL-710B addenda 1 + 2]: The email body an
  /// organiser sends to invite members. The invite now EXPLAINS ITSELF
  /// (Michael did not like "A demo PAID community:"): a standard sentence about
  /// what a community is, the organiser's description as "About this
  /// community:", the restriction lines generated from the community's REAL
  /// settings (paid/free, private/listed, waiver, rules, member-only
  /// downloads), the organiser + member count, an optional tour line (the
  /// picked tour, else the latest), and finally the join link + code.
  ///
  /// Delegates to [buildCommunityInvite] (share_code.dart) so the sending side
  /// and the tests share one implementation. The returned string ALWAYS
  /// contains the code + the link. Never claims the email was sent.
  static String emailInviteBody({
    required String communityName,
    String? description,
    String? organiserName,
    required String code,
    int? memberCount,
    bool isPaid = false,
    String visibility = 'private',
    bool hasWaiver = false,
    String? rulesText,
    String? cheapestPassPrice,
    String? cheapestPassLength,
    CommunityInviteTour? tour,
  }) =>
      buildCommunityInvite(CommunityInviteDetails(
        communityName: communityName,
        code: code,
        description: description,
        organiserName: organiserName,
        memberCount: memberCount,
        isPaid: isPaid,
        visibility: visibility,
        hasWaiver: hasWaiver,
        rulesText: rulesText,
        cheapestPassPrice: cheapestPassPrice,
        cheapestPassLength: cheapestPassLength,
        tour: tour,
      ));

  /// §4: A short email SUBJECT for the invite.
  static String emailInviteSubject(String communityName) =>
      'Join "$communityName" on Audioura';

  /// §4: Are all REQUIRED create fields present? Required: name, description,
  /// organiser name, rules. Location (lat+lng) is required ONLY for a Listed
  /// community. Pure so the gating is unit-testable without a widget.
  static bool requiredFieldsFilled({
    required String name,
    required String description,
    required String organiserName,
    required String rules,
    required bool listed,
    String latitude = '',
    String longitude = '',
  }) {
    final core = name.trim().isNotEmpty &&
        description.trim().isNotEmpty &&
        organiserName.trim().isNotEmpty &&
        rules.trim().isNotEmpty;
    if (!core) return false;
    if (listed && (latitude.trim().isEmpty || longitude.trim().isEmpty)) {
      return false;
    }
    return true;
  }

  /// §4: Is the Create button enabled? All required fields filled AND the
  /// Organiser Terms accepted AND the name is not known-taken (nameAvailable
  /// false). nameAvailable null (unknown / not yet checked) does NOT block.
  static bool createEnabled({
    required bool requiredFilled,
    required bool termsAccepted,
    bool? nameAvailable,
  }) =>
      requiredFilled && termsAccepted && nameAvailable != false;

  // ── [LOCAL-703 / D664] Launch-window countdown copy ─────────────────────────

  /// The rule stated on the Create screen, ABOVE the Create button, so the
  /// organiser knows the deal before committing. Paid vs free wording differs
  /// only in "paid members" vs "members".
  static String createLaunchRule({required bool paid}) {
    final who = paid ? 'paid members' : 'members';
    return 'Heads up: a new community has one week to get its first 2 $who '
        '(you don\'t count). You\'ll see a live countdown. Miss it and the '
        'community is archived and its invite code stops working — members keep '
        'anything they\'ve downloaded.';
  }

  /// The live countdown line on the organiser's community page and the creation
  /// confirmation. Before launch it reads, e.g.:
  ///   "152 h left to get 2 paid members — 1 of 2 so far"   (paid)
  ///   "152 h left to get 2 members — 1 of 2 so far"        (free)
  /// Once launched it is the green success line "Launched 🎉". Pure so the exact
  /// wording is unit-testable without a widget.
  static String launchCountdown({
    required bool launched,
    required bool paid,
    required int hoursLeft,
    required int membersSoFar,
    required int membersNeeded,
  }) {
    if (launched) return 'Launched 🎉';
    final who = paid ? 'paid members' : 'members';
    return '$hoursLeft h left to get $membersNeeded $who — '
        '$membersSoFar of $membersNeeded so far';
  }

  /// [LOCAL-738 / C2c] The "New tours: weekly" line shown on the community
  /// page, from the community's release_cadence (day|week|month|year). Pure so
  /// the exact wording is unit-testable without a widget. An unknown cadence
  /// falls back to the raw value so the line is never empty.
  static String releaseCadenceLabel(String cadence) {
    switch (cadence) {
      case 'day':
        return 'New tours: daily';
      case 'week':
        return 'New tours: weekly';
      case 'month':
        return 'New tours: monthly';
      case 'year':
        return 'New tours: yearly';
      default:
        return 'New tours: $cadence';
    }
  }

  /// The message a listener sees when an invite code resolves to a CLOSED
  /// (archived) community — the server returns 410 community_closed. Exactly
  /// the server wording (D664).
  static const String communityClosed = 'This community has closed.';
}

/// [LOCAL-738 §1 / Michael's review C2/C2d] Pure, Flutter-free logic for the
/// create form's membership block: ONE PRICE PER LENGTH. The organiser ticks a
/// length ON and picks exactly ONE price for it. This holds the rules so the
/// payload (exactly one {product_id, length} per ticked length), the validity
/// gate, and the "only server prices" guard are unit-testable without a widget
/// — the bugs Michael hit (the cross-product, the stale custom value, an
/// off-list price) are all caught here.
class CommunityPassForm {
  /// The four pass lengths, in display order.
  static const List<String> lengths = ['day', 'week', 'month', 'year'];

  /// Build the `pass_products` payload: exactly one {product_id, length} per
  /// TICKED length, using that length's chosen price. A ticked length with no
  /// price (or a price not in [allowed], when [allowed] is non-empty) is
  /// SKIPPED — never sent. The result's order follows [lengths]. This is what
  /// makes "what is shown selected is exactly what is sent" true: there is no
  /// cross-product and no stale custom value.
  static List<Map<String, String>> passOptions({
    required Map<String, bool> enabled,
    required Map<String, String?> price,
    Set<String> allowed = const {},
  }) {
    final out = <Map<String, String>>[];
    for (final len in lengths) {
      if (enabled[len] != true) continue;
      final product = price[len];
      if (product == null) continue;
      if (allowed.isNotEmpty && !allowed.contains(product)) continue;
      out.add({'product_id': product, 'length': len});
    }
    return out;
  }

  /// The create gate's pass condition: at least one length is on, and EVERY
  /// enabled length has a price (and, when [allowed] is given, a price that is
  /// in the allowed set — the red-test guard: an off-list price can never make
  /// the form valid).
  static bool passesValid({
    required Map<String, bool> enabled,
    required Map<String, String?> price,
    Set<String> allowed = const {},
  }) {
    final on = lengths.where((l) => enabled[l] == true).toList();
    if (on.isEmpty) return false;
    return on.every((l) {
      final p = price[l];
      if (p == null) return false;
      if (allowed.isNotEmpty && !allowed.contains(p)) return false;
      return true;
    });
  }
}
