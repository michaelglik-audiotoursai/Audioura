/// [LOCAL-579 / LOCAL-709 / LOCAL-710] Share-code helpers.
///
/// A share code is exactly 8 base62 characters (see tour_sharing.py). ST-3
/// taught the Home search box to recognise a bare code. This file is the one
/// place where the SENDING side builds a shareable link/message and the
/// RECEIVING side ([extractShareCode]) pulls the 8-char token back out.
///
/// [LOCAL-709 / D671] A shared tour leads with a real link:
///   https://audioura.com/t/FFush25U
/// With Audioura installed the link opens Home → Search with the code filled in
/// and the search already run (an App Link / Universal Link). Without it, the
/// link reaches the audioura.com/t/ landing page, which sends the visitor to
/// the store. [extractShareCode] still pulls CODE from the message, the bare
/// link, a link with a trailing slash, and (for back-compat) a link with `?n=`.
///
/// [LOCAL-710 / D672] Michael reviewed the generated emails. The wording is now
/// shaped by [ShareTourDetails]: a SHORT title (no "with a stop at …" clauses,
/// no long suffix), the number of stops + the first stop's name and location
/// (never the whole list), and a clean short link with no `?n=`. A free tour, a
/// paid tour and a community tour each get their own opening line, and the paid
/// price line comes last. See [buildShareMessage] / [buildShareSubject].
library;

/// The canonical host + path prefix for a tour share link (D671). One place so
/// the builder, the Android intent-filter, the iOS associated-domain and the
/// website all agree.
const String kShareLinkHost = 'audioura.com';
const String kShareLinkPrefix = 'https://$kShareLinkHost/t/';

/// Build the canonical share LINK for a tour (D671 / D672):
///   https://audioura.com/t/<CODE>
///
/// [code] is the 8-char share id. [LOCAL-710 / D672] The `?n=<name>` query is
/// GONE: the 8-char code already identifies the tour, and the landing page now
/// always shows "An Audioura tour for you". A short link is friendlier in an
/// email and leaks no tour name into URLs / referrers.
String buildShareLink(String code) => '$kShareLinkPrefix$code';

/// Build the share LINK for a community invite code (D671). A community invite
/// is carried by the SAME `https://audioura.com/t/<CODE>` link as a tour: the
/// app's single share-code path resolves a `/t/` code as a tour first and then
/// a community (home_screen `_dispatchShareCode`), and the landing page copies
/// the code regardless.
String buildCommunityInviteLink(String code) => '$kShareLinkPrefix$code';

/// Which kind of tour is being shared — drives the opening line (D672).
enum ShareTourKind { free, paid, community }

/// [LOCAL-710 / D672] Everything the share message needs, gathered from what the
/// sharing screen already holds (the tour map on My Tours, or the downloaded
/// tour's local files in the player). Pure data — no Flutter, no I/O — so the
/// exact wording is unit-testable.
///
/// A missing stop or location simply omits that line; the builder never prints
/// "null". [title] is the SHORT title (run [shortTourTitle] on the raw name
/// before constructing this, or pass an already-short title).
class ShareTourDetails {
  /// The short, human title (see [shortTourTitle]). Already trimmed.
  final String title;

  /// The 8-char share code.
  final String code;

  /// free / paid / community — picks the opening line.
  final ShareTourKind kind;

  /// Paid only: the display price label, e.g. "$4.99". Null/empty for free.
  final String? price;

  /// Community only: the community's name, e.g. "Demo Boston Walkers".
  final String? communityName;

  /// Number of stops in the tour. Null/≤0 omits the stops line.
  final int? stopCount;

  /// The first stop's display name, e.g. "Quincy Market". Null/empty omits the
  /// stops line's "starting at …" clause (and the line falls back to a bare
  /// count when there is no first stop).
  final String? firstStopName;

  /// The first stop's location — a street address or "Place, City". Null/empty
  /// drops the "(…)" after the first stop name.
  final String? firstStopLocation;

  /// The tour's city, e.g. "Boston". Used only for the subject line. Null/empty
  /// falls the subject back to the generic one.
  final String? city;

