/// [LOCAL-793] Choosing the RIGHT geocoder result for a Home place search.
///
/// Michael, iPhone TestFlight 83 (2026-10-27): typing "Saigon Vietnam" opened
/// the map on **Paris** — because the old geocoder asked Nominatim for `limit=1`
/// and blindly took result[0], which happened to be a restaurant named "Saigon
/// Vietnam" on Rue de Turin. "Hi Chi Minh, Vietnam" (a typo) landed on a bus
/// stop 11 km from District 1 and then showed "0 tours in this map area".
///
/// The fix for the ranking half of the bug lives here, as a PURE function so a
/// unit test can feed it the exact Nominatim payloads the LEAD reproduced and
/// assert the right pick with no network:
///
///   * Ask Nominatim for several results (`limit=8`), then PREFER a PLACE — a
///     city / town / village / suburb / county / state / country (OSM
///     `class=place` or `boundary=administrative`) — over a POI (a restaurant,
///     a bus stop, a shop). A place is chosen by importance / place_rank so the
///     biggest, most prominent administrative area wins.
///   * Only when NO place exists in the results do we fall back to the best POI
///     (so a genuine POI-only search — "Eiffel Tower" — still resolves).
///
/// The widget layer ([_geocodeLocation]) does the HTTP and, when this returns
/// null (no place AND we want to avoid a far POI), asks the server-side geocoder
/// which copes with typos ("Hi Chi Minh" → Ho Chi Minh City).
library;

/// One geocoder candidate, normalised from a Nominatim `search?format=json`
/// result. Only the fields the ranking needs are kept.
class GeoCandidate {
  final double lat;
  final double lon;

  /// OSM `class` (Nominatim calls it `class`, sometimes `category`): e.g.
  /// `place`, `boundary`, `amenity`, `highway`, `shop`, `tourism`.
  final String klass;

  /// OSM `type`: e.g. `city`, `town`, `village`, `administrative`, `restaurant`,
  /// `bus_stop`.
  final String type;

  /// Nominatim `place_rank` (lower = larger/more important administrative unit).
  /// 0 when absent.
  final int placeRank;

  /// Nominatim `importance` (0..1, higher = more prominent). 0 when absent.
  final double importance;

  /// Human-readable resolved name (`display_name`), shown in the Home banner so
  /// a wrong match is visible at a glance.
  final String displayName;

  const GeoCandidate({
    required this.lat,
    required this.lon,
    required this.klass,
    required this.type,
    required this.placeRank,
    required this.importance,
    required this.displayName,
  });

  /// Parse one raw Nominatim JSON object. Returns null when it has no usable
  /// coordinates (lat/lon missing or unparseable).
  static GeoCandidate? fromJson(Map<String, dynamic> j) {
    final lat = double.tryParse('${j['lat'] ?? ''}');
    final lon = double.tryParse('${j['lon'] ?? ''}');
    if (lat == null || lon == null) return null;
    // Nominatim uses `class`; some mirrors echo `category`. Accept either.
    final klass = '${j['class'] ?? j['category'] ?? ''}'.toLowerCase();
    final type = '${j['type'] ?? ''}'.toLowerCase();
    final placeRank = int.tryParse('${j['place_rank'] ?? ''}') ?? 0;
    final importance = double.tryParse('${j['importance'] ?? ''}') ?? 0.0;
    final displayName = '${j['display_name'] ?? ''}';
    return GeoCandidate(
      lat: lat,
      lon: lon,
      klass: klass,
      type: type,
      placeRank: placeRank,
      importance: importance,
      displayName: displayName,
    );
  }
}

/// The place TYPES we accept as a "place" (a geographic area a listener would
/// search for), from biggest to smallest. Used both as a membership test and as
/// a tie-breaker preference order.
const List<String> _placeTypes = <String>[
  'country',
  'state',
  'region',
  'province',
  'county',
  'city',
  'town',
  'municipality',
  'village',
  'hamlet',
  'suburb',
  'neighbourhood',
  'quarter',
  'borough',
  'district',
  'locality',
];

/// True when [c] is a geographic PLACE rather than a POI: an OSM `place`
/// (city/town/village/suburb/…) or an administrative `boundary`.
bool isPlace(GeoCandidate c) {
  if (c.klass == 'place' && _placeTypes.contains(c.type)) return true;
  if (c.klass == 'boundary' && c.type == 'administrative') return true;
  // Some administrative areas come back as class=place type=administrative.
  if (c.type == 'administrative') return true;
  return false;
}

