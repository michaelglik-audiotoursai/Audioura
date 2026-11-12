"""[LOCAL-900] Generic place-name helpers: a short spoken form of a stop title, the kind of a stop, and the
pin-vs-scope check for tours too short for GEO-CHECK. Pure, offline, no place names."""
import math
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

_LEAD_VERB = re.compile(
    r"(?i)^(?:(?:arriving|arrive|arrival|stopping|stop|leaving|leave|departing|depart|driving|drive|walking|walk|"
    r"heading|head|returning|return|continuing|continue|approaching|approach|visiting|visit|exploring|explore|"
    r"reaching|reach|passing|pass|ending|starting|start|finishing|finish)"
    r"(?:\s+(?:at|to|in|from|into|towards?|by|through|past|on|up|down|back))*\s+)+")
_AFTER_SEP = re.compile(r"\s+[–—-]\s+.*$|\s*:\s+.*$")
_TAIL = re.compile(r"(?i)\s+and\s+(?:the\s+)?(?:drive|ride|walk|trip|journey|way)\s+(?:home|back)\s*$|"
                   r"\s+and\s+back\s*$|\s+and\s+(?:the\s+)?return\s*$")


def short_place_name(title: str) -> str:
    """'Arriving at X – the mountain and its legends' -> 'X'; 'The summit views and the drive home' ->
    'the summit views'. Never returns an empty string (falls back to the stripped title)."""
    t = (title or "").strip()
    if not t:
        return t
    s = _AFTER_SEP.sub("", t).strip()
    s = _TAIL.sub("", s).strip()
    s2 = _LEAD_VERB.sub("", s).strip()
    s = s2 or s
    s = s.rstrip(" .,;:!?") or t
    s = re.sub(r"^(The|A|An)\s", lambda m: m.group(1).lower() + " ", s)
    return s


# ── kind of a stop (decides the non-factual sensory sentence) ────────────────
_KIND_RX = (
    ("worship", re.compile(r"(?i)\b(?:pagoda|temple|shrine|monastery|church|cathedral|mosque|abbey|place of worship|buddhist)\b")),
    ("height", re.compile(r"(?i)\b(?:mountain|mount|summit|peak|viewpoint|lookout|overlook|views?|vistas?|"
                          r"cable\s*car|ropeway|gondola|funicular|chairlift|hill|ridge|scenic)\b")),
    ("road", re.compile(r"(?i)\b(?:road|route|highway|plantations?|fields?|farm\w*|paddies|orchards?|vineyards?|"
                        r"agricultur\w*|countryside)\b")),
)


def stop_kind(title: str, type_specialty: str = "") -> str:
    """'worship' | 'height' | 'road' | 'neutral'. Type/Specialty first, then the title."""
    for text in (type_specialty or "", title or ""):
        for kind, rx in _KIND_RX:
            if rx.search(text):
                return kind
    return "neutral"


SENSORY_BY_KIND: Dict[str, Tuple[str, ...]] = {
    "road": ("As you pass {t}, look out at the road, the land around it and the pace of the day.",
             "Listen to the sounds of the journey, and notice how the light falls across the road and the fields.",
             "Settle back and let the scenery tell you what the records do not."),
    "height": ("At {t}, look out at the view and notice how far the land opens below you.",
               "Feel the height and the cooler, thinner air, and listen for the wind.",
               "Let the scenery tell you what the records do not."),
    "worship": ("At {t}, take in the courtyard and the quiet that settles over it.",
                "Listen for the soft sounds of the place, and notice how people move more slowly here.",
                "Stay a moment and let the calm tell you what the records do not."),
    "neutral": ("Take a moment at {t} and take in the place and the pace of the day.",
                "Listen for the sounds that belong to this spot, and notice how the light falls around you.",
                "Stay a while if you can, and let the atmosphere tell you what the records do not."),
}

_WEAK = {"view", "views", "ascent", "ride", "stop", "area", "spot", "drive", "home", "place", "the", "and", "back"}
_GENERIC_STOP = re.compile(r"[^\W_]+", re.U)


def _toks(text: str) -> List[str]:
    return [w.lower() for w in _GENERIC_STOP.findall(text or "")]


