// [LOCAL-853] A resilient flutter_map [TileProvider] that keeps the Home map
// usable from a flaky network (Michael's iPhone, Vietnam): it serves tiles from
// a persistent ON-DISK cache first, fetches missing tiles with RETRY + BACKOFF,
// and on a DNS/connect failure of the primary host it FALLS BACK to the mirror
// hosts from [MapTiles]. It NEVER throws from the image load path — on total
// failure it yields a transparent tile, so the map shows cached-or-grey tiles
// with the pins (MarkerLayer) still drawn and the Home screen is never blocked.
//
// Design notes:
//  * The pure decision logic (which URLs to try, the backoff schedule, whether
//    an error is worth retrying) lives in [TileFetchPlan] and
//    [isRetriableTileError] so it is unit-testable with no Flutter/IO/network.
//  * The provider owns one http Client, exactly like flutter_map's
//    NetworkTileProvider. It is only closed on dispose(); the Home map keeps
//    ONE stable TileLayer for its whole life (FirstLayoutTileLayer invariant),
//    so in-flight tile requests are never cancelled mid-load.
//  * The cache is a simple content-addressed file store under the app cache
//    dir, keyed by a hash of the tile URL (host-independent: a tile fetched
//    from a fallback host still satisfies a later primary-host request for the
//    same z/x/y). A size cap evicts oldest-first, best-effort.

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import '../config/map_tiles.dart';

/// Whether a tile fetch error is worth retrying / falling back on. DNS
/// ("Failed host lookup"), connection-cancelled/refused/reset, timeouts and
/// 5xx are transient; a 404/403 for a specific tile is not (that tile simply
/// does not exist on that host — try the next host, not the same one again).
bool isRetriableTileError(Object error) {
  if (error is SocketException) return true; // includes failed host lookup
  if (error is HttpException) return true;
  if (error is TimeoutException) return true;
  if (error is http.ClientException) return true;
  if (error is TileHttpStatus) return error.statusCode >= 500;
  return false;
}

/// Marker error carrying a non-2xx HTTP status so the retry logic can tell a
/// 5xx (retry/fallback) from a 4xx (skip to next host, do not hammer this one).
class TileHttpStatus implements Exception {
  const TileHttpStatus(this.statusCode, this.url);
  final int statusCode;
  final String url;
  @override
  String toString() => 'TileHttpStatus($statusCode, $url)';
}

/// Pure substitution of the standard `{z}`/`{x}`/`{y}` placeholders in a tile
/// URL [template] for the given [coordinates]. Used for the FALLBACK host
/// templates (all OSM-style `{z}/{x}/{y}.png` mirrors). The primary URL still
/// goes through flutter_map's own getTileUrl so retina/tms/subdomain handling
/// is unchanged. Separated out so it is trivially unit-testable.
String fillTileTemplate(String template, TileCoordinates coordinates) {
  return template
      .replaceAll('{z}', coordinates.z.toString())
      .replaceAll('{x}', coordinates.x.toString())
      .replaceAll('{y}', coordinates.y.toString());
}

/// A pure, testable plan for fetching ONE tile: the ordered list of candidate
/// URLs (primary then fallbacks) and the backoff delay before the Nth attempt.
///
/// Attempt semantics: attempt 0 is the first try of the FIRST url with no
/// delay; when a url fails with a retriable error we advance to the NEXT url
/// (so a primary DNS failure immediately tries a different host, which is the
/// whole point for Michael). Once every url has been tried once, we loop back
/// to the start for up to [maxRounds] rounds, waiting [backoffFor] between
/// rounds — the increasing delay gives a transiently-down network time to
/// recover without blocking (the fetch runs off the UI thread).
@immutable
class TileFetchPlan {
  const TileFetchPlan({
    required this.urls,
    this.maxRounds = 3,
    this.baseBackoff = const Duration(milliseconds: 400),
    this.maxBackoff = const Duration(seconds: 8),
  });

  /// Candidate URLs in priority order (primary first). Never empty in practice.
  final List<String> urls;

  /// How many full passes over [urls] to make before giving up.
  final int maxRounds;

  final Duration baseBackoff;
  final Duration maxBackoff;

  /// Total number of attempts across all rounds.
  int get totalAttempts => urls.length * maxRounds;

  /// The URL to try on [attempt] (0-based), cycling through [urls].
  String urlForAttempt(int attempt) => urls[attempt % urls.length];

  /// 1-based round number for [attempt].
  int roundForAttempt(int attempt) => (attempt ~/ urls.length) + 1;