  /// The tour type, e.g. "walking". Used in the subject line (lower-cased) and
  /// never shown in the body. Null/empty falls the subject back to the generic.
  final String? tourType;

  const ShareTourDetails({
    required this.title,
    required this.code,
    required this.kind,
    this.price,
    this.communityName,
    this.stopCount,
    this.firstStopName,
    this.firstStopLocation,
    this.city,
    this.tourType,
  });
}

String _clean(String? s) => (s ?? '').trim();

bool _has(String? s) => _clean(s).isNotEmpty;

/// [LOCAL-710 / D672] Shorten a raw tour name for an email / subject line.
///
/// The server stores long display names like
///   "Faneuil Hall Marketplace, Boston MA, with a stop at Quincy Market and a
///    stop at the Samuel Adams statue … - Walking Tour"
/// Michael wants the lede ("Faneuil Hall Marketplace") and a clean type suffix:
///   "Faneuil Hall Marketplace — Walking Tour".
///
/// Rules:
///   1. Cut everything from the first ", with a stop at" / " with a stop at"
///      (case-insensitive) up to the ` - <Type> Tour` suffix.
///   2. Drop a trailing city/state segment that merely repeats the place
///      (", Boston MA" / ", Boston, MA").
///   3. Normalise the suffix to " — <Type> Tour", the type Capitalised; an empty
///      type (`-  Tour`) becomes " — Tour".
///   4. NEVER return empty: fall back to the raw name, trimmed.
///
/// Pure + Unicode-safe (Russian names pass through unchanged apart from the
/// suffix / stop-clause trimming).
String shortTourTitle(String rawName) {
  final raw = rawName.trim();
  if (raw.isEmpty) return rawName.trim();

  var work = raw;

  // ── 1. Peel off a " - <Type> Tour" suffix, remembering the <Type>. ──────────
  // Matches " - Walking Tour", " - walking tour", " -  Tour" (empty type).
  // The type is everything between " - " and the final word "Tour".
  String? typeWord;
  final suffix = RegExp(
    r'\s*[-–—]\s*([^-–—]*?)\s*Tour\s*$',
    caseSensitive: false,
  );
  final suffixMatch = suffix.firstMatch(work);
  if (suffixMatch != null) {
    typeWord = suffixMatch.group(1)?.trim();
    work = work.substring(0, suffixMatch.start).trim();
  }

  // ── 2. Cut the "with a stop at …" clauses (and anything after). ─────────────
  // Case-insensitive; handles the leading comma variant ", with a stop at".
  final stopClause = RegExp(r',?\s+with\s+a\s+stop\s+at\b', caseSensitive: false);
  final stopMatch = stopClause.firstMatch(work);
  if (stopMatch != null) {
    work = work.substring(0, stopMatch.start).trim();
  }

  // ── 3. Drop a trailing ", City ST" / ", City, ST" that repeats the place. ───
  // Only a short, place-shaped tail is removed (≤ 3 comma-separated words, each
  // starting with a letter/upper), never real title words.
  work = _dropTrailingPlace(work);

  work = work.trim();

  // ── 4. Re-attach a normalised suffix. ───────────────────────────────────────
  if (suffixMatch != null) {
    final type = _capitalise(typeWord ?? '');
    if (type.isEmpty) {
      work = '$work — Tour';
    } else {
      work = '$work — $type Tour';
    }
  }

  work = work.trim();
  // Never return empty.
  if (work.isEmpty || work == '—' || work == '— Tour') return raw;
  return work;
}

/// Capitalise the first letter of each word of a tour type ("walking" →
/// "Walking", "self guided" → "Self Guided"). Unicode-aware enough for the Latin
/// types we ship; leaves already-capitalised words intact.
String _capitalise(String type) {
  final t = type.trim();
  if (t.isEmpty) return '';
  return t
      .split(RegExp(r'\s+'))
      .where((w) => w.isNotEmpty)
      .map((w) => w[0].toUpperCase() + w.substring(1))
      .join(' ');
}

