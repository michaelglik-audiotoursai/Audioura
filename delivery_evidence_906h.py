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


# [LOCAL-906J] Evidence PURITY. The store holds SOURCE text only. Every entry is tagged with its source kind; a kind the
# model can produce is impossible (``add`` refuses it, ``assert_pure`` proves it). D771 / LOCAL-892: LLM output is never
# evidence, and a delivery guard that reads it vouches for the narrator with the narrator's own words.
SOURCE_KINDS = frozenset({"article", "web", "user-article"})        # an encyclopedia article, a web snippet / page, the user stop's article
LLM_KINDS = frozenset({"fact-sheet", "signature", "refill", "rewrite", "llm", "knowledge_fallback", "parametric", "spine",
                       "thin-fact", "tour"})
# the legacy source labels the generator passes (their material is source text; the generator only hands over passages)
_DEFAULT_KIND = {"889": "web", "904": "web", "user-stop": "user-article", "article": "article", "web": "web",
                 "user-article": "user-article"}
_KINDS: Dict[str, Dict[str, int]] = rc._ScopedDict(dict)   # {source kind: {stop title: entries}}
_REFUSED: Dict[str, int] = rc._ScopedDict(dict)            # {refused kind: entries}, for the log and the tests
_ENTRIES: Dict[str, list] = rc._ScopedDict(dict)           # {stop title: [{"text", "kind", "domain"}]}: provenance per entry
_REFERENCE_DOMAINS = ("wikipedia.org", "wikidata.org", "britannica.com", "guinnessworldrecords.com", "recordsetter.com",
                      "worldrecordacademy.org", "recordholders.org")
_TWO_PART_TLDS = frozenset("co com org net gov edu ac or ne go".split())


def domain_of(url: str) -> str:
    """The registrable domain of a URL ("https://en.m.wikipedia.org/wiki/X" -> "wikipedia.org"); "" when none."""
    m = re.match(r"(?i)^\s*(?:[a-z][a-z0-9+.-]*://)?(?:[^/@\s]*@)?([a-z0-9.-]+\.[a-z]{2,})(?::\d+)?(?:[/?#]|$)", str(url or ""))
    if not m:
        return ""
    parts = m.group(1).lower().strip(".").split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in _TWO_PART_TLDS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_reference_domain(domain: str) -> bool:
    """An encyclopedia or an official / record-body page: a reference for a world-scope record."""
    d = (domain or "").lower()
    return d in _REFERENCE_DOMAINS or bool(re.search(r"(?:^|\.)(?:gov|gob|gouv|go)\.[a-z]{2}$|\.gov$|\.int$", d))


def entries(title: Optional[str] = None):
    """The per-entry provenance: {stop title: [{text, kind, domain}]}, or the list for one title (exact key)."""
    if title is not None:
        return list(_ENTRIES.get(str(title), []))
    return {k: list(v) for k, v in _ENTRIES.items()}


def kind_for(source: str, kind: Optional[str] = None) -> Optional[str]:
    k = (kind or _DEFAULT_KIND.get(str(source or "").strip().lower()) or "").strip().lower()
    return k if k in SOURCE_KINDS else None


def add(ev: Optional[Dict[str, object]], source: str, kind: Optional[str] = None) -> int:
    """Add SOURCE text (a str or a list of str per title) from ``source``. Returns the number of stops touched.
    ``kind`` (article / web / user-article; derived from ``source`` when omitted) tags the entry. An LLM kind, or a source
    whose kind is unknown, is refused: nothing is stored (a fact-sheet fact, a signature story, a refill sentence, a model
    rewrite). Registered LLM passages (``llm_evidence``) are scrubbed out of what is stored."""
    n = 0
    try:
        k_ = kind_for(source, kind)
        if k_ is None:
            _REFUSED[str(kind or source)] = _REFUSED.get(str(kind or source), 0) + sum(1 for _ in (ev or {}))
            return 0
        try:
            import llm_evidence as _le
        except Exception:  # pragma: no cover
            _le = None
        for k, v in (ev or {}).items():
            items = list(v) if isinstance(v, (list, tuple, set)) else [v]
            texts = []
            for it in items:
                # an item is a str, or {"text", "url", "kind"} (the url gives the entry its domain; the kind overrides)
                txt = str(it.get("text") or "") if isinstance(it, dict) else str(it or "")
                if _le is not None:
                    txt = _le.scrub(txt)
                txt = txt.strip()
                if not txt:
                    continue
                ik = (kind_for(source, it.get("kind")) if isinstance(it, dict) and it.get("kind") else None) or k_
                dom = domain_of(it.get("url") or it.get("domain") or "") if isinstance(it, dict) else ""
                if dom == "" and isinstance(it, dict) and it.get("domain"):
                    dom = str(it.get("domain")).lower()
                _ENTRIES.setdefault(str(k), []).append({"text": txt, "kind": ik, "domain": dom})
                by = _KINDS.setdefault(ik, {})
                by[str(k)] = by.get(str(k), 0) + 1
                texts.append(txt)
            blob = " ".join(texts).strip()
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


def kinds() -> Dict[str, int]:
    """{source kind: entries stored}; only SOURCE kinds can appear."""
    return {k: sum(v.values()) for k, v in _KINDS.items()}


def refused() -> Dict[str, int]:
    return dict(_REFUSED)


def assert_pure() -> None:
    """Raises AssertionError when any stored entry carries a non-source kind (cannot happen through ``add``)."""
    bad = [k for k in _KINDS if k not in SOURCE_KINDS]
    assert not bad, f"LLM / unknown evidence kinds in the delivery store: {bad}"


def get() -> Dict[str, str]:
    return dict(_STORE)


def clear() -> None:
    _STORE.clear()
    _SOURCES.clear()
    _KINDS.clear()
    _REFUSED.clear()
    _ENTRIES.clear()
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
        kd = ", ".join(f"{a}:{b}" for a, b in sorted(kinds().items())) or "none"
        log(f"  {TAG} delivery evidence: {k}/{n} stops ({srcs}) kinds {kd}")
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
