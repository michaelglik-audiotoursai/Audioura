"""[LOCAL-902] A single-place request that names several places ("A and the B, <Province>") makes each
named place a REQUIRED stop with its own title, like a user stop. Wave 49: "<Mountain> and the <Statue>"
came out as "<Mountain>" + "<Pagoda>"; the statue was never a stop. Pure, offline, no place names."""
import re
import unicodedata
from typing import Callable, Dict, List, Optional

_SPLIT = re.compile(r"\s+(?:and|&)\s+", re.IGNORECASE)
_ARTICLE = re.compile(r"(?i)^(?:the|a|an)\s+")
_TOUR_TAIL = re.compile(r"(?i)\s+(?:walking\s+|audio\s+)?(?:tour|walk|trip|visit)\s*$")
_FILLER = frozenset({"the", "of", "and", "a", "an", "de", "la", "le"})


def _fold(s: str) -> str:
    s = (s or "").replace("\u0111", "d").replace("\u0110", "D")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _toks(s: str) -> List[str]:
    return [w for w in _fold(s).split() if w not in _FILLER]


def required_places(location: str) -> List[str]:
    """The named places of a location of the shape "A and the B, <Province>[, <Country>]". The head (before the
    first comma) is split on "and" / "&"; leading articles are stripped. [] unless two or more names result
    (a lone name is the ordinary single-place request; a comma list is a stop list handled elsewhere)."""
    head = (location or "").split(",")[0].strip()
    head = _TOUR_TAIL.sub("", head)
    names = []
    for seg in _SPLIT.split(head):
        seg = _ARTICLE.sub("", seg.strip(" .;"))
        if len(seg) >= 3 and _toks(seg):
            names.append(seg)
    if len(names) < 2:
        return []
    # A single-place request: at least one name is a distinct structure (statue / pagoda / ...), the other the
    # site it stands at. Two districts ("A and B, <City>") are an area request, not required stops.
    try:
        from distinct_sites_901 import STRUCTURE_WORDS
    except Exception:
        STRUCTURE_WORDS = frozenset()
    STRUCTURE_WORDS = frozenset(STRUCTURE_WORDS) | {"buddha", "sculpture", "fountain", "gate", "arch", "cross", "waterfall"}
    if not any(set(_fold(n).split()) & STRUCTURE_WORDS or
               any(w.endswith("s") and w[:-1] in STRUCTURE_WORDS for w in _fold(n).split()) for n in names):
        return []
    return names


_STRUCTURE_SUFFIX = frozenset({"statue", "statues", "pagoda", "temple", "monument", "memorial", "buddha", "shrine",
                               "sculpture", "fountain", "gate", "arch", "cross", "waterfall", "tower", "mount",
                               "mountain", "peak", "hill", "bridge"})


def _core(toks: List[str]) -> List[str]:
    """The name's tokens without the generic structure words (\"<Statue> Statue\" ~ \"<Statue>\")."""
    c = [w for w in toks if w not in _STRUCTURE_SUFFIX and w.rstrip("s") not in _STRUCTURE_SUFFIX]
    return c


def _matches(name: str, title: str, loose: bool = False) -> bool:
    """A required name matches a stop title when every token of the name is in the title. [LOCAL-905] ``loose``:
    or every CORE token (the name without structure words such as statue / mountain) is -- used only for a name
    no stop matched strictly, and only on a stop no other name claimed."""
    nt = _toks(name)
    tt = set(_toks(title))
    if not nt:
        return False
    if all(w in tt or (w.endswith("s") and w[:-1] in tt) for w in nt):
        return True
    if not loose:
        return False
    core = _core(nt)
    return bool(core) and all(w in tt or (w.endswith("s") and w[:-1] in tt) for w in core)


def ensure_required_stops(poi_list: List[Dict], names: List[str], new_poi: Callable[[str, str], Dict],
                          max_stops: Optional[int] = None, log: Optional[Callable[[str], None]] = None
                          ) -> List[Dict]:
    """Every name in ``names`` is a stop titled with that name. A name already covered by a stop title is
    left alone (and flagged required). A missing name is added; when the tour is full it takes the place of
    the last stop that covers no required name. Required stops are flagged ``user_explicit`` / ``_required_902``
    so the user-stop protections apply. Returns the (possibly new) list."""
    emit = log or (lambda _m: None)
    if not names or poi_list is None:
        return poi_list
    cap = max_stops if max_stops else max(len(poi_list), len(names))
    out = list(poi_list)
    covered = {}
    for loose in (False, True):
        for n in names:
            if n in covered:
                continue
            for i, p in enumerate(out):
                if i in covered.values():
                    continue
                if _matches(n, str(p.get("name", "")), loose=loose):
                    covered[n] = i
                    p["user_explicit"] = True
                    p["_required_902"] = True
                    break
    for n in names:
        if n in covered:
            continue
        emit(f"[LOCAL-902] required place '{n}' was not a stop of the selected list "
             f"({[p.get('name') for p in out]}) -> added as its own stop")
        addr = next((str(p.get("address", "")) for p in out if p.get("address")), "")
        newp = new_poi(n, addr)
        newp["user_explicit"] = True
        newp["_required_902"] = True
        if len(out) >= cap:
            victim = next((i for i in range(len(out) - 1, -1, -1) if not out[i].get("_required_902")), None)
            if victim is None:
                continue
            emit(f"[LOCAL-902] stop '{out[victim].get('name')}' replaced by required place '{n}'")
            out[victim] = newp
        else:
            out.append(newp)
    # keep the request's order for the required stops among themselves
    pos = {n: k for k, n in enumerate(names)}
    req = sorted((p for p in out if p.get("_required_902")),
                 key=lambda p: next((pos[n] for n in names if _matches(n, str(p.get("name", "")), loose=True)), 99))
    it = iter(req)
    out = [next(it) if p.get("_required_902") else p for p in out]
    for i, p in enumerate(out):
        p["stop_number"] = i + 1
    return out
