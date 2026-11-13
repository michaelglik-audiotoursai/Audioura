"""[LOCAL-906C] Wave 52 leftovers. Pure, offline, name-free (D769). Every function returns the text unchanged on error.

  1. scope-matched superlatives / exclusivity     ``drop_unsupported_scope_claims``
       "the only", "the first", "the sole", "no other", "the largest / longest / tallest / biggest / oldest ... in
       <area>": the stop's evidence must state the superlative for the SAME scope or a WIDER one (a claim about a
       country is backed by evidence about the region, never the other way round). Unsupported: the sentence is
       dropped, or replaced by the evidence's own narrower, supported sentence when there is one.
  2. ``prefer_supported``      among same-fact sentences the one whose scope is unsupported is never kept.
  3. ``distinct_filler_bodies``  no two stops share an honest-filler body: (a) unused evidence of the neighbouring
       stops that names this stop's subject, (b) a filler variant keyed to the stop's kind, (c) merge into the
       previous stop (header dropped, Directions kept, count recomputed).
  4. ``repair_you_see_here``   "You see the X here is 49 meters long." -> "You see the X here. It is 49 meters long."
       (safety net; the cause is fixed in route_content_896._join_kept_clauses).
HTML comments (``<!-- ... -->``) are never body sentences here.
"""
from __future__ import annotations

import functools
import re
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

import route_content_896 as rc

TAG = "[LOCAL-906C]"
MARKER_LINE = re.compile(r"^\s*<!--.*?-->\s*$")
_MARKER_ANY = re.compile(r"<!--.*?-->", re.S)


def _emit(log: Optional[Callable]) -> Callable:
    return log or (lambda _m: None)


def _ev_map(evidence_by_title: Optional[Dict[str, str]]) -> Dict[str, str]:
    ev = dict(rc._EVIDENCE_904)
    try:   # [LOCAL-906H] the job's delivery-evidence store (every producer fills it)
        import delivery_evidence_906h as _de
        ev.update(_de.get())
    except Exception:
        pass
    ev.update({str(k): str(v) for k, v in (evidence_by_title or {}).items()})
    return {rc.fold(k): v for k, v in ev.items()}


def _body_idx(lines: List[str], last: bool) -> List[int]:
    """Prose lines that are the stop's own body (markers excluded; on the last stop only the first prose line,
    the rest is the tour's closing)."""
    idx = [i for i, ln in enumerate(lines)
           if i > 0 and ln.strip() and not rc._KEYED.match(ln) and not MARKER_LINE.match(ln)]
    return idx[:1] if last and idx else idx


def _edit_body(block: str, last: bool, fn: Callable[[List[str]], List[str]]) -> str:
    lines = block.split("\n")
    changed = False
    for i in _body_idx(lines, last):
        sents = rc.split_sentences(lines[i])
        new = fn(sents)
        if new != sents:
            changed = True
            lines[i] = " ".join(new) if new else None
    if not changed:
        return block
    return re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None))


# ══ 1. scope-matched superlatives and exclusivity ════════════════════════════════════════════════════════
_SUP_RX = re.compile(r"(?i)\bthe\s+(?:(?:very|joint|single)\s+)?"
                     r"(largest|biggest|greatest|longest|tallest|highest|oldest|deepest|widest|smallest|only|sole|first)\b")
_NO_OTHER = re.compile(r"(?i)\bno\s+other\b")
_ONE_OF = re.compile(r"(?i)\b(?:one|among|some)\s+of\s*$|\b(?:among|one\s+of)\s+$")
_NAME = r"(?:<[^>]{1,40}>|[A-ZÀ-Ỹ][\w'’\-]*)"
_GEN = r"(?:[Ww]orld|[Cc]ountry|[Nn]ation|[Rr]egion|[Cc]ontinent|[Pp]rovince|[Ss]tate|[Cc]ity|[Tt]own|[Ii]sland)\b"
# [LOCAL-906F] "in all of X", "across all of X", "in the whole of X", "anywhere in X" name the same scope as "in X"
_QUANT = r"(?:(?:all\s+of|the\s+whole\s+of|the\s+entire|the\s+whole|all|whole|entire)\s+)?"
_SCOPE_RX = re.compile(
    r"\b(?:in|across|within|throughout|anywhere\s+in|anywhere\s+within)\s+" + _QUANT +
    r"(?:the\s+)?(?P<s>" + _NAME + r"(?:\s+" + _NAME + r")*|" + _GEN + r")"
    r"|\bof\s+(?:the\s+)?(?P<s2><[^>]{1,40}>|[Ww]orld\b)")
_SIZE_WORDS = r"largest|biggest|greatest|longest|tallest|highest|oldest|deepest|widest|smallest"
# [LOCAL-906F] "<area>'s largest ..." / "the world's longest ..."
_POSS_RX = re.compile(
    r"(?P<s>(?:" + _NAME + r"(?:\s+" + _NAME + r")*)|[Tt]he\s+[Ww]orld|[Ww]orld)['\u2019]s\s+"
    r"(?:(?:very|joint|single)\s+)?(?:[\w\-]+\s+){0,2}?(?P<w>" + _SIZE_WORDS + r")\b")
_MOST_RX = re.compile(r"(?i)\bone\s+of\s+the\s+most\s+(?P<w>[a-z\-]{4,})\b")
_CLASS = {"largest": "size", "biggest": "size", "greatest": "size", "longest": "length", "tallest": "height",
          "highest": "height", "oldest": "age", "deepest": "depth", "widest": "width", "smallest": "small",
          "only": "only", "sole": "only", "no other": "only", "first": "first"}
_RANK_WORDS = {"world": 6.0, "continent": 5.0, "region": 4.0, "country": 3.0, "nation": 3.0, "state": 2.0,
               "province": 2.0, "city": 1.0, "town": 1.0, "island": 1.0, "district": 0.5}
_MACRO = {"asia": 5.0, "europe": 5.0, "africa": 5.0, "oceania": 5.0, "north america": 5.0, "south america": 5.0,
          "southeast asia": 4.0, "east asia": 4.0, "south asia": 4.0, "central asia": 4.0, "middle east": 4.0,
          "scandinavia": 4.0, "the balkans": 4.0, "balkans": 4.0, "latin america": 4.0, "caribbean": 4.0}
_NOISE_C = set(rc._NOISE) | {"largest", "biggest", "greatest", "longest", "tallest", "highest", "oldest", "deepest",
                             "widest", "smallest", "only", "sole", "first", "other", "country", "countries",
                             "nation", "region", "province", "world", "that", "part", "scale", "kind", "known",
                             "like", "such"}
_SIZE_FAMILY = {"size", "length", "height", "age", "depth", "width", "small"}


def _plain(text: str) -> str:
    return re.sub(r"<([^>]*)>", r"\1", text or "")


def scope_rank(scope: str) -> Optional[float]:
    """How wide a scope is: world 6 > continent / macro-region 5-4 > country 3 > province 2 > city 1. A generic word
    or a ``<Country>`` placeholder says it; a macro-region name too; any other proper name is unknown (None)."""
    s = rc.fold(_plain(scope)).strip()
    s = re.sub(r"^the\s+", "", s)
    if s in _MACRO:
        return _MACRO[s]
    for w in re.findall(r"[^\W\d_]+", s):
        if w in _RANK_WORDS:
            return _RANK_WORDS[w]
    return None


