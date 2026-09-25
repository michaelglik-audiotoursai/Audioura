import 'package:flutter/foundation.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

import '../screens/debug_log_viewer_screen.dart';

/// LOCAL-483 — forward `InAppWebView`'s `onConsoleMessage` into the app's
/// persisted debug log.
///
/// Why this exists (see task LOCAL-483 / the LOCAL-482 audio bug):
/// the "Failed to load audio" the field saw was a JavaScript `console.error`
/// inside the WebView (`html_audio_player_service` retry loop). The Dart layer
/// never saw it, so `DebugLogHelper` could not record it and the device log
/// showed only success lines. This forwarder is the bridge: every WebView the
/// app owns routes its console output back to `DebugLogHelper` so a future
/// reader sees on the log exactly what the user saw on screen.
///
/// Design decisions (stated in SUBMISSION_LOCAL-483.md):
///
/// * **Level filtering.** ERROR and WARNING are forwarded unconditionally —
///   they are the diagnostic signal, and losing them was the whole bug. LOG /
///   TIP / DEBUG are gated behind [kDebugMode]: the audio JS emits a
///   `console.log` per retry plus dozens of lifecycle logs per open, which in
///   release would be pure noise that buries the one ERROR line a reader needs.
///   A log that is 90% noise is unreadable, which is the failure mode on the
///   other side, so verbose levels ship only in debug builds.
///
/// * **Prefix.** Every line is tagged `WEBVIEW_JS[<source>] <LEVEL>: <msg>` so
///   a reader can tell an editor error from a player error at a glance.
///
/// * **Volume / de-duplication.** The retry loop alone emits five near-identical
///   `console.error('Failed to load audio after 5 retries')`-class lines. This
///   forwarder collapses *consecutive* identical (same level + message) console
///   messages from one WebView into a single line, appending `(xN)` when the run
///   ends or the widget is disposed, so one failure is one log line, not five.
///
/// * **No secrets.** Forwarding goes through [DebugLogHelper.addDebugLog], which
///   runs every message through `LogRedactor` — so a console line containing
///   `token=...` / `password=...` / `key=...` is scrubbed at the sink exactly
///   like every other log. This forwarder therefore adds no new secret exposure;
///   it does not log headers or synthesise query strings, it only relays what
///   the page already printed, redacted on the way in.
class WebViewConsoleLogger {
  /// A short, human-readable name for the WebView this logger serves, e.g.
  /// `editor-audio`, `editor-recorder`, `tour-player`, `news-player`. Shown in
  /// the log prefix so errors are attributable to a source at a glance.
  final String source;

  /// The sink each forwarded line is written to. Defaults to the app's
  /// redacting debug log. Injectable so tests can capture output without a
  /// WebView or SharedPreferences.
  final Future<void> Function(String message) sink;

  /// Whether verbose (LOG / TIP / DEBUG) console levels are forwarded. Defaults
  /// to [kDebugMode] so release builds keep only the error/warning signal.
  final bool verbose;

  // Consecutive-duplicate collapse state. A "run" is a maximal sequence of
  // identical (level, message) pairs. We hold the pending line and its count
  // and only emit when the run breaks (a different message arrives) or on
  // [flush] (widget dispose).
  String? _pendingLine;
  int _pendingCount = 0;

  WebViewConsoleLogger({
    required this.source,
    Future<void> Function(String message)? sink,
    bool? verbose,
  })  : sink = sink ?? DebugLogHelper.addDebugLog,
        verbose = verbose ?? kDebugMode;

  /// Whether a message at [level] should be forwarded at all. ERROR and WARNING
  /// always pass; everything else only in [verbose] mode.
  bool _shouldForward(ConsoleMessageLevel level) {
    if (level == ConsoleMessageLevel.ERROR ||
        level == ConsoleMessageLevel.WARNING) {
      return true;
    }
    return verbose;
  }

  static String _levelName(ConsoleMessageLevel level) {
    if (level == ConsoleMessageLevel.ERROR) return 'ERROR';
    if (level == ConsoleMessageLevel.WARNING) return 'WARNING';
    if (level == ConsoleMessageLevel.DEBUG) return 'DEBUG';
    if (level == ConsoleMessageLevel.TIP) return 'TIP';
    return 'LOG';
  }

  /// The tag every line carries, so a reader (and a test) can grep one source.
  String get _tag => 'WEBVIEW_JS[$source]';

  /// Handle one console message. This is what the `onConsoleMessage` callback
  /// calls. Returns the [Future] of any sink write it triggered so tests (and
  /// callers that care) can await it; returns `null` when the message was
  /// filtered out or merely coalesced into the pending run.
  Future<void>? onConsoleMessage(ConsoleMessage consoleMessage) {
    final level = consoleMessage.messageLevel;
    if (!_shouldForward(level)) {
      return null;
    }

    final line = '$_tag ${_levelName(level)}: ${consoleMessage.message}';

    // Same as the line we are currently holding? Just bump the count; do not
    // emit yet. This is what collapses the five-line retry burst into one.
    if (line == _pendingLine) {
      _pendingCount++;
      return null;
    }

    // A different line arrived: emit whatever run we were holding, then start
    // holding this new one.
    final emit = _emitPending();
    _pendingLine = line;
    _pendingCount = 1;
    return emit;
  }

  /// Emit the currently-held run (if any) and clear the pending state. Returns
  /// the sink write [Future], or `null` if nothing was pending.
  Future<void>? _emitPending() {
    final pending = _pendingLine;
    if (pending == null) return null;
    final count = _pendingCount;
    _pendingLine = null;
    _pendingCount = 0;
    final suffix = count > 1 ? ' (x$count)' : '';
    return sink('$pending$suffix');
  }

  /// Flush any held run to the sink. Call from the owning widget's `dispose()`
  /// so the last run is not lost when the WebView goes away.
  Future<void> flush() async {
    final f = _emitPending();
    if (f != null) await f;
  }
}
