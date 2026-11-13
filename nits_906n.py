"""[LOCAL-906N] Wave 55 cloud 551 nits. Pure, offline, name-free. Every function returns the text unchanged on error.

  1. ``unify_builder_names``   two person names sharing all but the last token, about the same object in two stops
                               ("Truong Dinh Tri" / "Truong Dinh Y") -> one spelling: the one the evidence states
                               (article first).
  2. ``restore_proper_case``   a multi-word name capitalised elsewhere in the tour (or in a stop title) and lowercased
                               here ("ta Cu Mountain") gets its capitalisation back.

(The mode-word capitalisation fix lives at its source, ``refill_quality_906k._mode_fix``.)
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional

import leftovers_906c as c
import leftovers_906f as f
import refill_quality_906k as _k906
import route_content_896 as rc

TAG = "[LOCAL-906N]"


def _emit(log: Optional[Callable]) -> Callable:
    return log or (lambda _m: None)


# ══ 1. one builder, one spelling ═════════════════════════════════════════════════════════════════════════
_W = r"[A-ZÀ-Ỹ][\wÀ-ỹ'’\-]*"
_PN = _W + r"(?:[ \t]+" + _W + r"){1,3}"
_BY_N = re.compile(r"\bby\s+(?:(?:the|a|an)\s+)?(?:[a-z]+\s+){0,2}?(?P<n>" + _PN + r")(?![\wÀ-ỹ])")
_BEFORE_N = re.compile(r"(?<![\wÀ-ỹ])(?P<n>" + _PN + r")\s+(?:built|carved|sculpted|designed|founded|constructed|created|commissioned|"
                       r"began|started|completed|finished)\b")


def person_names(sentence: str) -> List[str]:
    """Names of the builder in a sentence; unlike leftovers_906f's, a single-letter last token (\"Truong Dinh Y\") counts."""
    out: List[str] = []
    for rx in (_BY_N, _BEFORE_N):
        for m in rx.finditer(sentence):
            nm = m.group("n").strip()
            if nm not in out:
                out.append(nm)
    return out


def _sibling_names(a: str, b: str) -> bool:
    """Same person under two spellings: >= 2 tokens each, the same count, all but the last token equal, last differs."""
    ta, tb = rc.fold(a).split(), rc.fold(b).split()
    return len(ta) >= 2 and len(ta) == len(tb) and ta[:-1] == tb[:-1] and ta[-1] != tb[-1]


def _named_in(name: str, text: str) -> bool:
    return bool(re.search(r"(?<![\w])" + re.escape(rc.fold(name)) + r"(?![\w])", rc.fold(text or "")))


def _rank(name: str, art: str, ev: str) -> int:
    return 2 if _named_in(name, art) else 1 if _named_in(name, ev) else 0


