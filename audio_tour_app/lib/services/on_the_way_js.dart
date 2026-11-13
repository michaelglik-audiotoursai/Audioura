// [LOCAL-908] JS bridge for "On the way" topics inside the tour page.
//
// Topic audio plays in a detached `new Audio()` (not in the DOM), so the page's
// own <audio> list — and with it every stop index the player and the
// LOCAL-877 bar use — is untouched. Reports through `onTopicEvent`:
//   [kind, positionSeconds, durationSeconds]  kind: playing|tick|ended|error|stopped
//
// Also:
//  * window.__audHold = [stopIdx0, ...]: after those stops the page's own
//    'ended' handlers (auto-advance, etc.) are suppressed in the capture phase
//    and Dart gets `onStopEnded` so the topic countdown can run instead. The
//    LOCAL-670C 'ended' playback event is re-emitted so "listened" still counts.
//  * __audTopic.setMediaNext(on): registers the OS media-session "nexttrack"
//    (Bluetooth / CarPlay / Android Auto / steering wheel) ONLY while it means
//    "skip topic". Off = no handler, i.e. exactly today's behaviour.
//  * volume ramp for the fade-out. (iOS WebKit ignores programmatic volume, so
//    there the fade degrades to a stop after the same duration.)
library on_the_way_js;

const String kOnTheWayJs = r'''
(function () {
  if (window.__audTopic) { return 'already-installed'; }
  var a = null, fade = null, lastTick = 0;
  function cb() {
    var h = window.flutter_inappwebview;
    if (h) { h.callHandler.apply(h, arguments); }
  }
  function rep(kind) {
    var d = (a && isFinite(a.duration)) ? a.duration : 0;
    cb('onTopicEvent', kind, a ? (a.currentTime || 0) : 0, d || 0);
  }
  function clearFade() { if (fade) { clearInterval(fade); fade = null; } }
  function drop() {
    clearFade();
    var old = a; a = null;
    if (old) {
      try { old.pause(); } catch (e) {}
      try { old.removeAttribute('src'); old.load(); } catch (e) {}
    }
  }
  function meta(title) {
    try {
      if (navigator.mediaSession && window.MediaMetadata) {
        navigator.mediaSession.metadata = new MediaMetadata({
          title: title || '', artist: 'Optional topic \u00b7 on the way' });
      }
    } catch (e) {}
  }
  window.__audHold = window.__audHold || [];
  window.__audTopic = {
    play: function (url, start, title) {
      drop();
      try { if (window.__audBar) { window.__audBar.pause(); } } catch (e) {}
      var el = new Audio();
      a = el;
      el.preload = 'auto';
      el.src = url;
      el.addEventListener('loadedmetadata', function () {
        if (a !== el) { return; }
        if (start > 0) { try { el.currentTime = start; } catch (e) {} }
      });
      el.addEventListener('playing', function () { if (a === el) { rep('playing'); } });
      el.addEventListener('ended', function () { if (a === el) { rep('ended'); } });
      el.addEventListener('error', function () { if (a === el) { rep('error'); } });
      el.addEventListener('timeupdate', function () {
        if (a !== el) { return; }
        var n = Date.now();
        if (n - lastTick < 1000) { return; }
        lastTick = n; rep('tick');
      });
      meta(title);
      var p = el.play();
      if (p && p.catch) { p.catch(function () { if (a === el) { rep('error'); } }); }
    },
    fadeOut: function (ms) {
      var el = a;
      if (!el) { rep('stopped'); return; }
      clearFade();
      var steps = Math.max(1, Math.round((ms || 500) / 50)), i = 0, v0 = el.volume;
      fade = setInterval(function () {
        i++;
        try { el.volume = Math.max(0, v0 * (1 - i / steps)); } catch (e) {}
        if (i >= steps) {
          clearFade();
          if (a === el) { rep('tick'); drop(); rep('stopped'); }
        }
      }, 50);
    },
    stop: function () { drop(); rep('stopped'); },
    pause: function () { if (a) { try { a.pause(); } catch (e) {} } },
    resume: function () {
      if (a) { var p = a.play(); if (p && p.catch) { p.catch(function () {}); } }
    },
    toggle: function () {
      if (!a) { return; }
      if (a.paused) { window.__audTopic.resume(); } else { window.__audTopic.pause(); }
    },
    isActive: function () { return !!a; },
    setHold: function (list) { window.__audHold = list || []; },
    setMediaNext: function (on) {
      try {
        if (navigator.mediaSession) {
          navigator.mediaSession.setActionHandler('nexttrack',
            on ? function () { cb('onMediaNext'); } : null);
        }
      } catch (e) {}
    }
  };
  document.addEventListener('ended', function (ev) {
    var t = ev.target;
    if (!t || t.tagName !== 'AUDIO') { return; }
    var els = Array.prototype.slice.call(document.querySelectorAll('audio'));
    var idx = els.indexOf(t);
    if (idx < 0 || (window.__audHold || []).indexOf(idx) < 0) { return; }
    ev.stopImmediatePropagation();
    var d = t.duration;
    cb('onPlaybackEvent', idx, 'ended', t.currentTime || 0,
       (d && isFinite(d)) ? d : 0, t.playbackRate || 1);
    cb('onStopEnded', idx);
    try { if (window.__audBar) { window.__audBar.report(); } } catch (e) {}
  }, true);
  return 'installed';
})();
''';
