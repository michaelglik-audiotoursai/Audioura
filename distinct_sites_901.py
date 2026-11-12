"""[LOCAL-901] A distinct named structure is never "the same place as" the area that contains it.

Wave 48 (single-site tour): the 791E title dedupe dropped the requested statue, two pagodas and
the cable-car station as "the same place as <Mountain>", because their pins sat on the mountain
and/or their names share the mountain's tokens. A statue / pagoda / temple / station / museum is
its own stop. Only true duplicates merge: the same name modulo aliases, or the same QID.

``distinct_sites(a, b)`` is a VETO the two dedupe passes consult before merging on a weaker signal
(proximity, located-in, token overlap). Pure; no I/O.
"""
import re
import unicodedata
from typing import Dict, Iterable, Set

STRUCTURE_WORDS = frozenset({
    "statue", "pagoda", "temple", "station", "museum", "church", "cathedral", "basilica",
    "shrine", "monastery", "mosque", "synagogue", "tower", "bridge", "palace", "castle",
    "chapel", "monument", "memorial", "fort", "fortress", "lighthouse", "theatre", "theater",
    "gallery", "library", "cableway", "gondola", "tramway", "funicular", "stupa", "abbey",
    "pavilion", "obelisk", "mausoleum", "carillon", "belfry",
})
# Containers: the mountain / park / area a structure stands in.
CONTAINER_WORDS = frozenset({
    "mountain", "mount", "mt", "hill", "hills", "peak", "range", "park", "forest", "reserve",
    "valley", "lake", "beach", "island", "area", "district", "region", "province", "garden",
    "gardens", "plateau", "ridge", "canyon", "cave", "grotto", "reef", "bay",
})
_STOP = frozenset({"the", "of", "and", "de", "la", "le", "du", "des", "at", "on", "in", "a", "an",
                   "national", "old", "new", "central", "city", "car", "cable", "lower", "upper",
                   "main", "grand", "great", "little"})


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _words(name: str) -> list:
    return _fold(name).split()


def structure_tokens(name: str) -> Set[str]:
    w = _words(name)
    out = {t for t in w if t in STRUCTURE_WORDS}
    for i in range(len(w) - 1):                       # "cable car" is a structure (the station/line)
        if w[i] == "cable" and w[i + 1] == "car":
            out.add("cablecar")
    return out


def is_container_only(name: str) -> bool:
    w = _words(name)
    return bool(w) and not structure_tokens(name) and any(t in CONTAINER_WORDS for t in w)


def core_tokens(name: str) -> Set[str]:
    return {t for t in _words(name)
            if t not in STRUCTURE_WORDS and t not in CONTAINER_WORDS and t not in _STOP}


def _name(p: Dict) -> str:
    return (p.get("name") or p.get("title") or "") if isinstance(p, dict) else str(p or "")


def _alias_set(p: Dict) -> Set[str]:
    out: Set[str] = set()
    if not isinstance(p, dict):
        return out
    if _name(p):
        out.add(_fold(_name(p)))
    for k in ("aliases", "also_known_as", "alt_names", "alias"):
        v = p.get(k)
        vals: Iterable = [v] if isinstance(v, str) else (v if isinstance(v, (list, tuple, set)) else [])
        out |= {_fold(str(x)) for x in vals if x}
    return {a for a in out if a}


def _qid(p: Dict) -> str:
    return ((p.get("wikidata_qid") or p.get("qid") or "") if isinstance(p, dict) else "").strip()


def distinct_sites(a: Dict, b: Dict) -> bool:
    """True when ``a`` and ``b`` are two different named things that must NOT merge:
    a structure vs the area / mountain / park containing it, or two structures whose proper-noun
    cores differ. False (no veto) for the same QID, a shared name / alias, or when the names
    give no way to tell (the existing dedupe signals then decide as before)."""
    qa, qb = _qid(a), _qid(b)
    if qa and qb and qa == qb:
        return False
    if _alias_set(a) & _alias_set(b):
        return False
    na, nb = _name(a), _name(b)
    if not _fold(na) or not _fold(nb):
        return False
    sa, sb = structure_tokens(na), structure_tokens(nb)
    if (sa and is_container_only(nb)) or (sb and is_container_only(na)):
        return True
    if sa and sb:
        # Two structures at the identical STREET address (a house number, e.g. an English name and the
        # local name of one pagoda) are the same building: the address, not the name, is the identity.
        # A shared area address ("Gamma Mountain, Zeta, ...") is not a street address.
        aa, ab = _fold(a.get("address", "") if isinstance(a, dict) else ""), \
            _fold(b.get("address", "") if isinstance(b, dict) else "")
        if aa and aa == ab and aa[0].isdigit():
            return False
        ca, cb = core_tokens(na), core_tokens(nb)
        if ca and cb and not (ca <= cb or cb <= ca):
            return True
    return False
