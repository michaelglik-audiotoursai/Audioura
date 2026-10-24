"""
organiser_audio_tours.py — LOCAL-754B (D658 addendum 2 / D708 / LOCAL-745/746/748/750).

The organiser builds a REAL tour from their OWN hosted audio (an RSS feed and/or
MP3 links). Audioura never stores the audio files (D658 addendum 2): the package
carries a `remote_audio.json` mapping stop N → the organiser's URL and NO MP3.
The phone downloads each URL on download and saves it as `audio_N.mp3` next to
`index.html`, so on Listen the tour is indistinguishable from a generated one —
same page (tour_html_map.build_tour_page_html), same map buttons, same voice
control.

This module is SELF-CONTAINED on purpose (same reason as communities_api.py and
communities_rss.py): the user-api container's build context is ./user-tracking
and cannot import repo-root modules. It therefore imports only the stdlib and
the sibling `tour_html_map` (a copy of the repo-root renderer lives beside it,
exactly as the generator/editor share the one at the root — so the organiser-
audio page is byte-for-byte the same stop markup as a generated page).

Everything here is PURE of Flask and of the DB wiring, so a hermetic test drives
it with plain data and an injected URL checker — no network, no Postgres, no
rows written. communities_api owns the HTTP surface and the audio_tours row; it
calls build_package() and validate_audio_urls() here.

Fixed rules enforced:
  * organisers do NOT upload MP3s — they link audio they host; the package has
    NO .mp3, only remote_audio.json (D658 addendum 2).
  * only AUDIO enclosures are kept from a feed (audio/*, .mp3, .m4a, …); the
    count of skipped non-audio items is reported.
  * publish validates every audio URL (reachable, audio content type, size ≤
    MAX_AUDIO_BYTES) and names the first failing stop BY NAME.
  * the source marker is source_kind = 'organiser_audio' (an additive column).
  * translation of organiser audio is NOT offered (D708) — see
    translation_not_offered() here, the single source of truth the translation
    service and the app read.
"""

import io
import json
import re
import zipfile

from tour_html_map import build_tour_page_html, COORDINATES_RE  # noqa: F401


# ── Constants ────────────────────────────────────────────────────────────────

# The source marker written to audio_tours.source_kind (migration 049). A
# generated/ordinary tour has source_kind NULL; an organiser-audio tour carries
# this. The app and the translation gate key the "no translation / no MP3 in the
# ZIP" behaviour off this one value.
SOURCE_KIND = 'organiser_audio'

# Per-stop upload ceiling (D754: "size ≤ 200 MB/stop"). Bytes.
MAX_AUDIO_BYTES = 200 * 1024 * 1024

# A tour type → the tour_category the shared renderer uses to pick the stop icon
# and (for walking/biking/driving) the map button. 'other'/'museum' keep their
# own icon; an unknown type falls back to the renderer's generic pin.
TOUR_TYPES = ('walking', 'biking', 'driving', 'museum', 'other')

# The categories that REQUIRE a location on every stop (a map tour). 'other' and
# 'museum' make the location optional.
LOCATION_REQUIRED_TYPES = ('walking', 'biking', 'driving')

# Audio enclosure recognition: a content type of audio/*, or a URL path ending
# in a common audio extension. Used to keep only playable items from a feed and
# to validate a pasted MP3 link.
_AUDIO_EXT_RE = re.compile(r'\.(mp3|m4a|m4b|aac|ogg|oga|opus|wav|flac|mp4)(\?|#|$)',
                           re.IGNORECASE)


def _looks_like_audio_url(url):
    """True iff a URL path ends in a known audio extension. A feed <enclosure>
    without a usable content type still counts as audio when its URL ends .mp3
    etc. (podcast convention)."""
    return bool(_AUDIO_EXT_RE.search((url or '').strip()))


def _is_audio_content_type(content_type):
    """True iff an HTTP Content-Type names audio. 'audio/mpeg', 'audio/mp4',
    'audio/x-m4a', … all pass; '' / 'text/html' / 'application/xml' fail."""
    ct = (content_type or '').strip().lower()
    return ct.startswith('audio/')


# ── Feed → audio-only episodes ────────────────────────────────────────────────

def keep_audio_enclosures(episodes):
    """Keep only the AUDIO episodes from a parsed feed (D754: "keep only audio
    enclosures (audio/*, .mp3, .m4a); say how many were skipped").

    `episodes` is a list of dicts as communities_rss.parse_feed returns
    (title, audio_url, guid, position) — optionally carrying a `content_type`.
    An episode is AUDIO when its content_type is audio/* OR its URL ends in a
    known audio extension. Returns (kept, skipped_count): `kept` is the audio
    episodes in feed order (re-positioned 1..N), `skipped_count` is how many
    non-audio items were dropped. Pure — no network."""
    kept = []
    skipped = 0
    for ep in episodes or []:
        url = (ep.get('audio_url') or '').strip()
        ctype = ep.get('content_type')
        is_audio = _is_audio_content_type(ctype) or _looks_like_audio_url(url)
        if url and is_audio:
            kept.append({
                'position': len(kept) + 1,
                'title': ep.get('title') or f'Episode {len(kept) + 1}',
                'audio_url': url,
                'guid': ep.get('guid'),
            })
        else:
            skipped += 1
    return kept, skipped


