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

/// Pick the best candidate from a parsed Nominatim result list.
///
/// Rules (LOCAL-793):
///   1. If ANY candidate is a PLACE, return the best place — the most prominent
///      administrative area. Prominence is: higher `importance` first; then a
///      smaller `place_rank` (larger area); then the earlier entry in
///      [_placeTypes] (country before city before suburb). A POI can NEVER win
///      when a place exists, so "Saigon Vietnam" resolves to Ho Chi Minh City,
///      not to the Paris restaurant.
///   2. If NO candidate is a place, return the best POI by `importance` (then
///      the first entry), so a genuine POI-only search still resolves. The
///      widget may still prefer the server geocoder in this case.
///   3. Empty list → null.
GeoCandidate? pickBestPlace(List<GeoCandidate> candidates) {
  if (candidates.isEmpty) return null;

  final places = candidates.where(isPlace).toList();
  if (places.isNotEmpty) {
    places.sort((a, b) {
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
