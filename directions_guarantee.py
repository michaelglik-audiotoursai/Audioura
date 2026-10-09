#!/usr/bin/env python3
"""directions_guarantee.py — LOCAL-638 Note 4.

Michael listened to Frick tour 523 (D640):
    "The story stops abruptly and has no directions to the next exhibit."
In 523, Stop 2 had no "Your final stop…" transition before Stop 3.

Both base assembly paths DO attach a transition for every stop except the last
(stop_pool_assembly.assemble_building_tour's ``if i < n - 1`` loop; the fresh
render loop's ``if i < len(poi_list) - 1`` branch). But a LATER pass — the editor
(LOCAL-628), a dedupe/era/opener guard, or a conclusion rebuild — can drop the
transition sentence from a stop body, leaving the stop ending abruptly with no
hand-off to the next stop.

This module is the FINAL, every-path guarantee on the DELIVERED text: every stop
except the last MUST end with a transition that names the next stop. The two
functions below are pure, deterministic and idempotent:

  * count_stops_missing_directions(text) — the detector the test asserts is 0.
  * ensure_directions_between_stops(text) — appends a deterministic museum
    transition line to any non-last stop that lacks one, naming the next stop
    (the same templates the assembler uses: "Your final stop in <venue>: <next>."
    for the penultimate stop, else "Continue to <next>."). It never removes a
    stop's own content and never touches the last stop.
"""
import re
from typing import List, Optional, Tuple

try:
    from stop_pool_store import _STOP_HEADER, _SOURCES_LINE
except Exception:  # pragma: no cover - defensive fallback
    _STOP_HEADER = re.compile(r'^Stop (\d+):\s*(.+?)\s*$', re.M)
    _SOURCES_LINE = re.compile(r'(?ms)^\s*Sources:\s.*\Z')

# A bare "That's N stops" count opener (and the thematic/legacy thread openers)
# mark where any trailing conclusion begins — the directions guarantee operates
# only on the STOP BODIES before that.
_COUNT_OPENER = re.compile(r"\bThat['\u2019]s\s+\d+\s+stops?\b", re.IGNORECASE)
_THREAD_OPENER = re.compile(
    r'(?im)^(?:From\s+[^\n]+?\s+to\s+[^\n]+?,\s+you have followed the thread\b'
    r'|On this tour you have followed the thread\b)')

# Field-label lines that are not spoken narration (so they never count as the
# stop's transition and are skipped when we look for the block's last prose).
_FIELD_LINE_RE = re.compile(
    r'(?i)^\s*(address|coordinates|type/specialty|specific examples|'
    r'operational details|museum information|visiting hours|opening hours|hours|'
    r'sources?|tour-category|hours?/admission source)\s*:')

# A line that is itself an explicit directions label.
#
# [LOCAL-646 reg2] ``re.MULTILINE`` is REQUIRED. ``_block_has_transition`` tests
# this regex against the LAST few spoken lines of a stop joined with newlines
# ("\n".join(spoken_lines[-4:])). Without MULTILINE, ``^`` anchors only to the
# very start of that joined string, so an existing walking "Directions:" line
# that is NOT the first of the joined lines is never recognised. In tour 557 the
# "Directions:" line was the 4th (last) of the joined lines, so the guarantee
# treated the stop as missing a hand-off and appended a DUPLICATE "Continue to
# The Old State House." right after the real "Directions: … until you reach the
# iconic Old State House" line. MULTILINE makes ``^`` match the start of each
# physical line, so an existing Directions line anywhere in the tail is seen and
# nothing is added.
_DIRECTIONS_LABEL_RE = re.compile(r'(?im)^\s*directions:\s*\S')

# Transition template cues the assembler/fresh-path emit as the hand-off sentence.
_TRANSITION_CUE_RE = re.compile(
    r'(?i)\b(your\s+final\s+stop\b|continue\s+through\b|continue\s+to\b|'
    r'next\s*:|next\s+is\b|proceed\s+to\b|head\s+(?:to|toward|for)\b|'
    r'walk\s+(?:to|toward|into|through|on\s+to)\b|make\s+your\s+way\s+to\b|'
    r'move\s+(?:to|on\s+to|toward)\b|turn\s+(?:to|toward)\b|'
    r'our\s+(?:next|final)\s+stop\b|the\s+(?:next|final)\s+stop\b)')


def _bare_title(raw: str) -> str:
    """Strip a stop header's trailing ', <year>' / ' by <artist>' decoration."""
    t = re.sub(r',\s*\d{3,4}\s*$', '', (raw or "").strip())
    t = re.sub(r'\s+by\s+.+$', '', t, flags=re.IGNORECASE)
    return t.strip()


def _venue_name(location: str) -> str:
    """Resolve the BUILDING name for the spoken hand-off (mirrors the assembler)."""
    loc = (location or "").strip()
    if not loc:
        return ""
    try:
        from about_museum_stop import clean_venue_request_name
        cleaned = clean_venue_request_name(loc)
        if cleaned:
            return cleaned
    except Exception:
        pass
    return loc.split(",")[0].strip()