def subject_tokens(short_name: str) -> List[str]:
    return [w for w in _toks(short_name) if len(w) >= 3 and w not in _WEAK]


_BAD_NEIGH = re.compile(r"(?i)\b(?:minutes?|hours?|km|kilomet\w*|miles?|http|www|click|book|tickets?|price|vnd|\$|"
                        r"per person|children|adults?)\b|\d{4,}")


_NON_SUBJECT_OPEN = frozenset({
    "will", "to", "and", "but", "or", "with", "which", "that", "of", "in", "on", "at", "for", "by", "from", "as",
    "also", "is", "are", "was", "were", "has", "have", "had", "being", "be", "been", "then", "so", "while",
    "when", "where", "who", "whose", "if", "because", "although", "nearby", "can", "may", "could", "would"})


def _repeated_ngram(sentence: str, n_max: int = 3) -> bool:
    """True when a word, or a 2..n_max-word run, occurs twice IN A ROW or a 2+-word run occurs twice
    anywhere ("<Mountain> <Mountain> is ...", "the lake the lake")."""
    w = _toks(sentence)
    for i in range(len(w) - 1):
        if w[i] == w[i + 1]:
            return True
    for n in range(2, n_max + 1):
        seen = set()
        for i in range(len(w) - n + 1):
            g = tuple(w[i:i + n])
            if g in seen:
                return True
            seen.add(g)
    return False


def is_clean_neighbour_sentence(s: str) -> bool:
    """[LOCAL-902] ONE complete sentence: starts with a capital and a subject (not a verb / conjunction /
    preposition), at most 30 words, no repeated n-gram, not a fragment, a single terminal stop."""
    x = (s or "").strip()
    if not x or not x[0].isalpha() or not x[0].isupper():
        return False
    words = x.split()
    if len(words) < 5 or len(words) > 30:
        return False
    first = _toks(words[0])
    if not first or first[0] in _NON_SUBJECT_OPEN:
        return False
    if len(re.findall(r"[.!?](?:\s|$)", x)) > 1:
        return False
    if _repeated_ngram(x):
        return False
    try:
        from route_content_896 import is_fragment
        if is_fragment(x):
            return False
    except Exception:
        pass
    return True


def neighbour_sentence(short_name: str, neighbour_evidence: Sequence[str],
                       split: Callable[[str], List[str]]) -> Optional[str]:
    """[LOCAL-900/902] A sentence from a same-site neighbour that speaks about THIS stop's subject
    (>= half of its subject words, at least one). ``neighbour_evidence`` is the neighbour's DELIVERED BODY (whole
    sentences), never raw evidence text. The sentence must be one clean sentence (``is_clean_neighbour_sentence``);
    otherwise None -- no neighbour sentence is used."""
    subj = subject_tokens(short_name)
    if not subj:
        return None
    need = max(1, math.ceil(len(subj) / 2))
    for ev in neighbour_evidence:
        for s in split(ev or ""):
            n = len(s.split())
            if n < 6 or n > 30 or _BAD_NEIGH.search(s) or sum(ord(c) > 127 for c in s) > 3:
                continue
            words = set(_toks(s))
            if sum(1 for w in subj if w in words or (w.endswith("s") and w[:-1] in words)) >= need:
                s = s.strip()
                if not s[-1:] in ".!?":
                    continue                  # a body sentence is punctuated; one that is not is raw text
                if not is_clean_neighbour_sentence(s):
                    continue
                return s
    return None


# ── item 6: a model pin far from the scope geocode ───────────────────────────
SCOPE_RADIUS_KM = {"BUILDING": 15.0, "CORRIDOR": 15.0, "DISTRICT": 15.0, "CITY": 25.0}


