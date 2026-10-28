import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/place_geocoder.dart';

/// [LOCAL-793] The ranking half of Michael's "Saigon → Paris, 0 tours" bug.
///
/// The old geocoder asked Nominatim for `limit=1` and took result[0]. These
/// tests feed [pickBestPlace] the kind of multi-result payloads a `limit=8`
/// query returns for the three LEAD-reproduced searches and assert the RIGHT
/// pick — a PLACE always beating a POI when a place exists, so the restaurant
/// is never chosen.
///
/// These can FAIL: drop the "prefer place over POI" rule and the "Saigon
/// Vietnam" case picks the Paris restaurant again; drop the importance sort and
/// the city case can pick a tiny suburb instead of Ho Chi Minh City.
void main() {
  // Ho Chi Minh City centre, roughly.
  const hcmcLat = 10.7769;
  const hcmcLon = 106.7009;

  group('pickBestPlace — "Saigon Vietnam": a city beats a Paris restaurant', () {
    // A `limit=8` response: the top organic hit is a restaurant in Paris named
    // "Saigon Vietnam" (what result[0] used to be), but Ho Chi Minh City (whose
    // historic name is Saigon) is also present as a place.
    final payload = <Map<String, dynamic>>[
      {
        'lat': '48.8806',
        'lon': '2.3230',
        'class': 'amenity',
        'type': 'restaurant',
        'place_rank': '30',
        'importance': '0.45',
        'display_name': 'Saigon Vietnam, Rue de Turin, Paris, France',
      },
      {
        'lat': '$hcmcLat',
        'lon': '$hcmcLon',
        'class': 'place',
        'type': 'city',
        'place_rank': '16',
        'importance': '0.78',
        'display_name': 'Ho Chi Minh City, Vietnam',
      },
      {
        'lat': '10.82',
        'lon': '106.63',
        'class': 'place',
        'type': 'suburb',
        'place_rank': '19',
        'importance': '0.40',
        'display_name': 'Tân Bình, Ho Chi Minh City, Vietnam',
      },
    ];

    test('picks the city, never the restaurant', () {
      final best = pickBestPlace(parseNominatim(payload));
      expect(best, isNotNull);
      expect(best!.type, 'city');
      expect(best.displayName, contains('Ho Chi Minh City'));
      // Nowhere near Paris.
      expect(best.lat, closeTo(hcmcLat, 0.5));
      expect(best.lon, closeTo(hcmcLon, 0.5));
    });

    test('a POI can never win when a place is present', () {
      final best = pickBestPlace(parseNominatim(payload));
      expect(best!.klass, isNot('amenity'));
      expect(best.type, isNot('restaurant'));
    });
  });

  group('pickBestPlace — "Ho Chi Minh, Vietnam": the city (no typo)', () {
    // The correct-spelling search returns the city as the top place.
    final payload = <Map<String, dynamic>>[
      {
        'lat': '$hcmcLat',
        'lon': '$hcmcLon',
        'class': 'place',
        'type': 'city',
        'place_rank': '16',
        'importance': '0.80',
        'display_name': 'Ho Chi Minh City, Vietnam',
      },
      {
        'lat': '21.0278',
        'lon': '105.8342',
        'class': 'place',
        'type': 'city',
        'place_rank': '16',
        'importance': '0.60',
        'display_name': 'Hanoi, Vietnam',
      },
    ];

    test('resolves to Ho Chi Minh City by importance', () {
      final best = pickBestPlace(parseNominatim(payload));
      expect(best!.displayName, contains('Ho Chi Minh City'));
      expect(best.lat, closeTo(hcmcLat, 0.1));
    });
  });

  group('pickBestPlace — "Hi Chi Minh" typo: no place → null (server fallback)',
      () {
    // Nominatim cannot parse the typo to the city; it returns only a POI (the
    // "Jabil Vietnam" bus stop in Thu Duc the LEAD saw). With NO place present,
    // the picker must signal that no PLACE was found so the widget falls back to
    // the server geocoder — which resolves the typo to the city.
    final poiOnly = <Map<String, dynamic>>[
      {
        'lat': '10.836',
        'lon': '106.813',
        'class': 'highway',
        'type': 'bus_stop',
        'place_rank': '30',
        'importance': '0.12',
        'display_name': 'Jabil Vietnam, Thu Duc, Vietnam',
      },
    ];

    test('isPlace is false for the only (POI) candidate', () {
      final candidates = parseNominatim(poiOnly);
      expect(candidates.any(isPlace), isFalse,
          reason: 'a bus stop is a POI, not a place — the widget must then '
              'consult the server geocoder for the typo');
    });

    test('pickBestPlace still returns the POI (caller decides to skip it)', () {
      // pickBestPlace returns the best POI when no place exists; the WIDGET
      // ([_geocodeViaNominatim]) only accepts it when a place exists, so for a
      // POI-only result it returns null and the server geocoder runs.
      final best = pickBestPlace(parseNominatim(poiOnly));
      expect(best, isNotNull);
      expect(best!.type, 'bus_stop');
    });
  });

  group('pickBestPlace — degenerate inputs', () {
    test('empty list → null', () {
      expect(pickBestPlace(const <GeoCandidate>[]), isNull);
    });

    test('entries without coordinates are dropped by parseNominatim', () {
      final parsed = parseNominatim(<Map<String, dynamic>>[
        {'class': 'place', 'type': 'city', 'display_name': 'No coords'},
        {
          'lat': '1.0',
          'lon': '2.0',
          'class': 'place',
          'type': 'town',
          'display_name': 'Has coords',
        },
      ]);
      expect(parsed.length, 1);
      expect(parsed.first.displayName, 'Has coords');
    });
  });
}
