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
    "object_kind_of",
    "infer_stop_kind_from_body",
    "sentence_is_object_type_bleed",
    "filter_stop_body_object_type",
    "filter_tour_text_object_type",
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


# [LOCAL-636 issue 1] Style / technique / signature nouns that an artist "owns".
# A sentence saying "<Name>'s pointillist METHOD" / "<Name>'s STYLE" attributes a
# way of working to a named artist WITHOUT a creation verb, so artists_in_sentence
# (which keys on "X painted" / "by X") does not see it. On the Courtauld tour the
# Cézanne stop opened with "a hallmark of Seurat's pointillist method" — the
# Seurat stop's viewing text bled in. When the foreign artist is named this way
# and the stop's OWN artist is not named in the sentence, it is foreign content.
_TECHNIQUE_NOUN = (
    r"(?:method|technique|style|manner|approach|hallmark|signature|"
    r"brushwork|handling|palette|pointillis\w*|chromoluminaris\w*|"
    r"divisionis\w*|impasto|sfumato|chiaroscuro|facture)")
# "<Name>'s [adj] <technique-noun>". The NAME is matched case-sensitively (a
# capitalised span) — IGNORECASE here would let the uppercase class match a
# lowercase lead word ("hallmark of Seurat"), swallowing the preposition. Both a
# straight (') and a curly (’) apostrophe are accepted; the technique noun stays
# case-insensitive via an inline (?i:…) group.
_POSSESSIVE_TECHNIQUE_RE = re.compile(
    r"\b(" + _NAME_SPAN + r")['\u2019]s\s+(?:[a-zà-ÿ]+\s+){0,2}"
    r"(?i:" + _TECHNIQUE_NOUN + r")\b")


def _possessive_technique_artists(sentence: str) -> List[str]:
    """Names credited with a STYLE/TECHNIQUE via a possessive ("Seurat's
    pointillist method"), as written. Not a creation attribution, so these are
    found separately from artists_in_sentence."""
    out, seen = [], set()
    for m in _POSSESSIVE_TECHNIQUE_RE.finditer(sentence or ""):
        name = m.group(1).strip()
        lead = name.split()[0].lower() if name.split() else ""
        if lead in _NON_NAME_LEAD:
            continue
        if name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


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
        Corinth developed …"; OR
      • [LOCAL-636] it credits a STYLE/TECHNIQUE to a foreign artist via a
        possessive ("a hallmark of Seurat's pointillist method") while the stop's
        OWN artist is not named — the Seurat viewing text that bled into the
        Cézanne stop.

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

    # [LOCAL-636] a style/technique credited to a FOREIGN artist possessively
    # ("Seurat's pointillist method") while the stop's own artist is NOT named in
    # the sentence → foreign-content bleed. The stop-artist guard keeps a genuine
    # comparison that names the stop's own artist ("unlike Monet's method,
    # Cézanne …") from being dropped.
    tech = _possessive_technique_artists(s)
    tech_foreign = [n for n in tech if not _name_matches_stop_artist(n, stop_artist)]
    if tech_foreign:
        names_stop = bool(
            re.search(r"\b" + re.escape(surname_of(stop_artist)) + r"\b", s.lower()))
        if not names_stop:
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


