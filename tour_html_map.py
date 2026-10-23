"""Shared map-button building blocks for tour HTML (LOCAL-747).

Both the generator (tour_generation_modernized.generate_html_with_external_audio)
and the editor (tour_editing_phase2.create_clean_html) must render the SAME
per-stop map button: a round `.map-btn` that calls `openMap(<stop>)`, shown only
when the stop text carries a `Coordinates:` line, with a per-category icon. Before
LOCAL-747 the editor wrote its own index.html with no button at all, so a saved
edit dropped every map button. Rather than copy the button HTML a third time, the
pieces live here once and both services import them.

The icon map also now covers biking/cycling (LOCAL-747), which previously fell
back to the generic map pin on Michael's biking tour.
"""
import re

# A stop gets a map button only when its text has a "Coordinates: lat, lng" line.
# Anchored to a line start, case-insensitive, multiline — same rule the generator
# and the (legacy) translation path have always used.
COORDINATES_RE = re.compile(
    r'^Coordinates:\s*[-\d.]+\s*,\s*[-\d.]+', re.IGNORECASE | re.MULTILINE)

# Per-category stop icon. Keys are the lowercase tour category as written by
# generate_tour_text.py on the "Tour-Category:" line. Unknown/empty -> FALLBACK.
CATEGORY_ICONS = {
    'walking': '\U0001F6B6',      # 🚶
    'restaurant': '\U0001F374',   # 🍴
    'museum': '\U0001F3DB\uFE0F', # 🏛️
    'specialized': '\U0001F5FA\uFE0F',  # 🗺️
    'biking': '\U0001F6B2',       # 🚲  (LOCAL-747)
    'cycling': '\U0001F6B2',      # 🚲  (LOCAL-747 — same family as biking)
}
FALLBACK_ICON = '\U0001F5FA\uFE0F'  # 🗺️

# Inline CSS for the round map button. Kept identical to the generator's original
# styling so the saved-edit page looks the same as a freshly generated one.
MAP_BTN_CSS = (
    ".map-btn { background: #3d7ebf; border: none; border-radius: 50%; "
    "width: 36px; height: 36px; font-size: 20px; line-height: 1; "
    "cursor: pointer; display: inline-flex; align-items: center; "
    "justify-content: center; margin-left: 8px; vertical-align: middle; }"
)

# The openMap() bridge to the Flutter in-app webview. Identical in both pages.
OPENMAP_SCRIPT = (
    "    <script>\n"
    "        function openMap(stopNum) {\n"
    "            if (window.flutter_inappwebview && "
    "window.flutter_inappwebview.callHandler) {\n"
    "                window.flutter_inappwebview.callHandler('openMap', "
    "{stop: stopNum});\n"
    "            }\n"
    "        }\n"
    "    </script>"
)


def stop_has_coordinates(stop_text):
    """True if the stop text contains a valid `Coordinates: lat, lng` line."""
    return bool(COORDINATES_RE.search(stop_text or ''))


def category_icon(tour_category):
    """Return the stop icon for a tour category, falling back to the map pin."""
    return CATEGORY_ICONS.get((tour_category or '').strip().lower(), FALLBACK_ICON)


def build_map_button(stop_text, stop_num, tour_category=''):
    """Return the `.map-btn` HTML for a stop, or '' when it has no coordinates.

    stop_num is the 1-based stop number passed to openMap(); tour_category picks
    the icon. Matches the generator's button exactly so both pages agree.
    """
    if not stop_has_coordinates(stop_text):
        return ''
    icon = category_icon(tour_category)
    return (f'<button class="map-btn" onclick="openMap({stop_num})" '
            f'title="View on map">{icon}</button>')
