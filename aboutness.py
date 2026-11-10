"""[LOCAL-891] "Supported" must also mean "about THIS stop".

A sentence the evidence states is not enough: the 890 Cathedral shipped five sentences on a 1963
self-immolation that happened at a street intersection elsewhere, because the bundle held that
passage (city- or square-level material) and the gate/audit only asked "is it in the evidence".

Rule (generic, no venue named; D769):

  * The stop's evidence is split into ITEMS (sentence runs of <= ~600 chars) and each item is
    flagged ``about_stop``:
      (a) every item of the stop's OWN article (890 ``own_article``) is about the stop;
      (b) any other item (another article, a snippet, a review, a place's own site text) is about
          the stop only when it NAMES the stop (name, alias, canonical/local name, article title, or
          the stop's kind noun "the cathedral") with enough weight to be its subject: at least two
          mentions, or a mention in its first sentence; or when it is geo-tagged within 150 m
          (``geo_m``) AND names the stop.
    Anything else is CONTEXT (the city, a neighbouring place, a person).
  * A FACTUAL sentence is SUPPORTED only if the item that carries it is about_stop. Supported only by
    CONTEXT => UNSUPPORTED (off-topic), unless the sentence itself ties the event to a DIFFERENT place
    ("a few blocks away, at ..."); at most ONE such sentence per stop.
  * The judge returns the item id that supports each sentence; ``assess`` verifies the id by token
    overlap and re-sources to an about_stop item when one carries the sentence as well as the context
    item does. The audit calls the same ``assess`` over the same items.

Also here (deterministic, no LLM): tangent guard (a sentence whose subject is neither the stop nor its
parts/people/events), near-repeat dedupe, raw lead/infobox sentence guard, empty filler guard, a
pronoun-only opener fix, and the narrator-input filter (context never reaches the narrator as the
stop's history).
"""
from __future__ import annotations

import os
import re
import unicodedata
from typing import Callable, Dict, List, Optional, Sequence, Tuple

ENABLED = os.environ.get("ABOUTNESS_ENABLED", "1").strip() != "0"
# 'drop'     : context never reaches the narrator
# 'labelled' : context is appended in a block labelled "city background - do not present as this
#              stop's history"
NARRATOR_CONTEXT_MODE = os.environ.get("NARRATOR_CONTEXT_MODE", "drop").strip().lower()
GEO_NEAR_M = 150.0
ITEM_MAX = 600
OTHER_PLACE_CAP = 1


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


_TOK = re.compile(r"[^\W_]{3,}", re.UNICODE)
_STOPW = frozenset((
    "the and for with from that this were was are has had have been also their which there about "
    "where while after before into most more than when what they them then will your here still "
    "its his her who whom whose how can may one two").split())
_GENERIC = frozenset(("the", "and", "of", "de", "la", "le", "du", "des", "in", "at", "on", "a", "an"))
# kind nouns: a stop called just "Cathedral"/"Pier" is named by "the cathedral"
KIND = frozenset(("river city street palace hall cathedral church temple museum square market bridge "
                  "gate tower park garden pier station boulevard avenue road bank house office "
                  "university school hotel theatre theater opera basilica pagoda mosque castle "
                  "fortress library gallery quay wharf cafe bar restaurant shop store").split())
# a stop's kind noun may be written with its synonyms
_GENERIC_KIND = frozenset(("city river bank road street avenue boulevard house office bar shop store "
                          "square park garden market station school hotel cafe restaurant").split())
_KIND_SYN = {"theatre": ("theatre", "theater", "opera"), "theater": ("theatre", "theater", "opera"),
             "opera": ("opera", "theatre", "theater"), "pier": ("pier", "wharf", "quay", "port"),
             "cathedral": ("cathedral", "basilica"), "basilica": ("cathedral", "basilica"),
             "office": ("office", "post"), "hall": ("hall",), "palace": ("palace",)}


def _stem(w: str) -> str:
    return w[:-1] if w.endswith("s") and len(w) > 4 else w


def toks(text: str) -> List[str]:
    return [_stem(t) for t in _TOK.findall(_fold(text)) if t not in _STOPW]


def split_sentences(text: str) -> List[str]:
    t = re.sub(r"\s+", " ", text or "").strip()
    if not t:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[\"'“‘(\[]?[A-ZÀ-ỸĐ0-9])", t)
    out, buf = [], ""
    for p in parts:               # glue a split after an initial ("F. Kennedy") or an abbreviation
        if buf and re.search(r"(?:\b[A-Z]|\bSt|\bMr|\bMrs|\bDr|\bNo|\bvs|\bca)\.$", buf):
            buf += " " + p
            continue
        if buf:
            out.append(buf)
        buf = p
    if buf:
        out.append(buf)
    return [x.strip() for x in out if x.strip()]


