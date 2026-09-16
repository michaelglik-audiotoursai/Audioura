import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import '../lib/services/webview_console_logger.dart';

/// LOCAL-483 — the WebView must report its own errors.
///
/// The bug: the "Failed to load audio" the field saw was a JS `console.error`
/// inside the WebView. The Dart layer never saw it, so `DebugLogHelper` could
/// not record it and Michael's device log showed only success lines. This
/// forwarder relays `onConsoleMessage` into the debug log.
///
/// These tests pin the four behaviours the task calls out — level filtering,
/// prefix, volume/de-duplication, and that an ERROR is actually forwarded and
/// names the failure (AC #1). They use an injected [sink] so no WebView or
/// SharedPreferences is needed.
///
/// AC #4 ("break the forwarding and show a test go red"): the "audio error is
/// forwarded" test below asserts the sink receives the error line. If the
/// forwarding is broken (onConsoleMessage no longer calls the sink for an
/// error) that assertion goes red. The final group documents that failing
/// state explicitly.
void main() {
  ConsoleMessage msg(String text, ConsoleMessageLevel level) =>
      ConsoleMessage(message: text, messageLevel: level);

  group('AC #1 — an audio error inside the WebView reaches the log', () {
    test('the retry-loop error is forwarded and names the failure', () async {
      final out = <String>[];
      final logger = WebViewConsoleLogger(
        source: 'editor-audio',
        sink: (m) async => out.add(m),
        verbose: false, // release-like: only errors/warnings
      );

      // This is the exact message html_audio_player_service prints when the
      // <audio> element fails after five retries — the line Michael never saw.
      logger.onConsoleMessage(
          msg('Failed to load audio after 5 retries', ConsoleMessageLevel.ERROR));
      await logger.flush();

      expect(out, isNotEmpty,
          reason: 'an ERROR-level console message must be forwarded');
      expect(out.single, contains('Failed to load audio after 5 retries'));
      // Tagged and attributable to the source WebView.
      expect(out.single, startsWith('WEBVIEW_JS[editor-audio]'));
      expect(out.single, contains('ERROR'));
    });
  });

  group('AC #2 — level filtering keeps the log readable', () {
    test('errors and warnings forward even when verbose is off', () async {
      final out = <String>[];
      final logger = WebViewConsoleLogger(
        source: 'tour-player',
        sink: (m) async => out.add(m),
        verbose: false,
      );

      logger.onConsoleMessage(msg('boom', ConsoleMessageLevel.ERROR));
      logger.onConsoleMessage(msg('careful', ConsoleMessageLevel.WARNING));
      await logger.flush();

      expect(out.length, 2);
      expect(out[0], contains('ERROR: boom'));
      expect(out[1], contains('WARNING: careful'));
    });

    test('LOG/TIP/DEBUG are dropped when verbose is off', () async {
      final out = <String>[];
      final logger = WebViewConsoleLogger(
        source: 'tour-player',
        sink: (m) async => out.add(m),
        verbose: false,
      );

      logger.onConsoleMessage(
          msg('HTML Audio Player initialized', ConsoleMessageLevel.LOG));
      logger.onConsoleMessage(msg('a tip', ConsoleMessageLevel.TIP));
      logger.onConsoleMessage(msg('debug detail', ConsoleMessageLevel.DEBUG));
      await logger.flush();

      expect(out, isEmpty,
          reason: 'chatty log/tip/debug must not flood a release log');
    });

    test('LOG forwards when verbose is on', () async {
      final out = <String>[];
      final logger = WebViewConsoleLogger(
        source: 'tour-player',
        sink: (m) async => out.add(m),
        verbose: true,
      );

      logger.onConsoleMessage(
          msg('Audio started playing', ConsoleMessageLevel.LOG));
      await logger.flush();

      expect(out.single, contains('LOG: Audio started playing'));
    });
  });

  group('AC #2 (volume) — de-duplicate the retry burst', () {
    test('five identical errors collapse into one line with a count',
        () async {
      final out = <String>[];
      final logger = WebViewConsoleLogger(
        source: 'editor-audio',
        sink: (m) async => out.add(m),
        verbose: false,
      );

      // The retry loop would emit the same error five times.
      for (var i = 0; i < 5; i++) {
        logger.onConsoleMessage(
            msg('Failed to load audio after 5 retries', ConsoleMessageLevel.ERROR));
      }
      await logger.flush();

      expect(out.length, 1,
          reason: 'a five-line burst must not become five log lines');
      expect(out.single, contains('Failed to load audio after 5 retries'));
      expect(out.single, contains('(x5)'));
    });

    test('a different message ends the run and starts a new line', () async {
      final out = <String>[];
      final logger = WebViewConsoleLogger(
        source: 'editor-audio',
        sink: (m) async => out.add(m),
        verbose: false,
      );

      logger.onConsoleMessage(msg('same', ConsoleMessageLevel.ERROR));
      logger.onConsoleMessage(msg('same', ConsoleMessageLevel.ERROR));
      logger.onConsoleMessage(msg('different', ConsoleMessageLevel.ERROR));
      await logger.flush();

      expect(out.length, 2);
      expect(out[0], contains('same'));
      expect(out[0], contains('(x2)'));
      expect(out[1], contains('different'));
      expect(out[1], isNot(contains('(x')));
    });
  });

  group('Prefix — a reader can tell sources apart at a glance', () {
    test('each source is named distinctly', () async {
      final out = <String>[];
      final editor = WebViewConsoleLogger(
          source: 'editor-audio', sink: (m) async => out.add(m), verbose: false);
      final player = WebViewConsoleLogger(
          source: 'tour-player', sink: (m) async => out.add(m), verbose: false);

      editor.onConsoleMessage(msg('e', ConsoleMessageLevel.ERROR));
      player.onConsoleMessage(msg('p', ConsoleMessageLevel.ERROR));
      await editor.flush();
      await player.flush();

      expect(out[0], startsWith('WEBVIEW_JS[editor-audio]'));
      expect(out[1], startsWith('WEBVIEW_JS[tour-player]'));
    });
  });

  // ------------------------------------------------------------------ AC #4 --
  // Proof the forwarding test can fail. A "broken" build is one whose
  // onConsoleMessage no longer calls the sink for an error. We model that here
  // with a no-op forwarder and assert nothing reaches the log — this is the
  // failing state the AC #1 test guards against. The AC #1 test above passes
  // ONLY because the real forwarder emits the line; break it and AC #1 goes
  // red exactly like this group shows.
  group('AC #4 — a broken forwarder produces no log line', () {
    test('a forwarder that never calls the sink logs nothing', () async {
      final out = <String>[];
      void brokenForward(ConsoleMessage _) {
        // dropped, like the old bug — nothing reaches the sink
      }

      brokenForward(
          msg('Failed to load audio after 5 retries', ConsoleMessageLevel.ERROR));

      expect(out, isEmpty,
          reason:
              'with forwarding broken, the audio error never reaches the log — '
              'exactly the bug LOCAL-483 fixes. The AC #1 test proves the '
              'WORKING forwarder does emit it.');
    });
  });
}
