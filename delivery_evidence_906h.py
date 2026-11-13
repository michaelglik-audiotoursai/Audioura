"""[LOCAL-906H] Delivery always has the per-stop evidence. Pure, offline, name-free (D769); never raises.

906C / 906F judge a delivered sentence against the stop's evidence, but ``ensure_bodies`` was called with none, so on a
2-stop tour (no pool, no ``_EVIDENCE_904``) every scope / blocked / cross-stop check was a silent no-op. This module keeps
a JOB-scoped ``{stop title: evidence}`` store (a ``route_content_896._ScopedDict``: two jobs never share it, ``end_job``
drops it) that every evidence producer fills, and that the delivery guards read when the caller passes none.

Also (item 3 / 4): ``drop_dangling_quantifier`` and ``dedupe_count_sentences``.
"""
import re
from typing import Callable, Dict, List, Optional

import route_content_896 as rc

TAG = "[LOCAL-906H]"
_STORE: Dict[str, str] = rc._ScopedDict(dict)       # {stop title: evidence blob}
_SOURCES: Dict[str, int] = rc._ScopedDict(dict)     # {source name: stops it filled}
_LOGGED: Dict[str, bool] = rc._ScopedDict(dict)     # {"done": True} once the per-job line was logged


def add(ev: Optional[Dict[str, object]], source: str) -> int:
    """Add evidence (a str or a list of str per title) from ``source``. Returns the number of stops touched."""
    n = 0
    try:
        for k, v in (ev or {}).items():
            blob = " ".join(str(x) for x in v) if isinstance(v, (list, tuple, set)) else str(v or "")
            blob = blob.strip()
            if not blob or not str(k).strip():
                continue
            cur = _STORE.get(str(k), "")
            if blob not in cur:
                _STORE[str(k)] = (cur + " " + blob).strip()
            n += 1
        if n:
            _SOURCES[source] = _SOURCES.get(source, 0) + n
            _LOGGED.clear()          # a later source changes the picture: the next report logs again (still once per call site)
    except Exception:
        pass
    return n


def get() -> Dict[str, str]:
    return dict(_STORE)


def clear() -> None:
    _STORE.clear()
    _SOURCES.clear()
    _LOGGED.clear()