/// Drop a trailing place tail from a lede — a ", City, ST" / ", City, Country"
/// / ", Boston MA" that merely repeats or locates the place already named.
/// Conservative: it peels comma-separated TAIL segments that look like a place
/// (a 2-letter state, a country/region word, or a short Capitalised city —
/// especially a city word that already appears earlier in the kept lede), and
/// stops at the first segment that is clearly part of the title. So
/// "Cleveland Museum of Art, Cleveland, USA" → "Cleveland Museum of Art" and
/// "Faneuil Hall Marketplace, Boston MA" → "Faneuil Hall Marketplace", while
/// "Museum of Fine Arts" (no comma tail) is untouched.
String _dropTrailingPlace(String lede) {
  final parts = lede.split(',').map((p) => p.trim()).toList();
  if (parts.length < 2) return lede;

  bool looksLikeState(String s) => RegExp(r'^[A-Z]{2}$').hasMatch(s); // "MA"
  bool looksLikeCityState(String s) =>
      // "Boston MA" — a place then a 2-letter upper code.
      RegExp(r'^[^\d,]+\s+[A-Z]{2}$').hasMatch(s);
  bool shortCapWords(String s) {
    final words = s.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();
    if (words.isEmpty || words.length > 3) return false;
    // Each word starts with an upper/accented capital (a place name).
    return words.every((w) => RegExp(r'^[A-ZÀ-ÖØ-Þ]').hasMatch(w));
  }

  // Peel from the end while the tail looks like a place locator. Keep at least
  // the first segment (the real lede).
  var end = parts.length;
  while (end > 1) {
    final seg = parts[end - 1];
    final isState = looksLikeState(seg);
    final isCityState = looksLikeCityState(seg);
    final isPlaceWords = shortCapWords(seg);
    // A segment that repeats a word already present earlier in the kept lede.
    final keptHead = parts.sublist(0, end - 1).join(' ').toLowerCase();
    final repeats = seg
        .split(RegExp(r'\s+'))
        .any((w) => w.length > 2 && keptHead.contains(w.toLowerCase()));
    if (isState || isCityState || isPlaceWords || repeats) {
      end--;
      continue;
    }
    break;
  }
  if (end == parts.length) return lede;
  return parts.sublist(0, end).join(', ').trim();
}

/// [LOCAL-710 / D672] Pull the tour TYPE out of a raw tour name's
/// " - <Type> Tour" suffix (e.g. "… - Walking Tour" → "walking"). Returns ""
/// when the name has no such suffix or the type is empty. Lower-cased, for the
/// subject line. Pure.
String tourTypeFromName(String rawName) {
  final suffix = RegExp(
    r'[-–—]\s*([^-–—]*?)\s*Tour\s*$',
    caseSensitive: false,
  );
  final m = suffix.firstMatch(rawName.trim());
  if (m == null) return '';
  return (m.group(1) ?? '').trim().toLowerCase();
}

/// [LOCAL-710 / D672] Best-effort CITY for the subject line. Prefers the city
/// in a "Place, City" / "…, City, ST" first-stop location; else a "City, ST" /
/// "City ST" tail in the raw tour name. Returns "" when none is found. Pure.
String cityFromLocation(String? firstStopLocation, String rawName) {
  // 1. From the first stop's location: a US-style "…, City, ST ZIP" address.
  final loc = _clean(firstStopLocation);
  if (loc.isNotEmpty) {
    final parts = loc.split(',').map((p) => p.trim()).toList();
    // "4 S Market St, Boston, MA 02109" → ["4 S Market St","Boston","MA 02109"]
    if (parts.length >= 2) {
      // The segment just before a trailing "ST [ZIP]" segment is the city.
      final tail = parts.last;
      final isStateTail = RegExp(r'^[A-Z]{2}(\s+\d{3,}.*)?$').hasMatch(tail);
      if (isStateTail && parts.length >= 2) {
        final cand = parts[parts.length - 2];
        if (RegExp(r'^[A-Za-zÀ-ÖØ-öø-ÿ .\-]+$').hasMatch(cand)) return cand;
      }
    }
  }
  // 2. From the raw name tail: "…, Boston MA" / "…, Boston, MA".
  final name = rawName.trim();
  final parts = name.split(',').map((p) => p.trim()).toList();
  for (var i = parts.length - 1; i >= 0; i--) {
    final seg = parts[i];
    // "Boston MA"
    final cityState = RegExp(r'^([A-Za-zÀ-ÖØ-öø-ÿ .\-]+?)\s+[A-Z]{2}$').firstMatch(seg);
    if (cityState != null) return cityState.group(1)!.trim();
    // "MA" alone → the previous segment is the city.
    if (RegExp(r'^[A-Z]{2}$').hasMatch(seg) && i > 0) {
      final prev = parts[i - 1];
      if (RegExp(r'^[A-Za-zÀ-ÖØ-öø-ÿ .\-]+$').hasMatch(prev)) return prev;
    }
  }
  return '';
}

