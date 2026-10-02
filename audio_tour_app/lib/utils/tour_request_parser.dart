// [LOCAL-358 + LOCAL-363] Tour request parser — extracted for testability.
//
// Keyword list derived from the server's `_TRANSPORT_MODE_KEYWORDS` in
// `generate_tour_text.py`. The app only needs to send a reasonable tour_type
// hint; the server's own transport-mode detection (LLM intent + keyword
// guardrail) is the authoritative classifier.
//
// Default is '' (empty string) — signals "no category detected" to the server,
// which then relies on its own intent analysis and keyword guardrail. The
// previous 'museum' default caused transport tours (biking, camel, etc.) to
// produce museum stops 25 miles away from the requested location. A 'walking'
// default was also rejected because it loses bare venue requests like
// "tour of the Louvre" where the server's venue_name promotion would otherwise
// fire. An empty string is the honest "I don't know" value — the server treats
// it as no signal at the _effective_tour_type touchpoints (lines 3706/3714).
//
// Order rationale: transport modes are checked FIRST because they describe what
// the tour IS (the mode of travel), whereas 'park', 'museum', 'exhibit' can
// appear as place names in any tour type. "Biking tour in Central Park" is a
// biking tour, not a park tour. Word-boundary matching (RegExp \b) prevents
// substring false positives: 'walk' inside 'boardwalk', 'sidewalk',
// 'Walkerville'.
//
// [LOCAL-363] Place-name guard: transport words inside proper place names
// (e.g. "Horse Guards Parade", "Safari Park", "Scooter Alley") must NOT
// hijack the tour type. Transport patterns now require ACTIVITY CONTEXT:
// the mode word must appear BEFORE the first spatial preposition (of/in/at/
// around/through/along/across), which marks the boundary between the activity
// description and the place name. Words after the spatial prep are presumed
// to be part of the destination name.

/// Parse a free-text tour request into a location and tour_type hint.
///
/// Returns a map with 'location' and 'tour_type' keys.
Map<String, dynamic> parseTourRequest(String request) {
  final String lowerRequest = request.toLowerCase();

  // --- Transport modes FIRST (strongest signal: describes the tour itself) ---
  // Each transport check uses _hasActivityContext to guard against place-name
  // false positives.

  // Biking / cycling
  final bikeMatch =
      RegExp(r'\b(biking|cycling|bike)\b').firstMatch(lowerRequest);
  if (bikeMatch != null && _hasActivityContext(lowerRequest, bikeMatch)) {
    return _result(request, 'biking');
  }

  // Dog sledding / mushing
  final dogSledMatch =
      RegExp(r'\b(dogsled|dogsledding|dog\s+sled(?:ding)?|mushing|husky)\b')
          .firstMatch(lowerRequest);
  if (dogSledMatch != null &&
      _hasActivityContext(lowerRequest, dogSledMatch)) {
    return _result(request, 'dog sledding');
  }

  // Camel (but not camelback-the-mountain when in place name)
  final camelMatch =
      RegExp(r'\b(camel(?:back)?)\b').firstMatch(lowerRequest);
  if (camelMatch != null && _hasActivityContext(lowerRequest, camelMatch)) {
    return _result(request, 'camel');
  }

  // Horseback
  final horseMatch =
      RegExp(r'\b(horse(?:back)?)\b').firstMatch(lowerRequest);
  if (horseMatch != null && _hasActivityContext(lowerRequest, horseMatch)) {
    return _result(request, 'horseback');
  }

  // Vehicle modes
  final vehicleMatch =
      RegExp(r'\b(driving|jeep|motorcycle|scooter|off[- ]?road|car)\b')
          .firstMatch(lowerRequest);
  if (vehicleMatch != null &&
      _hasActivityContext(lowerRequest, vehicleMatch)) {
    return _result(request, 'driving');
  }

  // Country-scale / safari
  final safariMatch =
      RegExp(r'\broad\s*trip\b|\bcross[- ]?country\b|\bsafari\b')
          .firstMatch(lowerRequest);
  if (safariMatch != null &&
      _hasActivityContext(lowerRequest, safariMatch)) {
    return _result(request, 'safari');
  }

  // --- Category keywords (weaker signal: can be place names) ---
  // Walking/hiking ARE activities themselves -- no place-name guard needed.
  if (RegExp(r'\b(walking|walk|hike|hiking)\b').hasMatch(lowerRequest)) {
    return _result(request, 'walking');
  }
  // museum/park/exhibit can appear as place names ("Safari Park", "Horse
  // Museum") so they also require activity-context (before spatial prep).
  final museumMatch = RegExp(r'\bmuseum\b').firstMatch(lowerRequest);
  if (museumMatch != null && _hasActivityContext(lowerRequest, museumMatch)) {
    return _result(request, 'museum');
  }
  final parkMatch = RegExp(r'\bpark\b').firstMatch(lowerRequest);
  if (parkMatch != null && _hasActivityContext(lowerRequest, parkMatch)) {
    return _result(request, 'park');
  }
  final exhibitMatch = RegExp(r'\bexhibit\b').firstMatch(lowerRequest);
  if (exhibitMatch != null &&
      _hasActivityContext(lowerRequest, exhibitMatch)) {
    return _result(request, 'exhibit');
  }

  // --- No signal detected — let the server decide ---
  return _result(request, '');
}