def resolve(evidence_by_title: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The job store, overlaid with what the caller passed (the caller's entry wins per title)."""
    ev = dict(_STORE)
    try:
        ev.update({str(k): str(v) for k, v in (evidence_by_title or {}).items() if str(v or "").strip()})
    except Exception:
        pass
    return ev


def coverage(text: str, ev: Optional[Dict[str, str]] = None):
    """(stops with evidence, stops) for the delivered text."""
    ev_map = {rc.fold(k): v for k, v in (ev if ev is not None else resolve()).items()}
    blocks = rc._stop_blocks(text or "")
    k = sum(1 for (_s, _e, _n, title) in blocks if (rc._ev_for(ev_map, title) or "").strip())
    return k, len(blocks)


def report(text: str, log: Optional[Callable[[str], None]] = None,
           evidence_by_title: Optional[Dict[str, str]] = None) -> None:
    """Log ``[LOCAL-906H] delivery evidence: k/n stops (sources)`` once per job (until new evidence arrives)."""
    try:
        if _LOGGED.get("done") or not log:
            return
        k, n = coverage(text, resolve(evidence_by_title))
        srcs = ", ".join(f"{s}:{c}" for s, c in sorted(_SOURCES.items())) or "none"
        log(f"  {TAG} delivery evidence: {k}/{n} stops ({srcs})")
        _LOGGED["done"] = True
    except Exception:
        pass


# ══ item 3: a number cut left "an additional / another / a further / some" with nothing to quantify ════════
_STRONG = r"(?:an?\s+additional|an?\s+further|an?\s+extra)"
_WEAK = r"(?:another|some|about|around|roughly|approximately|nearly|over|more\s+than|up\s+to)"
_PREP = (r"from|to|of|in|at|on|by|for|with|into|onto|up|down|via|through|along|across|above|below|beyond|past|"
         r"before|after|between|toward|towards|within|and|or|but|which|that")
_CLAUSE_END = r"(?=\s*[,;:.!?]|\s*$)"
# an unambiguous quantifier ("an additional") never stands alone; a weak one ("another", "some", "about") can, so it is
# only judged in a sentence that is about a measure, and only before a source/direction word or the clause end
DANGLING = re.compile(r"(?i)(?<![\w'\u2019-])" + _STRONG + r"(?=\s+(?:" + _PREP + r")\b|\s*[,;:.!?]|\s*$)")
DANGLING_WEAK = re.compile(r"(?i)(?<![\w'\u2019-])" + _WEAK + r"(?=\s+(?:from|to|up|down|and|or|before|after)\b|\s*[,;:.!?]|\s*$)")
_MEASURE_CTX = re.compile(r"(?i)\b(?:climb\w*|steps?|stairs?|stairway|ascen\w+|ascend\w*|reach(?:ed|es)?|accessed|trek\w*|hike\w*|"
                          r"rises?|rose|long|high|tall|wide|deep|distance|elevation|metres?|meters?|feet|kilomet\w+|miles?)\b")


def _dangling_in(sent: str):
    m = DANGLING.search(sent)
    if m:
        return DANGLING
    if DANGLING_WEAK.search(sent) and _MEASURE_CTX.search(sent):
        return DANGLING_WEAK
    return None


def drop_dangling_quantifier(text: str, log: Optional[Callable[[str], None]] = None) -> str:
    """Remove a quantifier that no longer has a number to quantify ("is reached by climbing an additional from the
    station" -> "is reached by climbing from the station"). If nothing meaningful is left of the clause (the quantifier
    was the object of the verb at the sentence end) the sentence is dropped. Generic; structural lines untouched."""
    emit = log or (lambda _m: None)
    if not text or not (DANGLING.search(text) or DANGLING_WEAK.search(text)):
        return text
    try:
        out_lines = []
        for ln in text.split("\n"):
            if ln.lstrip().startswith("<!--") or rc._KEYED.match(ln) or rc._CLOSING_LINE.match(ln.strip()) \
                    or not (DANGLING.search(ln) or DANGLING_WEAK.search(ln)):
                out_lines.append(ln)
                continue
            kept: List[str] = []
            for sent in rc.split_sentences(ln):
                rx = _dangling_in(sent)
                if rx is None:
                    kept.append(sent)
                    continue
                fixed = rx.sub("", sent)
                fixed = re.sub(r"\s{2,}", " ", fixed)
                fixed = re.sub(r"\s+([,;:.!?])", r"\1", fixed).strip()
                fixed = re.sub(r"(?i)\b(by|of|for|with)\s+(climbing|walking|taking|following|crossing)\s*(?=[.!?]|$)", "", fixed)
                if fixed:
                    fixed = fixed[0].upper() + fixed[1:]
                emit(f'  {TAG} dangling quantifier removed: "{sent[:90]}"')
                ends_open = bool(re.search(r"(?i)\b(?:by|of|for|with|to|from|and|or|the|a|an|climbing|walking|taking)\s*[.!?]?$",
                                           fixed))
                if len(fixed.split()) >= 5 and not ends_open:
                    kept.append(fixed)
                else:
                    emit(f'  {TAG} clause empty after the quantifier went -> sentence dropped: "{sent[:90]}"')
            lead = re.match(r"\s*", ln).group(0)
            if kept:
                out_lines.append(lead + " ".join(kept))
            # a line left with no sentence is removed
        return re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines))
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} dangling-quantifier guard skipped (non-fatal): {err}")
        return text


# ══ item 4: exactly one count sentence per tour ══════════════════════════════════════════════════════════════
_VISITED = re.compile(r"(?i)\bYou(?:['’]ve|\s+have)\s+(?:now\s+)?visited\s+(\d+|\w+)\s+stops?(?:\s+in\s+all)?\s*[.!]\s*")
_THATS = re.compile(r"(?i)\bThat['’]s\s+(\d+)\s+stops?(?:\s+in\s+all)?\b")


def dedupe_count_sentences(text: str, log: Optional[Callable[[str], None]] = None) -> str:
    """\"You have now visited N stops (in all).\" next to the closing's \"That's N stops in all.\": the body copy goes
    (the closing is the one the 905 recount maintains). Exactly one count sentence per tour."""
    emit = log or (lambda _m: None)
    if not text or not _VISITED.search(text) or not _THATS.search(text):
        return text
    try:
        def sub(m):
            emit(f'  {TAG} second count sentence removed: "{m.group(0).strip()}"')
            return ""
        out = _VISITED.sub(sub, text)
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r"(?m)[ \t]+$", "", out)
        return re.sub(r"\n{3,}", "\n\n", out)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} count dedupe skipped (non-fatal): {err}")
        return text