/// [LOCAL-710 / D672] The opening line, by kind.
String _openingLine(ShareTourDetails d) {
  switch (d.kind) {
    case ShareTourKind.free:
      return 'Welcome to my free tour "${d.title}" on Audioura.';
    case ShareTourKind.paid:
      return 'Welcome to my tour "${d.title}" on Audioura.';
    case ShareTourKind.community:
      final community = _clean(d.communityName);
      if (community.isNotEmpty) {
        return 'Welcome to my tour "${d.title}" from the $community '
            'community on Audioura.';
      }
      // No community name → fall back to the plain opening.
      return 'Welcome to my tour "${d.title}" on Audioura.';
  }
}

/// [LOCAL-710 / D672] The stops line:
///   "<N> stops, starting at <first stop> (<its location>)."
/// Degrades gracefully: no location → "… starting at <first stop>."; no first
/// stop → "<N> stops."; no count at all → the line is omitted (returns null).
String? _stopsLine(ShareTourDetails d) {
  final count = d.stopCount;
  if (count == null || count <= 0) return null;
  final noun = count == 1 ? 'stop' : 'stops';
  final first = _clean(d.firstStopName);
  if (first.isEmpty) return '$count $noun.';
  final loc = _clean(d.firstStopLocation);
  if (loc.isEmpty) return '$count $noun, starting at $first.';
  return '$count $noun, starting at $first ($loc).';
}

/// [LOCAL-710 / D672] The exact message a curator sends when sharing a tour.
///
/// Body order (one blank line between paragraphs, no double spaces):
///   1. opening line (by kind);
///   2. "Hands-free audio: press play and walk.";
///   3. "<N> stops, starting at <first stop> (<location>).";   (when known)
///   4. the short link;
///   5. "(Or open Audioura, tap Search and paste <CODE>.)";
///   6. community only: "Join the <community> community in Audioura to download it.";
///   7. paid only, LAST: "The tour price is $<price>.".
///
/// [extractShareCode] still round-trips the code out of the result.
String buildShareMessage(ShareTourDetails details) {
  final paragraphs = <String>[];

  paragraphs.add(_openingLine(details));
  paragraphs.add('Hands-free audio: press play and walk.');

  final stops = _stopsLine(details);
  if (stops != null) paragraphs.add(stops);

  paragraphs.add(buildShareLink(details.code));
  paragraphs.add('(Or open Audioura, tap Search and paste ${details.code}.)');

  if (details.kind == ShareTourKind.community && _has(details.communityName)) {
    paragraphs.add(
      'Join the ${_clean(details.communityName)} community in Audioura to '
      'download it.',
    );
  }

  if (details.kind == ShareTourKind.paid && _has(details.price)) {
    paragraphs.add('The tour price is ${_clean(details.price)}.');
  }

  // One blank line between paragraphs; collapse any accidental double spaces.
  return paragraphs.join('\n\n').replaceAll(RegExp(r'  +'), ' ');
}

