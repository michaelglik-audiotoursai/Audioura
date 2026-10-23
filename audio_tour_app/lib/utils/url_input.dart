// [LOCAL-740 / A3b] One shared helper for links the listener types or pastes.
//
// Why (Michael's review, 2026-10-22): Generate → Newsletter refused
// `en.wikipedia.org/wiki/Boston` with "invalid URL". A browser's address bar
// accepts a link with no scheme and just adds `https://`; so must we. A link
// that already carries `http://` or `https://` is left exactly as typed.
//
// Pure (no Flutter, no I/O) so the behaviour is unit-tested without a widget
// tree or a running server, and so every URL field in the app shares ONE rule.

/// Trim [raw] and make it a usable absolute URL: a link that already starts with
/// a scheme (`http://`, `https://`, or any other `scheme://`) is returned
/// trimmed and unchanged; a link with no scheme gets `https://` prepended, the
/// way a browser's address bar does.
///
/// Returns '' for null / blank input (the caller decides what an empty field
/// means — this helper never invents a URL out of nothing).
///
/// Examples:
///   `en.wikipedia.org/wiki/Boston` → `https://en.wikipedia.org/wiki/Boston`
///   `  example.com  `              → `https://example.com`
///   `http://example.com`           → `http://example.com` (unchanged)
///   `https://example.com`          → `https://example.com` (unchanged)
///   `www.example.com`              → `https://www.example.com`
String normalizeUrlInput(String? raw) {
  if (raw == null) return '';
  final trimmed = raw.trim();
  if (trimmed.isEmpty) return '';
  // Already carries a scheme (http://, https://, ftp://, …)? Leave it alone.
  // A scheme is letters/digits/+/-/. followed by "://" at the very start.
  final hasScheme = RegExp(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://').hasMatch(trimmed);
  if (hasScheme) return trimmed;
  return 'https://$trimmed';
}

/// Whether [raw], once normalized, is a plausible web link: it has a host with a
/// dot (so `foo` alone is rejected but `foo.com` is accepted). A light client
/// check to replace the old "must start with http" gate — the server still has
/// the final say on whether the page can be fetched.
bool looksLikeUrl(String? raw) {
  final n = normalizeUrlInput(raw);
  if (n.isEmpty) return false;
  final uri = Uri.tryParse(n);
  if (uri == null) return false;
  if (!uri.hasAuthority) return false;
  return uri.host.contains('.') && uri.host.length >= 3;
}
