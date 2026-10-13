// [LOCAL-677B] Small pure helpers for the found-tour dialog display, extracted
// so they can be unit-tested without pumping the whole HomeScreen.

/// Whether to render the "Distance: N km" line for a found-tour entry.
///
/// The share-code (/tour-by-code) and search-results entries carry no distance,
/// so distance_km is null and "Distance: null km" is nonsense. Show the line
/// only when the server sent a real (non-null) distance.
bool shouldShowDistance(Map<String, dynamic> item) =>
    item['distance_km'] != null;
