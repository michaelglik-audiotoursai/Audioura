// [LOCAL-759 A] Tests for the streaming remote-audio fetcher — the core that
// lets the phone pull a REAL podcast episode (Michael's Salem tour: 72.5 / 80.9
// / 131.8 MB) that the old http.get(...).timeout(120s) could never finish.
//
// All red on d816a251 (the streaming fetcher does not exist yet). They exercise
// the fetcher directly with a FAKE http.Client (chunked bodies, redirects,
// stalls) and a temp directory, so no network and no real files beyond a temp
// dir are touched:
//   * streams a chunked body to audio_N.mp3.part then renames — never holds the
//     whole episode in memory (asserted by feeding chunks one at a time);
//   * the idle timeout fires ONLY on no data (a slow-but-steady stream that
//     takes longer than the idle window still completes);
//   * a failing stop is retried, then succeeds;
//   * the redirect chain (302 → 302 → 200) is followed;
//   * after retries a failing stop throws the NAMED message
//     ("Audio for stop 2 'The Accusations Begin' could not be downloaded.") and
//     leaves NO .part file behind;
//   * Cancel removes a partial .part file.

import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:audio_tour_app_dev/services/remote_audio_fetcher.dart';

/// A fake streamed response builder. Each entry is a scripted response the fake
/// client returns in sequence for successive requests.
class _ScriptedClient extends http.BaseClient {
  _ScriptedClient(this._handler);

  final Future<http.StreamedResponse> Function(http.BaseRequest request)
      _handler;
  final List<Uri> requested = [];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    requested.add(request.url);
    return _handler(request);
  }
}

http.StreamedResponse _streamed(
  List<List<int>> chunks, {
  int status = 200,
  Map<String, String> headers = const {},
  Duration gap = Duration.zero,
}) {
  Stream<List<int>> body() async* {
    for (final c in chunks) {
      if (gap > Duration.zero) await Future.delayed(gap);
      yield c;
    }
  }

  final contentLength = chunks.fold<int>(0, (a, c) => a + c.length);
  return http.StreamedResponse(body(), status,
      contentLength: contentLength, headers: headers);
}

