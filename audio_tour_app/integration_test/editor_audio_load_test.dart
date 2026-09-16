import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:path_provider/path_provider.dart';

import 'package:audio_tour_app_dev/services/html_audio_player_service.dart';

import 'mp3_fixture.dart';

/// LOCAL-482 — proves the editor's Original Audio actually loads on a real
/// WKWebView (iOS) / WebView, using the SAME access model as the players.
///
/// This is the on-device proof required by AC #2: a real InAppWebView, a real
/// decodable MP3 written into a real tours directory, loaded through
/// [HtmlAudioPlayerService.loadAudio]. If the sandbox blocked the audio (the
/// old `loadData(baseUrl: file://)` bug), `audio.duration` stays NaN/0 and the
/// duration assertion fails.
///
/// Run (iOS simulator):
///   flutter test integration_test/editor_audio_load_test.dart -d <sim-id>
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  /// Pump a real InAppWebView and return its controller once created.
  Future<InAppWebViewController> pumpWebView(WidgetTester tester) async {
    final completer = Completer<InAppWebViewController>();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            height: 300,
            width: 400,
            child: InAppWebView(
              initialSettings: InAppWebViewSettings(
                mediaPlaybackRequiresUserGesture: false,
                allowsInlineMediaPlayback: true,
                javaScriptEnabled: true,
              ),
              onWebViewCreated: (c) {
                if (!completer.isCompleted) completer.complete(c);
              },
            ),
          ),
        ),
      ),
    );
    // Let the platform view attach.
    for (var i = 0; i < 40 && !completer.isCompleted; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    return completer.future;
  }

  /// Poll the decoded audio state directly from the WebView. Reads
  /// `audio.duration` and `audio.error` via an explicit-return function (the
  /// reliable evaluateJavascript convention across platforms). Returns a map
  /// with `duration` (double) and `error` (int? MediaError code).
  Future<Map<String, dynamic>> waitForDecode(
      InAppWebViewController controller, WidgetTester tester) async {
    Map<String, dynamic> state = {'duration': 0.0, 'error': null};
    for (var i = 0; i < 60; i++) {
      await tester.pump(const Duration(milliseconds: 250));
      final raw = await controller.evaluateJavascript(source: '''
        (function(){
          var a = document.getElementById('audioPlayer');
          if (!a) return JSON.stringify({duration: 0, error: -1, ready: -1});
          return JSON.stringify({
            duration: (a.duration && !isNaN(a.duration)) ? a.duration : 0,
            error: a.error ? a.error.code : null,
            ready: a.readyState,
            currentSrc: a.currentSrc
          });
        })();
      ''');
      if (raw is String && raw.isNotEmpty) {
        state = json.decode(raw) as Map<String, dynamic>;
      }
      final d = (state['duration'] as num?)?.toDouble() ?? 0.0;
      if (d > 0) break;
      if (i % 8 == 7) {
        // ignore: avoid_print
        print('HTML_AUDIO: diag[$i]=$state');
      }
    }
    return state;
  }

  testWidgets(
      'AC#2 — original audio loads on a real WebView via the editor access model',
      (tester) async {
    // Arrange: a real tours directory with a real, decodable MP3, mirroring
    // .../Documents/tours/<tour>/audio_N.mp3.
    final docs = await getApplicationDocumentsDirectory();
    final tourDir = Directory('${docs.path}/tours/local482_it');
    await tourDir.create(recursive: true);
    final audioFile = File('${tourDir.path}/audio_1.mp3');
    await audioFile.writeAsBytes(base64Decode(realMp3Base64), flush: true);
    // ignore: avoid_print
    print('AUDIO_LOAD: Resolving original audio: ${audioFile.path} '
        '(exists: ${audioFile.existsSync()})');

    final controller = await pumpWebView(tester);
    final player = HtmlAudioPlayerService();

    // Act.
    final loaded = await player.loadAudio(audioFile.path, controller);
    expect(loaded, isTrue, reason: 'loadAudio should report success');

    final decode = await waitForDecode(controller, tester);
    final duration = (decode['duration'] as num?)?.toDouble() ?? 0.0;
    final mediaError = decode['error'];
    // ignore: avoid_print
    print('HTML_AUDIO: decoded duration=${duration}s error=$mediaError '
        'for ${audioFile.path}');

    // Assert: WKWebView actually read + decoded the file. If the sandbox had
    // blocked it (the old file:// baseURL bug), duration stays 0 and/or
    // audio.error is set (MEDIA_ERR_SRC_NOT_SUPPORTED / NETWORK).
    expect(mediaError, isNull,
        reason: 'audio.error must be null — WKWebView could read the file');
    expect(duration, greaterThan(0),
        reason: 'audio.duration must be > 0 — WKWebView decoded the audio');

    // AC#5: scratch HTML written beside the audio, then removed on dispose.
    final scratch =
        File('${tourDir.path}/${EditorAudioAccessModel.scratchFileName}');
    expect(scratch.existsSync(), isTrue,
        reason: 'scratch player HTML should exist while the editor is open');

    await player.dispose();
    expect(scratch.existsSync(), isFalse,
        reason: 'AC#5: scratch HTML must be gone after the editor closes');

    // No stray *.mp3 was invented and the scratch file is hidden.
    final mp3s = tourDir
        .listSync()
        .whereType<File>()
        .where((f) => f.path.endsWith('.mp3'))
        .toList();
    expect(mp3s.length, equals(1),
        reason: 'only the real audio_1.mp3 — scratch file is not a .mp3');

    await tourDir.delete(recursive: true);
  });

  testWidgets('AC#4 — a genuinely missing file still fails clearly',
      (tester) async {
    final docs = await getApplicationDocumentsDirectory();
    final missing = '${docs.path}/tours/local482_missing/audio_1.mp3';
    // ignore: avoid_print
    print('AUDIO_LOAD: Resolving original audio: $missing '
        '(exists: ${File(missing).existsSync()})');

    final controller = await pumpWebView(tester);
    final player = HtmlAudioPlayerService();

    final loaded = await player.loadAudio(missing, controller);

    // Do NOT paper over the error path — a missing file must return false.
    expect(loaded, isFalse,
        reason: 'AC#4: missing audio must report failure, not silently pass');
  });
}
