"""
[LOCAL-471] Carry coordinate confidence to the app.

WHY THIS EXISTS
`geocode_stops.resolve_point`/`resolve_poi` already decide, per stop, whether a
coordinate is corroborated ('high') or a lone model guess ('low'). Beta measured
the signal predictive over 28 stops with Wikidata ground truth: high-confidence
stops median 26 m error, low-confidence 303 m, and every stop worse than 500 m
was in the low group. The signal existed and stopped at the generator — nothing
downstream saw it, so a stop we have confirmed and a stop we are guessing at were
drawn as identical pins on the map. Yury Makedonov lost time following one.

WHAT THIS DOES
Writes a `Coordinate-Confidence: <high|low>` line into each stop's text block,
which is what becomes `audio_N.txt` in the tour zip and what
`tour_map_screen.dart` (and the editing screens and the translation splitter)
read. The mobile half — rendering the pin differently — is a separate task
(🟩 Mobile — Kiro); this only makes the field available.

WHY A NEW LINE, NOT A JSON SIDE-CHANNEL
`audio_N.txt` is already the per-stop artifact every parser reads, and every
existing parser keys off anchored line prefixes (`Coordinates:`, `Address:`,
`Type/Specialty:`) and ignores lines it does not recognise; the editing screens
treat the file as one opaque editable blob. A new labelled line therefore rides
the format every parser already tolerates, and it stays attached to the stop
text through translation (which copies unrecognised body lines through) with no
second file to keep in sync. See SUBMISSION_LOCAL-471.md for the parser audit.

DESIGN RULES
  * The field name the app should read is exactly `Coordinate-Confidence`.
  * Value is `high` or `low`; anything unknown or missing is treated as `low`,
    because an un-corroborated coordinate is exactly the case we must not
    present as trustworthy.
  * The line is inserted immediately after the stop's `Coordinates:` line so it
    sits with the other structured metadata. If a stop has no `Coordinates:`
    line the field is prepended after the title line so the value is never lost.
  * This is spoken-aloud metadata like the others, so callers must add
    `Coordinate-Confidence:` to their TTS strip set (both
    tour_generation_modernized.py and translation_service.py already strip the
    sibling nav fields).
  * `geocode_stops.py` is owned by LOCAL-470 concurrently and must NOT be edited
    here — this module reads its records and never imports its internals.
"""
import re

CONFIDENCE_LABEL = "Coordinate-Confidence"

# The field the app reads. Exported so tests and callers reference one constant.
CONFIDENCE_PREFIX = f"{CONFIDENCE_LABEL}:"

_COORD_LINE_RE = re.compile(r'^Coordinates:', re.IGNORECASE)
_EXISTING_CONFIDENCE_RE = re.compile(
    rf'^\s*{re.escape(CONFIDENCE_LABEL)}\s*:', re.IGNORECASE
)


def normalize_confidence(value):
    """Map any record's confidence to exactly 'high' or 'low'.

    Everything that is not an explicit 'high' becomes 'low'. A missing, unknown
    or malformed value must fail towards 'low' — presenting an unverified
    coordinate as trusted is the failure Yury hit.
    """
    return "high" if str(value).strip().lower() == "high" else "low"


def annotate_stop_text(stop_text, confidence):
    """Return stop_text with a single `Coordinate-Confidence:` line.

    Idempotent: if the stop already carries the line it is rewritten in place
    rather than duplicated, so re-running generation or re-annotating a
    round-tripped file cannot stack the field.
    """
    conf = normalize_confidence(confidence)
    new_line = f"{CONFIDENCE_PREFIX} {conf}"

    lines = stop_text.split('\n')

    # If the field already exists, replace it where it stands.
    for i, line in enumerate(lines):
        if _EXISTING_CONFIDENCE_RE.match(line):
            lines[i] = new_line
            return '\n'.join(lines)

    # Otherwise, insert right after the Coordinates: line.
    for i, line in enumerate(lines):
        if _COORD_LINE_RE.match(line):
            lines.insert(i + 1, new_line)
            return '\n'.join(lines)

    # No Coordinates: line at all — the map will not plot this stop anyway, but
    # the field must still be present and 'low'. Put it after the title line
    # (first non-empty line) so it stays with the stop's metadata.
    for i, line in enumerate(lines):
        if line.strip():
            lines.insert(i + 1, new_line)
            return '\n'.join(lines)

    # Empty stop text: return the field alone rather than dropping it.
    return new_line


def annotate_text_content(text_content, geo_records=None):
    """Add the confidence line to every stop in a text_content list.

    `text_content` is the list of per-stop strings the modernized service turns
    into `audio_N.txt`. `geo_records` is the list `geocode_stops.correct_stops`
    returns, aligned by index. When records are absent or shorter than the stop
    list — a geocoder import failure, or GEOCODE_STOPS=0 having produced fewer
    records — the missing stops are marked 'low' rather than skipped.

    Returns a new list; does not mutate the input.
    """
    records = geo_records or []
    out = []
    for i, stop_text in enumerate(text_content):
        rec = records[i] if i < len(records) else None
        conf = rec.get("confidence") if isinstance(rec, dict) else None
        out.append(annotate_stop_text(stop_text, conf))
    return out