  /// The delay to wait BEFORE [attempt]. No delay before the first attempt of a
  /// round-robin pass over distinct hosts (attempt < urls.length): a primary
  /// DNS failure should try the next host instantly. Between full rounds the
  /// delay grows exponentially (capped) — classic capped exponential backoff.
  Duration backoffFor(int attempt) {
    if (attempt < urls.length) return Duration.zero;
    final round = attempt ~/ urls.length; // 1, 2, ...
    final ms = baseBackoff.inMilliseconds * (1 << (round - 1));
    final capped = ms > maxBackoff.inMilliseconds ? maxBackoff.inMilliseconds : ms;
    return Duration(milliseconds: capped);
  }

  /// Build the plan for the live map config.
  factory TileFetchPlan.fromConfig(List<String> orderedUrls) =>
      TileFetchPlan(urls: orderedUrls);
}

/// Resilient tile provider. Use in place of the default network provider.
class ResilientTileProvider extends TileProvider {
  ResilientTileProvider({
    super.headers,
    http.Client? httpClient,
    TileCache? cache,
    List<String>? fallbackTemplates,
    this.debugKeyNamespace,
  })  : _client = httpClient ?? http.Client(),
        _cache = cache ?? TileCache.instance,
        _fallbackTemplates = fallbackTemplates ?? MapTiles.fallbackTemplates;

  final http.Client _client;
  final TileCache _cache;
  final List<String> _fallbackTemplates;

  /// Test-only: folded into each tile image's identity so two providers built
  /// with different namespaces never share Flutter's in-memory image cache.
  /// Production leaves this null (no effect). Used by the LOCAL-853 screenshot
  /// run to render three independent map states in one process.
  final String? debugKeyNamespace;

  /// Build the ordered candidate URLs for a tile: the layer's primary URL (via
  /// the public [getTileUrl]) followed by each configured fallback template
  /// populated for the same coordinates with [fillTileTemplate].
  List<String> candidateUrls(TileCoordinates coordinates, TileLayer options) {
    final primary = getTileUrl(coordinates, options);
    final urls = <String>[primary];
    // Resolve z/x/y from the SAME values flutter_map used for the primary, so a
    // fallback host serves the identical tile. We re-read them off the layer's
    // zoom math via the coordinates (no retina/tms edge handling needed for the
    // plain OSM-style mirrors; they all use {z}/{x}/{y}.png).
    for (final template in _fallbackTemplates) {
      try {
        final u = fillTileTemplate(template, coordinates);
        if (u != primary && !urls.contains(u)) urls.add(u);
      } catch (_) {
        // A malformed fallback template never breaks the primary path.
      }
    }
    return urls;
  }

  @override
  ImageProvider getImage(TileCoordinates coordinates, TileLayer options) {
    return _ResilientTileImage(
      plan: TileFetchPlan.fromConfig(candidateUrls(coordinates, options)),
      headers: headers,
      client: _client,
      cache: _cache,
      keyNamespace: debugKeyNamespace,
    );
  }

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }
}

/// The [ImageProvider] that actually loads one tile: cache → network (with the
/// plan's retry/fallback/backoff) → transparent-on-total-failure.
@immutable
class _ResilientTileImage extends ImageProvider<_ResilientTileImage> {
  const _ResilientTileImage({
    required this.plan,
    required this.headers,
    required this.client,
    required this.cache,
    this.keyNamespace,
  });

  final TileFetchPlan plan;
  final Map<String, String> headers;
  final http.Client client;
  final TileCache cache;
  final String? keyNamespace;

  /// Cache identity is the primary URL — the same tile from any host shares one
  /// cache slot and one image-cache entry. [keyNamespace] (test-only) further
  /// separates identities so independent map states don't share the in-memory
  /// image cache.
  String get _key =>
      keyNamespace == null ? plan.urls.first : '$keyNamespace|${plan.urls.first}';

  @override
  Future<_ResilientTileImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture<_ResilientTileImage>(this);

  @override
  ImageStreamCompleter loadImage(
    _ResilientTileImage key,
    ImageDecoderCallback decode,
  ) {
    return MultiFrameImageStreamCompleter(
      codec: _load(decode),
      scale: 1.0,
      debugLabel: _key,
    );
  }

  Future<ui.Codec> _load(ImageDecoderCallback decode) async {
    final bytes = await loadTileBytes(
      plan: plan,
      headers: headers,
      client: client,
      cache: cache,
    );
    final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
    return decode(buffer);
  }

  @override
  bool operator ==(Object other) =>
      other is _ResilientTileImage && other._key == _key;

  @override
  int get hashCode => _key.hashCode;
}