# ── [LOCAL-626 item 5] OBJECT-TYPE bleed ──────────────────────────────────────
#
# Tour 485 Stop 3 is "Footed Bowl with the Crucifixion" — a maiolica BOWL. Its
# narration then said: "this Crucifixion PANEL was specifically created for a
# hospital chapel." A panel is a flat wooden painting support — a different KIND
# of object from a bowl. The same-title bleed above binds TITLE→ARTIST; this binds
# TITLE→OBJECT KIND, so a sentence that re-labels the stop's object as an
# incompatible physical kind (bowl called a panel/canvas/sculpture/…) is dropped.
#
# Object-kind families. Each maps a surface noun to a canonical family; two works
# in DIFFERENT families are physically incompatible. Within one family (bowl/dish/
# plate = vessel; painting/canvas/panel = picture) nouns are compatible synonyms,
# so "the painting" never conflicts with "the canvas".
_OBJECT_KIND_FAMILIES = {
    # ceramic / vessel
    "bowl": "vessel", "footed bowl": "vessel", "dish": "vessel", "plate": "vessel",
    "platter": "vessel", "cup": "vessel", "vase": "vessel", "ewer": "vessel",
    "jar": "vessel", "jug": "vessel", "pitcher": "vessel", "tazza": "vessel",
    "charger": "vessel", "maiolica": "vessel", "majolica": "vessel",
    "porcelain": "vessel", "pottery": "vessel", "ceramic": "vessel",
    "urn": "vessel", "amphora": "vessel", "chalice": "vessel",
    # flat picture
    "painting": "picture", "canvas": "picture", "panel": "picture",
    "altarpiece": "picture", "fresco": "picture", "watercolour": "picture",
    "watercolor": "picture", "oil": "picture", "diptych": "picture",
    "triptych": "picture", "miniature": "picture",
    # works on paper
    "drawing": "paper", "print": "paper", "etching": "paper", "engraving": "paper",
    "lithograph": "paper", "woodcut": "paper", "sketch": "paper",
    "watercolour on paper": "paper",
    # three-dimensional
    "sculpture": "sculpture", "statue": "sculpture", "bust": "sculpture",
    "relief": "sculpture", "bronze": "sculpture", "marble": "sculpture",
    "figurine": "sculpture", "carving": "sculpture",
    # textile / furniture / other
    "tapestry": "textile", "textile": "textile", "rug": "textile",
    "furniture": "furniture", "cabinet": "furniture", "chair": "furniture",
    "table": "furniture", "clock": "clock", "medal": "medal", "coin": "coin",
    "manuscript": "manuscript", "book": "manuscript",
}

# Longest keys first so "footed bowl" / "watercolour on paper" win over "bowl".
_OBJECT_KIND_KEYS = sorted(_OBJECT_KIND_FAMILIES, key=len, reverse=True)

# [LOCAL-626 item 5] Nouns that are too ambiguous to be a KIND assertion on their
# own: "painting"/"drawing"/"print" also name the decoration/activity ("the
# painting on the bowl", "the drawing of the figure"), and material words
# ("ceramic", "oil", "marble", "bronze") describe the stop object itself. These
# resolve a stop's OWN kind (via object_kind_of on the title/material) but must
# NOT, by themselves, be read as re-labelling the object a different kind — only
# an unambiguous physical-object noun (panel, canvas, bowl, statue, tapestry, …)
# triggers an object-type bleed. This keeps "The painting was not chosen at
# random" (about the bowl's painted scene) from being mistaken for a panel claim.
_AMBIGUOUS_KIND_NOUNS = {
    "painting", "drawing", "print", "oil", "ceramic", "pottery", "porcelain",
    "maiolica", "majolica", "marble", "bronze", "watercolour", "watercolor",
    "miniature", "book", "sketch",
}

# Demonstrative reference to the stop's own object: "this bowl", "this panel",
# "this Crucifixion panel", "the painted ceramic", "the altarpiece". After a
# this/the/that, up to three intervening words (adjectives, the title noun) may
# precede the object noun, so "this Crucifixion panel" is read as a PANEL claim.
# Demonstrative reference to the stop's own object: "this bowl", "this panel",
# "this Crucifixion panel", "the painted ceramic", "the altarpiece". After a
# this/that/the, we scan the next few words for ANY object-kind noun, so
# "this Crucifixion panel" is read as a PANEL (picture) claim even though an
# adjective/title-noun sits between the demonstrative and the object noun.
_DEMONSTRATIVE_RE = re.compile(r"(?i)\b(?:this|that|the)\b")
_WORD_RE = re.compile(r"[A-Za-zà-ÿ']+")
# How many words after a demonstrative to scan for an object noun.
_OBJ_WINDOW = 4


def object_kind_of(*texts: str) -> Optional[str]:
    """Canonical object FAMILY implied by any of the given texts (title first,
    then material/period hints). Returns the family string ("vessel", "picture",
    …) or None when no object noun is present. The FIRST text that resolves a
    family wins, so pass the title before looser corpus text.
    """
    for text in texts:
        low = (text or "").lower()
        if not low:
            continue
        for key in _OBJECT_KIND_KEYS:
            if re.search(r"\b" + re.escape(key) + r"\b", low):
                return _OBJECT_KIND_FAMILIES[key]
    return None


