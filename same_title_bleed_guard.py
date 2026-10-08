#!/usr/bin/env python3
"""same_title_bleed_guard.py — LOCAL-623 defect 1: one work = one stop.

Museum Folkwang tour 468, Stop 1 is **Honoré Daumier's unfinished *Ecce Homo***.
Its narration then appended, as if the same object:

    "Lovis Corinth painted Ecce Homo in 1925 as an oil painting on canvas.
     In keeping with a long-standing artistic tradition, he chose to represent
     himself as the figure of Christ … The work emerged from an expressionistic
     style that Corinth developed late in his career …"

That is a DIFFERENT work (a 1925 self-portrait-as-Christ) by a DIFFERENT artist
(Lovis Corinth), in a different museum — pulled in by a web/snippet search on the
bare title "Ecce Homo" and never bound to the stop's own artist. A listener
standing in front of Daumier's canvas is told about Corinth's.

The durable fix is a BINDING, not a blocklist: each stop is bound to its
``{title, artist}``. A sentence that names the stop's TITLE while attributing it
to a DIFFERENT artist — or that is anchored on an artist who is not the stop's —
is a same-title (or wrong-artist) bleed and is dropped before the prose is
spoken. The stop's own artist, and any sentence that names neither a conflicting
artist nor a same-title-by-another-hand, is untouched.

Pure (no network, no LLM, no DB), deterministic, idempotent. Applied to the
delivered tour text (per stop) exactly like the other D611/D617/D620 body
filters, and usable on the evidence snippets before narration.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "surname_of",
    "artists_in_sentence",
    "sentence_is_bleed",
    "filter_stop_body_same_title",
    "filter_tour_text_same_title",
]

# A capitalised personal-name span (optionally with a particle: "van", "de").
# Used to find the AGENT a creation verb attributes the work to.
_NAME_SPAN = (
    r"[A-ZÀ-ÖØ-Þ][a-zà-ÿ]+(?:\s+(?:van|von|de|del|della|di|du|la|le|les|des|da)\b)?"
    r"(?:\s+[A-ZÀ-ÖØ-Þ][a-zà-ÿ]+){0,3}"
)

# "<Name> painted/created/made/produced/sculpted/drew/… <…>" — the agent that a
# creation/attribution verb names as the maker.
_ATTRIBUTION_RE = re.compile(
    r"\b(" + _NAME_SPAN + r")\s+"
    r"(?:painted|created|made|produced|sculpted|drew|executed|rendered|"
    r"designed|cast|carved|composed|conceived|completed|finished|"
    r"depicted\s+himself|depicted\s+herself)\b"
)

# "by <Name>" attribution tail: "Ecce Homo by Lovis Corinth".
_BY_ATTRIBUTION_RE = re.compile(r"\bby\s+(" + _NAME_SPAN + r")\b")

_PARTICLES = {"van", "von", "de", "del", "della", "di", "du", "la", "le",
              "les", "des", "da"}

# Words that look capitalised at a sentence start but never head a personal name.
_NON_NAME_LEAD = {
    "the", "this", "that", "these", "those", "a", "an", "in", "on", "at", "by",
    "from", "with", "for", "standing", "before", "visitors", "together",
    "orientation", "directions", "as", "it", "its", "his", "her", "their",
}


def surname_of(name: str) -> str:
    """Last non-particle token of a personal name, lower-cased.

    "Lovis Corinth" → "corinth"; "Honoré Daumier" → "daumier";
    "Jean-Baptiste-Camille Corot" → "corot"; "Vincent van Gogh" → "gogh".
    """
    toks = [t for t in re.split(r"\s+", (name or "").strip()) if t]
    for t in reversed(toks):
        tl = t.lower().strip(".,;:")
        if tl and tl not in _PARTICLES:
            return tl
    return (toks[-1].lower() if toks else "")


def _name_matches_stop_artist(name: str, stop_artist: str) -> bool:
    """True when ``name`` is (plausibly) the stop's own artist.

    Surname match is enough — "Corot" matches "Jean-Baptiste-Camille Corot".
    An empty stop artist matches nothing (we cannot bind, so never claim a match).
    """
    if not stop_artist:
        return False
    s_name = surname_of(name)
    s_stop = surname_of(stop_artist)
    return bool(s_name and s_stop and s_name == s_stop)


def artists_in_sentence(sentence: str) -> List[str]:
    """Every name a creation/attribution construction names as a maker.

    Returns the matched name spans (as written). Only names bound to a creation
    verb ("X painted") or a "by X" attribution are returned — a passing mention
    of a person who is not credited as the maker is not an attribution.
    """
    out: List[str] = []
    seen = set()
    for m in _ATTRIBUTION_RE.finditer(sentence or ""):
        name = m.group(1).strip()
        lead = name.split()[0].lower() if name.split() else ""
        if lead in _NON_NAME_LEAD:
            continue
        if name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    for m in _BY_ATTRIBUTION_RE.finditer(sentence or ""):
        name = m.group(1).strip()
        lead = name.split()[0].lower() if name.split() else ""
        if lead in _NON_NAME_LEAD:
            continue
        if name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def _title_tokens(title: str) -> List[str]:
    """Significant words of a work title, lower-cased (drops articles/punct)."""
    raw = re.findall(r"[A-Za-zà-ÿ]+", (title or "").lower())
    _stop = {"the", "a", "an", "of", "and", "le", "la", "les", "du", "des",
             "el", "il", "der", "die", "das", "ein", "eine"}
    return [w for w in raw if w not in _stop and len(w) > 1]


def _names_the_title(sentence: str, title: str) -> bool:
    """True when the sentence names the stop's work title (all significant tokens)."""
    toks = _title_tokens(title)
    if not toks:
        return False
    low = sentence.lower()
    return all(re.search(r"\b" + re.escape(t) + r"\b", low) for t in toks)