def _scope_key(scope: str) -> str:
    return re.sub(r"^the\s+", "", rc.fold(_plain(scope)).strip())


def scope_covers(evidence_scope: str, claim_scope: str) -> bool:
    """The evidence states the superlative for a scope that covers the claim's: the same scope, or a strictly wider
    one (known ranks). Two different names of the same rank, or an unknown name, do not cover each other."""
    if _scope_key(evidence_scope) == _scope_key(claim_scope):
        return True
    re_, rcl = scope_rank(evidence_scope), scope_rank(claim_scope)
    return re_ is not None and rcl is not None and rcl < re_


def scoped_claim(sentence: str, include_hedged: bool = False) -> Optional[Dict]:
    """Cached wrapper: the result is read-only to every caller ([LOCAL-906J]: the delivery pass asks about the same sentence
    several times). See ``_scoped_claim``."""
    return _scoped_claim_cached(sentence or "", bool(include_hedged))


@functools.lru_cache(maxsize=4096)
def _scoped_claim_cached(sentence: str, include_hedged: bool) -> Optional[Dict]:
    return _scoped_claim(sentence, include_hedged)


def _scoped_claim(sentence: str, include_hedged: bool = False) -> Optional[Dict]:
    """{'word', 'cls', 'scope', 'rank', 'toks', 'hedged'} for a sentence that makes a superlative / exclusivity claim
    for a named area (\"the longest reclining Buddha in <Region>\", \"the only country in <Region> to grow <fruit>\",
    \"the largest X in all of <Region>\", \"<Region>'s largest X\").
    A hedged \"one of the largest ... in <area>\" is returned (``hedged`` True) only with ``include_hedged``
    [LOCAL-906F]; None for anything else (no scope phrase)."""
    x = sentence or ""
    m = _SUP_RX.search(x)
    no = _NO_OTHER.search(x)
    cue = m or no
    hedged = False
    if cue and m and _ONE_OF.search(x[:cue.start()].rstrip() + " "):
        hedged = True
        if not include_hedged:
            return None
    word = (m.group(1).lower() if m else "no other") if cue else ""
    if not cue and include_hedged:
        mo = _MOST_RX.search(x)
        if mo:
            cue, hedged, word = mo, True, "most-" + mo.group("w").lower()
    if cue:
        rest = x[cue.end():]
        sm = _SCOPE_RX.search(rest)
        if sm:
            scope = (sm.group("s") or sm.group("s2") or "").strip()
            stripped = x[:cue.start()] + " " + rest[:sm.start()] + " " + rest[sm.end():]
            toks = {t for t in rc._content_tokens(_plain(stripped)) if t not in _NOISE_C}
            return {"word": word, "cls": _CLASS.get(word, word), "scope": scope, "rank": scope_rank(scope),
                    "toks": toks, "hedged": hedged}
        # also the scope BEFORE the cue: "In <Region>, this is the largest ..." is not handled (no cue-relative rule)
    pm = _POSS_RX.search(x)
    if pm:
        w = pm.group("w").lower()
        scope = pm.group("s").strip()
        if _ONE_OF.search(x[:pm.start()].rstrip() + " "):          # [LOCAL-906J] "one of <Region>'s largest X"
            if not include_hedged:
                return None
            stripped = x[:pm.start()] + " " + x[pm.end():]
            toks = {t for t in rc._content_tokens(_plain(stripped)) if t not in _NOISE_C}
            return {"word": w, "cls": _CLASS.get(w, w), "scope": re.sub(r"(?i)^the\s+", "", scope),
                    "rank": scope_rank(scope), "toks": toks, "hedged": True}
        stripped = x[:pm.start()] + " " + x[pm.end():]
        toks = {t for t in rc._content_tokens(_plain(stripped)) if t not in _NOISE_C}
        return {"word": w, "cls": _CLASS.get(w, w), "scope": re.sub(r"(?i)^the\s+", "", scope),
                "rank": scope_rank(scope), "toks": toks, "hedged": False}
    return None


_CLAUSE_SPLIT = re.compile(r"(?i)\s*;\s*|\s*,\s*|\s+(?:and|but|while|whereas)\s+|\s+(?=(?:also\s+)?remains\b)|\s+(?=(?:is|are)\s+also\b)")
_SIZE_ONE = {"size", "length"}          # [LOCAL-906K] largest / biggest / longest count as ONE size class


def cls_eq(a: Optional[str], b: Optional[str]) -> bool:
    return a == b or (a in _SIZE_ONE and b in _SIZE_ONE)


def scoped_claims(sentence: str, include_hedged: bool = False) -> List[Dict]:
    """[LOCAL-906K] EVERY superlative clause of a sentence (split on and / but / while / ; / , and "remains" / "is also"),
    the whole-sentence claim first. A clause's tokens carry the whole sentence's subject words, so ``remains one of the
    largest in <Region>`` still names the reclining Buddha of its first clause."""
    x = sentence or ""
    out: List[Dict] = []
    seen = set()
    first = scoped_claim(x, include_hedged)
    if first:
        out.append(first)
        seen.add((first["word"], first["scope"], first["hedged"]))
    parts = [p for p in _CLAUSE_SPLIT.split(x) if p and p.strip()]
    if len(parts) < 2:
        return out
    whole = {t for t in rc._content_tokens(_plain(x)) if t not in _NOISE_C}
    for part in parts:
        e = scoped_claim(part, include_hedged)
        if not e:
            continue
        key = (e["word"], e["scope"], e["hedged"])
        if key in seen:
            continue
        seen.add(key)
        scope_t = rc._content_tokens(_plain(e["scope"]))
        e = dict(e)
        e["toks"] = set(e["toks"]) | (whole - scope_t)
        out.append(e)
    return out


def _local_scope(claim: Dict, title: str) -> bool:
    """The scope is the stop's own venue / place (a name inside the stop title): not a regional claim."""
    st = rc._content_tokens(_plain(claim["scope"]))
    return bool(st) and st <= rc._content_tokens(title)


def _overlap_ok(a: Set[str], b: Set[str]) -> bool:
    return len(a & b) >= min(3, len(a)) and bool(a)


def check_claim(sentence: str, evidence: str, title: str = "") -> Tuple[str, Optional[str]]:
    """('na' | 'ok' | 'bad', narrower supported evidence sentence or None). ``na``: not a scoped claim."""
    c = scoped_claim(sentence, include_hedged=True)       # [LOCAL-906F] a hedged claim is scope-checked too
    if not c or _local_scope(c, title):
        return "na", None
    narrower = None
    for es, e in ((es_, e_) for es_ in rc.split_sentences(evidence or "") for e_ in scoped_claims(es_, include_hedged=True)):
        if e["hedged"] and not c["hedged"]:
            continue                       # "one of the largest" does not back "the largest"
        shared = len(c["toks"] & e["toks"])
        _ovl = _overlap_ok(c["toks"], e["toks"]) or (c["hedged"] and not c["toks"])
        if e["cls"] == c["cls"] and scope_covers(e["scope"], c["scope"]) and _ovl:   # (one size class: hedges only)
            return "ok", None
        if c["hedged"]:
            continue
        # a narrower version of the same fact: the evidence states a superlative of the same thing for a smaller area
        if (narrower is None and e["cls"] in _SIZE_FAMILY | {"only", "first"} and c["cls"] in _SIZE_FAMILY | {"only", "first"}
                and e["rank"] is not None and c["rank"] is not None and e["rank"] < c["rank"]
                and shared >= min(2, len(c["toks"])) and shared >= 1
                and 5 <= len(es.split()) <= 40 and es.strip()[-1:] in ".!?" and not rc.is_fragment(es)):
            narrower = es.strip()
    return "bad", narrower


