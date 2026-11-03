// [LOCAL-853] Unit tests for the resilient map-tile decision logic: which URLs
// are tried and in what order, the retry/backoff schedule, whether an error is
// retriable, and the cache-first / fallback-on-failure / never-throw behaviour
// of loadTileBytes. No real network and no files beyond a temp dir are touched.
//
// Run: flutter test test/resilient_tile_provider_local853_test.dart

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_map/flutter_map.dart';

import 'package:audio_tour_app_dev/services/resilient_tile_provider.dart';

/// A fake client whose per-URL handler decides the response (or throws).
class _ScriptedClient extends http.BaseClient {
  _ScriptedClient(this._handler);

  final FutureOr<http.Response> Function(Uri url) _handler;
  final List<Uri> requested = [];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requested.add(request.url);
    final resp = await _handler(request.url);
    return http.StreamedResponse(
      Stream.value(resp.bodyBytes),
      resp.statusCode,
      headers: resp.headers,
    );
  }
}

/// An in-memory TileCache so the tests touch no real files.
TileCache _memCache() => _MemCache();

class _MemCache extends TileCache {
  final Map<String, Uint8List> _mem = {};

  @override
  Future<Uint8List?> read(String url) async => _mem[url];

  @override
  Future<void> write(String url, Uint8List bytes) async {
    _mem[url] = bytes;
  }

  @override
  Future<void> clear() async => _mem.clear();
}

final Uint8List _png = Uint8List.fromList(const [0x89, 0x50, 0x4E, 0x47, 1, 2, 3]);

void main() {
  group('isRetriableTileError', () {
    test('DNS / socket failures are retriable', () {
      expect(
        isRetriableTileError(
          const SocketException("Failed host lookup: 'tile.openstreetmap.org'"),
        ),
        isTrue,
      );
    });

    test('http ClientException (connection cancelled) is retriable', () {
      expect(
        isRetriableTileError(
          http.ClientException('Connection attempt cancelled'),
        ),
        isTrue,
      );
    });

    test('timeouts are retriable', () {
      expect(isRetriableTileError(TimeoutException('slow')), isTrue);
    });

    test('5xx is retriable, 4xx is not', () {
      expect(isRetriableTileError(const TileHttpStatus(503, 'u')), isTrue);
      expect(isRetriableTileError(const TileHttpStatus(404, 'u')), isFalse);
      expect(isRetriableTileError(const TileHttpStatus(403, 'u')), isFalse);
    });

    test('a plain programming error is NOT retriable', () {
      expect(isRetriableTileError(ArgumentError('bad')), isFalse);
    });
  });

  group('TileFetchPlan', () {
    const plan = TileFetchPlan(urls: ['A', 'B', 'C']);

    test('round-robins the hosts in order', () {
      expect(plan.urlForAttempt(0), 'A');
      expect(plan.urlForAttempt(1), 'B');
      expect(plan.urlForAttempt(2), 'C');
      expect(plan.urlForAttempt(3), 'A'); // next round
    });

    test('round number advances every full pass', () {
      expect(plan.roundForAttempt(0), 1);
      expect(plan.roundForAttempt(2), 1);
      expect(plan.roundForAttempt(3), 2);
      expect(plan.roundForAttempt(6), 3);
    });

    test('no delay within the first pass over distinct hosts', () {
      // A primary DNS failure must try the NEXT host instantly.
      expect(plan.backoffFor(0), Duration.zero);
      expect(plan.backoffFor(1), Duration.zero);
      expect(plan.backoffFor(2), Duration.zero);
    });

    test('exponential, capped backoff between rounds', () {
      // round 2 -> base*1, round 3 -> base*2
      expect(plan.backoffFor(3), const Duration(milliseconds: 400));
      expect(plan.backoffFor(6), const Duration(milliseconds: 800));
    });

    test('backoff is capped at maxBackoff', () {
      const p = TileFetchPlan(
        urls: ['A'],
        maxRounds: 20,
        baseBackoff: Duration(seconds: 1),
        maxBackoff: Duration(seconds: 8),
      );
      // Very high round would be huge; must clamp to 8s.
      expect(p.backoffFor(19).inSeconds, lessThanOrEqualTo(8));
    });

    test('totalAttempts = hosts * rounds', () {
      expect(plan.totalAttempts, 9);
    });

    test('candidate URL ordering: primary first, then distinct fallbacks', () {
      final provider = ResilientTileProvider(
        fallbackTemplates: const [
          'https://b.example/{z}/{x}/{y}.png',
          'https://a.example/{z}/{x}/{y}.png', // primary dup dropped below
        ],
      );
      final opts = TileLayer(
        urlTemplate: 'https://a.example/{z}/{x}/{y}.png',
      );
      final urls = provider.candidateUrls(
        const TileCoordinates(1, 2, 3),
        opts,
      );
      // TileCoordinates(x:1, y:2, z:3) with template {z}/{x}/{y} -> 3/1/2
      expect(urls.first, 'https://a.example/3/1/2.png');
      expect(urls, contains('https://b.example/3/1/2.png'));
      // the fallback identical to the primary is not duplicated
      expect(urls.where((u) => u == 'https://a.example/3/1/2.png').length, 1);
    });
  });

  group('loadTileBytes', () {
    test('serves from cache first, no network call', () async {
      final cache = _memCache();
      await cache.write('A', _png);
      var calls = 0;
      final client = _ScriptedClient((u) {
        calls++;
        return http.Response('', 500);
      });
      final bytes = await loadTileBytes(
        plan: const TileFetchPlan(urls: ['A', 'B']),
        headers: const {},
        client: client,
        cache: cache,
      );
      expect(bytes, _png);
      expect(calls, 0, reason: 'cache hit must not touch the network');
    });

    test('falls back to the next host when the primary DNS-fails', () async {
      final cache = _memCache();
      final client = _ScriptedClient((u) {
        if (u.toString() == 'A') {
          throw const SocketException("Failed host lookup: 'A'");
        }
        return http.Response.bytes(_png, 200);
      });
      final bytes = await loadTileBytes(
        plan: const TileFetchPlan(urls: ['A', 'B']),
        headers: const {},
        client: client,
        cache: cache,
      );
      expect(bytes, _png);
      expect(client.requested.map((u) => u.toString()).toList(), ['A', 'B']);
      // and it got cached under the primary key
      expect(await cache.read('A'), _png);
    });

    test('returns the transparent tile (never throws) on total failure',
        () async {
      final cache = _memCache();
      final client = _ScriptedClient(
        (u) => throw const SocketException('down'),
      );
      final bytes = await loadTileBytes(
        plan: const TileFetchPlan(
          urls: ['A', 'B'],
          maxRounds: 1, // keep the test fast
        ),
        headers: const {},
        client: client,
        cache: cache,
      );
      // Transparent 1x1 PNG — the map shows grey + pins, never blocks Home.
      expect(bytes, TileProvider.transparentImage);
    });

    test('a 200 with an empty body is treated as a miss, tries next host',
        () async {
      final cache = _memCache();
      final client = _ScriptedClient((u) {
        if (u.toString() == 'A') return http.Response.bytes(Uint8List(0), 200);
        return http.Response.bytes(_png, 200);
      });
      final bytes = await loadTileBytes(
        plan: const TileFetchPlan(urls: ['A', 'B']),
        headers: const {},
        client: client,
        cache: cache,
      );
      expect(bytes, _png);
    });
  });
}