/// [LOCAL-710 / D672] The share SUBJECT:
///   "A <city> <type> tour for you"  (type lower-cased, e.g. "A Boston walking
///   tour for you"); falls back to "An Audioura tour for you" when city or type
///   is missing.
String buildShareSubject(ShareTourDetails details) {
  final city = _clean(details.city);
  final type = _clean(details.tourType).toLowerCase();
  if (city.isNotEmpty && type.isNotEmpty) {
    return 'A $city $type tour for you';
  }
  return 'An Audioura tour for you';
}

/// [LOCAL-710 / D672] The local fallback invite text an organiser shares for a
/// community. Leads with the opening line, shows the member count only when
/// known and ≥ 2, then the link + the code fallback. The "How to get Audioura"
/// and "(links coming soon)" lines are GONE — the link already leads to the
/// store. [memberCount] null or < 2 omits the member-count line.
String buildCommunityInviteMessage(
  String communityName,
  String code, {
  int? memberCount,
}) {
  final paragraphs = <String>[];
  paragraphs.add('Join "$communityName" on Audioura.');
  if (memberCount != null && memberCount >= 2) {
    paragraphs.add('$memberCount members.');
  }
  paragraphs.add(buildCommunityInviteLink(code));
  paragraphs.add('(Or open Audioura, tap Search and paste $code.)');
  return paragraphs.join('\n\n').replaceAll(RegExp(r'  +'), ' ');
}

/// A single base62 token of exactly 8 characters.
// Whole words only (\b): never a slice of a longer word like "Commonwealth".
final RegExp _codeToken = RegExp(r'\b[A-Za-z0-9]{8}\b');

/// True when [token] has the shape of a generated share code rather than a
/// place name: 8 base62 chars that contain a digit OR an internal capital.
///
/// This is the SAME discriminator ST-3 uses in home_screen._looksLikeShareCode
/// ("JmSTVsMv" is a code, "Brooklyn" is a place). Keeping it in one place means
/// the sender, the receiver and the tests cannot drift apart.
bool isShareCodeShape(String token) {
  if (token.length != 8) return false;
  if (!RegExp(r'^[A-Za-z0-9]{8}$').hasMatch(token)) return false;
  // A digit anywhere, or a capital that is not the very first character.
  return RegExp(r'[0-9]').hasMatch(token) || RegExp(r'^.+[A-Z]').hasMatch(token);
}

/// Extracts the 8-char share code from an arbitrary pasted string: a bare code,
/// the full share message, a share link, or any of those with surrounding
/// whitespace. Returns null when nothing in the input looks like a code.
///
/// Strategy: scan every 8-char base62 run in the text and return the first that
/// passes [isShareCodeShape]. A place name like "Boston" (6 chars) or
/// "Newton MA" (has a space, and no 8-run with a digit/internal capital) yields
/// null, so an ordinary location query is never mistaken for a code.
///
/// A link's path segment (…/t/FFush25U, …/tour/FFush25U) is just another 8-char
/// run, so no URL parsing is strictly needed; but if a path segment is a clean
/// code we prefer it, because a link is an unambiguous signal. This also makes
/// a `…/t/CODE/` link (trailing slash → an empty final segment) resolve from
/// the CODE segment rather than the empty one.
String? extractShareCode(String input) {
  final text = input.trim();
  if (text.isEmpty) return null;

  // Prefer a link's path segment when it is itself a valid code — a URL is the
  // least ambiguous carrier of a code. Scan every non-empty segment (not just
  // the last) so a trailing slash (`/t/CODE/`) or an extra segment does not
  // hide the code.
  final uri = Uri.tryParse(text);
  if (uri != null && uri.hasScheme && uri.pathSegments.isNotEmpty) {
    for (final seg in uri.pathSegments.reversed) {
      if (isShareCodeShape(seg)) return seg;
    }
  }

  // LAST code-shaped word wins: in the shared message the code comes after the tour name, and a
  // tour name can itself look code-shaped ("McDonald" has a capital after its first letter).
  final matches = _codeToken.allMatches(text).toList().reversed;
  for (final match in matches) {
    final token = match.group(0)!;
    if (isShareCodeShape(token)) return token;
  }
  return null;
}