# ══ 1b. [LOCAL-906J] a hedge anywhere wins ═══════════════════════════════════════════════════════════════
_J = "[LOCAL-906J]"
_SIZE_CLASSES = {"size", "length", "height", "age", "depth", "width", "small"}


def _plural(word: str) -> str:
    w = word or ""
    lw = w.lower()
    if not w or lw.endswith("s") and not lw.endswith("ss"):
        return w                                   # already plural ("statues")
    if re.search(r"(?i)[^aeiou]y$", w):
        return w[:-1] + "ies"
    if re.search(r"(?i)(?:s|x|z|ch|sh)$", w):
        return w + "es"
    return w + "s"


def _hedge_text(x: str) -> Optional[str]:
    """``x`` (an unhedged size superlative for a scope) rewritten as the hedged form, grammar included:
    "This statue is the largest reclining Buddha in <Region>." -> "... is one of the largest reclining Buddhas in <Region>."
    None when the sentence has no such shape."""
    m = _SUP_RX.search(x)
    if m and m.group(1).lower() in {"largest", "biggest", "greatest", "longest", "tallest", "highest", "oldest", "deepest",
                                    "widest", "smallest"}:
        rest = x[m.end():]
        sm = _SCOPE_RX.search(rest)
        if not sm:
            return None
        np_ = rest[:sm.start()]
        # the head noun: the last word before " of " when there is one, else the last word of the noun phrase
        if re.search(r"\bof\b", np_):
            head = re.match(r"(?s)^(.*?)(\b[\w'’\-]+)(\s+of\b.*)$", np_)
            np2 = (head.group(1) + _plural(head.group(2)) + head.group(3)) if head else np_
        else:
            wm = re.search(r"([\w'’\-]+)(\s*)$", np_)
            np2 = (np_[:wm.start()] + _plural(wm.group(1)) + wm.group(2)) if wm else np_
        lead = x[:m.start()]
        tail = re.sub(r"(?i)^(\b(?:in|across|within|throughout)\s+)(?:all|whole|entire)\s+(?!of\b)",
                      r"\1", rest[sm.start():])      # [LOCAL-906K] "in all <Region>" -> "in <Region>": the hedge carries no "all"
        return lead + "one of the " + m.group(1).lower() + np2 + tail
    pm = _POSS_RX.search(x)
    if pm and pm.group("w").lower() in {"largest", "biggest", "greatest", "longest", "tallest", "highest", "oldest", "deepest",
                                         "widest", "smallest"}:
        after = x[pm.end():]
        nm = re.match(r"((?:\s+[\w'’\-]+)+?)(?=\s+(?:in|on|at|of|with|by|for|from|to|that|which|and|is|are|was)\b|\s*[.,;:!?]|\s*$)", after)
        if nm:
            np_ = nm.group(1)
            wm = re.search(r"([\w'’\-]+)$", np_)
            after = np_[:wm.start()] + _plural(wm.group(1)) + after[nm.end():]
        return x[:pm.start()] + "one of " + x[pm.start():pm.end()] + after
    return None


def hedged_by_evidence(sentence: str, evidence: str, title: str = "") -> Optional[str]:
    """The hedged rewrite of an UNHEDGED size superlative when ANY evidence sentence hedges the same superlative class for
    the same scope ("one of the largest ... in <Region>", "among the largest ..."); None otherwise. A hedge anywhere wins."""
    c = scoped_claim(sentence)
    if not c or c["hedged"] or c["cls"] not in _SIZE_CLASSES or _local_scope(c, title):
        return None
    for e in (e_ for es_ in rc.split_sentences(evidence or "") for e_ in scoped_claims(es_, include_hedged=True)):
        if not e["hedged"] or not cls_eq(e["cls"], c["cls"]):      # [LOCAL-906K] a hedge in ANY clause, one size class
            continue
        if _scope_key(e["scope"]) != _scope_key(c["scope"]):
            continue
        ct = c["toks"] - set(rc._content_tokens(title))
        et = e["toks"] - set(rc._content_tokens(title))
        if not (ct and et and len(ct & et) >= min(2, len(ct))) and ct and et:
            continue
        new = _hedge_text(sentence)
        if new and new != sentence:
            return new
    return None


# ══ 1c. [LOCAL-906J] record claims are scoped claims ═════════════════════════════════════════════════════
_REC_WORDS = r"(?:highest|longest|largest|tallest|biggest|deepest|oldest|widest|fastest|steepest|smallest|most)"
_RECORD_RX = re.compile(
    r"(?i)\b(?:(?:world|guinness|national|all-time|official)[\s-]records?\b"
    r"|record[\s-]breaking\b"
    r"|(?:holds?|held|holding|owns?|set|sets|setting|broke|breaks|breaking)\s+(?:the\s+|a\s+)?(?:[\w\-]+\s+){0,2}?records?\b"
    r"|records?\s+for\s+(?:the\s+)?" + _REC_WORDS + r"\b"
    # [LOCAL-906K] exclusivity is a record class: "the only country in <Region> that ...", "the sole place ..."
    r"|\bthe\s+(?:only|sole)\s+(?:[\w\-]+\s+){0,2}?(?:countr(?:y|ies)|nations?|places?|cit(?:y|ies)|towns?|provinces?|regions?|"
    r"islands?|sites?|locations?|spots?|areas?|states?|villages?|temples?|pagodas?|statues?)\b)")
_REC_NOISE = {"record", "records", "holds", "hold", "held", "world", "guinness", "official", "breaking", "highest", "longest",
              "largest", "tallest", "biggest", "deepest", "oldest", "widest", "fastest", "steepest", "smallest", "national",
              "alltime", "this", "that", "which", "title"}


def record_claim(sentence: str) -> Optional[Dict]:
    """{'scope', 'rank', 'toks', 'kind'} for a record claim ("holds the (world) record for ...", "a (Guinness) world record",
    "record-breaking", "record for the highest ...", "the world's highest / longest ..."); the scope is the WORLD unless
    stated otherwise. A hedged "one of the ..." is not a record claim. None for anything else."""
    x = sentence or ""
    m = _RECORD_RX.search(x)
    kind = "record"
    scope = "world"
    if m and re.search(r"(?i)\b(?:only|sole)\b", m.group(0)):
        kind = "exclusivity"
    if m:
        if re.search(r"(?i)\bnational", m.group(0)):
            scope = "country"
        sm = _SCOPE_RX.search(x[m.end():])
        if sm:
            scope = (sm.group("s") or sm.group("s2") or "").strip() or scope
        stripped = x[:m.start()] + " " + x[m.end():]
    else:
        c = scoped_claim(x)
        if not c or c["hedged"] or c["cls"] not in _SIZE_CLASSES or c["rank"] != 6.0:
            return None                        # only the world's superlatives are record claims here
        kind, scope, stripped = "world-superlative", c["scope"], None
    if _ONE_OF.search(x[:m.start()].rstrip() + " " if m else ""):
        return None
    toks = ({t for t in rc._content_tokens(_plain(stripped)) if t not in _NOISE_C and t not in _REC_NOISE}
            if stripped is not None else {t for t in c["toks"] if t not in _REC_NOISE})
    return {"scope": scope, "rank": scope_rank(scope), "toks": toks, "kind": kind, "cls": (scoped_claim(x) or {}).get("cls")}


