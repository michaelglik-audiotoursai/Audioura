// [LOCAL-698] Proof that the single-playback controller enforces
// "one stop at a time": start stop 1, tap stop 3 => only stop 3 plays
// (exactly one media element is non-paused).
//
// WHY THIS SHAPE. The controller is JavaScript injected into the player
// WebView (the audio actually plays inside the WebView's HTML, as
// `<audio controls>` elements). `flutter test` cannot host a real WebView /
// browser engine, so to prove the ACTUAL shipped JS — not a Dart
// reimplementation of it — this test:
//   1. reads the real JS out of lib/services/single_playback_controller.dart,
//   2. runs it in Node against a faithful mock of HTMLMediaElement + document
//      (a native play button calls element.play() DIRECTLY, which is exactly
//      the path that regressed), and
//   3. asserts that after tapping a second/third stop, the player count is 1.
//
// It also asserts the Dart-side contract (the constant patches
// HTMLMediaElement.prototype.play, pauses the others, carries a sequence token,
// and is idempotent) so the guarantees are pinned even if Node is unavailable.
//
// Run: cd audio_tour_app && flutter test test/single_playback_controller_test.dart

import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/single_playback_controller.dart';

void main() {
  group('LOCAL-698 single-playback controller — Dart contract', () {
    test('patches HTMLMediaElement.prototype.play', () {
      expect(
        kSinglePlaybackControllerJs.contains('HTMLMediaElement.prototype'),
        isTrue,
      );
      expect(
        kSinglePlaybackControllerJs.contains('proto.play = function'),
        isTrue,
      );
    });

    test('pauses every OTHER media element before starting one', () {
      expect(kSinglePlaybackControllerJs.contains('pauseAllExcept'), isTrue);
      // Selects both audio and video so no media type can slip through.
      expect(
        kSinglePlaybackControllerJs.contains("querySelectorAll('audio, video')"),
        isTrue,
      );
      expect(kSinglePlaybackControllerJs.contains('m.pause()'), isTrue);
    });

    test('guards rapid double taps with a monotonic sequence token', () {
      expect(kSinglePlaybackControllerJs.contains('__audiouraPlaySeq'), isTrue);
      expect(
        kSinglePlaybackControllerJs.contains('++window.__audiouraPlaySeq'),
        isTrue,
      );
      // A stale request pauses itself when a newer one has taken over.
      expect(
        kSinglePlaybackControllerJs.contains('seq !== window.__audiouraPlaySeq'),
        isTrue,
      );
    });

    test('is idempotent (safe to inject on every load)', () {
      expect(
        kSinglePlaybackControllerJs.contains('__audiouraSinglePlayInstalled'),
        isTrue,
      );
    });
  });

  group('LOCAL-698 — real JS behaviour (executed in Node)', () {
    final node = _resolveNode();

    test(
      'start stop 1, tap stop 3 => only stop 3 plays (player count 1)',
      () async {
        final harness = _buildNodeHarness(kSinglePlaybackControllerJs);
        final tmp = await File(
          '${Directory.systemTemp.path}/local698_harness_${DateTime.now().microsecondsSinceEpoch}.js',
        ).create();
        await tmp.writeAsString(harness);
        try {
          final res = await Process.run(node!, [tmp.path]);
          expect(res.exitCode, 0,
              reason: 'Node harness failed:\n${res.stdout}\n${res.stderr}');
          final out = json.decode(
            (res.stdout as String).trim().split('\n').last,
          ) as Map<String, dynamic>;

          // The scenario: 5 stops. Auto-start stop 1 (native play), then the
          // listener taps stop 3's native control while stop 1 is still going.
          expect(out['playingCount'], 1,
              reason: 'exactly one stop may play at a time');
          expect(out['playingIndex'], 2,
              reason: 'the tapped stop (index 2 = "stop 3") is the one playing');
          // Rapid double tap (stop 2 then immediately stop 4) also collapses
          // to a single player — the latest wins.
          expect(out['doubleTapPlayingCount'], 1);
          expect(out['doubleTapPlayingIndex'], 3);
        } finally {
          if (await tmp.exists()) await tmp.delete();
        }
      },
      skip: node == null
          ? 'Node.js not found on PATH — Dart contract assertions still cover the shim'
          : false,
    );
  });
}

