import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/html_audio_player_service.dart';

/// LOCAL-482 — the stop editor's Original Audio failed to load on iOS.
///
/// Root cause: the editor built the player with `loadData(baseUrl: file://)`
/// and a `<source src="file://$absolutePath">`. On iOS `loadData` maps to
/// WKWebView's `loadHTMLString(_:baseURL:)`, which grants read access ONLY to
/// the baseURL's directory. A bare `file://` root granted access to nothing,
/// so the `<source>` into `.../tours/<tour>/audio_N.mp3` was sandbox-blocked
/// and the field showed "Failed to load audio".
///
/// The fix mirrors the Listen tab / news player, which work: load an HTML page
/// BY URL from INSIDE the audio's own directory, with a RELATIVE `<source>` so
/// it resolves within the granted scope.
///
/// [EditorAudioAccessModel] is the pure value object that encodes that model.
/// These tests pin it. Restoring the old `file://` baseURL model — an absolute
/// `file://` src, or a load URL whose directory is not the audio's directory —
/// breaks these expectations and goes red (AC #6).
///
/// LOCAL-3482 (build-25 re-report): the load-by-URL layout was not enough on
/// iOS — loadUrl needs an `allowingReadAccessTo` scope or it falls back to a
/// bare load that reads nothing. The added test pins [readAccessUrl] to the
/// audio directory; dropping the scope goes red.
void main() {
  const audioPath =
      '/var/mobile/Containers/Data/Application/UUID/Documents/tours/paris_42/audio_3.mp3';
  const audioDir =
      '/var/mobile/Containers/Data/Application/UUID/Documents/tours/paris_42';

  group('EditorAudioAccessModel — WKWebView access model (AC #6)', () {
    final model = EditorAudioAccessModel.forAudioPath(audioPath);

    test('the <source> src is RELATIVE — never an absolute file:// URL', () {
      // The whole bug: an absolute file:// src escapes the dir-scoped grant.
      // If someone restores `src="file://$audioPath"`, relativeSrc would carry
      // the scheme / a slash and this goes red.
      expect(model.relativeSrc, equals('audio_3.mp3'));
      expect(model.relativeSrc, isNot(contains('file://')));
      expect(model.relativeSrc, isNot(contains('/')));
    });

    test('the scratch HTML is written INTO the audio\'s own directory', () {
      // The baseURL's directory is the read-access scope. It MUST equal the
      // directory the audio lives in, or the audio is out of scope again.
      expect(model.directory, equals(audioDir));
      expect(model.scratchHtmlPath, startsWith('$audioDir/'));
      expect(
        model.scratchHtmlPath,
        equals('$audioDir/${EditorAudioAccessModel.scratchFileName}'),
      );
    });

    test('the load URL is the scratch file BY URL, scoped to the audio dir', () {
      // Mirrors news_player_screen.dart:75 `file://$dir/index.html`. Restoring
      // `WebUri('file://')` (the bare root) would make the URL directory NOT
      // equal the audio directory and this goes red.
      expect(model.loadUrl, equals('file://${model.scratchHtmlPath}'));
      expect(model.loadUrl, startsWith('file://$audioDir/'));
      // The bare-root regression that caused the bug: reject it explicitly.
      expect(model.loadUrl, isNot(equals('file://')));

      final lastSlash = model.loadUrl.lastIndexOf('/');
      final urlDir = model.loadUrl.substring('file://'.length, lastSlash);
      expect(urlDir, equals(audioDir),
          reason: 'load URL directory must equal the audio directory so '
              'WKWebView grants read access to the audio beside it');
    });

    test('the scratch file is hidden so tour parsers ignore it (AC #5)', () {
      // Tour parsers count *.mp3 (tour_generator_screen.dart:563,
      // tour_translation_helper.dart:166). A dot-prefixed, non-.mp3 name is
      // never counted and stays out of re-zips.
      expect(EditorAudioAccessModel.scratchFileName, startsWith('.'));
      expect(EditorAudioAccessModel.scratchFileName, endsWith('.html'));
      expect(EditorAudioAccessModel.scratchFileName, isNot(endsWith('.mp3')));
    });

    test('audioPath is preserved unchanged for logging/resolution', () {
      expect(model.audioPath, equals(audioPath));
    });

    // LOCAL-3482 (build-25 re-report) — the load-by-URL model above is
    // necessary but not sufficient on iOS. flutter_inappwebview's loadUrl only
    // grants directory read access when handed an `allowingReadAccessTo` URL;
    // without it, it falls through to a bare WKWebView.load(URLRequest) that
    // reads nothing beyond the HTML file, so the relative <source> stays
    // sandbox-blocked (InAppWebView.swift:925-932). readAccessUrl is the
    // audio directory the service passes to loadUrl(allowingReadAccessTo:).
    test('readAccessUrl is the audio directory as a file:// URL (AC #6)', () {
      // This is THE field the build-25 re-report turned on. If someone drops
      // the read-access scope (reverts to loadUrl with no allowingReadAccessTo,
      // or points it somewhere other than the audio dir), this goes red.
      expect(model.readAccessUrl, equals('file://$audioDir'));

      // The granted scope MUST be a file:// URL — WKWebView ignores a non-file
      // allowingReadAccessTo (InAppWebView.swift:928 requires .scheme=="file").
      expect(model.readAccessUrl, startsWith('file://'));

      // And it MUST be the directory the audio lives in, not the scratch file
      // and not the bare root. Strip the scheme and compare to the audio dir.
      final scopePath = model.readAccessUrl.substring('file://'.length);
      expect(scopePath, equals(audioDir));
      expect(scopePath, isNot(equals('/')),
          reason: 'a bare-root scope is the LOCAL-482 regression, not a fix');

      // The loaded HTML must sit INSIDE the granted read-access scope, or the
      // grant does not cover it.
      expect(model.loadUrl, startsWith('${model.readAccessUrl}/'));
    });
  });
}
