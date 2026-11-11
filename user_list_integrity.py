"""[LOCAL-894] Integrity helpers for requests that carry a long free-text
DESCRIPTION and/or a user-chosen stop LIST.

Pure, offline, generic (D769: no place name is hard-coded anywhere here).

Four jobs:
  1. ``derive_request_place`` -- a ``location`` that is really a description
     ("Create a half-day driving tour from X in A to Y in B and back ...") is not
     a place. Derive origin / destination / region from the explicit
     "from X ... to Y" wording, a short generated title (<= 60 chars), a scope
     string covering the whole route, and the request's topic clauses.
  2. ``reject_named_place_candidate`` -- sentence fragments / stopwords parsed out
     of a description are never "named places" (and never announced).
  3. ``stop_place_core`` -- reduce a narrative stop phrase ("Arriving at Ta Cu --
     the mountain and its legends (for the base)") to its place-name core for
     geocoding, and ``strip_qualifier`` -- strip only parenthetical qualifiers
     from a user title (never a named place).
  4. ``request_topics`` / ``topics_for_stop`` -- the "Include ..." clauses, so
     evidence search can be asked for what the listener actually requested.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

DESCRIPTION_MAX_PLACE_CHARS = 80
TITLE_MAX_CHARS = 60
# Sanitised input ceiling for a description. Long enough for a real brief; a
# description is never cut mid-word into a location or a title.
DESCRIPTION_INPUT_MAX = 2000

_SENTENCE_BOUNDARY = re.compile(r"[.!?]\s+[A-Z\u00C0-\u024F]")
_ROUTE_RE = re.compile(
    r"\bfrom\s+(?P<o>[^.;\u2014]+?)\s*,?\s+to\s+(?P<d>[^.;\u2014]+?)"
    r"(?=\s+and\s+(?:back|return)\b|\s+(?:and|then)\s+(?:back|return)\b|[.;\u2014]|$)",
    re.IGNORECASE)
_PROVINCE_WORDS = r"(?:province|prefecture|county|region|state|district|department)"
_TRAILING_ROUTE_NOISE = re.compile(r"\s+(?:and\s+)?(?:back|return(?:ing)?)\s*$", re.I)
_VIA_RE = re.compile(
    r"\b(?:through|via|past|along|across)\s+(?P<v>[A-Z][^.,;\u2014]*?)"
    r"(?=\s+(?:and|to|past|through|via|before|then)\b|[.,;\u2014]|$)")
_TRANSPORT_TITLE = {
    "driving": "Driving", "drive": "Driving", "vehicle": "Driving",
    "biking": "Cycling", "bike": "Cycling", "cycling": "Cycling",
    "walking": "Walking", "boat": "Boat", "sailing": "Boat",
}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip(" \t,;:-\u2013\u2014")


def looks_like_description(location: str) -> bool:
    """True when ``location`` is a request description, not a place name."""
    s = _clean(location)
    if not s:
        return False
    if len(s) > DESCRIPTION_MAX_PLACE_CHARS:
        return True
    if _SENTENCE_BOUNDARY.search(s):
        return True
    words = s.split()
    if len(words) >= 14:
        return True
    if re.match(r"(?i)^(create|make|build|generate|plan|give me|i want|i'd like|please)\b", s):
        return True
    return False


def _split_locality(phrase: str):
    """'Caty Mui Ne Resort in Ham Tien, Mui Ne' -> ('Caty Mui Ne Resort', 'Ham Tien, Mui Ne')."""
    p = _clean(phrase)
    m = re.match(r"^(?P<n>.+?)\s+(?:in|at|near|on)\s+(?P<l>[A-Z\u00C0-\u024F].*)$", p)
    if m:
        return _clean(m.group("n")), _clean(m.group("l"))
    return p, ""


def _region_of(locality: str) -> str:
    """Last locality segment that reads like a province/region, else ''."""
    loc = _clean(locality)
    m = re.search(r"([A-Z\u00C0-\u024F][\w\u00C0-\u024F' -]*?\s+" + _PROVINCE_WORDS + r")\b",
                  loc, re.I)
    if m:
        return _clean(m.group(1))
    return ""


def _transport_label(tour_type: str, text: str) -> str:
    t = (tour_type or "").strip().lower()
    if t in _TRANSPORT_TITLE:
        return _TRANSPORT_TITLE[t]
    for w, lab in _TRANSPORT_TITLE.items():
        if re.search(r"\b" + w + r"\b", (text or "").lower()):
            return lab
    return (t.title() if t else "Audio")


def _cap_title(s: str, limit: int = TITLE_MAX_CHARS) -> str:
    """Cut at a word boundary, never mid-word, never a dangling connector."""
    s = _clean(s)
    if len(s) <= limit:
        return s
    cut = s[:limit].rsplit(" ", 1)[0]
    cut = re.sub(r"(?i)\s+(?:to|and|the|of|in|at|from|-)\s*$", "", cut)
    return _clean(cut)


def short_title(origin: str, destination: str, tour_type: str = "",
                text: str = "", fallback_place: str = "") -> str:
    """A short generated tour name (<= 60 chars): '<origin> to <destination> - <Mode> Tour'."""
    label = _transport_label(tour_type, text)
    suffix = f" - {label} Tour"
    o, d = _clean(origin), _clean(destination)
    if o and d:
        base = f"{o} to {d}"
    else:
        base = o or d or _clean(fallback_place) or "Audio"
    base = _cap_title(base, TITLE_MAX_CHARS - len(suffix))
    return f"{base}{suffix}"


def request_topics(text: str) -> List[str]:
    """Topic clauses from the request's 'Include ...' sentence(s). Generic.

    'its construction' style continuations after a dash are attached to the
    phrase before the dash so each topic stays self-describing.
    """
    t = _clean(text)
    out: List[str] = []
    for m in re.finditer(r"\b(?:include|cover|covering|including|explain|tell(?:ing)?(?: the story of)?)\s+"
                         r"(?P<body>.+?)(?=(?<=[a-z\)])\.\s+[A-Z]|$)", t, re.I):
        body = m.group("body").strip().rstrip(".")
        head, _, tail = body.partition("\u2014")
        if not tail:
            head, _, tail = body.partition(" - ")
        parts = _split_topic_list(head)
        out.extend(parts)
        if tail:
            subject = parts[-1] if parts else ""
            for sub in _split_topic_list(tail):
                out.append(f"{subject} \u2014 {sub}" if subject else sub)
        break  # the first 'Include' clause is the brief's topic list
    seen, uniq = set(), []
    for x in out:
        k = x.lower()
        if x and k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq


def _split_topic_list(s: str) -> List[str]:
    s = re.sub(r",?\s+and\s+(?=(?:the|how|why|its|a|an)\b)", ", ", s, flags=re.I)
    s = re.sub(r"\s+and\s+(?=(?:the|how|why)\s)", ", ", s, flags=re.I)
    return [_clean(p) for p in s.split(",") if _clean(p)]


_TOPIC_STOP = {"the", "and", "of", "in", "for", "its", "how", "why", "is", "are", "a", "an",
               "to", "story", "history", "meaning", "tradition", "region", "famous", "grown",
               "heritage", "construction", "pilgrimage"}


def _toks(s: str) -> set:
    return {w for w in re.findall(r"[a-z\u00C0-\u024F0-9]{3,}", (s or "").lower())
            if w not in _TOPIC_STOP}


def topics_for_stop(topics: List[str], stop_title: str) -> List[str]:
    """Topics whose subject words overlap the stop's title (generic token match)."""
    st = _toks(stop_title)
    if not st:
        return []
    return [t for t in topics if _toks(t) & st]