def record_support(sentence: str, evidence: str, title: str = "", entries: Optional[List[Dict]] = None) -> str:
    """'na' (not a record claim / the stop's own venue) | 'ok' | 'bad'. Supported only when a NON-LLM source for this stop
    states a record for the same object. For WORLD scope that source must be a reference (encyclopedia, an official /
    record body page) OR two independent web domains; one web snippet is not enough. ``entries`` are the delivery
    store's per-entry provenance ({text, kind, domain}); without them (a caller-passed plain evidence string) the text
    alone is judged."""
    c = record_claim(sentence)
    if not c:
        return "na"
    if c["scope"] and rc._content_tokens(_plain(c["scope"])) and rc._content_tokens(_plain(c["scope"])) <= rc._content_tokens(title):
        return "na"

    def states(text: str) -> bool:
        for es in rc.split_sentences(text or ""):
            e = record_claim(es)
            if not e:
                continue
            if c["kind"] == "world-superlative" and e["kind"] == "world-superlative" and e["cls"] != c["cls"]:
                continue
            if (c["kind"] == "exclusivity") != (e["kind"] == "exclusivity"):
                continue                                       # [LOCAL-906K] "the only X" is backed only by "the only X"
            if c["kind"] == "exclusivity" and not scope_covers(e["scope"], c["scope"]):
                continue                                       # ... and for a scope that covers the claim's
            if not (e["scope"] and c["scope"]) or (c["rank"] is not None and e["rank"] is not None and e["rank"] < c["rank"]):
                continue
            shared = len(c["toks"] & e["toks"])
            if shared >= min(2, len(c["toks"])) and (shared >= 1 or not c["toks"]):
                return True
        return False
    ents = [en for en in (entries or []) if (en.get("kind") in ("article", "web", "user-article"))]
    if not ents:
        return "ok" if states(evidence) else "bad"
    sup = [en for en in ents if states(en.get("text", ""))]
    if not sup:
        return "bad"
    if c["kind"] != "exclusivity" and c["rank"] is not None and c["rank"] < 6.0 and c["scope"] != "world":
        return "ok"                                            # a narrower stated scope: any non-LLM statement
    try:
        import delivery_evidence_906h as _de
        ref = any(en.get("kind") == "article" or _de.is_reference_domain(en.get("domain", "")) for en in sup)
    except Exception:  # pragma: no cover
        ref = any(en.get("kind") == "article" for en in sup)
    domains = {en.get("domain") for en in sup if en.get("domain")}
    return "ok" if ref or len(domains) >= 2 else "bad"



def _entries_for(title: str) -> List[Dict]:
    """The delivery store's per-entry provenance for a stop title (exact, else a folded key that contains / is contained)."""
    try:
        import delivery_evidence_906h as _de
        allv = _de.entries()
        f = rc.fold(title)
        out: List[Dict] = []
        for k, v in allv.items():
            fk = rc.fold(k)
            if fk == f or (fk and f and (fk in f or f in fk)):
                out.extend(v)
        return out
    except Exception:  # pragma: no cover
        return []