void main() {
  late Directory tmp;

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('l759_fetch_');
  });
  tearDown(() async {
    if (tmp.existsSync()) await tmp.delete(recursive: true);
  });

  test('streams a chunked body to audio_N.mp3 (via .part) without holding it',
      () async {
    final client = _ScriptedClient((req) async =>
        _streamed([
          List.filled(1024, 1),
          List.filled(1024, 2),
          List.filled(1024, 3),
        ]));

    final fetcher = RemoteAudioFetcher(
      clientFactory: () => client,
      idleTimeout: const Duration(seconds: 30),
      maxRetries: 2,
    );

    await fetcher.fetchToFile(
      url: 'https://host/ep1.mp3',
      destPath: '${tmp.path}/audio_1.mp3',
      stopNumber: 1,
      stopName: 'Intro',
    );

    final f = File('${tmp.path}/audio_1.mp3');
    expect(f.existsSync(), isTrue);
    expect(f.lengthSync(), 3072);
    // The .part file is gone (renamed on completion).
    expect(File('${tmp.path}/audio_1.mp3.part').existsSync(), isFalse);
  });

  test('idle timeout fires only on NO data, not on total time', () async {
    // A steady stream whose TOTAL time exceeds the idle window but whose gaps
    // between chunks are small must still complete.
    final client = _ScriptedClient((req) async => _streamed(
          List.generate(10, (_) => List.filled(256, 7)),
          gap: const Duration(milliseconds: 20),
        ));

    final fetcher = RemoteAudioFetcher(
      clientFactory: () => client,
      idleTimeout: const Duration(milliseconds: 100),
      maxRetries: 0,
    );

    await fetcher.fetchToFile(
      url: 'https://host/ep.mp3',
      destPath: '${tmp.path}/audio_1.mp3',
      stopNumber: 1,
      stopName: 'Steady',
    );
    expect(File('${tmp.path}/audio_1.mp3').lengthSync(), 2560);
  });

  test('a stalled stream (no data past the idle window) fails then retries',
      () async {
    var attempt = 0;
    final client = _ScriptedClient((req) async {
      attempt++;
      if (attempt == 1) {
        // First attempt stalls forever after the first byte.
        Stream<List<int>> stalled() async* {
          yield [1];
          await Future.delayed(const Duration(seconds: 10));
        }

        return http.StreamedResponse(stalled(), 200);
      }
      // Second attempt succeeds.
      return _streamed([List.filled(512, 9)]);
    });

    final fetcher = RemoteAudioFetcher(
      clientFactory: () => client,
      idleTimeout: const Duration(milliseconds: 80),
      maxRetries: 2,
      backoff: (_) => Duration.zero,
    );

    await fetcher.fetchToFile(
      url: 'https://host/ep.mp3',
      destPath: '${tmp.path}/audio_1.mp3',
      stopNumber: 1,
      stopName: 'Retry',
    );
    expect(attempt, 2);
    expect(File('${tmp.path}/audio_1.mp3').lengthSync(), 512);
  });

  test('follows a redirect chain (302 → 302 → 200)', () async {
    var hop = 0;
    final client = _ScriptedClient((req) async {
      hop++;
      if (hop <= 2) {
        return http.StreamedResponse(const Stream.empty(), 302,
            headers: {'location': 'https://host/hop$hop.mp3'});
      }
      return _streamed([List.filled(400, 5)]);
    });

    final fetcher = RemoteAudioFetcher(
      clientFactory: () => client,
      idleTimeout: const Duration(seconds: 5),
      maxRetries: 0,
    );

    await fetcher.fetchToFile(
      url: 'https://dts.podtrac.com/redirect.mp3/host/ep.mp3',
      destPath: '${tmp.path}/audio_1.mp3',
      stopNumber: 1,
      stopName: 'Podtrac',
    );
    expect(hop, 3);
    expect(File('${tmp.path}/audio_1.mp3').lengthSync(), 400);
  });

  test('after retries a failing stop throws the NAMED message and cleans up',
      () async {
    final client = _ScriptedClient((req) async =>
        http.StreamedResponse(const Stream.empty(), 500));

    final fetcher = RemoteAudioFetcher(
      clientFactory: () => client,
      idleTimeout: const Duration(seconds: 1),
      maxRetries: 2,
      backoff: (_) => Duration.zero,
    );

    Object? thrown;
    try {
      await fetcher.fetchToFile(
        url: 'https://host/ep2.mp3',
        destPath: '${tmp.path}/audio_2.mp3',
        stopNumber: 2,
        stopName: 'The Accusations Begin',
      );
    } catch (e) {
      thrown = e;
    }
    expect(thrown, isNotNull);
    expect(
      thrown.toString(),
      contains(
          "Audio for stop 2 'The Accusations Begin' could not be downloaded."),
    );
    // No partial file left behind.
    expect(File('${tmp.path}/audio_2.mp3.part').existsSync(), isFalse);
    expect(File('${tmp.path}/audio_2.mp3').existsSync(), isFalse);
  });

  test('reports progress: received/total bytes per stop', () async {
    final client = _ScriptedClient((req) async => _streamed([
          List.filled(1000, 1),
          List.filled(1000, 2),
        ]));

    final events = <RemoteAudioProgress>[];
    final fetcher = RemoteAudioFetcher(
      clientFactory: () => client,
      idleTimeout: const Duration(seconds: 5),
      maxRetries: 0,
    );

    await fetcher.fetchToFile(
      url: 'https://host/ep.mp3',
      destPath: '${tmp.path}/audio_1.mp3',
      stopNumber: 1,
      stopName: 'P',
      onProgress: events.add,
    );

    expect(events, isNotEmpty);
    expect(events.last.receivedBytes, 2000);
    expect(events.last.totalBytes, 2000);
  });

  test('totalSizeBytes sums Content-Length across urls (following redirects)',
      () async {
    final client = _ScriptedClient((req) async {
      final path = req.url.path;
      if (path.contains('redirect')) {
        return http.StreamedResponse(const Stream.empty(), 302,
            headers: {'location': 'https://cdn/final_big.mp3'});
      }
      final size = path.endsWith('big.mp3') ? '131800000' : '76021760';
      return http.StreamedResponse(const Stream.empty(), 200,
          headers: {'content-length': size});
    });

    final fetcher = RemoteAudioFetcher(clientFactory: () => client);
    final total = await fetcher.totalSizeBytes([
      'https://dts.podtrac.com/redirect.mp3/host/big.mp3',
      'https://host/small.mp3',
    ]);
    expect(total, 131800000 + 76021760);
  });

  test('cancel removes the partial .part file and stops', () async {
    final cancel = RemoteAudioCancelToken();
    final client = _ScriptedClient((req) async {
      Stream<List<int>> slow() async* {
        yield List.filled(256, 1);
        await Future.delayed(const Duration(milliseconds: 50));
        cancel.cancel();
        yield List.filled(256, 2);
        await Future.delayed(const Duration(milliseconds: 50));
        yield List.filled(256, 3);
      }

      return http.StreamedResponse(slow(), 200);
    });

    final fetcher = RemoteAudioFetcher(
      clientFactory: () => client,
      idleTimeout: const Duration(seconds: 5),
      maxRetries: 0,
    );

    Object? thrown;
    try {
      await fetcher.fetchToFile(
        url: 'https://host/ep.mp3',
        destPath: '${tmp.path}/audio_1.mp3',
        stopNumber: 1,
        stopName: 'C',
        cancelToken: cancel,
      );
    } catch (e) {
      thrown = e;
    }
    expect(thrown, isA<RemoteAudioCancelled>());
    expect(File('${tmp.path}/audio_1.mp3.part').existsSync(), isFalse);
    expect(File('${tmp.path}/audio_1.mp3').existsSync(), isFalse);
  });
}