def derive_request_place(text: str, tour_type: str = "") -> Dict:
    """Derive the place of a described request. Never raises.

    Returns a dict:
      is_description, location (origin place, short), scope (region / route
      string for the scope box), origin, destination, through (list),
      title (<= 60 chars), topics.
    A plain place string returns ``is_description=False`` and itself as location.
    """
    raw = _clean(text)
    res = {"is_description": False, "location": raw, "scope": raw, "origin": "",
           "destination": "", "through": [], "title": "", "topics": [],
           "origin_locality": "", "region": ""}
    if not looks_like_description(raw):
        return res
    res["is_description"] = True
    res["topics"] = request_topics(raw)
    o_name = d_name = o_loc = d_loc = ""
    m = _ROUTE_RE.search(raw)
    if m:
        o_name, o_loc = _split_locality(m.group("o"))
        d_name, d_loc = _split_locality(_TRAILING_ROUTE_NOISE.sub("", m.group("d")))
    res["origin"], res["destination"] = o_name, d_name
    res["origin_locality"] = o_loc
    region = _region_of(d_loc) or _region_of(o_loc) or d_loc or o_loc
    res["region"] = region
    through = []
    for v in _VIA_RE.finditer(raw):
        nm = _clean(v.group("v"))
        if nm and nm not in through and len(nm) <= 40:
            through.append(nm)
    res["through"] = through[:4]
    if o_name:
        loc = ", ".join(x for x in (o_name, o_loc) if x)
        scope_parts = [region] if region else []
        scope_parts += [x for x in (o_name, d_name) if x]
        # The place the tour is set in: the origin's locality ("Ham Tien, Mui Ne")
        # when the origin is a named venue inside one, else the origin itself.
        res["location"] = _cap_title(o_loc or loc, DESCRIPTION_MAX_PLACE_CHARS)
        # The scope is the REGION when the request names one; the route end-points
        # ride along so a box built from them covers origin AND destination.
        res["scope"] = region or ", ".join(scope_parts)
        res["title"] = short_title(o_name, d_name, tour_type, raw)
    else:
        # No explicit route: the first capitalised place-like run is the best we
        # can do; never the raw sentence.
        names = _proper_nouns(raw)
        nm = names[0] if names else ""
        res["origin"] = nm
        res["location"] = nm or _cap_title(raw, 40)
        res["scope"] = res["location"]
        res["title"] = short_title(nm, "", tour_type, raw)
    return res


