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


# ── LOCAL-750 (B): one definition of the per-stop block, page header and CSS ──
#
# Michael's retest: the edited page's stop looked different from a generated
# one — the map sign sat AFTER the title instead of before, and the "Audio N"
# suffix was missing from the stop name. Cause: the generator
# (tour_generation_modernized.generate_html_with_external_audio) and the editor
# (tour_editing_phase2.create_clean_html) each wrote their OWN per-stop markup,
# header and CSS. They drifted.
#
# From here on BOTH services render a stop, the page header and the page CSS
# from the functions below, so the two pages can never diverge again. The markup
# matches the generated page Michael already approved:
#   * <h3>{first line}: Audio {n}</h3>  — the "Audio N" suffix is in the name,
#   * the map button immediately AFTER the <h3> (before the <audio>),
#   * <h1>{tour name}</h1> as the page header (not a generic "Audio Tour").
#
# Audio element ids follow the generator's scheme (`audio-{n-1}`, 0-based). The
# shared voice-control script (SHARED_VOICE_CONTROL_SCRIPT) binds via
# querySelectorAll('audio') and a 0-based index, so it is id-scheme agnostic and
# both pages drive the same handlers.

# Page CSS shared by the generated and edited pages. Includes MAP_BTN_CSS so the
# round button styling is defined exactly once.
PAGE_CSS = (
    "        body { font-family: Arial, sans-serif; margin: 20px; }\n"
    "        .audio-item { margin: 20px 0; padding: 15px; border: 1px solid #ccc; }\n"
    "        audio { width: 100%; }\n"
    "        " + MAP_BTN_CSS + "\n"
)


def build_page_header(tour_name):
    """Return the page `<h1>` — the tour's own name, title-cased.

    The generator fed `tour_name.replace('_', ' ').title()`; the editor used a
    hard-coded "Audio Tour". Both now call this so the header is the tour name on
    both pages (LOCAL-750 B). A blank/None name falls back to "Audio Tour".
    """
    name = (tour_name or '').strip()
    if not name:
        return '<h1>Audio Tour</h1>'
    return f"<h1>{name.replace('_', ' ').title()}</h1>"


def build_stop_block(stop_num, stop_text, tour_category=''):
    """Return the shared per-stop `<div class="audio-item">…</div>` block.

    [stop_num] is the 1-based stop number. The block is byte-for-byte the same
    on the generated and edited pages:
      * `<h3>{first line of stop_text}: Audio {stop_num}</h3>`,
      * the map button (empty string when the stop has no Coordinates:) right
        after the `<h3>`,
      * an `<audio id="audio-{stop_num-1}">` referencing `audio_{stop_num}.mp3`.
    """
    text = stop_text or ''
    lines = text.split('\n')
    stop_title = lines[0].strip() if lines and lines[0].strip() else f"Stop {stop_num}"
    map_button = build_map_button(text, stop_num, tour_category)
    return (
        '\n    <div class="audio-item">\n'
        f'        <h3>{stop_title}: Audio {stop_num}</h3>\n'
        f'        {map_button}\n'
        f'        <audio id="audio-{stop_num - 1}" controls preload="metadata">\n'
        f'            <source src="audio_{stop_num}.mp3" type="audio/mpeg">\n'
        '            Your browser does not support the audio element.\n'
        '        </audio>\n'
        '    </div>'
    )