# ── Stop normalisation ────────────────────────────────────────────────────────

def _coordinates_line(lat, lng):
    """The `Coordinates: lat, lng` line the shared renderer needs to draw a stop's
    map button, or '' when the stop has no location (an 'other' tour may omit
    it). The renderer's COORDINATES_RE matches this exact shape."""
    if lat is None or lng is None:
        return ''
    return f'Coordinates: {lat}, {lng}'


def stop_text_block(stop):
    """The per-stop text for one organiser-audio stop, in the SAME shape the
    generated tour's stop text uses so build_tour_page_html renders an identical
    block:

        <stop name>            ← first line → the <h3> title ("<name>: Audio N")
        Coordinates: lat, lng  ← drives the map button (omitted with no location)
        <optional body text>   ← shown on the page / used for search

    `stop` is a dict {name, lat, lng, text}. The name is required (the caller
    validates); a missing body is simply absent. Pure string building."""
    name = (stop.get('name') or '').strip() or 'Stop'
    lines = [name]
    coords = _coordinates_line(stop.get('lat'), stop.get('lng'))
    if coords:
        lines.append(coords)
    body = (stop.get('text') or '').strip()
    if body:
        lines.append('')
        lines.append(body)
    return '\n'.join(lines)


def tour_category_for(tour_type):
    """Map a tour TYPE to the renderer's tour_category. walking/biking/museum
    pass through (the renderer knows those icons); driving is rendered with the
    walking family's behaviour (a map tour) but keeps its own type on the row;
    'other'/unknown fall back to the generic pin via the renderer. Returns the
    lowercase string handed to build_tour_page_html."""
    t = (tour_type or '').strip().lower()
    return t


# ── Validation (publish gate) ─────────────────────────────────────────────────