def sentence_is_bleed(sentence: str, stop_title: str, stop_artist: str,
                      _wrong_artist_surnames: Optional[set] = None) -> bool:
    """True when a sentence is a same-title / wrong-artist bleed for this stop.

    A sentence bleeds when EITHER:
      • it names the stop's TITLE and attributes it to an artist whose surname is
        NOT the stop's artist (same title, different hand — the Corinth case); OR
      • it attributes a creation to an artist who is not the stop's artist AND the
        stop artist is known (a wrong-artist sentence that entered this stop); OR
      • it is a follow-on sentence anchored on a wrong artist already seen in this
        stop (``_wrong_artist_surnames`` carries their surnames) and names no
        other maker — "The work emerged from an expressionistic style that
        Corinth developed …".

    Never fires when the stop artist is unknown (nothing to bind to), and never
    drops a sentence whose only named maker IS the stop's artist.
    """
    s = (sentence or "").strip()
    if not s or not stop_artist:
        return False

    attributed = artists_in_sentence(s)
    foreign = [n for n in attributed if not _name_matches_stop_artist(n, stop_artist)]

    # same title named + attributed to a different hand → bleed
    if foreign and _names_the_title(s, stop_title):
        return True
    # a creation attributed to a non-stop artist → wrong-artist bleed
    if foreign:
        return True

    # follow-on sentence anchored on a wrong artist seen earlier in this stop,
    # naming no competing stop-artist attribution.
    if _wrong_artist_surnames:
        # the sentence must mention one of the wrong surnames and must NOT name
        # the stop's own artist (so we never drop a real stop-artist sentence).
        low = s.lower()
        names_wrong = any(re.search(r"\b" + re.escape(sur) + r"\b", low)
                          for sur in _wrong_artist_surnames)
        names_stop = bool(re.search(r"\b" + re.escape(surname_of(stop_artist)) + r"\b", low))
        if names_wrong and not names_stop:
            return True
    return False


def _split_sentences(text: str) -> List[str]:
    try:
        from sentence_split import split_sentences as _ss
        return [s for s in _ss(text or "") if s and s.strip()]
    except Exception:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


# A sentence that opens with a bare third-person pronoun subject (optionally after
# a leading adverbial clause): "He chose …", "In keeping with tradition, he chose …".
_LEADING_PRONOUN_RE = re.compile(r"(?i)^\s*(?:[^,.]{0,60},\s+)?(he|she)\b")


def _leads_with_dangling_pronoun(sentence: str, stop_artist: str) -> bool:
    """True when the sentence's subject is a bare he/she and it does NOT name the
    stop's own artist — so, right after a dropped bleed, its antecedent is gone.
    """
    s = (sentence or "").strip()
    if not _LEADING_PRONOUN_RE.match(s):
        return False
    sur = surname_of(stop_artist)
    if sur and re.search(r"\b" + re.escape(sur) + r"\b", s.lower()):
        return False
    return True


