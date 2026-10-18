/// [LOCAL-579 / LOCAL-709] Share-code helpers.
///
/// A share code is exactly 8 base62 characters (see tour_sharing.py). ST-3
/// taught the Home search box to recognise a bare code. This file is the one
/// place where the SENDING side builds a shareable link/message and the
/// RECEIVING side ([extractShareCode]) pulls the 8-char token back out.
///
/// [LOCAL-709 / D671] A shared tour now leads with a real link:
///
///   Listen to my Audioura tour "X": https://audioura.com/t/FFush25U
///   (or open Audioura, tap Search and paste FFush25U)
///
/// With Audioura installed the link opens Home → Search with the code filled in
/// and the search already run (an App Link / Universal Link, resolved by the
/// SAME code path a pasted code takes). Without it, the link reaches the
/// audioura.com/t/ landing page, which sends the visitor to the store.
/// [extractShareCode] still pulls CODE from the message, the bare link, the
/// link with `?n=`, and a link with a trailing slash.
library;

/// The canonical host + path prefix for a tour share link (D671). One place so
/// the builder, the Android intent-filter, the iOS associated-domain and the
/// website all agree.
const String kShareLinkHost = 'audioura.com';
const String kShareLinkPrefix = 'https://$kShareLinkHost/t/';

/// Build the canonical share LINK for a tour (D671):
///   https://audioura.com/t/<CODE>?n=<url-encoded tour name>
///
/// [code] is the 8-char share id; [tourName] is the tour title. `n` is only for
/// the landing page's headline — the app ignores it. The name is encoded with
/// [Uri.encodeQueryComponent] so quotes, `&` and accents survive intact.
String buildShareLink(String code, String tourName) {
  final encoded = Uri.encodeQueryComponent(tourName);
  return '$kShareLinkPrefix$code?n=$encoded';
}

/// The exact message a curator sends when sharing a tour (D671 §5). Leads with
/// the link and keeps the code as a fallback. Kept here so the sender (share
/// sheet) and the receiver (extractor test) agree on one wording.
///
/// [tourName] is the tour title; [code] is the 8-char share id.
String buildShareMessage(String tourName, String code) =>
    'Listen to my Audioura tour "$tourName": ${buildShareLink(code, tourName)}'
    '  (or open Audioura, tap Search and paste $code)';

/// Build the share LINK for a community invite code (D671). A community invite
/// is carried by the SAME `https://audioura.com/t/<CODE>` link as a tour: the
/// app's single share-code path resolves a `/t/` code as a tour first and then
/// a community (home_screen `_dispatchShareCode`), and the landing page copies
/// the code regardless. No `?n=` — a community has no tour-name headline.
String buildCommunityInviteLink(String code) => '$kShareLinkPrefix$code';

/// The local fallback invite text an organiser shares for a community (D671).
/// Leads with the link and keeps the code as a fallback, mirroring
/// [buildShareMessage]. The server may supply its own `invite_message`; this is
/// the client fallback when it does not.
String buildCommunityInviteMessage(String communityName, String code) =>
    'Join "$communityName" on Audioura: ${buildCommunityInviteLink(code)}'
    '  (or open Audioura, tap Search and paste $code)';

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
