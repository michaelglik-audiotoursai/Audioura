"""[D577] Never ship what we can refute.

Michael's ruling, 2026-09-17: *"Providing an uninteresting stop is better than
providing no stop, providing unverified story is better than providing no story.
All we have to do is to be clear and transparent how confident we are."*

So the floor is NOT "verified" — unverified material ships, hedged. The floor is
**not refuted**. Both real failures of September 2026 were refutable by simple
geography, with no deep verification needed:

  * the **Sistine Chapel Ceiling (Vatican City)** offered as a stop at a parish
    church in Newton MA — 6,700 km away (D564);
  * *"canonically recognized in 1966 by Cardinal James Francis McIntyre,
    **Archbishop of Los Angeles**"* narrated about a Newton MA parish, which sits
    in the Archdiocese of Boston — 4,000 km away (D567). The existence gate
    reported `2/2 stops verified (100%)` while this shipped.

**The distinction that keeps this cheap and stops it over-firing.** Distance alone
refutes nothing: *"a refuge for Irish Catholic immigrants"* and *"trained in Paris"*
are legitimate history in a Newton tour. What is refutable is a **binding claim** —
a distant place asserted as the location, jurisdiction or container OF the venue or
stop. "Irish immigrants" mentions Ireland; "Archbishop of Los Angeles recognized
this parish" binds the parish to Los Angeles.

Deterministic, no network of its own: the geocoder is injected.
"""

import math
import re

# A binding claim ties the venue/stop TO a place. Group 'place' is the bound place.
_BINDING_PATTERNS = (
    # ecclesiastical / civil jurisdiction — the D567 case
    r'\b(?:Arch)?[Bb]ishop\s+of\s+(?P<place>[A-Z][\w.\'-]*(?:\s+[A-Z][\w.\'-]*){0,3})',
    r'\bArchdiocese\s+of\s+(?P<place>[A-Z][\w.\'-]*(?:\s+[A-Z][\w.\'-]*){0,3})',
    r'\b[Dd]iocese\s+of\s+(?P<place>[A-Z][\w.\'-]*(?:\s+[A-Z][\w.\'-]*){0,3})',
    # physical containment
    r'\blocated\s+(?:in|at|within)\s+(?P<place>[A-Z][\w.\'-]*(?:\s+[A-Z][\w.\'-]*){0,3})',
    r'\bhoused\s+(?:in|at)\s+(?P<place>[A-Z][\w.\'-]*(?:\s+[A-Z][\w.\'-]*){0,3})',
    r'\bsituated\s+(?:in|at|within)\s+(?P<place>[A-Z][\w.\'-]*(?:\s+[A-Z][\w.\'-]*){0,3})',
    r'\bpart\s+of\s+the\s+(?P<place>[A-Z][\w.\'-]*(?:\s+[A-Z][\w.\'-]*){0,3})\s+(?:Archdiocese|Diocese)',
)
_COMPILED = tuple(re.compile(p) for p in _BINDING_PATTERNS)

# A parenthetical place on a STOP name is a location claim about the stop itself:
#   "Sistine Chapel Ceiling (Vatican City)"
_STOP_PARENTHETICAL = re.compile(r'\(([^)]+)\)\s*$')

# How far is too far for a BOUND place. Generous on purpose: this refutes the
# indefensible, it does not enforce a radius. A venue and its own jurisdiction or
# container are in the same metropolitan area; 150 km clears any of those while
# still catching Boston->Los Angeles and Newton->Vatican City.
DEFAULT_REFUTE_KM = 150.0


def haversine_km(a, b):
    """Great-circle distance in km between (lat, lng) pairs."""
    lat1, lng1 = float(a[0]), float(a[1])
    lat2, lng2 = float(b[0]), float(b[1])
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _normalise_place(raw):
    """Trim the sentence punctuation the name pattern swallows.

    `[\w.'-]*` has to admit the dot so "St. Louis" and "Washington D.C." survive,
    which means it also eats the full stop that ends a sentence. Strip trailing
    punctuation, but keep a dot that belongs to an abbreviation ("D.C.", "St.") —
    those end in a single capital or a known abbreviation, not a word.
    """
    place = (raw or '').strip()
    # A place name never spans a sentence boundary. The name pattern admits the dot
    # (for "St. Louis", "Washington D.C."), so on real prose it happily swallows the
    # start of the NEXT sentence: "Archbishop of Los Angeles. His act marked..." was
    # captured whole as "Los Angeles. His" and then failed to geocode, letting the
    # refuted claim through. Found only by running this against a real tour, not a
    # fixture — the D568 lesson applied to this module. A period after a lowercase
    # letter followed by a capital is a sentence end; "D.C." is not (capital before).
    place = re.split(r'(?<=[a-z])\.\s+(?=[A-Z])', place)[0].strip()
    while place and place[-1] in '.,;:':
        stem = place[:-1]
        # "Washington D.C." -> stem ends "D.C" ... the dot was part of the name.
        if place[-1] == '.' and re.search(r'(?:^|[\s.])[A-Z]$', stem):
            break
        place = stem.strip()
    return place


def find_bound_places(text):
    """Return [(place, matched_phrase), ...] for binding claims in `text`.

    Only binding relations — a bare mention of a distant place is NOT returned,
    because it is ordinary history and must keep shipping (D577).
    """
    out, seen = [], set()
    for rx in _COMPILED:
        for m in rx.finditer(text or ''):
            place = _normalise_place(m.group('place'))
            if place and place.lower() not in seen:
                seen.add(place.lower())
                out.append((place, m.group(0).strip()))
    return out


def refute_claims(text, anchor, geocoder, refute_km=DEFAULT_REFUTE_KM):
    """Find binding claims in `text` that a distant place refutes.

    `anchor` is the tour venue's (lat, lng). `geocoder` maps a place name to
    (lat, lng) or None — injected, so this module never touches the network and
    tests run offline.

    Returns {"refuted": [{place, phrase, km}], "checked": n, "unresolved": [...]}.
    A place the geocoder cannot resolve is NOT refuted — unresolved is unverified,
    and unverified ships (D577).
    """
    rec = {"refuted": [], "checked": 0, "unresolved": []}
    if not anchor:
        return rec
    for place, phrase in find_bound_places(text):
        rec["checked"] += 1
        try:
            pt = geocoder(place)
        except Exception:
            pt = None
        if not pt:
            rec["unresolved"].append(place)
            continue
        km = haversine_km(anchor, pt)
        if km > refute_km:
            rec["refuted"].append({"place": place, "phrase": phrase, "km": round(km, 1)})
    return rec


def refute_stop_by_distance(stop_name, anchor, geocoder, refute_km=DEFAULT_REFUTE_KM):
    """Refute a STOP whose own name places it far from the tour venue.

    Catches `Sistine Chapel Ceiling (Vatican City)` offered in Newton MA. Uses the
    trailing parenthetical when present, else the whole name. Unresolvable -> not
    refuted (D577).
    """
    name = (stop_name or '').strip()
    if not name or not anchor:
        return None
    m = _STOP_PARENTHETICAL.search(name)
    probe = m.group(1).strip() if m else name
    try:
        pt = geocoder(probe)
    except Exception:
        pt = None
    if not pt:
        return None
    km = haversine_km(anchor, pt)
    if km > refute_km:
        return {"stop": name, "resolved_as": probe, "km": round(km, 1)}
    return None