def drop_unsupported_scope_claims(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                                  log: Optional[Callable] = None, require_evidence_map: bool = True) -> str:
    """Item 2. On ANY tour: a scoped superlative / exclusivity sentence whose scope the stop's evidence does not
    cover is dropped (or replaced by the evidence's own narrower sentence). A stop with no evidence states nothing.
    ``require_evidence_map``: when no evidence at all was handed in AND the tour is neither a route nor a
    single-place tour, there is nothing to judge by and the text is returned as it is."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        ev_map = _ev_map(evidence_by_title)
        if require_evidence_map and not ev_map:
            import route_leftovers_906 as _l906
            if not _l906.in_scope(tour_text):
                return tour_text
        blocks = rc._stop_blocks(tour_text)
        no_map = not ev_map
        pieces, pos = [], 0
        for k, (s, e, num, title) in enumerate(blocks):
            pieces.append(tour_text[pos:s])
            pos = e
            ev = rc._ev_for(ev_map, title) or ""
            last = k == len(blocks) - 1

            def fix(sents: List[str], _ev=ev, _t=title, _n=num) -> List[str]:
                out: List[str] = []
                for x in sents:
                    if rc._CLOSING_LINE.match(x):
                        out.append(x)
                        continue
                    hedged = hedged_by_evidence(x, _ev, _t)           # [LOCAL-906J] a hedge anywhere wins
                    if hedged:
                        emit(f'  {_J} Stop {_n}: superlative hedged to match the evidence: "{x[:80]}"')
                        x = hedged
                    rec = record_support(x, _ev, _t, _entries_for(_t)) if (record_claim(x) and (_ev or not no_map)) else "na"
                    if rec == "bad":
                        emit(f'  {_J} Stop {_n}: record claim unsupported by a non-LLM source (reference or 2 domains for '
                             f'world scope): "{x[:80]}"')
                        continue
                    if rec == "ok":
                        out.append(x)
                        continue
                    status, narrower = check_claim(x, _ev, _t)
                    if no_map and status == "bad" and (scoped_claim(x, include_hedged=True) or {}).get("cls") not in ("only", "first"):
                        status = "na"       # no evidence at all was handed in: a plain superlative cannot be judged
                    if status != "bad":
                        out.append(x)
                        continue
                    emit(f'  {TAG} Stop {_n}: superlative scope unsupported: "{x[:80]}"')
                    if narrower and not any(rc.fold(narrower) == rc.fold(y)
                                            or (rc.same_fact(narrower, y, _t) and not claim_vs_plain(narrower, y))
                                            for y in sents + out if y is not x):
                        emit(f'  {TAG} Stop {_n}: narrower supported version used: "{narrower[:80]}"')
                        out.append(narrower)
                return out
            pieces.append(_edit_body(tour_text[s:e], last, fix))
        pieces.append(tour_text[pos:])
        return "".join(pieces)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} scope-claim guard skipped (non-fatal): {err}")
        return tour_text


# ══ 2. the within-stop duplicate keeps the supported claim ═══════════════════════════════════════════════
def prefer_supported(xa: str, xb: str, evidence: str, title: str = "") -> Optional[str]:
    """Which of two same-fact sentences LOSES: 'a' / 'b' when exactly one makes a scope claim the evidence does not
    support (the narrower, supported one stays); when both do (or neither has evidence to judge by) the one with the
    wider known scope loses; None when scope does not decide (then specificity does)."""
    ca, cb = scoped_claim(xa, include_hedged=True), scoped_claim(xb, include_hedged=True)
    if not ca and not cb:
        return None
    sa = check_claim(xa, evidence, title)[0] if ca else "na"
    sb = check_claim(xb, evidence, title)[0] if cb else "na"
    if sa == "bad" and sb != "bad":
        return "a"
    if sb == "bad" and sa != "bad":
        return "b"
    if ca and cb and ca["rank"] is not None and cb["rank"] is not None and ca["rank"] != cb["rank"]:
        return "a" if ca["rank"] > cb["rank"] else "b"
    return None


def claim_vs_plain(xa: str, xb: str) -> bool:
    """One sentence ranks the thing for an area ("the largest ... in <Country>"), the other only describes it
    ("... is 49 meters long"): two facts, not one, whatever words they share."""
    return (scoped_claim(xa) is None) != (scoped_claim(xb) is None)


# ══ 3. no two stops share a filler body ══════════════════════════════════════════════════════════════════
_DISC_PREFIX = None


def _disc_fold() -> str:
    global _DISC_PREFIX
    if _DISC_PREFIX is None:
        import strict_grounding_gate as sgg
        _DISC_PREFIX = rc.fold(sgg.NO_HISTORY_DISCLOSURE)[:30]
    return _DISC_PREFIX


def _is_disclosure(sentence: str) -> bool:
    return _disc_fold() in rc.fold(sentence)


_KIND_RX = (
    ("departure", re.compile(r"(?i)\b(?:drive\s+home|heading\s+home|going\s+home|way\s+back|departure|farewell|leaving|"
                             r"return(?:ing)?\s+(?:home|to)|back\s+to)\b")),
    ("ascent", re.compile(r"(?i)\b(?:ascent|ascend|cable\s*car|gondola|funicular|chair\s*lift|climb|ride\s+up|trail|hike)\b")),
    ("view", re.compile(r"(?i)\b(?:views?|viewpoint|overlook|lookout|panorama|vista|belvedere|scenic\s+stop)\b")),
    ("market", re.compile(r"(?i)\b(?:market|bazaar|stalls?|shopping|fair)\b")),
    ("shore", re.compile(r"(?i)\b(?:beach|shore|seaside|coast(?:line)?|bay|harbou?r|pier|waterfront|lakeside|cove)\b")),
)

# Generic, name-free filler variants per kind. Each is 2 sentences ({t} = the stop's short spoken name); the
# disclosure follows. Enough variants per kind (and a shared pool) that no two stops of a tour need the same one.
FILLER_VARIANTS: Dict[str, Tuple[Tuple[str, ...], ...]] = {
    "view": (
        ("From {t}, let your eyes travel to the horizon and notice how the distance softens into haze.",
         "Pause for a few breaths and listen to what the air carries."),
        ("Take in the wide view from {t}, and notice where the land meets the sky.",
         "Let the quiet open up around you before you move on."),
        ("At {t}, find a clear line of sight and follow the shapes of the land into the distance.",
         "Notice the light on the far slopes and the way it shifts."),
    ),
    "ascent": (
        ("On the way up at {t}, feel the ground fall away and the air begin to change.",
         "Watch how the trees thin out and the view widens as you climb."),
        ("As you rise at {t}, notice the sounds fading below you.",
         "Look back now and then to see how much ground you have covered."),
        ("Along {t}, take the climb at your own pace and let your breathing settle.",
         "Notice how the colours of the slope change with every few steps."),
    ),
    "departure": (
        ("As you leave {t}, let the day settle and carry the quiet of the trip with you.",
         "Look back once at where you have been before the road takes over."),
        ("On the way back from {t}, notice how the light has changed since the morning.",
         "Let your thoughts wander over the places you passed."),
        ("Heading away from {t}, watch the landscape slide by at an easier pace.",
         "Take a moment to recall the sounds and smells you met today."),
    ),
    "market": (
        ("Around {t}, listen to the calls of the sellers and the shuffle of people between the stalls.",
         "Notice the colours and the smells that mix in the air."),
        ("At {t}, let the bustle wash around you and watch how people choose and bargain.",
         "Pay attention to the sounds of weighing, wrapping and chatting."),
        ("Walking through {t}, follow the smell of fresh food and the rhythm of the crowd.",
         "Notice what is stacked, hung and piled at every stall."),
    ),
    "shore": (
        ("At {t}, listen to the water arriving and leaving along the edge of the land.",
         "Notice the feel of the breeze and the texture of the ground beneath your feet."),
        ("By {t}, watch how the water changes colour as the light moves.",
         "Breathe in the salt and the open air and let the pace slow."),
        ("Along {t}, follow the line where land meets water.",
         "Listen for birds, boats and the soft rhythm of the waves."),
    ),
    "road": (
        ("As you pass {t}, look out at the road, the land around it and the pace of the day.",
         "Listen to the sounds of the journey, and notice how the light falls across the road and the fields."),
        ("Along {t}, watch the fields and houses go by and notice how the land shifts from one stretch to the next.",
         "Let the rhythm of the road set the mood for the next stretch."),
        ("Through {t}, notice the small details at the roadside, from the plants to the signs.",
         "Roll the window down if you can and listen to the day."),
    ),
    "height": (
        ("At {t}, look out at the view and notice how far the land opens below you.",
         "Feel the height and the cooler, thinner air, and listen for the wind."),
        ("Up at {t}, let your gaze drop to the valleys and rise again to the clouds.",
         "Notice how the sounds of the lowlands fade at this height."),
        ("From {t}, notice how small the paths below look and how big the sky feels.",
         "Take a slow breath of the clear air."),
    ),
    "worship": (
        ("At {t}, take in the courtyard and the quiet that settles over it.",
         "Listen for the soft sounds of the place, and notice how people move more slowly here."),
        ("Within {t}, notice the colours, the carved details and the stillness between visitors.",
         "Lower your voice and let the calm of the place come to you."),
        ("Around {t}, follow the paths between the buildings and listen for bells or quiet voices.",
         "Notice the scent in the air and the way the light falls inside."),
    ),
    "neutral": (
        ("Take a moment at {t} and take in the place and the pace of the day.",
         "Listen for the sounds that belong to this spot, and notice how the light falls around you."),
        ("Slow down at {t} and notice the small things that make this spot what it is.",
         "Pay attention to what you can hear, smell and feel here."),
        ("Stand a while at {t} and let the surroundings come into focus.",
         "Notice the textures, the colours and the sounds close to you."),
        ("At {t}, look around you slowly and take in the shapes and the colours.",
         "Notice how the place feels different from the last one."),
        ("Spend a quiet minute at {t} and listen to what the place offers.",
         "Let your eyes settle on one detail and then widen out again."),
    ),
}


def filler_kind(title: str, type_text: str = "") -> str:
    """'view' | 'ascent' | 'departure' | 'market' | 'shore' | 'road' | 'height' | 'worship' | 'neutral'."""
    for text in (title or "", type_text or ""):
        for kind, rx in _KIND_RX:
            if rx.search(text):
                return kind
    try:
        import place_names_900 as pn
        return pn.stop_kind(title, type_text)
    except Exception:
        return "neutral"


def _toks_of(sents: Sequence[str], title: str) -> Set[str]:
    skip = set(rc._words(title))
    try:
        import place_names_900 as pn
        skip |= set(rc._words(pn.short_place_name(title)))
    except Exception:
        pass
    return {w for w in rc._words(" ".join(x for x in sents if not _is_disclosure(x))) if w not in skip}


def _same_body(a: Set[str], b: Set[str], thr: float = 0.8) -> bool:
    return len(a) >= 5 and len(b) >= 5 and len(a & b) / min(len(a), len(b)) >= thr


def _is_filler_body(sents: Sequence[str]) -> bool:
    if not sents:
        return False
    return any(_is_disclosure(x) for x in sents) or all(rc.is_mood_filler(x, set()) for x in sents)


def _stops_info(text: str) -> List[Dict]:
    blocks = rc._stop_blocks(text)
    out = []
    for k, (s, e, num, title) in enumerate(blocks):
        lines = text[s:e].split("\n")
        last = k == len(blocks) - 1
        try:
            import delivery_bodies_905 as db
            idx = [i for i in db._body_sentences(lines, last, rc) if not MARKER_LINE.match(lines[i])]
        except Exception:
            idx = _body_idx(lines, last)
        sents = [x for i in idx for x in rc.split_sentences(lines[i]) if not rc._CLOSING_LINE.match(x)]
        tm = re.search(r"(?mi)^Type/Specialty:\s*(.+?)\s*$", text[s:e])
        out.append({"s": s, "e": e, "num": num, "title": title, "lines": lines, "idx": idx, "sents": sents,
                    "type": tm.group(1) if tm else "", "last": last})
    return out


def _set_body(text: str, info: Dict, new_sents: List[str]) -> str:
    lines = list(info["lines"])
    idx = info["idx"]
    if not idx:
        return text
    lines[idx[0]] = " ".join(new_sents)
    for i in idx[1:]:
        lines[i] = None
    block = re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None))
    return text[:info["s"]] + block + text[info["e"]:]


def _borrow_sentence(info: Dict, infos: List[Dict], ev_map: Dict[str, str], taken: List[Set[str]],
                     _tour: Optional[str] = None, _log: Optional[Callable] = None) -> Optional[str]:
    """(a) A not-yet-delivered evidence sentence of a neighbouring stop (or the tour's scope) that names THIS stop's
    subject (D771: the sentence is grounded in evidence, not written). None when there is none."""
    try:
        import place_names_900 as pn
    except Exception:
        return None
    short = pn.short_place_name(info["title"])
    own = rc.fold(info["title"])
    for key, blob in ev_map.items():
        if key == own or not blob:
            continue
        usable = []
        for x in rc.split_sentences(blob):
            xs = set(rc._words(x))
            if len(xs) < 5 or any(len(xs & t) / min(len(xs), len(t)) >= 0.85 for t in taken if len(t) >= 5):
                continue                                           # already delivered somewhere
            if scoped_claim(x) and check_claim(x, blob, info["title"])[0] != "ok":
                continue
            if rc.is_mood_filler(x, set()) or rc._has_travel(x) or rc.is_offsite_suggestion(x, set()):
                continue
            try:       # [LOCAL-906K] the refill quality bar: a search snippet's junk is not unused evidence
                import refill_quality_906k as _k
                if _k.reject_logged(x, info["title"], _tour, _log, info["num"], _k.source_of(x, blob, key), info.get("type", "")):
                    continue
            except Exception:  # pragma: no cover
                pass
            usable.append(x)
        got = pn.neighbour_sentence(short, [" ".join(usable)], rc.split_sentences) if usable else None
        if got:
            return got.strip()
    return None


def _pick_variant(kind: str, info: Dict, others: List[Set[str]], skip_first: bool = False
                  ) -> Optional[Tuple[str, int, List[str]]]:
    """(kind used, variant number, sentences) of the first variant of ``kind`` (then the shared neutral pool) whose
    content differs from every other stop's body."""
    try:
        import place_names_900 as pn
        short = pn.short_place_name(info["title"])
    except Exception:
        short = info["title"]
    pools = [kind] + [k for k in ("neutral",) if k != kind]
    for pk in pools:
        for n, var in enumerate(FILLER_VARIANTS.get(pk, ()), 1):
            sents = [v.format(t=short) for v in var]
            key = _toks_of(sents, info["title"])
            if not any(_same_body(key, o) for o in others):
                return pk, n, sents
    return None


def _merge_into_previous(text: str, prev: Dict, cur: Dict) -> str:
    """(c) Drop ``cur``'s header, Coordinates / Type / Orientation / body; keep its Directions (and, on the last stop,
    the tour's closing). ``prev``'s own Directions pointed at ``cur`` and goes."""
    cl = cur["lines"]
    drop_i = set(cur["idx"]) | {0}
    tail = [ln for i, ln in enumerate(cl)
            if i not in drop_i and (not rc._KEYED.match(ln) or re.match(r"(?i)^\s*directions\s*:", ln))]
    tail_txt = re.sub(r"\n{3,}", "\n\n", "\n".join(tail)).strip("\n")
    pblock = text[prev["s"]:prev["e"]]
    trailing = pblock[len(pblock.rstrip()):]
    plines = [ln for ln in pblock.rstrip().split("\n") if not re.match(r"(?i)^\s*directions\s*:", ln)]
    new_prev = re.sub(r"\n{3,}", "\n\n", "\n".join(plines)).rstrip()
    if tail_txt.strip():
        new_prev += "\n\n" + tail_txt
    cblock = text[cur["s"]:cur["e"]]
    new_prev += cblock[len(cblock.rstrip()):] or trailing
    return text[:prev["s"]] + new_prev + text[cur["e"]:]


def distinct_filler_bodies(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                           log: Optional[Callable] = None) -> str:
    """Item 4. A stop whose honest-filler body repeats an earlier stop's body is rebuilt: (a) from unused evidence of
    the neighbouring stops that fits its title, (b) from a filler variant keyed to its kind that no other stop uses,
    (c) else merged into the previous stop and the count recomputed. The branch taken is logged."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        text = tour_text
        ev_map = _ev_map(evidence_by_title)
        merged = False
        for _round in range(len(rc._stop_blocks(text)) + 1):
            infos = _stops_info(text)
            if len(infos) < 2:
                break
            keys = [_toks_of(i["sents"], i["title"]) for i in infos]
            hit = None
            for k in range(1, len(infos)):
                if not _is_filler_body(infos[k]["sents"]):
                    continue
                prior = next((j for j in range(k) if _same_body(keys[k], keys[j])), None)
                if prior is not None:
                    hit = (k, prior)
                    break
            if hit is None:
                break
            k, prior = hit
            info = infos[k]
            others = [keys[j] for j in range(len(infos)) if j != k]
            taken = [set(rc._words(" ".join(i["sents"]))) for j, i in enumerate(infos) if j != k]
            head = f"  {TAG} Stop {info['num']} '{info['title'][:40]}': filler body repeats Stop {infos[prior]['num']}"
            borrowed = _borrow_sentence(info, infos, ev_map, taken, text, emit)
            var = _pick_variant(filler_kind(info["title"], info["type"]), info, others)
            if borrowed:
                body = [borrowed] + (var[2] if var else []) + [next((x for x in info["sents"] if _is_disclosure(x)), "")]
                body = [x for x in body if x]
                text = _set_body(text, info, body)
                emit(f"{head}; branch (a): unused evidence of a neighbouring stop \"{borrowed[:60]}\"")
                continue
            if var:
                body = var[2] + [next((x for x in info["sents"] if _is_disclosure(x)), "")]
                body = [x for x in body if x]
                text = _set_body(text, info, body)
                emit(f"{head}; branch (b): filler variant '{var[0]}' #{var[1]}")
                continue
            text = _merge_into_previous(text, infos[k - 1], info)
            merged = True
            emit(f"{head}; branch (c): merged into Stop {infos[k - 1]['num']} (header dropped, Directions kept)")
        if merged:
            import delivery_bodies_905 as db
            text = db.fix_counts(text, emit, renumber=True)
        return text
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} filler guard skipped (non-fatal): {err}")
        return tour_text


# ══ 4. "You see the X here is ..." ═══════════════════════════════════════════════════════════════════════
_YOU_SEE_HERE = re.compile(
    r"^(?P<head>(?:You(?:\s+can)?\s+see|Here\s+you\s+see)\s+(?:the|a|an|this|these)\s+[^,.;:!?]{2,80}?\s+here"
    r"(?:\s+(?:on|at|in|by|near)\s+[^,.;:!?]{2,60}?)?)"
    r"\s+(?P<verb>is|are|was|were|measures?|stands?|stretches|spans|rises|lies|sits)\s+(?P<tail>.+)$", re.S)


def repair_you_see_here(tour_text: str, log: Optional[Callable] = None) -> str:
    """"You see the reclining statue here is 49 meters long." -> "You see the reclining statue here. It is 49 meters
    long." Only a sentence of that exact shape is touched."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        blocks = rc._stop_blocks(tour_text)
        pieces, pos = [], 0
        for k, (s, e, num, title) in enumerate(blocks):
            pieces.append(tour_text[pos:s])
            pos = e
            last = k == len(blocks) - 1

            def fix(sents: List[str], _n=num) -> List[str]:
                out = []
                for x in sents:
                    m = _YOU_SEE_HERE.match(x)
                    if not m:
                        out.append(x)
                        continue
                    pron = "They" if m.group("verb").lower() in ("are", "were") else "It"
                    fixed = f"{m.group('head')}. {pron} {m.group('verb')} {m.group('tail')}"
                    emit(f'  {TAG} Stop {_n}: "You see ... here is" opener repaired: "{x[:80]}"')
                    out.append(fixed)
                return out
            pieces.append(_edit_body(tour_text[s:e], last, fix))
        pieces.append(tour_text[pos:])
        return "".join(pieces)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} opener repair skipped (non-fatal): {err}")
        return tour_text