# ═════════════════════ the stop's referent ═════════════════════
class Referent:
    """How the evidence can name the stop: distinctive name tokens, aliases, kind nouns."""

    def __init__(self, title: str, aliases: Sequence[str] = (), art_title: str = "",
                 art_lead: str = ""):
        names = [title] + list(aliases or [])
        self.phrases = []                    # folded multi-word names
        self.name_toks = set()               # distinctive (non-kind, non-generic) tokens
        self.kinds = set()
        for n in names:
            f = _fold(n)
            ws = [w for w in re.findall(r"[^\W_]+", f) if len(w) >= 3 and w not in _GENERIC]
            if not ws:
                continue
            if len(ws) >= 2:
                self.phrases.append(" ".join(ws))
            for w in ws:
                if w in KIND:
                    self.kinds.add(w)
                else:
                    self.name_toks.add(_stem(w))
        if art_title:                        # the own article's title names the stop as a PHRASE only
            ws = [w for w in re.findall(r"[^\W_]+", _fold(art_title)) if len(w) >= 3 and w not in _GENERIC]
            if len(ws) >= 2:
                self.phrases.append(" ".join(ws))
        # the title's own kind nouns are always the stop's kind; a kind that came from an alias or the
        # article title is accepted too (the 'Notre-Dame Cathedral Basilica' alias of 'Cathedral')
        for k in list(self.kinds):
            self.kinds.update(_KIND_SYN.get(k, ()))
        # aliases from the article lead: "(Vietnamese: ...)" and "also known as / called X"
        for a in lead_aliases(art_lead):
            f = _fold(a)
            ws = [w for w in re.findall(r"[^\W_]+", f) if len(w) >= 3 and w not in _GENERIC]
            if len(ws) >= 2:
                self.phrases.append(" ".join(ws))
        # kind nouns name the stop only when the title has no distinctive token of its own ("Cathedral",
        # "Pier", "Opera House"); never a word every passage has ("city", "street", "house" ...)
        self.count_kinds = (set() if self.name_toks else
                            {k for k in self.kinds if k not in _GENERIC_KIND})
        # a single-token name that is only a generic place word, e.g. "city": no distinctive token
        self.name_toks -= {"city", "saigon"} if len(self.name_toks) > 1 else set()

    def mentions(self, text: str) -> int:
        """Count of times ``text`` names the stop."""
        f = _fold(text)
        n = 0
        for ph in self.phrases:
            n += len(re.findall(r"\b" + re.escape(ph) + r"\b", f))
        # "The bar / The cafe / This street ..." opening a sentence is the stop for a snippet or review
        if self.kinds:
            for sent in split_sentences(text):
                m = re.match(r"(?:the|this)\s+([^\W_]+)", _fold(sent))
                if m and any(m.group(1).startswith(k) and len(m.group(1)) <= len(k) + 3 for k in self.kinds):
                    n += 1
        words = re.findall(r"[^\W_]+", f)
        kc = self.count_kinds
        for w in words:
            if _stem(w) in self.name_toks:
                n += 1
            elif kc and any(w.startswith(k) and len(w) <= len(k) + 3 for k in kc):
                n += 1                     # "the cathedral", "Cathédrale", "the theatre"
        return n


def lead_aliases(lead: str) -> List[str]:
    out = []
    first = (split_sentences(lead or "") or [""])[0]
    for m in re.finditer(r"\(([^()]{3,160})\)", first):
        for part in re.split(r"[;,]", m.group(1)):
            part = re.sub(r"^\s*(?:[A-Z][a-z]+|[a-z]+):\s*", "", part).strip()
            if 3 <= len(part) <= 60:
                out.append(part)
    for m in re.finditer(r"(?i)\b(?:also\s+(?:known|called)\s+as|formerly|locally\s+known\s+as)\s+"
                         r"([A-ZÀ-Ỹ][^.,;()]{2,60})", first):
        out.append(m.group(1).strip())
    return out


# ═════════════════════ evidence items ═════════════════════
def _split_item_text(text: str) -> List[str]:
    """Paragraph-sized pieces <= ITEM_MAX, split on sentence boundaries."""
    out = []
    for para in re.split(r"\n+", text or ""):
        para = re.sub(r"^\s*\[[^\]]{1,60}\]\s*", "", para).strip()
        if not para:
            continue
        if len(para) <= ITEM_MAX:
            out.append(para)
            continue
        cur = ""
        for s in split_sentences(para):
            if cur and len(cur) + len(s) + 1 > ITEM_MAX:
                out.append(cur)
                cur = s
            else:
                cur = (cur + " " + s).strip()
        if cur:
            out.append(cur)
    return out


def _paragraphs(text: str) -> List[str]:
    return [re.sub(r"^\s*\[[^\]]{1,60}\]\s*", "", p).strip() for p in re.split(r"\n+", text or "") if p.strip()]


def para_about(para: str, ref: Referent, geo_m: Optional[float] = None) -> Tuple[bool, str]:
    """Is a non-own paragraph ABOUT the stop? It must name the stop with the weight of a subject:
    >= 2 mentions, or a mention in its first sentence (single-sentence items need 1). A geo-tag
    within 150 m lets a paragraph that names the stop stand on 1 mention anywhere."""
    sents = split_sentences(para)
    if not sents:
        return False, "empty"
    total = ref.mentions(para)
    if total == 0:
        return False, "never names the stop"
    if ref.mentions(sents[0]) >= 1:
        return True, f"names the stop in its first sentence ({total}x)"
    if total >= 2:
        return True, f"names the stop {total}x"
    if len(sents) == 1:
        return True, "single sentence naming the stop"
    if geo_m is not None and geo_m <= GEO_NEAR_M:
        return True, f"geo-tagged {geo_m:.0f} m and names the stop"
    return False, "names the stop only in passing"


