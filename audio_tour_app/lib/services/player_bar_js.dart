// [LOCAL-877] JS bridge between the tour page's <audio> elements and the
// persistent player bar. Works on the audio elements directly, so it does not
// depend on a page defining nextStop()/previousStop() (downloaded tours differ).
//
// Reports state through the `onBarState` handler:
//   [stopIndex, playing, positionSeconds, durationSeconds, stopName, totalStops]
// and exposes window.__audBar.{play,pause,toggle,next,previous,go(i,pos)}.
// Idempotent. Single-playback (LOCAL-698) still guarantees one stop at a time.
library player_bar_js;

const String kPlayerBarJs = r'''
(function () {
  if (window.__audBar) { return 'already-installed'; }
  var cur = 0;
  var lastTick = 0;
  function audios() {
    return Array.prototype.slice.call(document.querySelectorAll('audio'));
  }
  function curIdx() {
    var a = audios();
    for (var i = 0; i < a.length; i++) { if (!a[i].paused) { return i; } }
    return cur;
  }
  function nameFor(idx) {
    try {
      var byId = document.getElementById('stopTitle' + (idx + 1))
              || document.getElementById('stop-title-' + (idx + 1))
              || document.getElementById('stop' + (idx + 1) + 'Title');
      if (byId && byId.textContent) { return byId.textContent.trim(); }
      var h = document.querySelectorAll('h1,h2,h3,.stop-title,.stop-name');
      if (h && h.length > idx && h[idx].textContent) { return h[idx].textContent.trim(); }
    } catch (e) {}
    return null;
  }
  function report(force) {
    var now = Date.now();
    if (!force && now - lastTick < 900) { return; }
    lastTick = now;
    var a = audios();
    if (!a.length || !window.flutter_inappwebview) { return; }
    var i = curIdx();
    cur = i;
    var m = a[i];
    var d = m.duration;
    window.flutter_inappwebview.callHandler('onBarState', i,
      !m.paused && !m.ended, m.currentTime || 0, (d && isFinite(d)) ? d : 0,
      nameFor(i), a.length);
  }
  function go(i, pos) {
    var a = audios();
    if (!a.length) { return; }
    if (i < 0) { i = 0; }
    if (i > a.length - 1) { i = a.length - 1; }
    cur = i;
    var m = a[i];
    try { if (pos && pos > 0) { m.currentTime = pos; } else { m.currentTime = 0; } } catch (e) {}
    var p = m.play();
    if (p && p.catch) { p.catch(function () {}); }
    report(true);
  }
  window.__audBar = {
    play: function () {
      var a = audios(); if (!a.length) { return; }
      var p = a[curIdx()].play(); if (p && p.catch) { p.catch(function () {}); }
    },
    pause: function () {
      audios().forEach(function (m) { if (!m.paused) { m.pause(); } });
      report(true);
    },
    toggle: function () {
      var a = audios(); if (!a.length) { return; }
      var m = a[curIdx()];
      if (m.paused) { window.__audBar.play(); } else { window.__audBar.pause(); }
    },
    next: function () { go(curIdx() + 1, 0); },
    previous: function () { go(curIdx() - 1, 0); },
    go: go,
    report: function () { report(true); }
  };
  audios().forEach(function (m) {
    ['play', 'pause', 'ended', 'loadedmetadata'].forEach(function (ev) {
      m.addEventListener(ev, function () { report(true); });
    });
    m.addEventListener('timeupdate', function () { report(false); });
  });
  report(true);
  return 'installed';
})();
''';