/// Determines if a transport-mode keyword match is in an "activity context"
/// (describing the tour activity) vs. being part of a proper place name.
///
/// The key heuristic: a spatial preposition (of/in/at/around/through/along/
/// across) marks the boundary between the "activity portion" and the "place
/// portion" of a request. Words BEFORE the first spatial prep describe
/// what the tour IS; words AFTER describe WHERE.
///
/// Activity context is true when ANY of:
///   (a) The mode word appears BEFORE the first spatial preposition.
///   (b) The mode word follows by/on/via (e.g. "tour by bike").
///   (c) The mode word is the first substantive word with no spatial prep.
///
/// If the mode word is AFTER the spatial preposition, it is presumed to be
/// part of a place name and returns false.
bool _hasActivityContext(String lowerRequest, Match modeMatch) {
  final int matchStart = modeMatch.start;

  // Find the first spatial preposition marking where place names begin.
  final spatialPrepMatch = RegExp(
    r'\b(of|in|at|around|through|along|across)\b',
  ).firstMatch(lowerRequest);

  // (a) Mode word is before the first spatial preposition -> activity portion
  if (spatialPrepMatch != null && matchStart < spatialPrepMatch.start) {
    return true;
  }

  // If there is no spatial preposition at all, check other signals
  if (spatialPrepMatch == null) {
    // Mode word + activity noun anywhere -> activity context
    final activityNounPattern = RegExp(
      r'\b(tour|ride|riding|trip|excursion|tours|rides|trips)\b',
    );
    if (activityNounPattern.hasMatch(lowerRequest)) {
      return true;
    }
    // Leading word position -> activity context
    final leadingPattern = RegExp(r'^(?:(?:a|the|take\s+a|go)\s+)?');
    final leadingMatch = leadingPattern.firstMatch(lowerRequest);
    if (leadingMatch != null && leadingMatch.end == matchStart) {
      return true;
    }
    return false;
  }

  // Mode word is AFTER the spatial preposition -- it is in the place-name zone.
  // Only allow if preceded by by/on/via (e.g. "tour of X on horseback").
  // [LOCAL-363 LEAD] An indefinite article may intervene ("on a scooter",
  // "on an e-bike"). "the" is deliberately excluded: "on the boardwalk" and
  // "on the Horse Guards Parade" are place names, which is the bug this
  // guard exists to prevent.
  final textBefore = lowerRequest.substring(0, matchStart);
  final byOnViaPattern = RegExp(r'\b(by|on|via)\s+(?:an?\s+)?$');
  if (byOnViaPattern.hasMatch(textBefore)) {
    return true;
  }

  // No activity context -- mode word is inside a place name
  return false;
}

/// Build the result map with location extraction.
Map<String, dynamic> _result(String request, String tourType) {
  // Location extraction: use text after "for" if present, else full request
  String location = request;
  final RegExp forMatch = RegExp(r'for\s+(.+)', caseSensitive: false);
  final Match? match = forMatch.firstMatch(request);
  if (match != null) {
    location = match.group(1)!.trim();
  }

  return {
    'location': location,
    'tour_type': tourType,
  };
}