def _proper_nouns(text: str) -> List[str]:
    found = []
    for m in re.finditer(r"(?<![.!?]\s)(?<!^)\b([A-Z\u00C0-\u024F][\w\u00C0-\u024F'-]+"
                         r"(?:\s+[A-Z\u00C0-\u024F][\w\u00C0-\u024F'-]+)*)", text):
        s = _clean(m.group(1))
        if s and s.lower() not in {"include", "keep", "end", "create"} and s not in found:
            found.append(s)
    return found


def route_place_names(info: Dict) -> List[str]:
    """Origin, through-places, destination, region -- for a scope box."""
    out = []
    for x in [info.get("origin"), *(info.get("through") or []), info.get("destination"),
              info.get("region")]:
        x = _clean(x or "")
        if x and x not in out:
            out.append(x)
    return out


def bbox_covering(points, margin_km: float = 12.0):
    """Bounding box (south, west, north, east) covering all (lat, lng) points + margin."""
    pts = [(float(a), float(b)) for a, b in points if a is not None and b is not None]
    if not pts:
        return None
    import math
    lat0 = sum(p[0] for p in pts) / len(pts)
    dlat = margin_km / 111.0
    dlng = margin_km / (111.0 * max(0.2, math.cos(math.radians(lat0))))
    return (min(p[0] for p in pts) - dlat, min(p[1] for p in pts) - dlng,
            max(p[0] for p in pts) + dlat, max(p[1] for p in pts) + dlng)


def bbox_contains(bbox, lat: float, lng: float) -> bool:
    return bool(bbox) and bbox[0] <= lat <= bbox[2] and bbox[1] <= lng <= bbox[3]


# ── named-place candidate hygiene ────────────────────────────────────────────
_STOPWORDS = {"the", "a", "an", "and", "or", "of", "in", "at", "to", "for", "with", "from",
              "on", "by", "it", "its", "this", "that", "their", "our", "your", "his", "her"}


def reject_named_place_candidate(name: str) -> bool:
    """True when ``name`` must NOT be treated as a named place (and never announced):
    a stopword, a lowercase single word, or text containing a sentence boundary."""
    n = _clean(name)
    if len(n) < 3:
        return True
    if n.lower() in _STOPWORDS:
        return True
    words = n.split()
    if len(words) == 1 and n[:1].islower():
        return True
    if _SENTENCE_BOUNDARY.search(n) or re.search(r"[.!?]$", n) and len(words) > 3:
        return True
    if len(words) > 8:
        return True
    if all(w.lower() in _STOPWORDS for w in words):
        return True
    if n[:1].islower() and len(words) >= 3:
        return True  # a lowercase phrase is prose, not a proper name
    return False


# ── user stop titles ─────────────────────────────────────────────────────────
_PAREN = re.compile(r"\s*[\(\[\uff08][^()\[\]\uff08\uff09]*[\)\]\uff09]")


def strip_qualifier(title: str) -> str:
    """Strip ONLY parenthetical qualifiers; a named place in the title is kept whole."""
    t = _PAREN.sub("", title or "")
    return _clean(t)


_LEAD_VERBS = re.compile(
    r"^(?:arriv(?:e|ing|al)\s+(?:at|in)|leav(?:e|ing)|depart(?:ing)?(?:\s+from)?|"
    r"approach(?:ing)?|reach(?:ing)?|visit(?:ing)?|exploring|explore|welcome\s+to|"
    r"a\s+stop\s+at|stop\s+at)\s+", re.I)
_LEAD_ARTICLE = re.compile(r"^(?:the|a|an)\s+", re.I)
_DASHES = re.compile(r"\s+[\u2013\u2014-]\s+|\s*[\u2013\u2014]\s*|:\s+")


def stop_place_core(title: str) -> str:
    """Place-name core of a narrative stop phrase, for geocoding. The DISPLAY
    title is untouched; this only decides what to look up.

    'Arriving at Ta Cu - the mountain and its legends (for the base)' -> 'Ta Cu'
    'Linh Son Truong Tho Pagoda' -> unchanged
    'Phan Thiet and the Ca Ty River' -> unchanged (a named place after 'and')
    """
    t = strip_qualifier(title)
    head = _DASHES.split(t, maxsplit=1)[0]
    head = _clean(head) or t
    head = _LEAD_VERBS.sub("", head)
    head = _LEAD_ARTICLE.sub("", head)
    head = _clean(head)
    return head or _clean(t)