# The voice-control script shared by both pages. It binds every <audio> on the
# page via querySelectorAll (so it does not depend on the id scheme) and exposes
# the same window.* handlers the Flutter voice-control layer calls. Kept here so
# the generated and edited pages run identical control code.
SHARED_VOICE_CONTROL_SCRIPT = '''    <script>
        let audioElements = [];
        let currentStopIndex = 0;
        let wasPlayingBeforeVoice = false;

        window.playAudio = function() {
            audioElements.forEach((audio, index) => {
                if (index !== currentStopIndex) {
                    audio.pause();
                    audio.currentTime = 0;
                }
            });
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].play();
                return "Success: Playing stop-" + currentStopIndex;
            }
            return "Error: No audio to play";
        };

        window.pauseAudio = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].pause();
                return "Success: Audio paused";
            }
            return "Error: No audio to pause";
        };

        window.pauseAllAudio = function() {
            wasPlayingBeforeVoice = false;
            if (audioElements[currentStopIndex] && !audioElements[currentStopIndex].paused) {
                wasPlayingBeforeVoice = true;
                audioElements[currentStopIndex].pause();
            }
            return "Success: Audio paused for voice recognition";
        };

        window.nextStop = function() {
            if (currentStopIndex < audioElements.length - 1) {
                currentStopIndex++;
                return "Success: Moved to stop-" + currentStopIndex;
            }
            return "Error: Already at last stop";
        };

        window.previousStop = function() {
            if (currentStopIndex > 0) {
                currentStopIndex--;
                return "Success: Moved to stop-" + currentStopIndex;
            }
            return "Error: Already at first stop";
        };

        window.repeatStop = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].currentTime = 0;
                return "Success: Reset stop-" + currentStopIndex + " to beginning";
            }
            return "Error: No audio to reset";
        };

        window.seekForward = function(seconds = 10) {
            if (audioElements[currentStopIndex]) {
                const audio = audioElements[currentStopIndex];
                const newTime = audio.currentTime + seconds;
                const maxTime = audio.duration || 0;
                if (newTime >= maxTime) {
                    audio.currentTime = maxTime - 1;
                    return "Success: Moved to near end (" + seconds + "s would exceed duration)";
                } else {
                    audio.currentTime = newTime;
                    return "Success: Moved forward " + seconds + " seconds";
                }
            }
            return "Error: No audio to seek";
        };

        window.seekBackward = function(seconds = 10) {
            if (audioElements[currentStopIndex]) {
                const audio = audioElements[currentStopIndex];
                const newTime = audio.currentTime - seconds;
                if (newTime < 0) {
                    audio.currentTime = 0;
                    return "Success: Moved to beginning (" + seconds + "s would go below 0)";
                } else {
                    audio.currentTime = newTime;
                    return "Success: Moved backward " + seconds + " seconds";
                }
            }
            return "Error: No audio to seek";
        };

        window.initializeAudio = function() {
            return "Success: Audio system initialized with " + audioElements.length + " stops";
        };

        document.addEventListener('DOMContentLoaded', function() {
            const audios = document.querySelectorAll('audio');
            audioElements = Array.from(audios);
            audioElements.forEach((audio, index) => {
                audio.addEventListener('play', function() {
                    audioElements.forEach((otherAudio, otherIndex) => {
                        if (otherIndex !== index && !otherAudio.paused) {
                            otherAudio.pause();
                        }
                    });
                    currentStopIndex = index;
                });
            });
        });
    </script>'''


def build_tour_page_html(tour_name, stops, tour_category=''):
    """Render the full tour page both services share (LOCAL-750 B).

    [stops] is the ordered list of stops. Each element is either a plain stop
    text (the stop number is then its 1-based position — the generator's case)
    or a ``(stop_num, stop_text)`` pair (the editor passes the real, possibly
    renumbered stop numbers so the `audio_<n>.mp3` references and `openMap(<n>)`
    calls stay correct). The page carries the shared CSS, the tour-name `<h1>`,
    the openMap bridge, one shared per-stop block per stop, and the shared
    voice-control script. Both the generator and the editor call this, so the
    generated and edited pages are byte-for-byte identical for the same stops.
    """
    display_name = (tour_name or 'Audio Tour')
    head = (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '    <meta charset="UTF-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'    <title>{display_name}</title>\n'
        '    <style>\n'
        + PAGE_CSS +
        '    </style>\n'
        '</head>\n'
        '<body>\n'
        '    ' + build_page_header(tour_name) + '\n'
        + OPENMAP_SCRIPT
    )
    body = ''
    for pos, item in enumerate(stops, 1):
        if isinstance(item, (tuple, list)) and len(item) == 2:
            stop_num, text = item
        else:
            stop_num, text = pos, item
        body += build_stop_block(stop_num, text, tour_category)
    tail = '\n\n' + SHARED_VOICE_CONTROL_SCRIPT + '\n</body>\n</html>'
    return head + body + tail