def unify_builder_names(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                        log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        ev_map = c._ev_map(evidence_by_title)
        text = tour_text
        for _round in range(6):
            infos = f._stops(text)
            claims = []
            for k, st in enumerate(infos):
                for i, j, x in st["flat"]:
                    cl = f._claim_of(x, st["title"])
                    names = person_names(x) if cl else []
                    if names:
                        claims.append((k, x, {**cl, "builders": names}))
            hit = None
            for a in range(len(claims)):
                for b in range(a + 1, len(claims)):
                    ka, xa, ca = claims[a]
                    kb, xb, cb = claims[b]
                    if ka == kb:
                        continue
                    # same linked title, or the same object noun ("the statue"): two near-identical person names are
                    # evidence enough on their own, so a shared object noun suffices
                    linked = f._link_token(infos[ka]["title"], infos[kb]["title"], xa, xb)
                    if not (ca["thing"] & cb["thing"] or (linked and len(ca["obj"] & cb["obj"]) >= 2)):
                        continue
                    for na in ca["builders"]:
                        for nb in cb["builders"]:
                            if _sibling_names(na, nb):
                                hit = (ka, na, kb, nb)
                                break
                        if hit:
                            break
                    if hit:
                        break
                if hit:
                    break
            if not hit:
                break
            ka, na, kb, nb = hit
            sa, sb = infos[ka], infos[kb]
            eva = rc._ev_for(ev_map, sa["title"]) or ""
            evb = rc._ev_for(ev_map, sb["title"]) or ""
            arta = _k906._article_text(eva, sa["title"], None)[0]
            artb = _k906._article_text(evb, sb["title"], None)[0]
            ra = _rank(na, arta + " " + artb, eva + " " + evb)
            rb = _rank(nb, arta + " " + artb, eva + " " + evb)
            if ra == rb == 0:
                break                                           # the evidence states neither spelling: nothing to go by
            if ra == rb:                                        # both stated at the same level: the stop's own article first
                ra = _rank(na, arta, eva)
                rb = _rank(nb, artb, evb)
                if ra == rb:
                    ra, rb = 1, 0                               # still tied: the earlier stop's spelling
            keep, lose, lose_stop = (na, nb, sb) if ra > rb else (nb, na, sa)
            emit(f"  {TAG} builder name unified: '{lose}' -> '{keep}'")
            lo, hi = lose_stop["s"], lose_stop["e"]
            block = re.sub(r"(?<![\w])" + re.escape(lose) + r"(?![\w])", keep, text[lo:hi])
            if block == text[lo:hi]:
                break
            text = text[:lo] + block + text[hi:]
        return text
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} builder-name unification skipped (non-fatal): {err}")
        return tour_text


# ══ 2. a proper name keeps its capitals ══════════════════════════════════════════════════════════════════
_CAP = r"[A-ZÀ-Ỹ][\wÀ-ỹ'’\-]+"
_CAP_SEQ = re.compile(r"(?<![\wÀ-ỹ])(?:" + _CAP + r")(?:[ \t]+" + _CAP + r"){1,3}(?![\wÀ-ỹ])")
_LEAD_COMMON = frozenset("the a an this that these those its their his her our your my it they he she we you i in on at of to "
                         "and or but as if when while with from by for there here then also now after before during "
                         "many some most each every one two three first second third last next".split())


def _names_of(text: str, titles: List[str]) -> Dict[str, str]:
    """{folded name: name} of every multi-word capitalised sequence in the tour (a leading common word trimmed). A
    sequence that only ever stands at a sentence start counts only when a stop title holds it."""
    found: Dict[str, str] = {}
    mid: set = set()
    for m in _CAP_SEQ.finditer(text):
        words = m.group(0).split()
        while words and words[0].lower() in _LEAD_COMMON:
            words = words[1:]
        if len(words) < 2:
            continue
        name = " ".join(words)
        before = text[:m.start()].rstrip()
        at_start = (not before) or before[-1] in ".!?:\n" or before.endswith(("\"", "“")) and not before[:-1].strip()
        found.setdefault(rc.fold(name), name)
        if not at_start or len(words) != len(m.group(0).split()):
            mid.add(rc.fold(name))
    tl = " ".join(titles)
    return {k: v for k, v in found.items() if k in mid or _named_in(v, tl)}


def restore_proper_case(tour_text: str, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        titles = [(st.get("title") or "") for st in c._stops_info(tour_text)]
        names = _names_of(tour_text, titles)
        text = tour_text
        for name in sorted(names.values(), key=lambda n: -len(n)):
            toks = name.split()
            rx = re.compile(r"(?<![\wÀ-ỹ])" + r"\s+".join(re.escape(t) for t in toks) + r"(?![\wÀ-ỹ])", re.I)

            def fix(m, _name=name):
                got = m.group(0)
                if got == _name or " ".join(got.split()) == _name:
                    return got
                if got == got.lower() and len(toks) < 3:          # "old town": an ordinary phrase, not a lost capital
                    return got
                emit(f'  {TAG} proper name case restored: "{got}" -> "{_name}"')
                return _name
            text = rx.sub(fix, text)
        return text
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} proper-name case guard skipped (non-fatal): {err}")
        return tour_text