def build_items(evidence: str, title: str, aliases: Sequence[str] = (),
                geo: Optional[Dict[str, float]] = None) -> List[Dict]:
    """The stop's evidence as flagged items: {id, text, about_stop, kind, source, why}.

    ``geo`` maps an article title (folded) or a snippet prefix to its distance in metres from the
    stop's pin, when the caller knows it."""
    import key_fact_coverage as kfc
    ev = evidence or ""
    own = None
    try:
        own = kfc.own_article(ev, title)
    except Exception:
        own = None
    arts = []
    try:
        arts = kfc.articles(ev)
    except Exception:
        arts = []
    ref = Referent(title, aliases, (own or {}).get("title", ""), (own or {}).get("lead", ""))
    items: List[Dict] = []

    def add(text, about, kind, source, why):
        for piece in _split_item_text(text):
            items.append({"id": f"E{len(items) + 1}", "text": piece, "about_stop": bool(about),
                          "kind": kind, "source": source, "why": why})

    consumed = []
    for a in arts:
        is_own = own is not None and a.get("title") == own.get("title") and a.get("lang") == own.get("lang")
        if not is_own and own is not None and _same_entity(own, a):
            is_own = True                    # the stop's LOCAL-language edition (its local name)
        src = a.get("title", "")
        g = (geo or {}).get(_fold(src))
        body_parts = [("lead", a.get("lead", "")), ("passages", a.get("passages", ""))]
        for part, txt in body_parts:
            if not (txt or "").strip():
                continue
            if is_own:
                add(txt, True, "own_article", src, "the stop's own article")
                continue
            for para in _paragraphs(txt):
                ok, why = para_about(para, ref, g)
                add(para, ok, "passage" if ok else "context", src, why)
        if a.get("infobox"):
            if is_own:
                add(a["infobox"], True, "own_article", src, "own-article infobox")
            else:
                ok, why = para_about(a["infobox"], ref, g)
                add(a["infobox"], ok, "passage" if ok else "context", src, "infobox: " + why)
        consumed.append(src)
    # everything that is not a Wikipedia article: snippets, page facts, reviews, a place's own site
    rest = ev
    try:
        heads = list(kfc._HEAD_RE.finditer(ev))
        if heads:
            rest = ev[:heads[0].start()]
            # text after the last article body is not separable here; articles() already took it
    except Exception:
        pass
    for chunk in _non_article_chunks(rest):
        g = None
        if geo:
            for k, v in geo.items():
                if k and k in _fold(chunk[:80]):
                    g = v
        ok, why = para_about(chunk, ref, g)
        if not ok and why == "never names the stop" and not _names_other_subject(chunk):
            # a bare fact ("The Hotel de Ville was constructed between ...") whose subject is a generic
            # noun phrase: it may be the stop under another name, so it is not called context
            ok, why = True, "never names the stop but its subject is a generic noun phrase (undecided)"
        add(chunk, ok, "snippet" if ok else "context", "snippet", why)
    # UNDECIDABLE: no article at all and no item names the stop (a bare list of page facts gathered FOR
    # this stop). Nothing can be told apart, so nothing is called context; the judge's verdict stands.
    if items and not arts and not any(i["about_stop"] for i in items):
        for it in items:
            it["about_stop"] = True
            it["kind"] = "snippet"
            it["why"] = "no item names the stop: undecidable, treated as the stop's own facts"
    return items


def _names_other_subject(chunk: str) -> bool:
    """The chunk's first sentence opens on a capitalised proper NAME ('Ho Chi Minh was ...', 'Thich
    Quang Duc ...'), i.e. its subject is a person or place other than the stop."""
    first = (split_sentences(chunk) or [""])[0].strip()
    m = re.match(r"^((?:[A-ZÀ-ỸĐ][\wÀ-ÿ'’-]*\s+){1,}[A-ZÀ-ỸĐ]?[\wÀ-ÿ'’-]*)", first)
    if not m:
        return False
    w0 = _fold(first.split()[0])
    if w0 in _STARTERS_WORDS:
        return False
    return bool(re.match(r"^[A-ZÀ-ỸĐ]", first)) and len(first.split()) >= 2 and \
        bool(re.match(r"^[A-ZÀ-ỸĐ][\wÀ-ÿ'’-]*\s+[A-ZÀ-ỸĐ]", first))


_YEAR = re.compile(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})(?!\d)")


def _article_years(a: Dict) -> set:
    return set(_YEAR.findall(" ".join(str(a.get(k, "")) for k in ("lead", "passages", "infobox"))))


def _same_entity(own: Dict, other: Dict) -> bool:
    """``other`` is the stop's own article in another language (its local edition): a different
    language edition that shares at least two years with the own article. A neighbouring place's
    article in any language shares at most a year by chance."""
    if other.get("lang") == own.get("lang"):
        return False
    a, b = _article_years(own), _article_years(other)
    return len(a & b) >= 2 and len(a & b) >= 0.4 * min(len(a), len(b))


def _non_article_chunks(text: str) -> List[str]:
    out = []
    for ln in re.split(r"\n+", text or ""):
        ln = ln.strip()
        if not ln:
            continue
        out.extend(_split_item_text(ln))
    return out


