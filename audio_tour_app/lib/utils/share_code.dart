/// [LOCAL-579] Share-code helpers.
///
/// A share code is exactly 8 base62 characters (see tour_sharing.py). ST-3
/// taught the Home search box to recognise a bare code. This adds the inverse
/// of the SENDING side's message: a listener who receives the full share text
///
///   Listen to my Audioura tour "X". Open Audioura, tap Search on the Home
///   page and paste this code: FFush25U
///
/// — or a share link like https://audioura.io/tour/FFush25U — can paste the
/// WHOLE thing into Search and still land on the tour. [extractShareCode]
/// pulls the 8-char token back out of that noise.
library;

/// The exact message a curator sends when sharing a tour. Kept here so the
/// sender (share sheet) and the receiver (extractor test) agree on one wording.
///
/// [tourName] is the tour title; [code] is the 8-char share id.
String buildShareMessage(String tourName, String code) =>
    'Listen to my Audioura tour "$tourName". Open Audioura, tap Search on the '
    'Home page and paste this code: $code';

/// A single base62 token of exactly 8 characters.
final RegExp _codeToken = RegExp(r'[A-Za-z0-9]{8}');

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
/// A link's path segment (…/tour/FFush25U) is just another 8-char run, so no
/// URL parsing is needed; but if the last path segment is a clean code we
/// prefer it, because a link is an unambiguous signal.
String? extractShareCode(String input) {
  final text = input.trim();
  if (text.isEmpty) return null;

  // Prefer a link's final path segment when it is itself a valid code — a URL
  // is the least ambiguous carrier of a code.
  final uri = Uri.tryParse(text);
  if (uri != null && uri.hasScheme && uri.pathSegments.isNotEmpty) {
    final last = uri.pathSegments.last;
    if (isShareCodeShape(last)) return last;
  }

  for (final match in _codeToken.allMatches(text)) {
    final token = match.group(0)!;
    if (isShareCodeShape(token)) return token;
  }
  return null;
}
