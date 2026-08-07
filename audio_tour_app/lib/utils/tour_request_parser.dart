// [LOCAL-358] Tour request parser — extracted for testability.
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

/// Parse a free-text tour request into a location and tour_type hint.
///
/// Returns a map with 'location' and 'tour_type' keys.
Map<String, dynamic> parseTourRequest(String request) {
  final String lowerRequest = request.toLowerCase();

  // --- Transport modes FIRST (strongest signal: describes the tour itself) ---
  // Biking / cycling
  if (RegExp(r'\b(biking|cycling|bike)\b').hasMatch(lowerRequest)) {
    return _result(request, 'biking');
  }
  // Dog sledding / mushing
  if (RegExp(r'\b(dogsled|dogsledding|dog\s+sled(?:ding)?|mushing|husky)\b')
      .hasMatch(lowerRequest)) {
    return _result(request, 'dog sledding');
  }
  // Camel
  if (RegExp(r'\b(camel(?:back)?)\b').hasMatch(lowerRequest)) {
    return _result(request, 'camel');
  }
  // Horseback
  if (RegExp(r'\b(horse(?:back)?)\b').hasMatch(lowerRequest)) {
    return _result(request, 'horseback');
  }
  // Vehicle modes
  if (RegExp(r'\b(driving|jeep|motorcycle|scooter|off[- ]?road)\b')
      .hasMatch(lowerRequest) ||
      RegExp(r'\bcar\b').hasMatch(lowerRequest)) {
    return _result(request, 'driving');
  }
  // Country-scale / safari
  if (RegExp(r'\broad\s*trip\b|\bcross[- ]?country\b|\bsafari\b')
      .hasMatch(lowerRequest)) {
    return _result(request, 'safari');
  }

  // --- Category keywords (weaker signal: can be place names) ---
  // Use word boundaries to prevent substring matches (boardwalk, sidewalk).
  if (RegExp(r'\b(walking|walk|hike|hiking)\b').hasMatch(lowerRequest)) {
    return _result(request, 'walking');
  }
  if (RegExp(r'\bmuseum\b').hasMatch(lowerRequest)) {
    return _result(request, 'museum');
  }
  if (RegExp(r'\bpark\b').hasMatch(lowerRequest)) {
    return _result(request, 'park');
  }
  if (RegExp(r'\bexhibit\b').hasMatch(lowerRequest)) {
    return _result(request, 'exhibit');
  }

  // --- No signal detected — let the server decide ---
  return _result(request, '');
}

/// Build the result map with location extraction.
Map<String, dynamic> _result(String request, String tourType) {
  // Location extraction — use text after "for" if present, else full request
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