/// How much to prefer a place's TYPE — a lower number sorts first (country
/// before city before suburb). Unlisted types sort after every listed one.
int _typePriority(GeoCandidate c) {
  final i = _placeTypes.indexOf(c.type);
  return i < 0 ? _placeTypes.length : i;
}

/// Lower-case and strip diacritics so a query like "Mui Ne" matches a
/// display_name of "Phường Mũi Né" (and "Ho Chi Minh" matches "Hồ Chí Minh").
/// Only the Latin accents that appear in place names we care about are mapped;
/// anything unmapped is kept as-is, so this never throws and never over-reaches.
String _foldAccents(String s) {
  final lower = s.toLowerCase();
  const map = {
    'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
    'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
    'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
    'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
    'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
    'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
    'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
    'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
    'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
    'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
    'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
    'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
    'đ': 'd', 'ñ': 'n', 'ç': 'c',
  };
  final sb = StringBuffer();
  for (final ch in lower.split('')) {
    sb.write(map[ch] ?? ch);
  }
  return sb.toString();
}

/// How well [c]'s display name matches the search [query], diacritic- and
/// case-insensitively. Higher is a better match. 0 when there is no query or no
/// overlap. This is what keeps "Mui Ne" on **Mũi Né, Vietnam** instead of the
/// globally-more-"important" **Meizhou, China** that Nominatim also returns:
/// query relevance is a stronger signal than raw global importance for a place
/// the user actually typed. The query's leading token (usually the place name,
/// e.g. "mui ne" from "Mui Ne" or "mui ne" before the comma in "Mui Ne,
/// Vietnam") must appear in the name to score; a bare country word alone does
/// not (so it never drags an unrelated place up).
int _queryRelevance(GeoCandidate c, String query) {
  final q = _foldAccents(query).trim();
  if (q.isEmpty) return 0;
  final name = _foldAccents(c.displayName);
  if (name.isEmpty) return 0;
  // The part before any comma is the place the user named ("Mui Ne" from
  // "Mui Ne, Vietnam"); fall back to the whole query when there is no comma.
  final head = (q.contains(',') ? q.split(',').first : q).trim();
  int score = 0;
  // Strongest: the whole named place appears verbatim in the display name.
  if (head.isNotEmpty && name.contains(head)) score += 100;
  // Otherwise reward each query token found in the name, so a partial match
  // ("mui" and "ne") still beats a zero-overlap candidate.
  for (final tok in q.split(RegExp(r'[\s,]+'))) {
    if (tok.length >= 2 && name.contains(tok)) score += 10;
  }
  return score;
}

/// Pick the best candidate from a parsed Nominatim result list.
///
/// Rules (LOCAL-793):
///   1. If ANY candidate is a PLACE, return the best place. When a [query] is
///      given, a place whose name MATCHES what the user typed wins first
///      ([_queryRelevance]) — this keeps "Mui Ne" on Mũi Né, Vietnam rather
///      than the globally-more-important Meizhou, China that Nominatim also
///      returns. Ties (and the no-query case) fall back to the original order:
///      higher `importance`, then a smaller `place_rank` (larger area), then
///      the type-preference order (country → city → suburb). A POI can NEVER
///      win when a place exists, so "Saigon Vietnam" resolves to Ho Chi Minh
///      City, not to the Paris restaurant.
///   2. If NO candidate is a place, return the best POI by `importance` (then
///      the first entry), so a genuine POI-only search still resolves. The
///      widget may still prefer the server geocoder in this case.
///   3. Empty list → null.
///
/// [query] is the raw text the user typed; when null/empty the ranking is
/// exactly the pre-relevance behaviour (so callers and tests that pass no query
/// are unaffected).
GeoCandidate? pickBestPlace(List<GeoCandidate> candidates, {String? query}) {
  if (candidates.isEmpty) return null;

  final q = query ?? '';
  final places = candidates.where(isPlace).toList();
  if (places.isNotEmpty) {
    places.sort((a, b) {
      // Query relevance first (0 for both when no query → no effect).
      if (q.isNotEmpty) {
        final rel = _queryRelevance(b, q).compareTo(_queryRelevance(a, q));
        if (rel != 0) return rel;
      }
      // Higher importance first.
      final imp = b.importance.compareTo(a.importance);
      if (imp != 0) return imp;
      // Then smaller place_rank (a larger administrative area). place_rank 0
      // means "unknown"; treat it as the least prominent so a ranked city wins.
      final ar = a.placeRank == 0 ? 1 << 30 : a.placeRank;
      final br = b.placeRank == 0 ? 1 << 30 : b.placeRank;
      final rank = ar.compareTo(br);
      if (rank != 0) return rank;
      // Then the type preference order (country → city → suburb → …).
      return _typePriority(a).compareTo(_typePriority(b));
    });
    return places.first;
  }

  // No place at all: best POI by importance, else the first entry.
  final pois = List<GeoCandidate>.from(candidates);
  pois.sort((a, b) => b.importance.compareTo(a.importance));
  return pois.first;
}