# ═════════════════════ judge request ═════════════════════
_STARTERS_WORDS = frozenset(("the this that these those a an in on at as it its you your here there today from "
                            "inside outside after before during when while with without for by to of and but or "
                            "so then now once if one some many most each every both all few several").split())


def _item_score(text: str, tset: set) -> float:
    it = set(toks(text))
    hit = tset & it
    return len(hit) + 3.0 * len({t for t in hit if t.isdigit()})


def render_items(items: List[Dict], sentences: Sequence[str], cap: int = 6000,
                 exclude_ids: Optional[set] = None) -> Tuple[str, List[str]]:
    """The evidence block of the gate request: every item with its id and ``about_stop`` flag.
    When everything fits it is sent whole; otherwise the leading about-stop items and the items
    sharing the most year/name tokens with the sentences are kept (source order)."""
    exclude_ids = exclude_ids or set()
    pool = [it for it in items if it["id"] not in exclude_ids]

    def line(it):
        return (f"[{it['id']} | about_stop={'true' if it['about_stop'] else 'false'} | {it['kind']}"
                f"{' | ' + it['source'][:40] if it.get('source') and it['kind'] != 'snippet' else ''}] "
                f"{it['text']}")
    if sum(len(line(i)) + 1 for i in pool) <= cap:
        chosen = pool
    else:
        tset = set()
        for s in sentences:
            tset.update(toks(s))
        head, used = [], 0
        for it in pool:
            if it["about_stop"] and used + len(line(it)) + 1 <= cap // 4:
                head.append(it)
                used += len(line(it)) + 1
        ids = {i["id"] for i in head}
        ranked = sorted((i for i in pool if i["id"] not in ids),
                        key=lambda i: (-_item_score(i["text"], tset), i["id"]))
        for it in ranked:
            if _item_score(it["text"], tset) <= 0:
                break
            if used + len(line(it)) + 1 > cap:
                continue
            head.append(it)
            used += len(line(it)) + 1
        chosen = sorted(head, key=lambda i: int(i["id"][1:]))
    return "\n".join(line(i) for i in chosen), [i["id"] for i in chosen]


JUDGE_ADDENDUM = (
    "\nEach evidence item is tagged with an id and about_stop=true/false. about_stop=true means the "
    "item is the stop's own article or a passage whose subject is the stop; about_stop=false is CONTEXT "
    "(the city, a neighbouring place, a person). For EVERY verdict return \"source\": the id (e.g. "
    "\"E3\") of the single item that best supports the sentence, or \"\" when none does. Do not prefer "
    "a context item over an about_stop item that states the same fact."
)


# ═════════════════════ the aboutness verdict ═════════════════════
_OTHER_PLACE = re.compile(
    r"(?i)\b(?:a\s+few\s+(?:blocks?|streets?|minutes?|hundred\s+(?:metres|meters|yards))\s+(?:away|from)|"
    r"(?:blocks?|streets?)\s+away|not\s+far\s+from\s+here|elsewhere\s+in\s+the\s+(?:city|town)|"
    r"(?:nearby|close\s+by),?\s+(?:at|on|in)\s+(?:the\s+)?[A-Z]|"
    r"(?:a\s+short\s+walk|minutes?)\s+(?:away|from\s+here)|"
    r"(?:at|on)\s+the\s+(?:intersection|junction|corner)\s+of\s+[A-Z])")


def _coverage(sent_toks: set, item_text: str) -> float:
    if not sent_toks:
        return 0.0
    it = set(toks(item_text))
    return len(sent_toks & it) / len(sent_toks)


def _distinct_toks(sentence: str, ref: Optional[Referent] = None) -> set:
    t = set(toks(sentence))
    if ref is not None:
        t -= ref.name_toks
        t -= {_stem(k) for k in ref.kinds}
    # words every sentence has (verbs of being, generic place words) do not identify a source
    return {w for w in t if len(w) >= 4 or w.isdigit()} - {"stop", "tour", "today", "visitors", "years"}


def assess(sentence: str, items: List[Dict], *, judge_source: Optional[str] = None,
           ref: Optional[Referent] = None, other_place_used: int = 0) -> Dict:
    """Aboutness verdict for ONE factual sentence the judge called SUPPORTED (or did not judge).

    Returns {ok, why, source, rescued_by, other_place}. ``ok`` False means UNSUPPORTED (off-topic).
    Undecidable (no item shares enough tokens with the sentence) => ok True, source None: the
    judge's own verdict stands."""
    res = {"ok": True, "why": "", "source": None, "other_place": False}
    if not items:
        return res
    st = _distinct_toks(sentence, ref)
    if len(st) < 2:
        return res
    cov = {it["id"]: _coverage(st, it["text"]) for it in items}
    by_id = {it["id"]: it for it in items}
    best_about = max((it for it in items if it["about_stop"]), key=lambda i: cov[i["id"]], default=None)
    best_ctx = max((it for it in items if not it["about_stop"]), key=lambda i: cov[i["id"]], default=None)
    ba = cov[best_about["id"]] if best_about else 0.0
    bc = cov[best_ctx["id"]] if best_ctx else 0.0
    j = by_id.get((judge_source or "").strip())
    if j is not None and cov[j["id"]] < 0.25:
        j = None                           # the judge named an item that does not carry the sentence
    if j is not None and j["about_stop"]:
        res.update(source=j["id"], why="judge source is about the stop")
        return res
    if ba >= 0.5 and ba >= 0.75 * max(bc, (cov[j["id"]] if j else 0.0)):
        res.update(source=best_about["id"], why="an about-stop item carries it")
        return res
    # the sentence is carried only by context
    ctx_id = (j or best_ctx or {}).get("id") if (j or best_ctx) else None
    cbest = cov.get(ctx_id, 0.0) if ctx_id else 0.0
    if cbest < 0.4 or cbest <= ba:
        # no context item carries it better than the stop's own items: not decidable as off-topic,
        # the judge's verdict stands
        if best_about is not None and ba >= 0.3:
            res.update(source=best_about["id"], why="an about-stop item partly carries it")
        return res
    if _OTHER_PLACE.search(sentence) and other_place_used < OTHER_PLACE_CAP:
        res.update(source=ctx_id, other_place=True,
                   why="context-supported; the sentence ties the event to a different place")
        return res
    src = by_id.get(ctx_id) or {}
    res.update(ok=False, source=ctx_id,
               why=f"off-topic: supported only by context ({src.get('source', '')[:40] or 'snippet'}: "
                   f"{src.get('why', '')})")
    return res