/// Load one tile's PNG bytes: serve from [cache] if present; otherwise walk the
/// [plan] (primary then fallbacks, with backoff between rounds), caching the
/// first success; and if everything fails, return the transparent 1×1 tile so
/// the image load NEVER throws and the map is never blocked.
///
/// Separated from the ImageProvider so it can be unit-tested with a fake client
/// and a temp-dir cache.
Future<Uint8List> loadTileBytes({
  required TileFetchPlan plan,
  required Map<String, String> headers,
  required http.Client client,
  required TileCache cache,
}) async {
  final cacheKey = plan.urls.first;

  // 1) On-disk cache: show previously-seen tiles instantly, even fully offline.
  final cached = await cache.read(cacheKey);
  if (cached != null) return cached;

  // 2) Network with retry + fallback + backoff.
  Object? lastError;
  for (var attempt = 0; attempt < plan.totalAttempts; attempt++) {
    final delay = plan.backoffFor(attempt);
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    final url = plan.urlForAttempt(attempt);
    try {
      final resp = await client
          .get(Uri.parse(url), headers: headers)
          .timeout(const Duration(seconds: 12));
      if (resp.statusCode == 200 && resp.bodyBytes.isNotEmpty) {
        unawaited(cache.write(cacheKey, resp.bodyBytes));
        return resp.bodyBytes;
      }
      lastError = TileHttpStatus(resp.statusCode, url);
      if (!isRetriableTileError(lastError)) {
        // 4xx: this host won't serve it — move to the next host immediately
        // (the round-robin does that), but don't treat it as fatal.
        continue;
      }
    } catch (e) {
      lastError = e;
      if (!isRetriableTileError(e)) {
        // Non-network programming error: stop, fall through to transparent.
        break;
      }
    }
  }

  // 3) Total failure: never throw. Grey/transparent tile, pins still draw.
  if (kDebugMode) {
    debugPrint('[LOCAL-853] tile load failed for $cacheKey: $lastError');
  }
  return TileProvider.transparentImage;
}

/// A small persistent on-disk tile cache. Content is keyed by a SHA-1 of the
/// tile URL; a best-effort size cap evicts the oldest files. All methods are
/// failure-tolerant: a cache problem never breaks tile loading.
class TileCache {
  TileCache({this.maxBytes = 50 * 1024 * 1024});

  static final TileCache instance = TileCache();

  /// Soft cap on total cache size. Default 50 MB.
  final int maxBytes;

  Future<Directory>? _dirFuture;

  Future<Directory> _directory() {
    return _dirFuture ??= () async {
      final base = await getTemporaryDirectory();
      final dir = Directory('${base.path}/local853_tiles');
      if (!await dir.exists()) {
        await dir.create(recursive: true);
      }
      return dir;
    }();
  }

  String _fileNameFor(String url) => sha1.convert(utf8.encode(url)).toString();

  File _fileFor(Directory dir, String url) =>
      File('${dir.path}/${_fileNameFor(url)}.tile');

  /// Read cached bytes for [url], or null if absent / unreadable.
  Future<Uint8List?> read(String url) async {
    try {
      final dir = await _directory();
      final f = _fileFor(dir, url);
      if (!await f.exists()) return null;
      final bytes = await f.readAsBytes();
      if (bytes.isEmpty) return null;
      // Touch for LRU-ish eviction ordering (best-effort).
      unawaited(f.setLastModified(DateTime.now()).catchError((_) {}));
      return bytes;
    } catch (_) {
      return null;
    }
  }

  /// Write [bytes] for [url]; best-effort, then enforce the size cap.
  Future<void> write(String url, Uint8List bytes) async {
    try {
      final dir = await _directory();
      final f = _fileFor(dir, url);
      await f.writeAsBytes(bytes, flush: false);
      unawaited(_enforceCap(dir));
    } catch (_) {
      // Ignore: the cache is an optimisation, not a requirement.
    }
  }

  Future<void> _enforceCap(Directory dir) async {
    try {
      final files = <File>[];
      await for (final e in dir.list()) {
        if (e is File) files.add(e);
      }
      var total = 0;
      final stats = <MapEntry<File, FileStat>>[];
      for (final f in files) {
        final s = await f.stat();
        total += s.size;
        stats.add(MapEntry(f, s));
      }
      if (total <= maxBytes) return;
      // Evict oldest-first until under the cap.
      stats.sort((a, b) => a.value.modified.compareTo(b.value.modified));
      for (final entry in stats) {
        if (total <= maxBytes) break;
        try {
          await entry.key.delete();
          total -= entry.value.size;
        } catch (_) {}
      }
    } catch (_) {}
  }

  /// Delete everything in the cache (test / "clear cache" affordance).
  Future<void> clear() async {
    try {
      final dir = await _directory();
      await for (final e in dir.list()) {
        if (e is File) {
          try {
            await e.delete();
          } catch (_) {}
        }
      }
    } catch (_) {}
  }
}