def core_after_descriptor(title: str, descriptor_words=("mountain", "pagoda", "temple", "river",
                                                       "lake", "beach", "bay", "hill", "falls")) -> str:
    """Append the descriptor the dash-clause names ('Ta Cu - the mountain ...' ->
    'Ta Cu Mountain') when the head alone is a bare proper name."""
    head = stop_place_core(title)
    t = strip_qualifier(title)
    parts = _DASHES.split(t, maxsplit=1)
    if len(parts) == 2 and len(head.split()) <= 3:
        m = re.match(r"(?i)^(?:the\s+)?(" + "|".join(descriptor_words) + r")\b", _clean(parts[1]))
        if m and m.group(1).lower() not in head.lower():
            return f"{head} {m.group(1).title()}"
    return head


def lookup_core(title: str) -> str:
    """Geocoding query for a user stop title: the place-name core, or '' when the
    phrase names no proper noun (nothing to look up -- never invent one)."""
    c = core_after_descriptor(title)
    # a proper noun = a capitalised word that is not the sentence's first article word
    words = c.split()
    if not any(w[:1].isupper() for w in words):
        return ""
    # 'summit views and the drive home' style: lowercase-led phrase with no name
    if c[:1].islower():
        return ""
    return c


def topic_support(topics: List[str], evidence_texts) -> Dict[str, bool]:
    """Does the evidence FOUND support each requested topic? A topic is supported
    when at least half of its distinctive words (>= 4 letters, minus generic
    connectors) appear in the evidence. Pure; never invents -- an unsupported topic
    is reported as unsupported and simply not claimed."""
    ev = " ".join(str(x) for x in (evidence_texts or [])).lower()
    out: Dict[str, bool] = {}
    for t in topics or []:
        # a "subject \u2014 aspect" topic is scored on the ASPECT's own words, so the
        # subject's name alone never counts as covering "its construction".
        _scored = t.split("\u2014", 1)[1] if "\u2014" in t else t
        words = [w for w in re.findall(r"[a-z\u00C0-\u024F]{4,}", _scored.lower())
                 if w not in _TOPIC_STOP - {"construction", "pilgrimage", "meaning",
                                            "heritage", "history", "tradition", "grown"}]
        if not words:
            out[t] = False
            continue
        hit = sum(1 for w in set(words) if w in ev)
        out[t] = hit * 2 >= len(set(words))
    return out


def driving_register_block(title: str, topics: List[str]) -> str:
    """Prompt block for a stop on a DRIVING tour (generic)."""
    seg = bool(re.search(r"(?i)\b(leav|drive|driv|road|along|journey|route|heading|return)", title or ""))
    lines = [
        "\nDRIVING-TOUR REGISTER (critical): the listener is riding in a vehicle, not walking. "
        "Never tell them to walk, step, look around at the street or the pavement, or stand "
        "anywhere; speak to someone watching the road and landscape go by, or, at a stop, "
        "stepping out of the car.",
    ]
    if seg:
        lines.append(
            "This is a DRIVE SEGMENT: give it the longer, unhurried story the listener can "
            "enjoy while the miles pass, built ONLY from the reference material supplied.")
    else:
        lines.append(
            "This is a STOP: keep the segment short and concrete, built ONLY from the "
            "reference material supplied.")
    if topics:
        lines.append(
            "The listener asked this part of the tour to cover: " + "; ".join(topics) +
            ". Cover a topic ONLY where the reference material supports it; if it does not, "
            "leave it out. Never invent a fact, date or name to cover a topic.")
    return "\n".join(lines) + "\n"


_DRIVE_SEG = re.compile(r"(?i)\b(leav\w*|drive|driving|road|along|journey|route|heading|return\w*|"
                        r"country|plantations?|fields?)\b")


def route_topics(topics: List[str], titles: List[str]) -> Dict[str, List[str]]:
    """{title: [topics]} -- each topic to the stop(s) whose title shares its subject
    words; a topic that matches NO stop (a region-wide theme) goes to the drive
    segment(s), else the first stop, so every requested topic is searched once.
    A "why X is famous for it" follow-on rides with the topic before it."""
    out: Dict[str, List[str]] = {t: [] for t in titles}
    if not titles:
        return out
    drives = [t for t in titles if _DRIVE_SEG.search(t)] or [titles[0]]
    prev_home: List[str] = []
    for tp in topics or []:
        homes = [t for t in titles if tp in topics_for_stop([tp], t)]
        if not homes and re.search(r"(?i)\b(it|its|them|they)\b", tp) and prev_home:
            homes = prev_home
        if not homes:
            homes = drives[:1]
        for h in homes:
            if tp not in out[h]:
                out[h].append(tp)
        prev_home = homes
    return out