# ═════════════════════ tangent / repeat / filler guards ═════════════════════
_PARTS = frozenset((
    "facade façade tower towers dome hall room rooms wall walls map maps statue statues window windows "
    "door doors roof bell bells gallery galleries floor floors courtyard garden gardens exhibit exhibits "
    "collection collections aircraft jar jars display displays foyer stage balcony spire entrance gate "
    "gates column columns arch arches ceiling interior exterior architecture design decoration decorations "
    "furnishings inscriptions reliefs chamber chambers lobby staircase stairs clock clocks mosaic mosaics "
    "tiles paintings painting sculpture sculptures altar nave bricks brick construction renovation "
    "restoration building structure site museum palace cathedral church theatre theater pier port "
    "ferry terminal tank tanks guillotine photographers photojournalists tribute memorial plaza "
    "shop shops stalls stall cafés cafes restaurants floors complex apartments apartment").split())
_VERB = re.compile(
    r"(?i)\b(?:is|was|are|were|has|had|have|became|become|stands?|stood|houses?|housed|built|designed|"
    r"completed|opened|features?|contains?|served|serves|remains?|dates?|sits?|rises?|measures?|"
    r"hosts?|hosted|holds?|held|displays?|shows?|tells?|marks?|marked|commemorates?|honou?rs?|"
    r"honou?red|stored|preserves?|preserved|credited|known|called|named|introduced|issued|created|"
    r"started|began|ended|replaced|replaces|crashed|seized|promised|inspired)\b")
_LEAD_PHRASE = re.compile(r"(?i)^(?:(?:in|on|by|from|during|after|before|since|until|between|following|"
                          r"under|at|over|throughout)\b[^,]{0,70},\s*)+")
_PRONOUNS = frozenset(("it", "its", "this", "that", "their", "these", "those", "he", "she", "they"))
_ART_WORDS = frozenset(("the", "a", "an", "this", "these", "that", "those", "it", "its", "their", "his",
                        "her", "he", "she", "they", "we", "you", "one", "some", "many", "each", "both"))


def subject_of(sentence: str) -> str:
    s = _LEAD_PHRASE.sub("", sentence.strip())
    s = re.sub(r"^(?:known|called|named)\s+[^,]{0,60},\s*", "", s, flags=re.I)
    for m in _VERB.finditer(s):
        allw = s[:m.start()].split()
        pre = [w for w in allw if w.lower().strip(",") not in _ART_WORDS]
        if not pre and allw and allw[0].lower() in _PRONOUNS:
            return " ".join(allw)          # "It is ...", "Its ..." : the subject is the pronoun
        if pre:                            # "The displays gathered ..." : 'displays' is a noun here
            return s[:m.start()].strip(" ,")
    return " ".join(s.split()[:10])


def tangent_reason(sentence: str, ref: Referent, own_sentences: Sequence[str] = ()) -> Optional[str]:
    """The sentence's main entity is neither the stop nor its parts, people or events.

    The subject (text before the main verb, after any leading time/place phrase) must (1) name the stop,
    (2) be a pronoun / 'the building' reference, (3) be a PART of a stop (facade, maps, statue ...), or
    (4) be a person/event that the stop's own text ties to the stop (its capitalised words occur in an
    own-article sentence that also names the stop). Otherwise it is a tangent (the 1864 stamp)."""
    subj = subject_of(sentence)
    if not subj.split():
        return None
    if ref.mentions(subj):
        return None
    fwords = re.findall(r"[^\W_]+", _fold(subj))
    part_stems = {_stem(p) for p in _PARTS}
    if fwords and (fwords[0] in _PRONOUNS or (len(fwords) <= 3 and _PRONOUNS & set(fwords))):
        rest = [w for w in fwords if w not in _PRONOUNS]
        if not rest or rest[0] in ref.kinds or any(_stem(w) in part_stems for w in rest):
            return None                    # "It", "Its tower", "This building"
    elif any(_stem(w) in part_stems for w in fwords):
        return None                        # a PART of the stop: facade, maps, statue, exhibits
    # a person / place / event: its capitalised words must occur in an own-article sentence that also
    # names the stop, or the sentence itself must name the stop
    words = subj.split()
    caps = [w for k, w in enumerate(words) if k > 0 and re.match(r"[A-ZÀ-ỸĐ]", w) and _fold(w) not in _ART_WORDS]
    if caps:
        folded = [_fold(re.sub(r"\W+$", "", c)) for c in caps]
        for o in own_sentences:
            fo = _fold(o)
            if any(re.search(r"\b" + re.escape(c) + r"\b", fo) for c in folded if c):
                return None
        if not own_sentences:
            return None                    # no own article to test a named person/place against
    if ref.mentions(sentence):
        return None
    return f"subject '{subj[:50]}' is neither the stop nor one of its parts, people or events"