def _asserted_kinds(sentence: str) -> List[str]:
    """Object FAMILIES a sentence asserts via a 'this/that/the <…> <noun>'
    reference. For each demonstrative, scan the next few words and collect every
    object-kind noun found (so "this Crucifixion panel" yields the panel family).
    """
    low = (sentence or "").lower()
    words = _WORD_RE.findall(low)
    # index each word's position so we can window after a demonstrative
    out: List[str] = []
    for i, w in enumerate(words):
        if w in ("this", "that", "the"):
            window = words[i + 1:i + 1 + _OBJ_WINDOW]
            for j, wj in enumerate(window):
                # support the two-word key "footed bowl"
                if wj == "footed" and j + 1 < len(window):
                    fam = _OBJECT_KIND_FAMILIES.get("footed " + window[j + 1])
                    if fam:
                        out.append(fam)
                        continue
                if wj in _AMBIGUOUS_KIND_NOUNS:
                    continue  # too ambiguous to be a KIND re-label on its own
                fam = _OBJECT_KIND_FAMILIES.get(wj)
                if fam:
                    out.append(fam)
    return out


def sentence_is_object_type_bleed(sentence: str, stop_kind: Optional[str]) -> bool:
    """True when a sentence re-labels the stop's object as an INCOMPATIBLE kind.

    Fires only when (a) the stop's own object family is known, and (b) the
    sentence makes a demonstrative reference ("this <noun>"/"the <noun>") whose
    noun belongs to a DIFFERENT family — the "this Crucifixion panel" (picture)
    on a stop whose object is a bowl (vessel). A sentence that uses a compatible
    synonym within the same family ("the vessel", "the dish") never fires, and a
    sentence with no demonstrative object reference never fires.
    """
    if not stop_kind:
        return False
    kinds = _asserted_kinds(sentence)
    return any(k != stop_kind for k in kinds)


# [LOCAL-636 issue 1] An unambiguous object noun DECLARED about the stop's own
# object, e.g. "is an oil and resin painting on panel", "these monumental oils on
# wood", "the canvas before you". When the title carries no object noun (a work
# titled only by its subject — "Leda col cigno") and the POI material field is
# empty, the stop's own kind is still stated plainly in its narration. We read the
# DOMINANT declared family from the body so a lone cross-genre sentence (a
# sculpture condition blurb lifted into a painting stop) can still be caught.
#
# Only unambiguous physical-object nouns vote (the _AMBIGUOUS_KIND_NOUNS set is
# excluded) so "the painting on the bowl" never mislabels a vessel as a picture.
# A medium phrase such as "oil ON panel" / "oils on wood" is a reliable picture
# declaration, so "panel"/"wood"/"canvas"/"paper" following "oil(s)/tempera/
# acrylic/watercolour on" is counted even though those nouns alone are generic.
_MEDIUM_ON_SUPPORT_RE = re.compile(
    r"(?i)\b(?:oil|oils|tempera|acrylic|watercolou?r|gouache|fresco)\b"
    r"[^.?!]{0,40}?\bon\b\s+(?:a\s+)?(panel|canvas|wood|paper|copper|board)\b")
_SUPPORT_FAMILY = {
    "panel": "picture", "canvas": "picture", "wood": "picture",
    "board": "picture", "copper": "picture", "paper": "paper",
}


def _declared_kinds_in_body(body: str) -> List[str]:
    """Every object FAMILY the body declares about its OWN object, via an
    unambiguous object noun or a 'medium ON support' phrase. Ambiguous nouns
    (painting/drawing/oil/marble …) do NOT vote on their own, mirroring
    _asserted_kinds, so a decoration or technique mention is never a kind claim.
    """
    low = (body or "").lower()
    out: List[str] = []
    for m in _MEDIUM_ON_SUPPORT_RE.finditer(low):
        fam = _SUPPORT_FAMILY.get(m.group(1))
        if fam:
            out.append(fam)
    for key in _OBJECT_KIND_KEYS:
        if key in _AMBIGUOUS_KIND_NOUNS:
            continue
        if re.search(r"\b" + re.escape(key) + r"\b", low):
            out.append(_OBJECT_KIND_FAMILIES[key])
    return out