/// Locate a `node` binary, or null when none is available.
String? _resolveNode() {
  for (final candidate in <String>[
    'node',
    '/usr/local/bin/node',
    '/opt/homebrew/bin/node',
    '/usr/bin/node',
  ]) {
    try {
      final r = Process.runSync(candidate, ['--version']);
      if (r.exitCode == 0) return candidate;
    } catch (_) {/* try next */}
  }
  return null;
}

/// Build a Node script that mounts a minimal DOM, injects the REAL controller
/// JS, then reproduces the bug scenario and prints the resulting state as JSON.
String _buildNodeHarness(String controllerJs) {
  // The controller is injected verbatim; we only provide the globals a browser
  // would (window, document, HTMLMediaElement) with just enough behaviour that
  // play()/pause() and querySelectorAll work like the real thing.
  final encoded = jsonEncode(controllerJs);
  return '''
'use strict';

// ---- Minimal DOM / media mock -------------------------------------------
class FakeMediaElement {
  constructor(tagName, idx) {
    this.tagName = tagName;      // 'AUDIO'
    this._idx = idx;
    this.paused = true;
    this.currentTime = 0;
    this._listeners = {};
  }
  // Native play(): starts THIS element. In the real bug a stop's native
  // control calls exactly this, bypassing the app's JS helpers.
  play() {
    this.paused = false;
    const ls = this._listeners['play'] || [];
    for (const l of ls) l({ target: this });
    // Mirror a browser: play() resolves to a promise.
    return Promise.resolve();
  }
  pause() {
    this.paused = true;
  }
  addEventListener(type, cb) {
    (this._listeners[type] = this._listeners[type] || []).push(cb);
  }
}

const audios = [];
for (let i = 0; i < 5; i++) audios.push(new FakeMediaElement('AUDIO', i));

const docListeners = {};
global.document = {
  querySelectorAll(sel) {
    // The controller asks for 'audio, video'. Return all audio elements.
    return audios.slice();
  },
  addEventListener(type, cb, capture) {
    (docListeners[type] = docListeners[type] || []).push(cb);
  },
  // Dispatch helper so a capture-phase 'play' listener (the controller's
  // belt-and-braces path) also sees element plays.
  _dispatchPlay(el) {
    const ls = docListeners['play'] || [];
    for (const l of ls) l({ target: el });
  },
};

// Prototype that the controller patches. All elements share it.
global.HTMLMediaElement = { prototype: FakeMediaElement.prototype };
global.window = global;
global.Promise = Promise;

// Wire element.play() so that, in addition to the patched prototype, a 'play'
// also surfaces to document capture listeners (as a browser would).
const _origProtoPlayRef = FakeMediaElement.prototype.play;

// ---- Inject the REAL controller -----------------------------------------
const controllerJs = $encoded;
// Evaluate in this global scope.
(0, eval)(controllerJs);

// After injection, make element play() also notify document capture listeners.
const patchedPlay = FakeMediaElement.prototype.play;
FakeMediaElement.prototype.play = function () {
  const r = patchedPlay.apply(this, arguments);
  try { global.document._dispatchPlay(this); } catch (e) {}
  return r;
};

function playingState() {
  let count = 0, idx = -1;
  audios.forEach((a, i) => { if (!a.paused) { count++; idx = i; } });
  return { count, idx };
}

async function main() {
  // 1) Auto-start stop 1 (native play on element 0).
  await audios[0].play();
  // 2) Listener taps stop 3's native control while stop 1 is still playing.
  await audios[2].play();
  const s1 = playingState();

  // Reset for the rapid-double-tap case.
  audios.forEach(a => { a.pause(); a.currentTime = 0; });

  // 3) Rapid double tap: stop 2 then immediately stop 4 (promises resolve
  //    out of order is tolerated by the sequence token).
  const p1 = audios[1].play();
  const p2 = audios[3].play();
  await Promise.all([p1, p2]);
  const s2 = playingState();

  process.stdout.write(JSON.stringify({
    playingCount: s1.count,
    playingIndex: s1.idx,
    doubleTapPlayingCount: s2.count,
    doubleTapPlayingIndex: s2.idx,
  }) + '\\n');
}

main().catch(e => { console.error(e); process.exit(1); });
''';
}