def _body_and_tail(text: str) -> Tuple[str, str]:
    """Split the tour into (stop_bodies, trailing_tail). The tail is everything
    from the conclusion/recap opener (or the Sources block) to the end — the
    directions guarantee must never write into it."""
    sources_start = len(text)
    m_src = _SOURCES_LINE.search(text)
    if m_src:
        sources_start = m_src.start()
    headers = list(_STOP_HEADER.finditer(text))
    search_from = headers[-1].end() if headers else 0
    cut = sources_start
    m_thread = _THREAD_OPENER.search(text, search_from)
    if m_thread:
        cut = min(cut, m_thread.start())
    m_count = _COUNT_OPENER.search(text, search_from)
    if m_count:
        cut = min(cut, m_count.start())
    return text[:cut], text[cut:]


def _stop_blocks(body: str) -> List[Tuple[int, int, str]]:
    """Return [(start, end, bare_title)] for every ``Stop N:`` block in ``body``,
    where [start, end) spans from the header to just before the next header."""
    headers = list(_STOP_HEADER.finditer(body))
    out: List[Tuple[int, int, str]] = []
    for idx, h in enumerate(headers):
        start = h.start()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(body)
        out.append((start, end, _bare_title(h.group(2))))
    return out


def _block_has_transition(block: str, next_title: str) -> bool:
    """True when ``block`` already hands off to the next stop.

    A transition is present when, among the block's LAST spoken paragraphs, a line
    either carries an explicit 'Directions:' label, names the next stop's title, or
    uses a movement/next-stop template cue. Field-label lines are ignored."""
    nt = (next_title or "").strip()
    # Look at the spoken (non-field) lines of the block.
    spoken_lines = [ln for ln in block.split("\n")
                    if ln.strip() and not _FIELD_LINE_RE.match(ln)]
    if not spoken_lines:
        return False
    # The hand-off, when present, is at or near the end of the block. Inspect the
    # last few spoken lines so a transition that is its own short paragraph is seen.
    tail = " \n ".join(spoken_lines[-4:])
    if _DIRECTIONS_LABEL_RE.search("\n".join(spoken_lines[-4:])):
        return True
    if nt and nt.lower() in tail.lower() and _TRANSITION_CUE_RE.search(tail):
        return True
    # A template that names the next stop even without a separate cue
    # ("Your final stop in X: <next>.") — cue + title covered above; also accept a
    # bare next-stop template line that the assembler emits.
    if nt and re.search(r'(?i)(your\s+final\s+stop\b|continue\b|next\b|proceed\b)'
                        r'[^.\n]*' + re.escape(nt), tail):
        return True
    return False


def _transition_line(i: int, n: int, next_title: str, venue: str) -> str:
    """The deterministic museum hand-off for position i → i+1 (0-based), matching
    stop_pool_assembly._museum_transition."""
    venue = _venue_name(venue)
    if venue and i == n - 2:
        return f"Your final stop in {venue}: {next_title}."
    return f"Continue to {next_title}."


def count_stops_missing_directions(text: str, venue_name: str = "") -> int:
    """[LOCAL-638 Note 4] The detector the test asserts is 0: how many stops
    (except the last) do NOT end with a transition to the next stop. Pure."""
    if not text or not text.strip():
        return 0
    body, _tail = _body_and_tail(text)
    blocks = _stop_blocks(body)
    if len(blocks) < 2:
        return 0
    missing = 0
    n = len(blocks)
    for i in range(n - 1):          # every stop except the last
        start, end, _title = blocks[i]
        next_title = blocks[i + 1][2]
        if not _block_has_transition(body[start:end], next_title):
            missing += 1
    return missing


def ensure_directions_between_stops(text: str, venue_name: str = "") -> Tuple[str, int]:
    """[LOCAL-638 Note 4] Guarantee every stop except the last ends with a
    transition to the next stop. Returns ``(text, n_added)``.

    For each non-last stop whose body carries no hand-off, append a deterministic
    museum transition line naming the next stop ("Your final stop in <venue>:
    <next>." for the penultimate, else "Continue to <next>."). Deterministic, pure,
    idempotent; never removes content and never touches the last stop or the
    trailing conclusion/Sources block.
    """
    if not text or not text.strip():
        return text or "", 0
    body, tail = _body_and_tail(text)
    blocks = _stop_blocks(body)
    if len(blocks) < 2:
        return text, 0
    n = len(blocks)
    added = 0
    # Rebuild the body back-to-front so earlier offsets stay valid.
    pieces: List[str] = []
    prev_end = len(body)
    for i in range(n - 1, -1, -1):
        start, end, _title = blocks[i]
        block = body[end:prev_end]  # text AFTER this block up to the previous cut
        pieces.append(block)
        seg = body[start:end]
        if i < n - 1:
            next_title = blocks[i + 1][2]
            if not _block_has_transition(seg, next_title):
                line = _transition_line(i, n, next_title, venue_name)
                seg = seg.rstrip() + "\n\n" + line + "\n\n"
                added += 1
        pieces.append(seg)
        prev_end = start
    # Anything before the first header (title block).
    pieces.append(body[:blocks[0][0]])
    new_body = "".join(reversed(pieces))
    if not added:
        return text, 0
    out = new_body.rstrip() + ("\n\n" + tail.lstrip() if tail.strip() else "\n")
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out, added


if __name__ == "__main__":  # pragma: no cover
    import sys
    with open(sys.argv[1], encoding="utf-8") as f:
        t = f.read()
    v = sys.argv[2] if len(sys.argv) > 2 else ""
    print("missing before:", count_stops_missing_directions(t, v))
    fixed, n = ensure_directions_between_stops(t, v)
    print("added:", n, "missing after:", count_stops_missing_directions(fixed, v))
