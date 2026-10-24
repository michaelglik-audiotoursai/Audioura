// [LOCAL-759 A] Streaming fetch of ONE remote (organiser-hosted) audio episode
// to a file on the device.
//
// Why this exists (Michael's Salem tour, 2026-10-24): the old
// _fetchRemoteAudioDevice did `http.get(url).timeout(120 s)` and held the whole
// episode in `resp.bodyBytes`. A real podcast episode is 70–130 MB; the 120-s
// limit was for the ENTIRE transfer (so a slow 131 MB download never finished),
// there was no retry, and a failure surfaced as a generic "The download failed."
//
// This fetcher fixes all of that for the DEVICE path (dart:io):
//   * STREAMS the body to `<dest>.part` via http.Client().send → a file sink,
//     then renames to <dest> on completion. The episode is never held in memory.
//   * Follows the podtrac/podbean 302 redirect chain itself (we issue the next
//     GET on a 3xx Location, up to a sane hop limit).
//   * Idle timeout: the transfer fails only when NO DATA arrives for
//     [idleTimeout] (default 30 s) — NOT a cap on the total transfer time, so a
//     large-but-steady download completes.
//   * Retries a failing stop [maxRetries] times with backoff.
//   * Reports progress (received / total bytes) for the download sheet.
//   * Cancellable (removes the partial .part file).
//   * On final failure throws [RemoteAudioError] carrying the EXACT named
//     message "Audio for stop N '<name>' could not be downloaded." so the UI can
//     show which stop failed (D754) instead of a generic message.
//
// Pure of widgets/BuildContext and of SharedPreferences: the http.Client is
// injected (clientFactory) and the destination is a plain path, so the whole
// thing is unit-tested with a fake client + a temp dir (no network, no plugins).

import 'dart:async';
import 'dart:io';

import 'package:http/http.dart' as http;

/// A progress tick for one stop's download.
class RemoteAudioProgress {
  final int stopNumber;
  final int receivedBytes;

  /// The total bytes expected (Content-Length), or null when the server did
  /// not send one. The UI shows "a / b MB" when total is known, else "a MB".
  final int? totalBytes;

  const RemoteAudioProgress({
    required this.stopNumber,
    required this.receivedBytes,
    this.totalBytes,
  });
}

/// A cancellation handle shared by the caller and the fetcher. Calling
/// [cancel] makes the in-flight (or next) download stop and clean up its
/// partial file, throwing [RemoteAudioCancelled].
class RemoteAudioCancelToken {
  bool _cancelled = false;
  bool get isCancelled => _cancelled;
  void cancel() => _cancelled = true;
}

/// Thrown when a download is cancelled via a [RemoteAudioCancelToken].
class RemoteAudioCancelled implements Exception {
  @override
  String toString() => 'RemoteAudioCancelled';
}

/// Thrown after all retries fail. [message] is the EXACT user-facing wording
/// that must reach the SnackBar; [stopNumber]/[stopName] identify the stop.
class RemoteAudioError implements Exception {
  final int stopNumber;
  final String stopName;
  final String message;
  final Object? cause;

  const RemoteAudioError({
    required this.stopNumber,
    required this.stopName,
    required this.message,
    this.cause,
  });

  @override
  String toString() => message;
}

/// The user-facing message for a stop that could not be downloaded (D754). ONE
/// source of truth so the fetcher, the download service and the tests agree.
/// Names the stop when a non-empty [stopName] is given.
String remoteAudioStopFailureMessage(int stopNumber, String stopName) {
  final name = stopName.trim();
  if (name.isEmpty) {
    return 'Audio for stop $stopNumber could not be downloaded.';
  }
  return "Audio for stop $stopNumber '$name' could not be downloaded.";
}

/// [LOCAL-759 A3] The download-sheet / SnackBar line while a tour's audio
/// downloads: "Downloading audio — stop X of Y · a / b MB" (or "· a MB" when
/// the total for the current stop is unknown). PURE so the wording is tested
/// and comes from one place.
String downloadingAudioLabel({
  required int stopIndex, // 1-based: the stop currently downloading
  required int stopCount,
  required int receivedBytes,
  int? totalBytes,
}) {
  final a = _mb(receivedBytes);
  final size = (totalBytes != null && totalBytes > 0)
      ? '$a / ${_mb(totalBytes)} MB'
      : '$a MB';
  return 'Downloading audio — stop $stopIndex of $stopCount · $size';
}