_REL = {
    "host": re.compile(r"(?i)\b(?:venue|home\s+to|hosted?|hosting|holding|held|housed?|seat\s+of|meeting|"
                       r"assembly|met\s+(?:here|at))\b"),
    "build": re.compile(r"(?i)\b(?:built|constructed?|construction|completed|designed|opened|erected|"
                        r"founded|established|inaugurated)\b"),
    "rename": re.compile(r"(?i)\b(?:renamed|named|known\s+as|called)\b"),
    "damage": re.compile(r"(?i)\b(?:bombed|bombing|damaged|destroyed|burn\w*|demolished|attacked|shelled)\b"),
}
_ENTITY = re.compile(r"\b(?:[A-ZÀ-ỸĐ][\wÀ-ÿ'’-]+)(?:\s+(?:of|de|the|and)?\s*[A-ZÀ-ỸĐ][\wÀ-ÿ'’-]+)+")


def _entities(sentence: str, ref: Referent) -> set:
    body = re.sub(r"^\W*[A-ZÀ-ỸĐ][\wÀ-ÿ'’-]*\s+", "", sentence)       # drop the sentence-initial capital
    ents = set()
    for m in _ENTITY.finditer(body):
        e = _fold(m.group(0))
        if not ref.mentions(m.group(0)):
            ents.add(e)
    for m in re.finditer(r"\b(?:the\s+)?([A-Z][\w'’-]+(?:'s|’s)?\s+[A-Z][\w'’-]+)\b", body):
        pass
    return ents


def _concreteness(s: str) -> int:
    return 3 * len(re.findall(r"\b(?:1[0-9]{3}|20[0-9]{2})\b", s)) + len(_ENTITY.findall(s))


def near_repeats(sentences: Sequence[str], ref: Referent) -> List[Tuple[int, int, str]]:
    """Pairs (drop_index, keep_index, why) of near-repeat facts inside one stop: two sentences that
    state the same relation (hosting, building, renaming, damage) about the same named entity, or whose
    content tokens overlap by >= 70%. The more concrete one (dated, named) stays; ties keep the first."""
    out = []
    ents = [_entities(s, ref) for s in sentences]
    ct = [set(toks(s)) for s in sentences]
    dropped = set()
    for j in range(len(sentences)):
        for i in range(j):
            if i in dropped or j in dropped:
                continue
            shared = ents[i] & ents[j]
            same_rel = [r for r, rx in _REL.items() if rx.search(sentences[i]) and rx.search(sentences[j])]
            jac = len(ct[i] & ct[j]) / max(1, min(len(ct[i]), len(ct[j])))
            why = None
            if shared and same_rel:
                why = f"states the same {same_rel[0]} fact about {sorted(shared)[0]!r} twice"
            elif jac >= 0.7:
                why = f"{int(jac * 100)}% of its content repeats another sentence"
            if not why:
                continue
            drop, keep = (i, j) if _concreteness(sentences[j]) > _concreteness(sentences[i]) else (j, i)
            dropped.add(drop)
            out.append((drop, keep, why))
    return out


_FILLER = re.compile(
    r"(?i)(?:\bmaking\s+it\s+(?:easy|simple|convenient)\s+to\s+(?:find|spot|reach|get\s+to)\b|"
    r"\beasy\s+to\s+(?:find|spot|reach)\b|"
    r"^as\s+you\s+look\s+(?:up|around|closely)\b[^.]*\byou\s+(?:can|will|may)\s+see\b|"
    r"\byou\s+can\s+see\s+the\s+(?:multiple|many|several|various)\s+(?:floors|levels|storeys|stories)\b|"
    r"\bthis\s+unique\s+multi-?(?:story|storey|level)\b|"
    r"^(?:take|enjoy)\s+a\s+moment\b|^have\s+a\s+look\s+around\b)")


def is_filler(sentence: str) -> bool:
    s = sentence.strip()
    return bool(_FILLER.search(s)) and not re.search(r"\b(?:1[0-9]{3}|20[0-9]{2})\b", s)


_ADDRESS = re.compile(r"(?i)\b(?:at\s+)?\d{1,4}[A-Za-z]?\s+[\wÀ-ÿ'’ .-]{2,30}?\b(?:street|road|avenue|boulevard|"
                      r"đường|phố|lane|square|st\.?)\b|\bin\s+[A-ZÀ-Ỹ][\wÀ-ÿ]+\s+(?:ward|district|province)\b|"
                      r"\b(?:ward|district)\s+\d+\b")