def infer_stop_kind_from_body(body: str) -> Optional[str]:
    """Best-guess the stop's OWN object family from its narration, or None.

    Returns the DOMINANT declared family (the most frequently declared one) when
    the body plainly states its medium/support, so a stop whose title and material
    field carry no object noun can still be bound to a kind. Ties and a body with
    no clear declaration return None (we never guess from a single ambiguous
    mention — that would risk dropping the stop's real content).
    """
    kinds = _declared_kinds_in_body(body)
    if not kinds:
        return None
    counts: Dict[str, int] = {}
    for k in kinds:
        counts[k] = counts.get(k, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None  # no clear majority → do not guess
    return ranked[0][0]


def filter_stop_body_object_type(body: str, stop_title: str,
                                  stop_material: str = "",
                                  stop_kind_override: Optional[str] = None
                                  ) -> Tuple[str, Dict]:
    """Drop object-type bleed sentences from one stop body. Never empties a body
    (D577). Returns (new_body, report) with report = {dropped, stop_kind, changed}.

    [LOCAL-636 issue 1] The stop's own kind is resolved from the title and the POI
    material field first; when neither carries an object noun (a subject-only title
    like "Leda col cigno" with an empty material field) the kind is inferred from
    the body's OWN declared medium ("oil and resin painting on panel" → picture),
    so a lone sculpture-condition sentence bled in from a statue record is still
    dropped. ``stop_kind_override`` lets the tour-level caller resolve the kind
    once from the WHOLE stop body and apply it to each paragraph (the medium is
    often declared in a different paragraph from the bleed).
    """
    report = {"dropped": 0, "stop_kind": None, "changed": False}
    if not body or not body.strip():
        return body, report
    stop_kind = stop_kind_override or object_kind_of(stop_title, stop_material)
    if not stop_kind:
        stop_kind = infer_stop_kind_from_body(body)
    report["stop_kind"] = stop_kind
    if not stop_kind:
        return body, report
    sents = _split_sentences(body)
    if len(sents) <= 1:
        return body, report
    kept, dropped = [], 0
    for s in sents:
        if sentence_is_object_type_bleed(s, stop_kind):
            dropped += 1
            continue
        kept.append(s)
    if dropped == 0:
        return body, report
    new_body = " ".join(k.strip() for k in kept if k.strip()).strip()
    if not new_body:
        return body, report
    report["dropped"] = dropped
    report["changed"] = True
    return new_body, report


def filter_tour_text_object_type(tour_text: str,
                                 stop_titles: Optional[Dict[int, str]] = None,
                                 stop_materials: Optional[Dict[int, str]] = None
                                 ) -> Tuple[str, Dict]:
    """Apply the object-type bleed filter across a delivered tour, per stop.
    Mirrors filter_tour_text_same_title's structure. Pure string→string."""
    report = {"stops": 0, "dropped": 0, "changed": False}
    if not tour_text or not tour_text.strip():
        return tour_text, report
    parts = _STOP_HEADER_RE.split(tour_text)
    if len(parts) < 3:
        return tour_text, report
    out = [parts[0]]
    i, stop_index, total_dropped = 1, 0, 0
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        stop_index += 1
        report["stops"] += 1
        title = (stop_titles or {}).get(stop_index, "") or _title_from_header(header)
        material = (stop_materials or {}).get(stop_index, "")
        # [LOCAL-636 issue 1] Resolve the stop's own kind ONCE from the whole stop
        # body: title/material first, else inferred from the body's declared
        # medium. The medium ("oil … on panel") and the bled sentence ("the
        # sculpture …") usually sit in different paragraphs, so a per-paragraph
        # inference would miss it; a single whole-body kind is applied to each.
        stop_kind = object_kind_of(title, material) or infer_stop_kind_from_body(body)
        paras = re.split(r"(\n\s*\n)", body)
        new_paras: List[str] = []
        for seg in paras:
            if seg.strip() == "" or re.fullmatch(r"\n\s*\n", seg):
                new_paras.append(seg)
                continue
            filtered, prep = filter_stop_body_object_type(
                seg, title, material, stop_kind_override=stop_kind)
            total_dropped += prep.get("dropped", 0)
            new_paras.append(filtered)
        out.append(header)
        out.append("".join(new_paras))
        i += 2
    report["dropped"] = total_dropped
    report["changed"] = total_dropped > 0
    return "".join(out), report
