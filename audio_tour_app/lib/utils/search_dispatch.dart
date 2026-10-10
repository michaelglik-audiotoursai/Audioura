/// [LOCAL-665] One Home search box, three formats.
///
/// Michael (2026-10-10): "I sometimes confuse which button to press for the
/// tour search: flag (the right one) or arrow-glass for location search. Can we
/// merge them somehow, because the format is very different and by the format we
/// can understand what the listener is looking for."
///
/// The Home AppBar used to carry two buttons — `Icons.tour` (share code +
/// tour-name search) and `Icons.search` (place lookup, moves the map). This
/// util is the pure, UI-free brain of the single merged button: given the raw
/// text a listener typed, decide WHAT to do, in a fixed priority order. The
/// widget layer (home_screen.dart) then performs the chosen action with its
/// existing functions (`_resolveShareCode`, `_mapController.move`,
/// `_searchTours`, `_geocodeLocation`).
///
/// Keeping the decision here — with no Flutter imports — is what makes it
/// testable: a widget test cannot easily assert "a code was tried before a
/// place", but a unit test over [classifySearchInput] can, and does
/// (test/search_dispatch_test.dart).
library;

import 'share_code.dart';

/// The kind of action the single search box should take for a given input,
/// chosen in this strict priority order (LOCAL-665 Deliver §2):
///   1. [shareCode]   — looks like a share code (bare, message, or link).
///   2. [coordinates] — a "lat, lng" pair.
///   3. [text]        — anything else: run tour-name search AND place lookup.
enum SearchKind { shareCode, coordinates, text }

/// The outcome of classifying a raw search string: the [kind] plus whichever
/// payload that kind carries. Exactly one payload is non-null for the first two
/// kinds; [text] carries the trimmed [query] to feed to both lookups.
class SearchDispatch {
  final SearchKind kind;

  /// Set when [kind] == [SearchKind.shareCode]: the extracted 8-char token.
  final String? shareCode;

  /// Set when [kind] == [SearchKind.coordinates].
  final double? latitude;
  final double? longitude;

  /// Set for every kind: the trimmed input. For [SearchKind.text] this is the
  /// string to pass to both the tour-name search and the place geocoder.
  final String query;

  const SearchDispatch._({
    required this.kind,
    required this.query,
    this.shareCode,
    this.latitude,
    this.longitude,
  });

  factory SearchDispatch.shareCode(String code, String query) =>
      SearchDispatch._(kind: SearchKind.shareCode, shareCode: code, query: query);

  factory SearchDispatch.coordinates(double lat, double lng, String query) =>
      SearchDispatch._(
          kind: SearchKind.coordinates,
          latitude: lat,
          longitude: lng,
          query: query);

  factory SearchDispatch.text(String query) =>
      SearchDispatch._(kind: SearchKind.text, query: query);

  @override
  String toString() {
    switch (kind) {
      case SearchKind.shareCode:
        return 'SearchDispatch.shareCode($shareCode)';
      case SearchKind.coordinates:
        return 'SearchDispatch.coordinates($latitude, $longitude)';
      case SearchKind.text:
        return 'SearchDispatch.text("$query")';
    }
  }
}

/// A "lat, lng" pair: two signed decimals separated by a comma (any surrounding
/// whitespace allowed). Latitude in [-90, 90], longitude in [-180, 180].
///
/// Deliberately strict: it requires the comma so a bare tour name with numbers
/// (e.g. "Route 66") or a single number is NOT mistaken for coordinates and
/// instead flows to the ordinary tour-name + place search. Returns null when
/// the input is not a well-formed, in-range pair.
({double lat, double lng})? parseCoordinates(String input) {
  final text = input.trim();
  // Two decimal numbers (optional sign, optional fraction) around one comma.
  final match = RegExp(
    r'^([-+]?\d{1,3}(?:\.\d+)?)\s*,\s*([-+]?\d{1,3}(?:\.\d+)?)$',
  ).firstMatch(text);
  if (match == null) return null;

  final lat = double.tryParse(match.group(1)!);
  final lng = double.tryParse(match.group(2)!);
  if (lat == null || lng == null) return null;
  if (lat < -90 || lat > 90) return null;
  if (lng < -180 || lng > 180) return null;
  return (lat: lat, lng: lng);
}

/// Classify raw search-box text into the action the single Home search button
/// should take, applying the LOCAL-665 priority order.
///
/// Order matters and is the whole point of the one-button merge:
///   1. Share code first — a resolved code jumps straight to the tour, and an
///      UNRESOLVED code must NOT fall through to a place search (the widget
///      shows "No tour with that code…" instead). We only decide the SHAPE
///      here; resolution happens in the widget.
///   2. Coordinates — an explicit "lat, lng" moves the map.
///   3. Otherwise text — run the tour-name search and the place lookup together.
///
/// Empty / whitespace-only input classifies as [SearchKind.text] with an empty
/// query; the caller should early-return on empty before dispatching.
SearchDispatch classifySearchInput(String raw) {
  final query = raw.trim();

  final code = extractShareCode(query);
  if (code != null) {
    return SearchDispatch.shareCode(code, query);
  }

  final coords = parseCoordinates(query);
  if (coords != null) {
    return SearchDispatch.coordinates(coords.lat, coords.lng, query);
  }

  return SearchDispatch.text(query);
}

/// The result of the concurrent text search (tours found + place found), mapped
/// to the single outcome the dialog should present. Pure so a unit test can
/// enumerate every branch (LOCAL-665 Deliver §2c) without a geocoder or server.
enum TextSearchOutcome {
  /// Tours were found AND a place was found: show the found tours, plus an extra
  /// "Show <place> on the map" action.
  toursAndPlace,

  /// Only tours: present them with the shared found-tours dialogs.
  toursOnly,

  /// Only a place: move the map there (today's location behaviour).
  placeOnly,

  /// Neither: "Nothing found for '<text>'".
  nothing,
}

/// Decide what to present after the tour-name search and place lookup both
/// return. [tourCount] is how many tours matched; [placeFound] is whether the
/// geocoder resolved the text to a location.
TextSearchOutcome resolveTextSearch({
  required int tourCount,
  required bool placeFound,
}) {
  final hasTours = tourCount > 0;
  if (hasTours && placeFound) return TextSearchOutcome.toursAndPlace;
  if (hasTours) return TextSearchOutcome.toursOnly;
  if (placeFound) return TextSearchOutcome.placeOnly;
  return TextSearchOutcome.nothing;
}