class StopValidationError(Exception):
    """A stop failed validation. `stop_name` names the offending stop so the UI
    can say exactly which one, and `code` is a stable reason."""

    def __init__(self, code, message, stop_name=None, position=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.stop_name = stop_name
        self.position = position


def validate_stops(stops, tour_type):
    """Structural validation of the ordered stop list BEFORE any network check.

    Rules (D754):
      * at least one stop;
      * every stop has a non-empty name;
      * every stop has an audio_url;
      * for a walking/biking/driving tour every stop has a location (lat+lng).

    Raises StopValidationError(code, message, stop_name, position) on the first
    offending stop; returns None when the list is structurally valid. Pure."""
    if not stops:
        raise StopValidationError('no_stops', 'A tour needs at least one stop.')
    needs_location = (tour_type or '').strip().lower() in LOCATION_REQUIRED_TYPES
    for idx, stop in enumerate(stops, 1):
        name = (stop.get('name') or '').strip()
        if not name:
            raise StopValidationError(
                'stop_needs_name', f'Stop {idx} needs a name.', position=idx)
        if not (stop.get('audio_url') or '').strip():
            raise StopValidationError(
                'stop_needs_audio', f'"{name}" has no audio.',
                stop_name=name, position=idx)
        if needs_location and (stop.get('lat') is None or stop.get('lng') is None):
            raise StopValidationError(
                'stop_needs_location',
                f'"{name}" needs a location for a {tour_type} tour.',
                stop_name=name, position=idx)
    return None


def validate_audio_urls(stops, url_check):
    """Validate every stop's audio URL is reachable, audio, and ≤ MAX_AUDIO_BYTES
    (D754: "server validates every audio URL (HEAD/ranged GET) and reports a
    failing stop by name"). `url_check(url) -> (ok, content_type, size_bytes)`
    is INJECTED so a test runs with no network; communities_api passes a real
    HEAD/ranged-GET checker.

    Raises StopValidationError on the FIRST failing stop, naming it:
      * 'audio_unreachable'  — url_check returned ok=False;
      * 'audio_not_audio'    — content type is not audio/* (and the URL has no
                               audio extension to vouch for it);
      * 'audio_too_large'    — size_bytes > MAX_AUDIO_BYTES.
    Returns None when every stop's URL passes. Pure apart from the injected
    checker."""
    for idx, stop in enumerate(stops, 1):
        name = (stop.get('name') or '').strip() or f'Stop {idx}'
        url = (stop.get('audio_url') or '').strip()
        try:
            ok, content_type, size_bytes = url_check(url)
        except Exception as e:  # noqa: BLE001 — a checker error is an unreachable URL
            raise StopValidationError(
                'audio_unreachable', f'"{name}" could not be reached ({e}).',
                stop_name=name, position=idx)
        if not ok:
            raise StopValidationError(
                'audio_unreachable', f'"{name}" could not be reached.',
                stop_name=name, position=idx)
        if not _is_audio_content_type(content_type) and not _looks_like_audio_url(url):
            raise StopValidationError(
                'audio_not_audio',
                f'"{name}" is not an audio file (got {content_type or "no type"}).',
                stop_name=name, position=idx)
        if size_bytes is not None and size_bytes > MAX_AUDIO_BYTES:
            raise StopValidationError(
                'audio_too_large',
                f'"{name}" is larger than the 200 MB per-stop limit.',
                stop_name=name, position=idx)
    return None


# ── Package build ─────────────────────────────────────────────────────────────

def _manifest(tour_name):
    """The PWA manifest, identical in shape to the generator's generate_manifest
    so the package looks the same to the app."""
    return json.dumps({
        "name": tour_name,
        "short_name": (tour_name or 'Tour')[:12],
        "start_url": "/",
        "display": "standalone",
        "background_color": "#2c3e50",
        "theme_color": "#2c3e50",
        "icons": []
    }, indent=2)


def _service_worker():
    """The same offline service worker the generator ships, so voice control and
    offline playback behave identically on the organiser-audio page."""
    return (
        "const CACHE_NAME = 'tour-cache-v1';\n"
        "self.addEventListener('fetch', function(event) {\n"
        "  if (event.request.url.includes('.mp3') || "
        "event.request.url.includes('.txt')) {\n"
        "    event.respondWith(\n"
        "      caches.open(CACHE_NAME).then(function(cache) {\n"
        "        return cache.match(event.request).then(function(response) {\n"
        "          return response || fetch(event.request).then(function(r) {\n"
        "            cache.put(event.request, r.clone());\n"
        "            return r;\n"
        "          });\n"
        "        });\n"
        "      })\n"
        "    );\n"
        "  }\n"
        "});\n"
    )


def remote_audio_map(stops):
    """The remote_audio.json mapping stop N (1-based, as a string key) → the
    organiser's audio URL. This is the ONLY place the audio lives in the package
    (D658 addendum 2: Audioura never stores the files). The phone downloads each
    URL on download and writes audio_N.mp3. Pure."""
    return {str(idx): (stop.get('audio_url') or '').strip()
            for idx, stop in enumerate(stops, 1)}


def build_package(tour_name, stops, tour_type=''):
    """Build the organiser-audio tour package ZIP (bytes).

    Contents — the SAME as a generated package EXCEPT the audio is remote:
      * index.html        — build_tour_page_html(tour_name, stop_texts, category)
                            — byte-for-byte the generated page's stop markup
                            (": Audio N" headings, map buttons from the
                            Coordinates line, the shared voice-control script);
      * audio_N.txt       — the per-stop text (name, Coordinates line, body),
                            exactly like a generated package's per-stop text;
      * tour_content.txt  — the whole tour text (stops joined), for search/edit;
      * manifest.json     — the PWA manifest;
      * service-worker.js — offline caching of audio_N.mp3 / .txt;
      * remote_audio.json — {N: url} the phone fetches. NO .mp3 in the ZIP.

    `stops` is the ordered list of {name, lat, lng, text, audio_url}. Pure (no
    network, no DB) — returns the ZIP as bytes so the caller stores it in
    audio_tours.audio_tour exactly as a generated tour's ZIP."""
    category = tour_category_for(tour_type)
    stop_texts = [stop_text_block(s) for s in stops]
    html = build_tour_page_html(tour_name, stop_texts, category)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('index.html', html)
        for idx, text in enumerate(stop_texts, 1):
            zf.writestr(f'audio_{idx}.txt', text.encode('utf-8'))
        zf.writestr('tour_content.txt', '\n\n'.join(stop_texts).encode('utf-8'))
        zf.writestr('manifest.json', _manifest(tour_name))
        zf.writestr('service-worker.js', _service_worker())
        # The remote-audio map — the whole point: the audio is the organiser's,
        # referenced by URL, NEVER stored in the package (D658 addendum 2).
        zf.writestr('remote_audio.json',
                    json.dumps(remote_audio_map(stops), indent=2))
    return buf.getvalue()


def tour_content_text(stops):
    """The whole-tour text (stops joined) the caller stores in
    audio_tours.tour_content for search and edit — the same text as
    tour_content.txt in the package."""
    return '\n\n'.join(stop_text_block(s) for s in stops)


# ── Translation gate (D708) ───────────────────────────────────────────────────

def translation_not_offered(source_kind):
    """[D708] True iff a tour with this `source_kind` may NOT be translated —
    i.e. it is an organiser-audio tour. Translation of organiser audio is NOT
    offered: Audioura never had the text to translate and never stored the
    audio to re-synthesize. The translation service refuses such a request (403
    translation_not_offered) and the app hides the Translate menu item. This one
    function is the single source of truth for both sides."""
    return (source_kind or '') == SOURCE_KIND