_LEAD_FORM = re.compile(r"(?i)^(?:the\s+)?[^,.;]{2,70}?\s+(?:is|was)\s+(?:an?|the)\s+[^,.;]{0,50}?"
                        r"(?:museum|palace|building|church|cathedral|bar|cafe|café|pier|park|street|market|"
                        r"theatre|theater|hall|office|hotel|complex|site|monument|temple|pagoda|shop)\b")


def is_raw_lead(sentence: str, ref: Referent) -> bool:
    """A lead/infobox-style definition with an address and no story: 'The X is a war museum at 28 Y
    Street, Z Ward, City, Country.'"""
    s = sentence.strip()
    if not _LEAD_FORM.search(s):
        return False
    return bool(_ADDRESS.search(s)) or bool(re.search(r"(?i),\s*(?:vietnam|france|italy|spain|usa|"
                                                       r"united\s+states|england|germany|japan|china)\.?$", s))


_PRON_OPEN = re.compile(r"^(?:It|This|They)\s+(?:is|was|are|were|has|had)\b")


def fix_leading_pronoun(first: str, title: str) -> str:
    """The body's first sentence opens on 'It is often mistakenly credited ...' with no antecedent:
    name the stop."""
    if not _PRON_OPEN.match(first.strip()):
        return first
    t = title.strip()
    last = _fold(t).split()[-1] if t.split() else ""
    name = ("The " + t) if last in KIND and not re.match(r"(?i)the\s", t) else t
    return _PRON_OPEN.sub(lambda m: name + " " + m.group(0).split(None, 1)[1], first.strip(), count=1)


# ═════════════════════ one stop ═════════════════════
def clean_stop(title: str, sentences: List[str], evidence: str, *, items: Optional[List[Dict]] = None,
               log: Optional[Callable] = None, where: str = "final", min_keep: int = 2
               ) -> Tuple[List[str], Dict]:
    """Deterministic aboutness hygiene of one stop's body: filler, tangent, near-repeat, raw lead at the
    end, pronoun-only first sentence. Never shrinks the stop below ``min_keep``."""
    rep = {"filler": [], "tangent": [], "repeat": [], "raw_lead": [], "pronoun_fixed": 0}
    if not ENABLED:
        return list(sentences), rep
    import key_fact_coverage as kfc
    own = None
    try:
        own = kfc.own_article(evidence, title)
    except Exception:
        pass
    ref = Referent(title, (), (own or {}).get("title", ""), (own or {}).get("lead", ""))
    own_sents = []
    try:
        own_sents = kfc.own_prose_sentences(evidence, title)
    except Exception:
        pass
    cur = list(sentences)

    def drop(i, bucket, why):
        if len(cur) <= min_keep:
            return False
        rep[bucket].append((cur[i][:100], why))
        if log:
            log(f"  [LOCAL-891] {where} dropped ({bucket}) in '{title[:40]}': {why}: \"{cur[i][:100]}\"")
        try:
            kfc.deny_record(title, cur[i], "gate:deterministic")
        except Exception:
            pass
        cur.pop(i)
        return True

    for i in range(len(cur) - 1, -1, -1):
        if is_filler(cur[i]):
            drop(i, "filler", "empty filler")
    for i in range(len(cur) - 1, -1, -1):
        if i >= len(cur):
            continue
        s = cur[i]
        try:
            import strict_grounding_gate as _sgg
            fact = _sgg.is_factual_sentence(s) or _past_event(s)
        except Exception:
            fact = True
        if fact and own_sents and not _is_navigation(s) and not kfc.is_sensory(s):
            why = tangent_reason(s, ref, own_sents)
            if why:
                drop(i, "tangent", why)
    for d, k, why in sorted(near_repeats(cur, ref), key=lambda x: -x[0]):
        if d < len(cur):
            drop(d, "repeat", why + f" (kept: \"{cur[min(k, len(cur) - 1)][:60]}\")")
    while cur and is_raw_lead(cur[-1], ref) and len(cur) > min_keep:
        drop(len(cur) - 1, "raw_lead", "ends on a raw lead/infobox-style sentence")
    if cur:
        f2 = fix_leading_pronoun(cur[0], title)
        if f2 != cur[0]:
            rep["pronoun_fixed"] += 1
            cur[0] = f2
    return cur, rep


_STARTERS = frozenset(("the this that these those a an in on at as it its you your here there today from inside "
                       "outside standing look after before during when while with without for by to of and but "
                       "or so then now once if one some many most each every both all few several").split())
_PAST = re.compile(r"(?i)\b(?:was|were|had|became|\w{3,}ed|made|built|took|led|began|saw|held|sent|"
                   r"kept|gave|won|lost|fell|rose|grew|ran|came|went|brought|taught|wrote|chose)\b")
_YEARNUM = re.compile(r"\b(?:1[0-9]{3}|20[0-9]{2})\b")


def is_claim(s: str) -> bool:
    """A sentence that states a checkable event/person claim the 888 factual cue misses: it opens on a
    capitalised NAME ('Thích Quảng Đức's heart was seized ...') or tells a past event."""
    t = (s or "").strip()
    if len(t) < 25 or re.search(r"(?i)\b(?:you|your)\b", t):
        return False
    m = re.match(r"^((?:[A-ZÀ-ỸĐ][\wÀ-ÿ'’-]*\s+){2,})", t)
    if m and _fold(m.group(1).split()[0]) not in _STARTERS:
        return True
    return bool(_PAST.search(t)) and not _is_navigation(t)