def _hav(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


# [LOCAL-900B] how specific a reference point is. A pin is a PLACE; only a reference at least that specific may
# replace it. A province / region / country centroid (wave 47: Binh Thuan 11.0833,108.0833, 35 km from the site)
# is never the truth about a place pin.
PRECISION_RANK = {"country": 0, "region": 1, "province": 1, "state": 1, "city": 2, "town": 2, "district": 3,
                  "neighbourhood": 3, "neighborhood": 3, "place": 4, "poi": 4, "building": 4, "destination": 4}
_STOP_PRECISION = "place"


def _rank(precision: str) -> int:
    return PRECISION_RANK.get((precision or "").strip().lower(), -1)


OWN_REF_MAX_KM = 100.0


def stop_verified_reference(p: dict) -> Optional[Tuple[float, float]]:
    """A coordinate already fetched and verified for THIS stop (its Wikidata P625), or None."""
    try:
        la, lo = p.get("wikidata_lat"), p.get("wikidata_lng")
        if la is not None and lo is not None:
            return (float(la), float(lo))
    except (TypeError, ValueError):
        pass
    return None


def check_pins_against_scope(stops: List[dict], scope_center: Optional[Tuple[float, float]],
                             scope_precision: str = "", parse: Optional[Callable] = None,
                             log: Optional[Callable] = None, ref_precision: str = "place",
                             ref_source: str = "") -> int:
    """Used when GEO-CHECK is skipped (< 3 pinned stops). A stop pin farther than the scope radius from a
    reference is replaced by that reference, flagged approximate. Mutates ``stops``; returns the number
    replaced. No network call.

    [LOCAL-900B] The reference must be a place-level point: the stop's own verified coordinate (Wikidata P625
    already on the stop), or ``scope_center`` when ``ref_precision`` says it is the geocode of the requested place
    itself. A coarser reference (district / city / province / country centroid -- ``ref_precision`` below place)
    never replaces a pin: ``action=skipped_coarse_ref``. The default ``ref_precision='place'`` keeps the original
    contract for a caller that vouches for its centre; the pipeline always passes the real precision."""
    if not stops:
        return 0
    radius = SCOPE_RADIUS_KM.get((scope_precision or "").upper(), 25.0)
    parse = parse or (lambda s: (lambda m: (float(m.group(1)), float(m.group(2))) if m else None)(
        re.match(r"\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", s or "")))
    centre_ok = bool(scope_center) and _rank(ref_precision) >= _rank(_STOP_PRECISION)
    n = 0
    for i, p in enumerate(stops, 1):
        c = parse(p.get("coordinates", "")) if isinstance(p.get("coordinates"), str) else p.get("coordinates")
        if not c:
            continue
        own = stop_verified_reference(p)
        # [LOCAL-900B/LEAD] a Wikidata NAME lookup can return a same-named place abroad (wave 47: the 552
        # statue's P625 is in another country). Even a coarse centre bounds it: farther than
        # OWN_REF_MAX_KM from any known scope centre, the stop's own point is not trusted.
        if own and scope_center and _hav(own, scope_center) > OWN_REF_MAX_KM:
            if log:
                log(f"  [LOCAL-900B] stop={i} own reference {own} is {_hav(own, scope_center):.0f} km from the "
                    f"scope centre -> ignored")
            own = None
        ref, why = (own, "stop_verified") if own else ((scope_center, ref_source or "scope") if centre_ok else (None, ""))
        if ref is None:
            if scope_center:
                d = _hav(c, scope_center)
                if d > radius and log:
                    log(f"  [LOCAL-900] pin check stop={i} dist_km={d:.1f} action=skipped_coarse_ref "
                        f"ref_precision={ref_precision or 'unknown'} ref_source={ref_source or 'unknown'}")
                elif log:
                    log(f"  [LOCAL-900] pin check stop={i} dist_km={d:.1f} action=kept")
            continue
        d = _hav(c, ref)
        if d > radius:
            p["coordinates"] = f"{ref[0]:.6f}, {ref[1]:.6f}"
            p["coordinates_approximate"] = True
            n += 1
            act = "replaced"
        else:
            act = "kept"
        if log:
            log(f"  [LOCAL-900] pin check stop={i} dist_km={d:.1f} action={act} ref={why}")
    if log:
        log(f"  [LOCAL-900B] pin check reference: center={scope_center} precision={ref_precision or 'unknown'} "
            f"source={ref_source or 'unknown'} usable={'yes' if centre_ok else 'no (coarser than a place)'}")
    return n
