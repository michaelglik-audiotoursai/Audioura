// [LOCAL-698] Single-playback controller.
//
// Michael, 2026-10-15 (Pixel-4, a DOWNLOADED Russian translation): tapping a
// different stop while one is speaking started the second WITHOUT stopping the
// first — both played at once. This regressed a BETA-1 fix (Yury Makedonov).
//
// ROOT CAUSE. Every stop in a tour/news page is rendered as an
// `<audio controls>` element (see tour_generation_modernized.py,
// translation-service/translation_service.py, news_processor_service.py). Each
// element therefore has its OWN native play button. The earlier fix only
// routed the JS helpers (window.playAudio / goToStop / playAudioByIndex)
// through a "pause the others first" path. But tapping a stop's NATIVE control
// calls that element's `.play()` DIRECTLY — it never goes through those
// helpers, so nothing pauses the element already playing. On a downloaded tour
// (and every translation, which is its own HTML file) the page is already on
// the device, so a server-side or Dart-only change cannot retroactively fix
// the file the listener already has.
//
// THE FIX — ONE shared controller, enforced at the lowest level. We patch
// `HTMLMediaElement.prototype.play` on the page so that EVERY play path — a
// native control tap, window.playAudio(), goToStop(), playAudioByIndex(),
// autoplay, voice command, anything — first pauses and rewinds every OTHER
// audio/video element before the chosen one starts. A monotonically
// increasing sequence token makes rapid double-taps safe: only the most recent
// request may remain playing; an older request that resolves late and finds a
// newer one already in charge pauses itself. This is injected by the Flutter
// player on EVERY page load, so it also fixes tours that were downloaded before
// this build.
//
// The guarantee: at most one media element is ever non-paused. "Start stop 1,
// tap stop 3 => only stop 3 plays."
library single_playback_controller;

/// The JavaScript source of the single-playback controller. Injected into the
/// tour player and news player WebViews on every page load. Idempotent: a
/// second injection is a no-op (guarded by `__audiouraSinglePlayInstalled`).
///
/// Pure string with no Dart interpolation so it is safe to inject verbatim and
/// easy to assert on in a unit test.
const String kSinglePlaybackControllerJs = r'''
(function () {
  // Idempotent: never patch play() twice (double patching would recurse).
  if (window.__audiouraSinglePlayInstalled) { return 'already-installed'; }
  window.__audiouraSinglePlayInstalled = true;

  // Monotonic token. Every accepted play() bumps it; the element that owns the
  // current token is the single allowed player. A late-resolving older request
  // whose token is stale pauses itself so two stops never overlap.
  window.__audiouraPlaySeq = 0;
  window.__audiouraCurrent = null;

  var proto = window.HTMLMediaElement && window.HTMLMediaElement.prototype;
  if (!proto || typeof proto.play !== 'function') {
    return 'no-media-element';
  }

  // Pause + rewind every media element EXCEPT the one we are about to start.
  function pauseAllExcept(keep) {
    var media = document.querySelectorAll('audio, video');
    for (var i = 0; i < media.length; i++) {
      var m = media[i];
      if (m === keep) { continue; }
      try {
        if (!m.paused) { m.pause(); }
        // Rewind so a re-tap starts the stop from the top, matching the
        // product behaviour of "one stop at a time, from the beginning".
        m.currentTime = 0;
      } catch (e) { /* a detached element must never throw here */ }
    }
  }

  var nativePlay = proto.play;
  proto.play = function () {
    var el = this;
    // This tap/command becomes the newest request and the single owner.
    var seq = ++window.__audiouraPlaySeq;
    window.__audiouraCurrent = el;

    // Stop everything else BEFORE starting this one — the core invariant.
    pauseAllExcept(el);

    var result;
    try {
      result = nativePlay.apply(el, arguments);
    } catch (e) {
      // Mirror native behaviour: surface as a rejected promise when possible.
      return (window.Promise)
        ? Promise.reject(e)
        : (function () { throw e; })();
    }

    // play() returns a promise on modern engines. If a NEWER request arrived
    // while this one was resolving (rapid double tap), this element is no
    // longer the owner — pause it so only the latest stop remains playing.
    if (result && typeof result.then === 'function') {
      return result.then(function (v) {
        if (seq !== window.__audiouraPlaySeq) {
          try { el.pause(); } catch (e) {}
        }
        return v;
      }).catch(function (err) {
        // Autoplay rejections etc. — do not crash the page.
        return undefined;
      });
    }

    // Older engines without a play() promise: enforce synchronously.
    if (seq !== window.__audiouraPlaySeq) {
      try { el.pause(); } catch (e) {}
    }
    return result;
  };

  // Belt-and-braces: if some element starts playing through a path we somehow
  // did not see (e.g. a future engine quirk), the capture-phase 'play' event
  // still collapses to a single player.
  document.addEventListener('play', function (ev) {
    var started = ev.target;
    if (!started || (started.tagName !== 'AUDIO' && started.tagName !== 'VIDEO')) {
      return;
    }
    if (window.__audiouraCurrent !== started) {
      window.__audiouraCurrent = started;
      window.__audiouraPlaySeq++;
    }
    pauseAllExcept(started);
  }, true);

  return 'installed';
})();
''';