# ══ 5. [LOCAL-906E] a body that opens with a pronoun with nothing before it ════════════════════════════
_PRON_OPEN = re.compile(r"^(?P<pron>Its|It|They|Their|This|These)\b\s*(?P<rest>.*)$", re.S)
_PRON_VERB = rc._VERB_OPEN | {"represents", "represent", "captures", "capture", "remains", "remain", "became",
                              "becomes", "reaches", "reach", "dates", "date", "draws", "draw", "serves", "serve",
                              "looks", "look", "gives", "give", "makes", "make", "belongs", "belong"}


def _title_toks(title: str) -> Set[str]:
    return {w for w in rc.fold(title).split() if len(w) >= 4}


_COMMON_HEADS_906F = frozenset(
    "statue pagoda temple church cathedral museum bridge tower castle palace market park garden station hotel beach building "
    "house gate fort monastery shrine mosque cave waterfall lake river square harbor harbour port gallery theater theatre "
    "monument mausoleum lighthouse fountain library school university stadium airport resort villa tomb arch wall zoo "
    "aquarium cable cableway tram trail path road street avenue boulevard hill mountain island bay valley canyon".split())


def definite_name(title: str) -> str:
    """[LOCAL-906F] "The <Title>" for a title with a common-noun head ("The Reclining Buddha Statue"); the bare title for a
    proper name with none (a capitalised multi-word name, a placeholder, "Mount X"): "The <Mountain> is home to ..." was wrong."""
    t = (title or "").strip()
    if not t or re.match(r"(?i)^(?:the|a|an)\s", t):
        return t if t else "The stop"
    words = re.findall(r"[^\W\d_][\w'’\-]*", re.sub(r"<[^>]*>", " ", t))
    if not words:                                         # a bare placeholder: a proper name
        return t
    if not all(w[:1].isupper() for w in words) and not t.startswith("<"):
        return "The " + t
    head = rc.fold(words[-1])
    if t.endswith(">") or head not in _COMMON_HEADS_906F:
        return t
    return "The " + t


