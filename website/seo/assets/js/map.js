/* Audioura SEO — lazy Leaflet + OpenStreetMap route map (LOCAL-812).
 * Loads Leaflet from unpkg only when the #map element scrolls into view, so
 * the map never blocks first paint or hurts the Lighthouse performance score.
 * OSM tile attribution is always shown (OSM tile usage policy).
 * Degrades gracefully: with JS off, the stop list already describes the route.
 */
(function () {
  "use strict";
  var el = document.getElementById("map");
  var data = window.__TOUR__;
  if (!el || !data) return;

  var LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
  var LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
  var loaded = false;

  function loadCss(href) {
    var l = document.createElement("link");
    l.rel = "stylesheet";
    l.href = href;
    l.integrity = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=";
    l.crossOrigin = "";
    document.head.appendChild(l);
  }

  function loadJs(src, cb) {
    var s = document.createElement("script");
    s.src = src;
    s.integrity = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=";
    s.crossOrigin = "";
    s.onload = cb;
    document.head.appendChild(s);
  }

  function init() {
    if (loaded || !window.L) return;
    loaded = true;
    var L = window.L;
    var map = L.map(el, { scrollWheelZoom: false }).setView(data.center, 15);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    var bounds = [];
    data.points.forEach(function (p) {
      if (p.lat == null || p.lng == null) return;
      var icon = L.divIcon({
        className: "stop-marker",
        html: '<span>' + p.n + "</span>",
        iconSize: [26, 26]
      });
      L.marker([p.lat, p.lng], { icon: icon, title: p.title, alt: p.title })
        .addTo(map)
        .bindPopup(p.n + ". " + p.title);
      bounds.push([p.lat, p.lng]);
    });
    if (bounds.length > 1) map.fitBounds(bounds, { padding: [30, 30] });
  }

  function start() {
    loadCss(LEAFLET_CSS);
    loadJs(LEAFLET_JS, init);
  }

  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          io.disconnect();
          start();
        }
      });
    }, { rootMargin: "200px" });
    io.observe(el);
  } else {
    start();
  }
})();