def filter_stop_body_same_title(body: str, stop_title: str, stop_artist: str
                                ) -> Tuple[str, Dict]:
    """Drop same-title / wrong-artist bleed sentences from one stop body.

    Walks the body sentence by sentence. The first time a wrong artist is seen
    (in a sentence that is dropped), its surname is remembered so a following
    sentence that merely elaborates on that wrong artist ("… that Corinth
    developed late in his career") is dropped too. Never empties a body: if every
    sentence would be dropped, the body is returned unchanged (D577).

    Returns (new_body, report) with report = {dropped, bled_artists, changed}.
    """
    report = {"dropped": 0, "bled_artists": [], "changed": False}
    if not body or not body.strip() or not stop_artist:
        return body, report

    sents = _split_sentences(body)
    if len(sents) <= 1:
        return body, report

    wrong_surnames: set = set()
    kept: List[str] = []
    dropped = 0
    prev_dropped_bleed = False
    for s in sents:
        if sentence_is_bleed(s, stop_title, stop_artist, wrong_surnames):
            dropped += 1
            prev_dropped_bleed = True
            for n in artists_in_sentence(s):
                if not _name_matches_stop_artist(n, stop_artist):
                    sur = surname_of(n)
                    if sur:
                        wrong_surnames.add(sur)
                        if n not in report["bled_artists"]:
                            report["bled_artists"].append(n)
            continue
        # A sentence immediately after a dropped bleed that leads with a bare
        # pronoun subject ("He chose …", "She developed …") refers to the wrong
        # artist we just removed — its antecedent is gone, so it dangles. Drop it
        # too, unless it names the stop's own artist.
        if prev_dropped_bleed and _leads_with_dangling_pronoun(s, stop_artist):
            dropped += 1
            prev_dropped_bleed = True  # chain further continuations
            continue
        prev_dropped_bleed = False
        kept.append(s)

    if dropped == 0:
        return body, report
    new_body = " ".join(k.strip() for k in kept if k.strip()).strip()
    if not new_body:  # never empty a stop
        return body, report
    report["dropped"] = dropped
    report["changed"] = True
    return new_body, report


_STOP_HEADER_RE = re.compile(r"(?mi)^(Stop\s+\d+\s*[:\-][^\n]*)$")


def filter_tour_text_same_title(tour_text: str,
                                stop_titles: Optional[Dict[int, str]] = None,
                                stop_artists: Optional[Dict[int, str]] = None
                                ) -> Tuple[str, Dict]:
    """Apply the same-title bleed filter across a delivered tour, per stop.

    Splits on real ``Stop N:`` headers and runs ``filter_stop_body_same_title``
    on each stop's body with that stop's bound ``{title, artist}``. The Stop-1
    opening (About) section and the preamble/conclusion are not special-cased:
    the filter only ever drops a sentence that attributes the stop's title to a
    different artist (or names a wrong artist's creation), which never occurs in
    the About story. Pure string→string. Returns (new_text, report).
    """
    report = {"stops": 0, "dropped": 0, "changed": False, "bled": []}
    if not tour_text or not tour_text.strip():
        return tour_text, report

    parts = _STOP_HEADER_RE.split(tour_text)
    if len(parts) < 3:
        return tour_text, report

    out = [parts[0]]
    i = 1
    stop_index = 0
    total_dropped = 0
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        stop_index += 1
        report["stops"] += 1
        title = (stop_titles or {}).get(stop_index, "") or _title_from_header(header)
        artist = (stop_artists or {}).get(stop_index, "")

        # Filter paragraph by paragraph so blank-line structure is preserved.
        paras = re.split(r"(\n\s*\n)", body)
        new_paras: List[str] = []
        for seg in paras:
            if seg.strip() == "" or re.fullmatch(r"\n\s*\n", seg):
                new_paras.append(seg)
                continue
            filtered, prep = filter_stop_body_same_title(seg, title, artist)
            total_dropped += prep.get("dropped", 0)
            for a in prep.get("bled_artists", []):
                if a not in report["bled"]:
                    report["bled"].append(a)
            new_paras.append(filtered)
        out.append(header)
        out.append("".join(new_paras))
        i += 2

    report["dropped"] = total_dropped
    report["changed"] = total_dropped > 0
    return "".join(out), report


def _title_from_header(header: str) -> str:
    """Pull the work title out of a 'Stop N: <title>' header."""
    m = re.match(r"(?i)^\s*Stop\s+\d+\s*[:\-]\s*(.+?)\s*$", header or "")
    return m.group(1).strip() if m else ""