def repair_pronoun_opener(tour_text: str, log: Optional[Callable] = None) -> str:
    """When earlier sentences were dropped, a stop body can open with "Its white color stands out ..." -- a pronoun
    with nothing before it. The pronoun is replaced by the stop's title: "Its X" -> "The <Title>'s X";
    "It is/stands ..." and "They ..." -> "The <Title> ..."; "This <title word> ..." -> "The <Title> ..." (a "This"
    followed by a noun the title does not hold carries its own noun and is left). Only the FIRST body sentence."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        blocks = rc._stop_blocks(tour_text)
        pieces, pos = [], 0
        for k, (s, e, num, title) in enumerate(blocks):
            pieces.append(tour_text[pos:s])
            pos = e
            block = tour_text[s:e]
            title = (title or "").strip()
            idx = _body_idx(block.split("\n"), k == len(blocks) - 1)[:1]
            if not title or not idx:
                pieces.append(block)
                continue
            lines = block.split("\n")
            sents = rc.split_sentences(lines[idx[0]])
            m = _PRON_OPEN.match(sents[0]) if sents else None
            if not m:
                pieces.append(block)
                continue
            pron, rest = m.group("pron"), m.group("rest")
            first = rest.split(" ", 1)[0].lower().strip(",.;:") if rest else ""
            the = definite_name(title)             # [LOCAL-906F] no article before a proper name
            if pron == "Its" or pron == "Their":
                fixed = f"{the}'s {rest}" if the.endswith(("s", "S")) is False else f"{the}' {rest}"
            elif pron in ("It", "They"):
                fixed = f"{the} {rest}"
            elif first in _PRON_VERB:                            # "This is ..."
                fixed = f"{the} {rest}"
            elif first and first in _title_toks(title):          # "This statue ..." -> the title names it
                fixed = f"{the} {rest.split(' ', 1)[1] if ' ' in rest else ''}".strip()
            else:
                pieces.append(block)
                continue
            if fixed == sents[0]:
                pieces.append(block)
                continue
            emit(f'  [LOCAL-906E] Stop {num}: body opened with a pronoun, repaired with the title: "{sents[0][:60]}"')
            sents[0] = fixed
            lines[idx[0]] = " ".join(sents)
            pieces.append("\n".join(lines))
        pieces.append(tour_text[pos:])
        return "".join(pieces)
    except Exception as err:  # pragma: no cover
        emit(f"  [LOCAL-906E] pronoun opener repair skipped (non-fatal): {err}")
        return tour_text


# ══ 4. [LOCAL-906J] a thing referent with no antecedent ══════════════════════════════════════════════════
_THING_HEADS = frozenset(
    "pagoda temple statue church cathedral tower shrine mosque monastery palace castle bridge monument mausoleum fountain "
    "gate fort lighthouse building hall tomb museum market station garden park cave waterfall lake".split())
_THING_OPEN = re.compile(r"^The\s+(?P<head>" + "|".join(sorted(_THING_HEADS)) + r")(?P<poss>['\u2019]s)?\b(?P<rest>.*)$", re.S | re.I)
_NAME_TOK = r"(?:<[^>]{1,40}>|[A-ZÀ-Ỹ][\w'’\-]*)"


_SELF_ANCHOR = re.compile(
    r"^\s+(?:at|on|of|in|near|by|beside|above|atop|inside|outside)\s+(?:(?:the|a)\s+)?(?:[a-z][\w'’\-]*\s+){0,3}?"
    r"(?:<[^>]{1,40}>|[A-ZÀ-Ỹ][\w'’\-]*)")


def _named_things(evidence: str, head: str) -> List[str]:
    """Names in the evidence that end with the generic ``head`` ("Shwe Pagoda", "<Pagoda>"), one per distinct name."""
    H = head.capitalize()
    found: List[str] = []
    for m in re.finditer(r"(?:<[^>]{0,38}\b" + H + r"\b[^>]{0,38}>|<" + H + r">|(?:" + _NAME_TOK + r"\s+(?:(?:of|de|da)\s+)?){1,3}" + H + r"\b)",
                         evidence or ""):
        n = re.sub(r"^(?:The|A|An)\s+", "", m.group(0).strip())
        if n and rc.fold(n) not in {rc.fold(x) for x in found}:
            found.append(n)
    # one thing under two spellings: a name whose words are a subset of another's is the same
    keep: List[str] = []
    for n in sorted(found, key=lambda z: -len(z)):
        wn = set(rc._words(re.sub(r"[<>]", " ", n)))
        if not any(wn <= set(rc._words(re.sub(r"[<>]", " ", k))) for k in keep):
            keep.append(n)
    return keep


def repair_thing_referent(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                          log: Optional[Callable] = None) -> str:
    """A body sentence that opens "The <generic noun>'s ..." / "The <generic noun> ..." (pagoda / temple / statue / ...) when
    that noun (or a name ending in it) is in neither the stop title nor an earlier sentence of the stop has no antecedent.
    When the stop's own evidence names exactly one such thing it is named ("The <Pagoda>'s presence ..."); else the
    sentence is dropped."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        ev_map = _ev_map(evidence_by_title)
        n_stops = len(_stops_info(tour_text))
        for k in range(n_stops):
            infos = _stops_info(tour_text)
            if k >= len(infos):
                break
            info = infos[k]
            sents = list(info["sents"])
            if not sents:
                continue
            ev = rc._ev_for(ev_map, info["title"]) or ""
            title_f = " " + " ".join(rc.fold(re.sub(r"[<>]", " ", info["title"] or "")).split()) + " "
            new: List[str] = []
            changed = False
            for x in sents:
                m = _THING_OPEN.match(x)
                if not m:
                    new.append(x)
                    continue
                head = m.group("head").lower()
                if _SELF_ANCHOR.match(m.group("rest") or ""):          # [LOCAL-906K] "The statue at <Name> ..." names itself
                    new.append(x)
                    continue
                seen = title_f + " ".join(rc.fold(re.sub(r"[<>]", " ", y)) for y in new)
                if re.search(r"\b" + head + r"s?\b", seen):
                    new.append(x)
                    continue
                cands = _named_things(ev, head)
                if len(cands) == 1:
                    name = cands[0]
                    fixed = "The " + name + (m.group("poss") or "") + m.group("rest")
                    emit(f'  {_J} Stop {info["num"]}: "The {head}" had no antecedent; named from the evidence ({name}): "{x[:80]}"')
                    new.append(fixed)
                else:
                    emit(f'  {_J} Stop {info["num"]}: "The {head}" had no antecedent and the evidence names '
                         f'{"none" if not cands else "several"} -> sentence dropped: "{x[:80]}"')
                changed = True
            if changed and new:
                tour_text = _set_body(tour_text, info, new)
            elif changed and not new:
                tour_text = _set_body(tour_text, info, [])
        return tour_text
    except Exception as err:  # pragma: no cover
        emit(f"  {_J} thing-referent repair skipped (non-fatal): {err}")
        return tour_text


