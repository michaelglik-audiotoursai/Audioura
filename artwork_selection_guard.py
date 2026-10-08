"""artwork_selection_guard.py — LOCAL-629 items 1 & 2.

An art-museum tour's stops are its ARTWORKS, by varied artists — never the
events that happened in its halls, nor the rooms, the building or its
architecture.

Belvedere (tour 492, Kiro 3/10): all three stops were "the Austrian State Treaty
was signed in this hall" — diplomatic EVENTS that merely took place in the
palace. They reached the tour because Wikidata P276 ("location") returns an event
whose location is the venue, and the deterministic selector trusts a
SPARQL-confirmed row as a work without ever asking WHAT KIND of thing it is.
LOCAL-626 #1 stops the VENUE itself becoming a stop, and LOCAL-625 stops a ROOM,
but a signing ceremony, a coronation, a room of state or the building's
architecture still slip through.

Uffizi (tour 489): 3 of 3 stops were Leonardo and there was no Botticelli — the
signature-first sort piled the museum's most-prominent single artist into every
slot.

This module is the deterministic lever against both. It is pure (no network, no
LLM, no DB) so every rule is unit-testable and cannot drift at runtime.

  is_artwork_instance(instance_of_qids)   -> bool
      True when ANY P31 QID is an artwork class (painting / sculpture / drawing /
      print / artwork / decorative-arts object or a known subclass).

  is_nonartwork_instance(instance_of_qids) -> bool
      True when ANY P31 QID is a REJECT class (event, treaty, ceremony,
      building, architectural structure, room, …) — used to drop an entry even
      when its label looks innocent.

  looks_like_event_title(title)           -> bool
      Deterministic multilingual title test for events (treaty, signing,
      coronation, congress, battle, meeting …) and architecture/building
      language, for when P31 is missing or coarse.

  work_has_creator(entry)                 -> bool
      True when a work entry carries a creator / attribution (P170 or a
      "creators" list, or an "attributed to …" alias).

  enforce_artworks_only(works, venue_name, is_art_museum, …) -> (kept, dropped)
      the ITEM-1 filter: for an ART museum, keep only entries that are an
      artwork (by P31 when known; by title/creator signal when P31 is absent)
      and reject events / rooms / the building / architecture. Each dropped entry
      carries a reason so the caller can show the before/after list. Pure and
      order-preserving.

  cap_artist_variety(works, n_stops, …)   -> (kept, dropped)
      the ITEM-2 cap: at most ceil(n_stops / 3) works by any one artist, applied
      to an ALREADY-RANKED list so signature-first still decides WHICH work of a
      given artist leads. A one-artist venue (a Van Gogh / Matisse house museum)
      is detected and left untouched — the cap only bites when the catalogue has
      the artists to satisfy it.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "is_artwork_instance",
    "is_nonartwork_instance",
    "looks_like_event_title",
    "work_has_creator",
    "work_artist_key",
    "enforce_artworks_only",
    "cap_artist_variety",
]

# ─────────────────────────────────────────────────────────────────────────────
# P31 (instance-of) QID sets. Wikidata item-type QIDs for the artwork classes a
# museum stop may be, and for the non-artwork classes a museum stop may NEVER be.
# Kept conservative and well-commented; both are matched by "ANY QID in set".
# ─────────────────────────────────────────────────────────────────────────────

# ARTWORK classes — a work whose P31 is any of these is a stand-in-front-of-it
# object. painting, sculpture, drawing, print, work of art (the superclass),
# plus common decorative-arts / medium subclasses that museums catalogue.
_ARTWORK_INSTANCE_QIDS = frozenset({
    "Q3305213",    # painting
    "Q860861",     # sculpture
    "Q93184",      # drawing
    "Q11060274",   # print
    "Q18761202",   # engraving / etching family (print subclass)
    "Q838948",     # work of art (the superclass)
    "Q4502142",    # visual artwork
    "Q110304307",  # artwork (object) — modern alias
    "Q179700",     # statue
    "Q3917681",    # painting series / cycle member
    "Q46686",      # altarpiece
    "Q207628",     # decorative/painted panel — polyptych panels
    "Q22669857",   # tapestry (decorative-arts object)
    "Q46100",      # fresco
    "Q184811",     # watercolor painting
    "Q18674739",   # decorative arts object
    "Q2576062",    # mural
    "Q106857709",  # porcelain object (decorative arts)
})

# NON-ARTWORK classes — a work whose P31 is any of these is NOT a museum artwork
# stop. Events (treaty, signing, coronation, congress, battle), the building and
# its architecture, and rooms/spaces. The Belvedere "Austrian State Treaty"
# (Q156298, a treaty) is here by class, so it is dropped even though its label
# carries no room number and names no medium.
_NONARTWORK_INSTANCE_QIDS = frozenset({
    # ── events ──────────────────────────────────────────────────────────────
    "Q1190554",    # occurrence / event (superclass)
    "Q1656682",    # event
    "Q625298",     # peace treaty
    "Q131569",     # treaty
    "Q1072326",    # signing (ceremony)
    "Q209158",     # coronation
    "Q2334719",    # legal case
    "Q178561",     # battle
    "Q198",        # war (defensive)
    "Q625994",     # conference
    "Q2495862",    # congress / assembly
    "Q40231",      # election (defensive)
    "Q1656682",    # dup
    "Q18608583",   # recurring event
    "Q13418847",   # historical event
    "Q27968055",   # ceremonial event
    "Q4504495",    # award ceremony
    # ── building / architecture / place ───────────────────────────────────────
    "Q41176",      # building
    "Q811979",     # architectural structure
    "Q24354",      # theatre building (place, not a work)
    "Q33506",      # museum (the institution/building)
    "Q207694",     # art museum (the institution/building)
    "Q2087181",    # historic house
    "Q16560",      # palace
    "Q751876",     # château
    "Q44613",      # monastery
    "Q16970",      # church building
    "Q180958",     # mansion
    "Q1322352",    # architectural element
    "Q1498681",    # façade (architectural element)
    "Q35112127",   # architectural ensemble
    # ── rooms / spaces (belt & braces; room_candidate_guard also covers these)
    "Q180516",     # room
    "Q1360474",    # hall
    "Q2110884",    # exhibition hall / gallery space
})
_NONARTWORK_INSTANCE_QIDS = frozenset(
    q for q in _NONARTWORK_INSTANCE_QIDS if re.fullmatch(r"Q\d+", q))


def _qids(instance_of) -> List[str]:
    """Normalise a P31 value (str, list, or None) to a clean QID list."""
    if not instance_of:
        return []
    if isinstance(instance_of, str):
        vals = [instance_of]
    else:
        vals = list(instance_of)
    out = []
    for v in vals:
        s = str(v or "").strip()
        # accept a bare QID or a Wikidata URI tail
        if "/" in s:
            s = s.rsplit("/", 1)[-1]
        if re.fullmatch(r"Q\d+", s):
            out.append(s)
    return out


def is_artwork_instance(instance_of) -> bool:
    """True when ANY P31 QID is an artwork class. Unknown/empty → False (the
    caller then falls back to the title/creator signal — never a hard reject on
    a missing P31, so a real work with sparse Wikidata is not lost)."""
    return any(q in _ARTWORK_INSTANCE_QIDS for q in _qids(instance_of))


def is_nonartwork_instance(instance_of) -> bool:
    """True when ANY P31 QID is a known non-artwork class (event / building /
    architecture / room). A hard reject signal, independent of the label."""
    return any(q in _NONARTWORK_INSTANCE_QIDS for q in _qids(instance_of))


# ─────────────────────────────────────────────────────────────────────────────
# Title-level event / architecture signal (EN + DE + FR + IT/ES, the live-venue
# languages). Used only when P31 is ABSENT or coarse — a P31 artwork class always
# wins over a title that merely MENTIONS an event ("The Signing of the Treaty",
# a genre painting, keeps its P31=painting).
# ─────────────────────────────────────────────────────────────────────────────

# Event nouns/verbs that, when they are the SUBJECT of the title, mark a histored
# event rather than a work: a signing, a treaty, a coronation, a congress.
_EVENT_TITLE_RE = re.compile(
    r"(?i)(?:^|\b)("
    # English
    r"treaty|signing\s+of|was\s+signed|coronation|congress\s+of|"
    r"declaration\s+of|proclamation\s+of|accession\s+of|abdication|"
    r"battle\s+of|siege\s+of|liberation\s+of|occupation\s+of|"
    r"summit|conference\s+of|armistice|ceasefire|"
    # German
    r"staatsvertrag|vertrag\s+von|unterzeichnung|kr[öo]nung|"
    r"schlacht\s+(?:bei|von|um)|kongress\s+von|"
    # French
    r"trait[ée]\s+de|signature\s+du|couronnement|congr[èe]s\s+de|"
    r"bataille\s+de|si[èe]ge\s+de|"
    # Italian / Spanish
    r"trattato\s+di|tratado\s+de|firma\s+del|coronaci[óo]n|incoronazione|"
    r"batalla\s+de|battaglia\s+di"
    r")\b")

# Architecture / building language as the SUBJECT of the title (the building, its
# façade, its staircase as a monument) — distinct from a painting that merely
# depicts a building.
_ARCHITECTURE_TITLE_RE = re.compile(
    r"(?i)^\s*(?:the\s+|le\s+|la\s+|das\s+|der\s+|die\s+|il\s+|lo\s+)?("
    r"palace|palais|palazzo|palacio|château|chateau|schloss|"
    r"facade|fa[çc]ade|fassade|"
    r"grand\s+staircase|great\s+staircase|main\s+staircase|"
    r"cupola|dome|rotunda|colonnade|portico|"
    r"architecture\s+of|the\s+building\s+of"
    r")\b\s*$")


def looks_like_event_title(title: str) -> bool:
    """True when a candidate title names an EVENT or the BUILDING/architecture,
    not an artwork — a deterministic multilingual fallback for when P31 is absent.

    A genre painting whose title DEPICTS an event ("The Signing of the Declaration
    of Independence") is a real artwork; such a title keeps its P31=painting and
    is therefore handled by ``is_artwork_instance`` upstream. This test only bites
    when there is no artwork P31 to rely on, and only when the event/architecture
    noun is the title's own subject.
    """
    t = (title or "").strip()
    if not t:
        return False
    if _EVENT_TITLE_RE.search(t):
        return True
    if _ARCHITECTURE_TITLE_RE.search(t):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Creator / attribution.
# ─────────────────────────────────────────────────────────────────────────────

_ATTRIBUTION_ALIAS_RE = re.compile(
    r"(?i)\b(attributed\s+to|workshop\s+of|circle\s+of|follower\s+of|"
    r"studio\s+of|school\s+of|after\s+\w)")


def work_has_creator(entry: Dict) -> bool:
    """True when a work entry carries a creator / attribution.

    Accepts a P170 ``creator`` / ``creator_qid``, a non-empty ``creators`` list,
    or an attribution phrase in an alias ("attributed to …", "workshop of …").
    Unknown creator → False; the caller decides whether a missing creator is a
    hard reject (ART museum) or merely a weaker signal.
    """
    if not isinstance(entry, dict):
        return False
    if (entry.get("creator") or "").strip():
        return True
    if (entry.get("creator_qid") or "").strip():
        return True
    creators = entry.get("creators") or []
    if isinstance(creators, (list, tuple)) and any((c or "").strip() for c in creators):
        return True
    for alias in entry.get("aliases", []) or []:
        if _ATTRIBUTION_ALIAS_RE.search(alias or ""):
            return True
    return False


def work_artist_key(entry: Dict) -> str:
    """A normalised artist key for the variety cap. Uses the creator QID when
    present (stable across label spellings), else the normalised creator surname,
    else "" (unknown — never capped against another unknown)."""
    if not isinstance(entry, dict):
        return ""
    qid = (entry.get("creator_qid") or "").strip()
    if qid:
        return qid.lower()
    name = (entry.get("creator") or "").strip()
    if not name:
        creators = entry.get("creators") or []
        if isinstance(creators, (list, tuple)) and creators:
            name = (creators[0] or "").strip()
    if not name:
        return ""
    # normalise: lowercase, drop particles, keep the last token (surname)
    toks = [t for t in re.split(r"[\s,]+", name.lower())
            if t and t not in {"van", "von", "de", "del", "della", "di", "la",
                               "le", "du", "des", "der", "den", "el"}]
    return toks[-1] if toks else name.lower()


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 1 — artworks only, for art museums.
# ─────────────────────────────────────────────────────────────────────────────

def enforce_artworks_only(
    works: Sequence[Dict],
    venue_name: str = "",
    is_art_museum: bool = True,
    *,
    title_key: str = "title",
    require_creator: bool = True,
) -> Tuple[List[Dict], List[Dict]]:
    """[LOCAL-629 item 1] Keep only ARTWORKS; reject events / rooms / building /
    architecture. Returns (kept, dropped); each dropped entry is a shallow copy
    with a ``_reject_reason`` key so the caller can print the before/after list.

    Decision, per entry (order-preserving, pure):
      1. A known NON-ARTWORK P31 (event/treaty/building/architecture/room) →
         REJECT, whatever the label says.
      2. An EVENT or ARCHITECTURE title (when P31 gives no artwork class) →
         REJECT.
      3. A room/space or the venue itself (reuse room_candidate_guard) → REJECT.
      4. Otherwise it must POSITIVELY read as an artwork:
           * a known artwork P31 → KEEP; else
           * ``require_creator`` and a creator/attribution present → KEEP; else
           * no artwork P31 and no creator → REJECT (an ART museum stop must be a
             Wikidata work with a creator/attribution).
      5. When ``is_art_museum`` is False, the positive-artwork requirement in (4)
         is relaxed to "not a known non-artwork and not an event/room title" so a
         history museum / mixed venue is not stripped.

    A missing P31 never hard-rejects on its own; only the combination "no artwork
    P31 AND no creator" (step 4) rejects, and only for an art museum.
    """
    try:
        from room_candidate_guard import (is_room_or_space_title as _is_room,
                                           is_venue_itself_title as _is_venue)
    except Exception:  # pragma: no cover
        _is_room = _is_venue = None

    kept: List[Dict] = []
    dropped: List[Dict] = []

    def _reject(entry: Dict, reason: str):
        d = dict(entry) if isinstance(entry, dict) else {"title": str(entry)}
        d["_reject_reason"] = reason
        dropped.append(d)

    for entry in works or []:
        if not isinstance(entry, dict):
            entry = {title_key: str(entry or "")}
        title = (entry.get(title_key) or entry.get("label_en")
                 or entry.get("label_local") or entry.get("name") or "").strip()
        inst = entry.get("instance_of")

        # 1. hard class reject
        if is_nonartwork_instance(inst):
            _reject(entry, f"nonartwork_class ({','.join(_qids(inst))})")
            continue

        has_artwork_class = is_artwork_instance(inst)

        # 2. event / architecture title (only when no artwork P31 to trust)
        if not has_artwork_class and looks_like_event_title(title):
            _reject(entry, "event_or_architecture_title")
            continue

        # 3. room / venue-itself
        if _is_room is not None and title and _is_room(title, venue_name):
            _reject(entry, "room_or_space_title")
            continue
        if _is_venue is not None and title and _is_venue(title, venue_name):
            _reject(entry, "venue_itself_title")
            continue

        # 4. positive artwork requirement (art museum only)
        if has_artwork_class:
            kept.append(entry)
            continue
        if not is_art_museum:
            # mixed/history venue: no positive-artwork gate, the rejects above suffice
            kept.append(entry)
            continue
        if require_creator and work_has_creator(entry):
            kept.append(entry)
            continue
        # no artwork P31 and no creator → not demonstrably a work
        _reject(entry, "no_artwork_class_and_no_creator")

    return kept, dropped


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 2 — artist variety.
# ─────────────────────────────────────────────────────────────────────────────

def _distinct_artist_count(works: Sequence[Dict]) -> int:
    keys = set()
    unknown = 0
    for w in works or []:
        k = work_artist_key(w)
        if k:
            keys.add(k)
        else:
            unknown += 1
    # unknown-artist works each count as their own distinct "artist" for the
    # purpose of deciding whether a venue is effectively single-artist.
    return len(keys) + (1 if unknown else 0)


def cap_artist_variety(
    works: Sequence[Dict],
    n_stops: int,
    *,
    cap: Optional[int] = None,
) -> Tuple[List[Dict], List[Dict]]:
    """[LOCAL-629 item 2] Cap works per artist at ceil(n_stops / 3).

    ``works`` MUST already be ranked (signature-first): this pass only drops the
    OVERFLOW of an over-represented artist, so the leading (most prominent) work
    of each artist is the one kept. 3 stops → cap 1 (3 different artists); 6 stops
    → cap 2 (at most 2 each).

    Returns (kept, dropped), order-preserving. Works with an UNKNOWN artist are
    never capped against one another (we cannot prove they share a maker).

    A single-artist venue (a Van Gogh / Matisse house museum, where the catalogue
    simply has one artist) is detected — if the number of DISTINCT artists is less
    than the number of stops requested, the cap would make the tour impossible, so
    it is NOT applied and all works are kept. The cap only bites when the catalogue
    actually has the artists to satisfy a varied selection.
    """
    works = list(works or [])
    if n_stops <= 0 or not works:
        return works, []

    eff_cap = cap if cap is not None else max(1, math.ceil(n_stops / 3))

    # Single-artist (or too-few-artists) venue: don't strand the tour. Skip the cap
    # ONLY when applying it could not fill n_stops — i.e. when the catalogue does
    # not have enough distinct artists to supply n_stops works at eff_cap each
    # (distinct_artists * eff_cap < n_stops). A one-artist house museum (a Van Gogh
    # / Matisse venue) hits this and keeps all its works; a multi-artist catalogue
    # that CAN satisfy the cap has it enforced.
    _distinct = _distinct_artist_count(works)
    if _distinct <= 1 or _distinct * eff_cap < n_stops:
        return works, []

    kept: List[Dict] = []
    dropped: List[Dict] = []
    seen: Dict[str, int] = {}
    for w in works:
        key = work_artist_key(w)
        if not key:
            kept.append(w)  # unknown artist — never capped
            continue
        c = seen.get(key, 0)
        if c < eff_cap:
            kept.append(w)
            seen[key] = c + 1
        else:
            d = dict(w)
            d["_reject_reason"] = f"artist_variety_cap (>{eff_cap} by {key})"
            dropped.append(d)
    return kept, dropped