def _past_event(s: str) -> bool:
    return bool(_YEARNUM.search(s) or _PAST.search(s))


def _is_navigation(s: str) -> bool:
    return bool(re.match(r"(?i)^(?:head|turn|walk|continue|proceed|make your way|from here|directions)\b", s.strip()))


# ═════════════════════ refill facts (WRM) ═════════════════════
def refill_facts(evidence: str, title: str, limit: int = 24) -> List[str]:
    """Plain, about-the-stop sentences of the stop's OWN article (lead + 885 select_passages),
    richest first by story content (dates, names, defining events), never a raw lead sentence."""
    import key_fact_coverage as kfc
    art = kfc.own_article(evidence, title)
    if art is None:
        return []
    ref = Referent(title, (), art.get("title", ""), art.get("lead", ""))
    out, seen = [], set()
    for k, s in enumerate(kfc.own_prose_sentences(evidence, title)):
        s = s.strip()
        if (not s.endswith((".", "!", "?")) or len(s) > 320 or is_raw_lead(s, ref) or is_filler(s)
                or kfc.garbled(s) or kfc.is_preview(s) or kfc.is_sensory(s)):
            continue
        key = _fold(s)[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append((-(_concreteness(s) + 2 * len(kfc._FAMOUS.findall(s))), k, s))
    out.sort()
    return [s for _c, _k, s in out[:limit]]


# ═════════════════════ narrator input ═════════════════════
def narrator_items(title: str, wiki_items: Sequence[str], aliases: Sequence[str] = (),
                   mode: Optional[str] = None) -> Tuple[List[str], str]:
    """Filter the Wikipedia evidence the NARRATOR sees. The stop's own article passes whole. Another
    article keeps only its about_stop paragraphs. Context is dropped (``drop``) or returned as a
    separate block labelled "city background - do not present as this stop's history" (``labelled``).
    Returns (items_for_narrator, context_block)."""
    mode = (mode or NARRATOR_CONTEXT_MODE)
    items = [str(x) for x in (wiki_items or []) if str(x).strip()]
    if not ENABLED or not items:
        return items, ""
    import key_fact_coverage as kfc
    try:
        own = kfc.own_article("\n".join(items), title)
    except Exception:
        own = None
    ref = Referent(title, aliases, (own or {}).get("title", ""), (own or {}).get("lead", ""))
    keep, ctx = [], []
    for it in items:
        arts = kfc.articles(it)
        if not arts:
            keep.append(it)
            continue
        a = arts[0]
        if own is not None and (a is own or (a.get("title") == own.get("title")
                                             and a.get("lang") == own.get("lang"))
                                or _same_entity(own, a)):
            keep.append(it)
            continue
        good, bad = [], []
        for part in (a.get("lead", ""), a.get("passages", "")):
            for para in _paragraphs(part):
                (good if para_about(para, ref)[0] else bad).append(para)
        if good:
            keep.append(f"{a.get('title', '')} - Wikipedia ({a.get('lang', 'en')}). " + "\n".join(good))
        if bad:
            ctx.append(f"{a.get('title', '')}: " + " ".join(bad))
    if own is None and not any(kfc.articles(k) for k in keep):
        return items, ""          # no own article and nothing about the stop: cannot tell, leave as it was
    block = ""
    if ctx and mode == "labelled":
        block = ("\n\nCITY BACKGROUND - do not present as this stop's history (it is about the city or a "
                 "neighbouring place, not about " + title + "):\n" + "\n".join(c[:900] for c in ctx[:2]))
    return keep, block


# ═════════════════════ audit ═════════════════════
def audit_tour(tour_text: str, evidence_by_title: Dict[str, str], *,
               judge_sources: Optional[Dict[Tuple[str, str], str]] = None) -> Dict:
    """The audit's aboutness half: the same ``assess`` over the same items for every factual sentence
    of every stop. Returns {"offtopic": [{stop, claim, why, source}], "items": {stop: [...]}}."""
    import strict_grounding_gate as sgg
    out = {"offtopic": [], "items": {}}
    norm = {sgg._fold(k): v for k, v in (evidence_by_title or {}).items()}
    for num, title, _b in sgg._split_blocks(tour_text or ""):
        blk = sgg._block_for(tour_text, num)
        if blk is None:
            continue
        ev = sgg._lookup(norm, title) or ""
        items = build_items(ev, title)
        out["items"][title] = [{k: it[k] for k in ("id", "about_stop", "kind", "source", "why")}
                               | {"text": it["text"]} for it in items]
        import key_fact_coverage as kfc
        own = kfc.own_article(ev, title)
        ref = Referent(title, (), (own or {}).get("title", ""), (own or {}).get("lead", ""))
        used = 0
        for s in sgg._content_sentences(sgg._block_body_prose(blk)):
            if not sgg.is_factual_sentence(s) or _is_navigation(s):
                continue
            r = assess(s, items, judge_source=(judge_sources or {}).get((title, s)), ref=ref,
                       other_place_used=used)
            if r.get("other_place"):
                used += 1
            if not r["ok"]:
                out["offtopic"].append({"stop": title, "claim": s, "why": r["why"], "source": r["source"]})
    return out
