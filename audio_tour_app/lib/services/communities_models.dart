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
  // [LOCAL-702 / D663 §1] The organiser step-down state machine.
  final String status; // active | handover | archived
  final bool lookingForOrganiser; // true while in hand-over
  final bool archived; // true once archived
  final bool acceptsNewMembers; // false in handover/archived
  final String? steppedDownAt;
  final String? archivedAt;
  final List<OrganiserOffer> organiserOffers; // owner view, during hand-over
  final MyOffer? myOffer; // the caller's own offer, during hand-over

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
    this.status = 'active',
    this.lookingForOrganiser = false,
    this.archived = false,
    this.acceptsNewMembers = true,
    this.steppedDownAt,
    this.archivedAt,
    this.organiserOffers = const [],
    this.myOffer,
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
      'Communities can be free (like a book club) or paid. A paid membership is '
      'a pass you buy — a day, a week, a month, or a year. Nothing renews '
      'automatically: when a pass ends we remind you, and you can buy again. '
      'Audio you have already downloaded stays with you.';

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

  /// §4: The email body an organiser sends to invite members. Contains the
  /// community name + description, the organiser name, how to get Audioura
  /// (install link), and the exact join instruction with the CODE. The returned
  /// string ALWAYS contains the code and the install line, which the tests
  /// assert. Never claims the email was sent — that is the composer's job.
  static String emailInviteBody({
    required String communityName,
    String? description,
    String? organiserName,
    required String code,
  }) {
    final buf = StringBuffer();
    buf.writeln('You are invited to join "$communityName" on Audioura.');
    buf.writeln();
    if (description != null && description.trim().isNotEmpty) {
      buf.writeln(description.trim());
      buf.writeln();
    }
    if (organiserName != null && organiserName.trim().isNotEmpty) {
      buf.writeln('Organiser: ${organiserName.trim()}');
      buf.writeln();
    }
    buf.writeln('How to get Audioura: $installUrl');
    buf.writeln('(App Store / Google Play links coming soon.)');
    buf.writeln();
    buf.writeln('Then open Audioura → Search → type the code $code');
    return buf.toString();
  }

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
}