String _mb(int bytes) {
  final mb = bytes / (1024 * 1024);
  return mb >= 10 ? mb.toStringAsFixed(0) : mb.toStringAsFixed(1);
}


class RemoteAudioFetcher {
  RemoteAudioFetcher({
    http.Client Function()? clientFactory,
    this.idleTimeout = const Duration(seconds: 30),
    this.maxRetries = 2,
    Duration Function(int attempt)? backoff,
    this.maxRedirects = 5,
  })  : _clientFactory = clientFactory ?? (() => http.Client()),
        _backoff = backoff ?? _defaultBackoff;

  final http.Client Function() _clientFactory;

  /// No data for this long → the attempt fails (an IDLE timeout, not a total
  /// cap). Default 30 s (D754B / LOCAL-759 A1).
  final Duration idleTimeout;

  /// How many times a failing stop is retried after the first attempt.
  final int maxRetries;

  /// Max 3xx hops to follow (podtrac → podbean is 2; default 5 is generous).
  final int maxRedirects;

  final Duration Function(int attempt) _backoff;

  static Duration _defaultBackoff(int attempt) =>
      Duration(milliseconds: 500 * (1 << (attempt - 1))); // 0.5s, 1s, 2s…

  /// Stream [url] into [destPath], retrying on failure. On success [destPath]
  /// holds the complete file (written via a `.part` sibling then renamed). On
  /// final failure throws [RemoteAudioError] with the named message; on cancel
  /// throws [RemoteAudioCancelled]. Both leave NO partial file.
  Future<void> fetchToFile({
    required String url,
    required String destPath,
    required int stopNumber,
    required String stopName,
    void Function(RemoteAudioProgress)? onProgress,
    RemoteAudioCancelToken? cancelToken,
  }) async {
    Object? lastError;
    for (var attempt = 0; attempt <= maxRetries; attempt++) {
      if (cancelToken?.isCancelled == true) {
        await _deletePart(destPath);
        throw RemoteAudioCancelled();
      }
      if (attempt > 0) {
        await Future.delayed(_backoff(attempt));
      }
      try {
        await _attempt(
          url: url,
          destPath: destPath,
          stopNumber: stopNumber,
          onProgress: onProgress,
          cancelToken: cancelToken,
        );
        return; // success
      } on RemoteAudioCancelled {
        await _deletePart(destPath);
        rethrow;
      } catch (e) {
        lastError = e;
        await _deletePart(destPath);
        // loop → retry
      }
    }
    throw RemoteAudioError(
      stopNumber: stopNumber,
      stopName: stopName,
      message: remoteAudioStopFailureMessage(stopNumber, stopName),
      cause: lastError,
    );
  }

