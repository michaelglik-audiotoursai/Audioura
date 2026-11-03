// [LOCAL-853] Single source of truth for the Home / builder map tile source.
//
// THE BUG (GCloud_Storied_1 failure_events, Michael's iPhone, Vietnam,
// since 2026-11-02 08:21Z): 31 × "Failed host lookup:
// 'tile.openstreetmap.org'" + 10 × "Connection attempt cancelled, host:
// tile.openstreetmap.org:443". Every /tours-near call in the same window was
// 200, so the server is fine — it is the OSM tile host that is unreachable or
// slow from that network. The default flutter_map NetworkTileProvider has no
// on-disk cache and only a RetryClient, so once DNS fails the Home map is grey
// with no previously-seen tiles to fall back to.
//
// THE FIX: the tile URL now comes from ONE place (this file). [primaryTemplate]
// is byte-for-byte the URL the app already used, so the default behaviour is
// unchanged. [fallbackTemplates] is a list of OSM-tile-compatible mirrors with
// the SAME {z}/{x}/{y}.png contract, tried IN ORDER only when the primary host
// fails to resolve or connect (see ResilientTileProvider). A persistent on-disk
// cache (also wired by ResilientTileProvider) makes previously-seen tiles show
// offline and on flaky networks, so a tile failure shows the cached-or-grey map
// with pins still visible and NEVER blocks the Home screen.
//
// NO paid key or account is configured here: that is a LEAD decision (see the
// provider comparison in SUBMISSION_LOCAL-853.md). The fallback mirrors below
// are all key-less, OSM-tile-policy-compatible community/CDN endpoints.

class MapTiles {
  const MapTiles._();

  /// The user agent OSM (and the mirrors) require; a generic `com.example`
  /// agent is throttled. Unchanged from the previous hardcoded value.
  static const String userAgentPackageName = 'com.audioura.audiotours';

  /// The primary tile URL template. Default unchanged: the live OSM host.
  /// Overridable at build time via
  /// `--dart-define=MAP_TILE_URL=https://…/{z}/{x}/{y}.png` so LEAD can point
  /// the app at a CDN-backed provider or our own caching proxy WITHOUT a code
  /// change (the key, if any, is baked into the template there).
  static const String primaryTemplate = String.fromEnvironment(
    'MAP_TILE_URL',
    defaultValue: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  );

  /// Fallback tile URL templates, tried in order ONLY when [primaryTemplate]'s
  /// host fails to resolve or connect. Each uses the identical
  /// `{z}/{x}/{y}.png` contract and is key-less + OSM-tile-policy compatible,
  /// so no account is needed. These are community/CDN mirrors of the same
  /// OSM raster tiles; LEAD may replace them with a commercial CDN provider.
  ///
  /// NB: the OSM Foundation asks heavy/commercial apps NOT to lean on
  /// tile.openstreetmap.org — these mirrors are a stop-gap so the map survives
  /// a primary-host DNS failure; the long-term answer is the CDN provider LEAD
  /// picks from the comparison. Overridable via
  /// `--dart-define=MAP_TILE_FALLBACKS=url1,url2`.
  static const String _rawFallbacks = String.fromEnvironment(
    'MAP_TILE_FALLBACKS',
    defaultValue:
        'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png,'
        'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png,'
        'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png',
  );

  static List<String> get fallbackTemplates => _rawFallbacks
      .split(',')
      .map((s) => s.trim())
      .where((s) => s.isNotEmpty)
      .toList(growable: false);

  /// The full ordered list the provider tries: primary first, then each
  /// fallback whose host differs from the primary's (a fallback that is just
  /// the primary host again adds nothing on a DNS failure).
  static List<String> get orderedTemplates {
    final primaryHost = _hostOf(primaryTemplate);
    final out = <String>[primaryTemplate];
    for (final t in fallbackTemplates) {
      if (t == primaryTemplate) continue;
      // Keep same-host fallbacks (a/b/c.tile.* ARE distinct hosts) but drop an
      // exact duplicate of the primary.
      if (_hostOf(t) == primaryHost && t == primaryTemplate) continue;
      out.add(t);
    }
    return out;
  }

  static String _hostOf(String template) {
    final uri = Uri.tryParse(template.replaceAll(RegExp(r'\{[^}]+\}'), '0'));
    return uri?.host ?? template;
  }
}