/// Parse a raw decoded Nominatim JSON list into [GeoCandidate]s, dropping any
/// entry without coordinates. Convenience for the widget and the tests.
List<GeoCandidate> parseNominatim(List<dynamic> raw) {
  final out = <GeoCandidate>[];
  for (final item in raw) {
    if (item is Map<String, dynamic>) {
      final c = GeoCandidate.fromJson(item);
      if (c != null) out.add(c);
    } else if (item is Map) {
      final c = GeoCandidate.fromJson(Map<String, dynamic>.from(item));
      if (c != null) out.add(c);
    }
  }
  return out;
}

/// [LOCAL-789 ADDENDUM / LOCAL-793] Historic / colonial place names that
/// Nominatim's free text search does NOT resolve to the modern city: a bare
/// "Saigon Vietnam" returns only POIs literally named "Saigon" (Michael's live
/// run ended on "Nothing found"), never Ho Chi Minh City. Each key is the old
/// name; the value is today's name Nominatim indexes. Keys are stored folded
/// (lower-case, diacritics stripped) for a case/diacritic-insensitive match.
///
/// Scope is deliberately tiny and well-known so it can never mangle an
/// unrelated query — only these exact whole words are rewritten. (NB: "Canton"
/// is mapped to Guangzhou per the LEAD's list; US towns named Canton are
/// searched with their state, which keeps the state token and still finds them.)
const Map<String, String> kHistoricPlaceAliases = <String, String>{
  'saigon': 'Ho Chi Minh City',
  'bombay': 'Mumbai',
  'peking': 'Beijing',
  'calcutta': 'Kolkata',
  'madras': 'Chennai',
  'rangoon': 'Yangon',
  'canton': 'Guangzhou',
};

/// Lower-case and strip the Latin diacritics we care about, so "Sài Gòn" folds
/// to "sai gon" and matches the alias key "saigon" after whitespace is dropped
/// on a per-token basis. Mirrors the private folder used by the ranker; kept
/// separate and public-via-[applyPlaceAliases] so the alias step needs no other
/// export.
String _foldForAlias(String s) {
  final lower = s.toLowerCase();
  const map = {
    'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
    'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
    'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
    'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
    'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
    'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
    'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
    'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
    'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
    'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
    'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
    'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
    'đ': 'd', 'ñ': 'n', 'ç': 'c',
  };
  final sb = StringBuffer();
  for (final ch in lower.split('')) {
    sb.write(map[ch] ?? ch);
  }
  return sb.toString();
}

/// [LOCAL-789 ADDENDUM] Rewrite any historic place name in [query] to its
/// modern name BEFORE geocoding, so "Saigon Vietnam" is sent as "Ho Chi Minh
/// City Vietnam" and Nominatim actually finds the city (with the server
/// `/geocode` not deployed, the old name dead-ends at "Nothing found").
///
/// Matching is WHOLE-WORD and case/diacritic-insensitive: each run of letters
/// in the query is folded and looked up in [kHistoricPlaceAliases]; only an
/// exact whole-token hit is replaced, so "Saigons Bar" or "New Bombayville"
/// are left untouched. Surrounding words, punctuation and spacing are
/// preserved (", Vietnam" stays), and a query with no historic token is
/// returned unchanged (same string instance semantics are not relied upon).
String applyPlaceAliases(String query) {
  if (query.isEmpty) return query;
  // Split into word / non-word runs so separators (space, comma) are kept
  // verbatim and only whole words are candidates for replacement.
  final tokens = query.split(RegExp(r'(?<=[^A-Za-zÀ-ỹ])|(?=[^A-Za-zÀ-ỹ])'));
  final out = StringBuffer();
  for (final tok in tokens) {
    final folded = _foldForAlias(tok);
    final alias = kHistoricPlaceAliases[folded];
    out.write(alias ?? tok);
  }
  return out.toString();
}