  /// One streaming attempt. Throws on any failure (the caller retries).
  Future<void> _attempt({
    required String url,
    required String destPath,
    required int stopNumber,
    void Function(RemoteAudioProgress)? onProgress,
    RemoteAudioCancelToken? cancelToken,
  }) async {
    final client = _clientFactory();
    final partPath = '$destPath.part';
    IOSink? sink;
    StreamSubscription<List<int>>? sub;
    var closedClient = false;

    void closeClient() {
      if (!closedClient) {
        closedClient = true;
        client.close();
      }
    }

    try {
      final response = await _sendFollowingRedirects(client, url);
      if (response.statusCode != 200) {
        throw HttpException('HTTP ${response.statusCode}');
      }

      final total = response.contentLength;
      final partFile = File(partPath);
      await partFile.parent.create(recursive: true);
      sink = partFile.openWrite();

      var received = 0;
      final completer = Completer<void>();
      Timer? idleTimer;

      void resetIdle() {
        idleTimer?.cancel();
        idleTimer = Timer(idleTimeout, () {
          if (!completer.isCompleted) {
            completer.completeError(
                TimeoutException('no data for ${idleTimeout.inSeconds}s'));
          }
        });
      }

      resetIdle();
      sub = response.stream.listen(
        (chunk) {
          if (cancelToken?.isCancelled == true) {
            if (!completer.isCompleted) {
              completer.completeError(RemoteAudioCancelled());
            }
            return;
          }
          received += chunk.length;
          sink!.add(chunk);
          resetIdle();
          onProgress?.call(RemoteAudioProgress(
            stopNumber: stopNumber,
            receivedBytes: received,
            totalBytes: (total != null && total > 0) ? total : null,
          ));
        },
        onError: (e, st) {
          if (!completer.isCompleted) completer.completeError(e);
        },
        onDone: () {
          if (!completer.isCompleted) completer.complete();
        },
        cancelOnError: true,
      );

      try {
        await completer.future;
      } finally {
        idleTimer?.cancel();
      }

      await sub.cancel();
      sub = null;
      await sink.flush();
      await sink.close();
      sink = null;
      closeClient();

      if (received == 0) {
        throw const HttpException('empty body');
      }
      // Rename the completed .part into place.
      await File(partPath).rename(destPath);
    } catch (e) {
      // Tear down the stream + sink on any failure so the .part can be removed.
      try {
        await sub?.cancel();
      } catch (_) {}
      try {
        await sink?.close();
      } catch (_) {}
      closeClient();
      rethrow;
    }
  }

  /// Issue a GET and follow 3xx Location headers up to [maxRedirects]. We follow
  /// redirects by hand so a streamed Client.send (which does NOT auto-follow on
  /// every platform) still reaches the final 200 (podtrac 302 → podbean 302 →
  /// 200), matching what the task observed.
  Future<http.StreamedResponse> _sendFollowingRedirects(
      http.Client client, String url) async {
    var current = url;
    for (var hop = 0; hop <= maxRedirects; hop++) {
      final request = http.Request('GET', Uri.parse(current))
        ..followRedirects = false;
      final response = await client.send(request);
      final code = response.statusCode;
      if (code == 301 || code == 302 || code == 303 || code == 307 || code == 308) {
        final location = response.headers['location'];
        // Drain the (usually empty) redirect body so the socket is freed.
        await response.stream.drain<void>();
        if (location == null || location.isEmpty) {
          throw HttpException('redirect $code with no Location');
        }
        current = Uri.parse(current).resolve(location).toString();
        continue;
      }
      return response;
    }
    throw const HttpException('too many redirects');
  }

  /// [LOCAL-759 A4] Sum the Content-Length of every [urls] via a HEAD (following
  /// redirects), so the UI can show "This tour is 285 MB. Download on Wi-Fi?"
  /// before pulling anything. Returns the summed bytes; a URL whose size cannot
  /// be read contributes 0 (the total is then a lower bound — never an error).
  Future<int> totalSizeBytes(Iterable<String> urls) async {
    final client = _clientFactory();
    var total = 0;
    try {
      for (final url in urls) {
        try {
          var current = url;
          for (var hop = 0; hop <= maxRedirects; hop++) {
            final req = http.Request('HEAD', Uri.parse(current))
              ..followRedirects = false;
            final resp = await client.send(req);
            await resp.stream.drain<void>();
            final code = resp.statusCode;
            if (code == 301 ||
                code == 302 ||
                code == 303 ||
                code == 307 ||
                code == 308) {
              final loc = resp.headers['location'];
              if (loc == null || loc.isEmpty) break;
              current = Uri.parse(current).resolve(loc).toString();
              continue;
            }
            final len = int.tryParse(resp.headers['content-length'] ?? '');
            if (len != null && len > 0) total += len;
            break;
          }
        } catch (_) {
          // Unknown size for this url → contributes 0.
        }
      }
    } finally {
      client.close();
    }
    return total;
  }

  Future<void> _deletePart(String destPath) async {
    try {
      final part = File('$destPath.part');
      if (await part.exists()) await part.delete();
    } catch (_) {}
  }
}