# ══ the pass ═════════════════════════════════════════════════════════════════════════════════════════════
def final_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
               log: Optional[Callable] = None) -> str:
    """Scope claims, the opener repair and the filler bodies, on ANY tour (the last thing before the 905 recount)."""
    t = tour_text
    try:   # [LOCAL-906H] no evidence passed -> the job's delivery-evidence store
        import delivery_evidence_906h as _de
        evidence_by_title = _de.resolve(evidence_by_title)
        _k906h, _n906h = _de.coverage(tour_text, evidence_by_title)
    except Exception:  # pragma: no cover
        _k906h, _n906h = 0, len(rc._stop_blocks(tour_text or ""))
    try:   # [LOCAL-906F] blocked claims, promo, cross-stop conflicts, leads, names, hyphens, person pronouns
        import leftovers_906f as _f
        t = _f.run_pass(t, evidence_by_title, log)
    except Exception as err:  # pragma: no cover
        _emit(log)(f"  [LOCAL-906F] pass skipped (non-fatal): {err}")
    t = drop_unsupported_scope_claims(t, evidence_by_title, log)
    t = repair_you_see_here(t, log)
    t = repair_thing_referent(t, evidence_by_title, log)      # [LOCAL-906J]
    t = distinct_filler_bodies(t, evidence_by_title, log)
    t = repair_pronoun_opener(t, log)         # [LOCAL-906E]
    try:   # [LOCAL-906F] what the removals above left must not open with a person pronoun or an orphan compound
        import leftovers_906f as _f
        t = _f.repair_person_pronoun(t, evidence_by_title, log)
        t = _f.fix_orphan_compounds(t, log)
    except Exception as err:  # pragma: no cover
        _emit(log)(f"  [LOCAL-906F] closing repair skipped (non-fatal): {err}")
    try:   # [LOCAL-906H] a quantifier whose number was cut; one summary line (never a silent no-op)
        import delivery_evidence_906h as _de
        t = _de.drop_dangling_quantifier(t, log)
    except Exception as err:  # pragma: no cover
        _emit(log)(f"  [LOCAL-906H] dangling-quantifier guard skipped (non-fatal): {err}")
    try:
        import difflib
        _a, _b = (tour_text or "").split("\n"), t.split("\n")
        _chg = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in
                   difflib.SequenceMatcher(None, _a, _b, autojunk=False).get_opcodes() if tag != "equal")
        if _k906h == 0:
            _emit(log)(f"  [LOCAL-906C] final pass: evidence for 0/{_n906h} stops, {_chg} change(s) -- NO evidence: "
                      f"scope/blocked/cross-stop checks skipped")
        else:
            _emit(log)(f"  [LOCAL-906C] final pass: evidence for {_k906h}/{_n906h} stops, {_chg} change(s)")
    except Exception:  # pragma: no cover
        pass
    return t
