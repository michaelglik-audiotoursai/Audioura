"""room_candidate_guard.py — [LOCAL-625 item 3] Reject room/gallery/wing/building
candidates from museum stop selection.

A museum tour stop must be an ARTWORK — a {title, artist} record a listener can
stand in front of. On the Alte Pinakothek (tour 471) Stop 2 was
"Alte Pinakothek, Obergeschoss, Kabinett 1-2" — a ROOM, narrated with the
von Klenze building history, not a work. It reached the tour because the
site-first builder's LOCAL-599B "named spaces" fill emits galleries/floors/the
building as stops when the exhibition stops fall short.

This module provides ONE pure predicate, ``is_room_or_space_title``, that
recognises a room / gallery / wing / floor / building name in English, German
and French (the three live-venue languages seen so far). Stop selection uses it
to drop such candidates and replace them from the corpus, so every museum stop
is a work with an artist — never a space narrated as institutional history.

Pure: no network, no LLM, no I/O. Deterministic token test, kept conservative so
an artwork whose TITLE happens to contain a space word in a descriptive way
("The Music Room", "View of the Great Hall") — a painting OF a room — is NOT
rejected: those are only rejected when the title is JUST the space designation
(optionally numbered), e.g. "Kabinett 1-2", "Gallery 3", "Saal II",
"Second Floor", "Obergeschoss".
"""

import re

__all__ = ["is_room_or_space_title", "filter_out_room_candidates"]

# Space / room / building nouns. English + German (Saal, Raum, Kabinett, Flügel,
# Geschoss/Obergeschoss/Erdgeschoss, Gebäude, Halle) + French (salle, aile,
# étage, galerie, cabinet, bâtiment, rez-de-chaussée).
_SPACE_NOUNS = (
    # English
    r"gallery|galleries|room|rooms|hall|halls|wing|wings|floor|floors|"
    r"mezzanine|rotunda|court|courtyard|atrium|lobby|foyer|corridor|landing|"
    r"staircase|stairwell|pavilion|annex|annexe|building|cabinet|cabinets|"
    r"storey|story|basement|ground\s+floor|first\s+floor|second\s+floor|"
    r"third\s+floor|upper\s+floor|lower\s+floor|east\s+wing|west\s+wing|"
    r"north\s+wing|south\s+wing|"
    # German
    r"kabinett|kabinette|saal|s[äa]le|raum|r[äa]ume|fl[üu]gel|halle|"
    r"geschoss|obergeschoss|erdgeschoss|untergeschoss|geb[äa]ude|"
    r"ausstellungsraum|ausstellungssaal|"
    # French
    r"salle|salles|aile|ailes|[ée]tage|galerie|galeries|cabinet|cabinets|"
    r"b[âa]timent|rez-de-chauss[ée]e|niveau"
)

# A numbering/ordinal tail a space often carries: "1-2", "II", "IIa", "No. 3",
# "3", "A", "1a", roman numerals (optionally with a trailing letter: "Saal IIa"),
# "1 & 2".
_NUM_TAIL = (
    r"(?:[\s:.\-–—]*"
    r"(?:no\.?\s*)?"
    r"(?:\d+[a-z]?|[ivxlcdm]+[a-z]?|[a-z])"
    r"(?:\s*[-–—&,]\s*(?:\d+[a-z]?|[ivxlcdm]+[a-z]?|[a-z]))*"
    r")?"
)

# The title is JUST a space designation when, after stripping a leading venue
# qualifier and any floor qualifier, the remaining head is a space noun with only
# an optional number tail — nothing that names a work or a maker.
_SPACE_ONLY_RE = re.compile(
    r"^\s*(?:the\s+|le\s+|la\s+|les\s+|das\s+|der\s+|die\s+)?"
    r"(?:" + _SPACE_NOUNS + r")"
    + _NUM_TAIL +
    r"\s*$",
    re.IGNORECASE,
)

# Floor/level qualifier segments that commonly PREFIX the real space designation
# on German/French pages ("Obergeschoss, Kabinett 1-2"; "1er étage, Salle 5").
_FLOOR_SEG_RE = re.compile(
    r"(?i)^\s*(?:"
    r"obergeschoss|erdgeschoss|untergeschoss|\d+\s*\.?\s*geschoss|"
    r"\d+(?:st|nd|rd|th)?\s+floor|ground\s+floor|upper\s+floor|lower\s+floor|"
    r"\d+(?:er|e|[èe]me)?\s+[ée]tage|rez-de-chauss[ée]e|niveau\s*\d+"
    r")\s*$"
)


def _strip_venue_and_floor_qualifiers(title: str, venue_name: str = "") -> str:
    """Drop a leading venue name and any floor/level qualifier segments so the
    remaining head is the actual space (or work) designation.

    "Alte Pinakothek, Obergeschoss, Kabinett 1-2" → "Kabinett 1-2".
    Comma-separated segments are peeled from the LEFT while they are the venue
    name or a floor qualifier; the first non-qualifier segment onward is kept.
    """
    t = (title or "").strip()
    if not t:
        return t
    vn = (venue_name or "").strip().lower()
    segs = [s.strip() for s in t.split(",")]
    while segs:
        head = segs[0]
        hl = head.lower()
        is_venue = bool(vn) and (hl == vn or hl in vn or vn in hl) and len(segs) > 1
        is_floor = bool(_FLOOR_SEG_RE.match(head)) and len(segs) > 1
        if is_venue or is_floor:
            segs = segs[1:]
            continue
        break
    return ", ".join(segs).strip() if segs else t


def is_room_or_space_title(title: str, venue_name: str = "") -> bool:
    """True when ``title`` names a MUSEUM SPACE (room/gallery/wing/floor/building),
    not an artwork.

    Peels a leading venue name and floor qualifiers, then tests whether the head
    is a bare space noun with only an optional number tail. A painting whose title
    merely mentions a room ("The Music Room", "View of the Great Hall") is NOT
    rejected, because such titles carry additional words beyond the space noun and
    its number. Pure.
    """
    if not title or not title.strip():
        return False
    head = _strip_venue_and_floor_qualifiers(title, venue_name)
    # If, after stripping qualifiers, nothing is left (the title WAS only the venue
    # + a floor), treat it as a space.
    if not head:
        return True
    # The whole stripped head must BE a space designation.
    if _SPACE_ONLY_RE.match(head):
        return True
    # Also catch the case where stripping left only a floor qualifier.
    if _FLOOR_SEG_RE.match(head):
        return True
    return False


def filter_out_room_candidates(candidates, venue_name: str = "",
                               title_key: str = "title"):
    """Return (kept, dropped): candidates split by whether their title names a
    room/space. ``candidates`` is a list of dicts; ``title_key`` selects the title
    field. Order-preserving and pure.
    """
    kept, dropped = [], []
    for c in candidates or []:
        title = ""
        if isinstance(c, dict):
            title = (c.get(title_key) or c.get("name") or "").strip()
        else:
            title = str(c or "").strip()
        if title and is_room_or_space_title(title, venue_name):
            dropped.append(c)
        else:
            kept.append(c)
    return kept, dropped
