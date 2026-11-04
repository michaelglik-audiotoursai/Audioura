#!/usr/bin/env python3
"""user_stop_context.py — LOCAL-862B (D760).

D760 (Michael, 2026-11-03): "Humans would prefer to hear something interesting of
questionable validity, than nothing or short descriptions as long as we disclose
what the speculation is.  Of course the best is when the stories are interesting
and true."

LOCAL-862 gave a user stop LAYER 1: sourced venue facts (Places record, reviews,
the venue's own site).  A small venue often has few of those, and the stop came out
as two lines.  This module adds the two layers around it:

  LAYER 2 — TRUE CONNECTED CONTEXT, stated as fact.  Sourced from Wikipedia and
            Serper, each fact tied to something the venue actually has:
              * the meaning/origin of the venue's NAME when the name is a word
                (Longan: Chinese lóngyǎn, "dragon eye"; Rambutan: Malay "rambut",
                hair);
              * the documented story of its STREET or district (Bùi Viện, the
                backpacker quarter);
              * the TRADITION behind what it offers (karaoke, Vietnamese massage,
                live acoustic music in Saigon cafés).
  LAYER 3 — DISCLOSED LEGEND OR SPECULATION.  A folk tale tied to the name, or an
            unverified claim that appears in a snippet.  EVERY layer-3 sentence
            must carry a disclosure marker ("A Vietnamese folk tale tells …",
            "We couldn't confirm this, but …").  ``has_disclosure`` is the single
            definition of "carries a marker"; the scrub and the verifier both use
            it, so an undisclosed legend is dropped and a disclosed one is kept.

The verifier gate here (``layer_gate``) is DETERMINISTIC and runs after the model's
labels.  A disclosure marker never licenses an invention: a marked sentence must
still draw on a layer-3 source line, and a year, a "first", or a piece of geography
that no source line contains is dropped whether or not it is marked.

Network access is injected (``wiki_fn``, ``wiki_search_fn``, ``serp_fn``) so every
unit test runs offline.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

from text_polish import city_from_scope
from user_stop_narration import _fold, _split_sentences

__all__ = [
    "has_disclosure", "is_name_meaning_sentence", "name_words",
    "street_from_address", "gather_context", "layer_gate", "layer_tag",
    "strip_layer_tag", "clear_cache",
]

# ─────────────────────────────────────────────────────────────────────────────
# disclosure marker — the ONE definition
# ─────────────────────────────────────────────────────────────────────────────

_TALE = r"(?:folk\s*tales?|folktales?|legends?|myths?|folk\s+stor(?:y|ies)|fables?|folklore|lore)"
DISCLOSURE_RE = re.compile(
    r"(?i)(?:"
    # "A Vietnamese folk tale tells …", "One legend says …", "The legend goes …"
    r"\b(?:an?|one|the|some|local)\s+(?:[\w'’-]+\s+){0,3}" + _TALE
    + r"\s+(?:tells|says|holds|goes|has\s+it|recounts|claims|relates|speaks|describes|"
    r"links|connects|traces)\b"
    # "Legend has it …", "Legend says …"
    r"|\blegend\s+(?:has\s+it|says|holds|tells|goes)\b"
    # "According to (a) (local) legend / folk tale …"
    r"|\baccording\s+to\s+(?:an?\s+|one\s+|the\s+|some\s+)?(?:[\w'’-]+\s+){0,3}"
    + _TALE + r"\b"
    # "It is said that …", "The story goes …", "Folklore holds …"
    r"|\bit\s+is\s+said\s+that\b|\b(?:the\s+)?stor(?:y|ies)\s+goes\b"
    r"|\bfolklore\s+(?:says|holds|tells)\b"
    # explicit unverified marker
    r"|\bwe\s+(?:couldn['’]?t|could\s+not|were\s+unable\s+to|can['’]?t|cannot|"
    r"haven['’]?t\s+been\s+able\s+to)\s+(?:confirm|verify)\b"
    r"|\b(?:unconfirmed|unverified)\b"
    r")")


def has_disclosure(sentence: str) -> bool:
    """True when the sentence carries a layer-3 disclosure marker."""
    return bool(sentence and DISCLOSURE_RE.search(sentence))


# ─────────────────────────────────────────────────────────────────────────────
# name meaning
# ─────────────────────────────────────────────────────────────────────────────

_NAME_MEANING_CUE_RE = re.compile(
    r"(?i)\b(means?|meaning|derived\s+from|derives\s+from|comes?\s+from|stems?\s+from|"
    r"literally|translates?|translation|named\s+(?:after|for|from)|"
    r"from\s+the\s+(?:[\w'’-]+\s+){0,2}word|word\s+for|called|known\s+as|etymolog\w*)\b")
# narrative-legend vocabulary: if present, the sentence tells a story, it does not
# explain a word, so the name-meaning exemption does not apply.
_NARRATIVE_LEGEND_RE = re.compile(
    r"(?i)\b(hatched|once\s+upon|the\s+boy|a\s+boy|village|robber|raven|spirits?|"
    r"gods?|goddess|demons?|serpents?|magic\w*|enchant\w*|fairy|fables?|tales?|"
    r"legends?|myths?|folk\w*|egg|king|princess)\b")

_GENERIC_WORDS = {
    "the", "and", "for", "bar", "spa", "cafe", "café", "restaurant", "club",
    "lounge", "shop", "store", "street", "saigon", "city", "house", "pub",
    "venue", "studio", "salon", "market", "star", "born", "walking", "nightlife",
    "karaoke", "coffee", "massage", "ho", "chi", "minh", "vietnam",
}


def name_words(name: str) -> List[str]:
    """Distinctive single words of a venue name that could be a WORD with a
    meaning/origin (Longan, Rambutan).  Short or generic tokens are skipped."""
    out = []
    for w in _fold(name).split():
        if len(w) >= 4 and w not in _GENERIC_WORDS and w not in out:
            out.append(w)
    return out[:2]


def is_name_meaning_sentence(sentence: str, name: str) -> bool:
    """A sentence that explains the meaning/origin of a word in the venue's name
    ("The word longan comes from the Chinese lóngyǎn, literally 'dragon eye'").
    It must carry a meaning cue, contain a distinctive word of the name, and tell
    no story (hatched, village, tale …)."""
    if not sentence or not name:
        return False
    if not _NAME_MEANING_CUE_RE.search(sentence):
        return False
    if _NARRATIVE_LEGEND_RE.search(sentence):
        return False
    toks = set(_fold(sentence).split())
    return any(w in toks for w in name_words(name))


# ─────────────────────────────────────────────────────────────────────────────
# Wikipedia + Serper (injectable), small per-process cache
# ─────────────────────────────────────────────────────────────────────────────

_CACHE: Dict[Tuple, object] = {}
_UA = "Audioura/2.2 (audio tour research; contact: support@audioura.app)"


def clear_cache() -> None:
    _CACHE.clear()


def _default_wiki_fn(title: str) -> Optional[Dict]:
    """Plain-text extract of an English Wikipedia page, following redirects.
    Returns {"title","text","disambiguation","url"} or None."""
    key = ("wiki", title)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    try:
        import requests
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "prop": "extracts|pageprops",
                    "explaintext": "1", "titles": title, "redirects": "1",
                    "ppprop": "disambiguation", "format": "json"},
            headers={"User-Agent": _UA}, timeout=8)
        if r.status_code == 200:
            for pid, p in ((r.json().get("query") or {}).get("pages") or {}).items():
                if str(pid) == "-1" or not p.get("extract"):
                    continue
                res = {"title": p.get("title") or title, "text": p["extract"],
                       "disambiguation": "pageprops" in p,
                       "url": "https://en.wikipedia.org/wiki/"
                              + quote((p.get("title") or title).replace(" ", "_"))}
                break
    except Exception:
        res = None
    _CACHE[key] = res
    return res


def _default_wiki_search_fn(query: str) -> List[str]:
    key = ("wikisearch", query)
    if key in _CACHE:
        return _CACHE[key]
    out: List[str] = []
    try:
        import requests
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": query,
                    "srlimit": 4, "format": "json"},
            headers={"User-Agent": _UA}, timeout=8)
        if r.status_code == 200:
            out = [x.get("title") for x in
                   ((r.json().get("query") or {}).get("search") or [])
                   if x.get("title")]
    except Exception:
        out = []
    _CACHE[key] = out
    return out


def _sections(text: str) -> List[Tuple[str, str]]:
    """Split a plain-text Wikipedia extract into (heading, body); the lead has
    heading ''."""
    parts: List[Tuple[str, str]] = []
    head, buf = "", []
    for ln in (text or "").split("\n"):
        m = re.match(r"^\s*=+\s*(.+?)\s*=+\s*$", ln)
        if m:
            parts.append((head, "\n".join(buf).strip()))
            head, buf = m.group(1).strip(), []
        else:
            buf.append(ln)
    parts.append((head, "\n".join(buf).strip()))
    return [(h, b) for h, b in parts if b]


_CJK_RE = re.compile(r"[\u3000-\u9fff\uf900-\ufaff]")


def _clean_sentence(s: str) -> str:
    s = re.sub(r"\s*\((?:[^()]*;[^()]*|\s*)\)", "", s)          # "(; Dimocarpus …)" stubs
    if _CJK_RE.search(s):
        # a sentence that spells Chinese characters cannot be spoken as is; keep
        # only the gloss ("... literally means "dragon eye"") when there is one
        m = re.search(r'literally\s+means?\s+("[^"]+")', s)
        if m:
            return f"The Chinese characters together literally mean {m.group(1)}."
        s = re.sub(r"(?:simplified|traditional)\s+Chinese:\s*[^;.]*;?\s*", "", s)
        s = _CJK_RE.sub("", s)
        s = re.sub(r"\s*;\s*;", ";", s)
        s = re.sub(r"\s+([,.;:])", r"\1", s)
        if re.search(r"(?i)\b(?:characters?|while|and)\s+(?:means?|mean)\b|\bso\s+together\s*[,.]", s):
            return ""
    if re.search(r"[A-Za-z]\d\b", s):          # tone-number romanisation: lung4 ngaan5
        return ""
    s = " ".join(s.split())
    return s.strip()


_ELLIPSIS_RE = re.compile(r"\s*(?:\.\.\.|…)\s*$")


def _trim_truncated(s: str) -> str:
    """A search snippet that ends in an ellipsis is cut back to its last whole
    clause ('..., and from his spirit grew the ...' -> '...'), so a sentence is
    never read out half-finished.  Returns '' when too little is left."""
    s = " ".join((s or "").split())
    if not _ELLIPSIS_RE.search(s):
        return s
    s = _ELLIPSIS_RE.sub("", s)
    cut = max(s.rfind(", "), s.rfind("; "), s.rfind(". "))
    if cut < 80:
        return ""
    s = s[:cut].rstrip(" ,;")
    return s if s.endswith((".", "!", "?")) else s + "."


def _good_sentence(s: str, lo: int = 30, hi: int = 330) -> bool:
    return lo <= len(s) <= hi and s[-1:] in ".!?" and not s.endswith("…")


def _ffold(t: str) -> str:
    return _fold(t).replace("đ", "d")


def _default_serp_fn():
    try:
        from work_story_searcher import _serp_search
        return _serp_search
    except Exception:
        return None


def _serp(query: str, serp_fn, calls: Dict, log=None):
    key = ("serp", query)
    if key in _CACHE:
        return _CACHE[key]
    fn = serp_fn or _default_serp_fn()
    if fn is None:
        return []
    calls["serp"] = calls.get("serp", 0) + 1
    try:
        res, _lat = fn(query)
    except Exception as e:
        if log:
            log(f"[LOCAL-862B] serp failed {query!r}: {e}")
        res = []
    res = [r for r in (res or []) if isinstance(r, dict)]
    _CACHE[key] = res
    return res


# ─────────────────────────────────────────────────────────────────────────────
# layer 2a — the meaning of the name
# ─────────────────────────────────────────────────────────────────────────────

_LEGEND_CUE_RE = re.compile(
    r"(?i)\b(legend\w*|myth\w*|folk\s*tales?|folktales?|folklore|fables?|"
    r"according\s+to\s+(?:a\s+)?(?:legend|tale))\b")


def _name_meaning_facts(word: str, wiki_fn, calls: Dict) -> Tuple[List[Dict], List[Dict]]:
    """(context_facts, legend_facts) from the Wikipedia article for the word."""
    page = wiki_fn(word.capitalize())
    calls["wiki"] = calls.get("wiki", 0) + 1
    if not page or page.get("disambiguation"):
        return [], []
    if _ffold(page["title"]) != _ffold(word):
        return [], []
    secs = _sections(page["text"])
    ety = [b for h, b in secs if re.search(r"(?i)etymolog|name|origin", h or "")]
    lead = next((b for h, b in secs if not h), "")
    ctx: List[Dict] = []
    leg: List[Dict] = []
    src = page["url"]
    ety_sents = [_clean_sentence(s) for b in ety for s in _split_sentences(b)]
    ety_sents = [s for s in ety_sents if s and _good_sentence(s)]
    # no etymology section -> this is just a dictionary entry, not a name story
    if not ety_sents:
        return [], []
    for s in ety_sents[:4]:
        d = {"kind": "name_meaning", "layer": 2, "text": s, "source": src,
             "specific": True}
        if _LEGEND_CUE_RE.search(s):
            d.update(kind="legend", layer=3)
            leg.append(d)
        else:
            ctx.append(d)
    # what the word denotes - framed so it can never read as "the venue IS a tree"
    for s in _split_sentences(lead)[:1]:
        s = _clean_sentence(s)
        if s and _good_sentence(s):
            ctx.append({"kind": "name_meaning", "layer": 2, "specific": True,
                        "text": f'As a plain word, "{word}" also names a plant. {s}',
                        "source": src})
    # a Description/Fruit sentence that explains the word ("hence the name ... hairy";
    # "This gives the illusion of an eye") - with the sentence it refers back to
    for h, b in secs:
        if not re.search(r"(?i)^(?:description|fruit)$", h or ""):
            continue
        ss = [_clean_sentence(x) for x in _split_sentences(b)]
        for i, x in enumerate(ss):
            if x and _good_sentence(x) and re.search(
                    r"(?i)hence\s+the\s+name|illusion\s+of|resembl\w+", x):
                if re.match(r"(?i)(this|it|these|they)\b", x) and i > 0 and ss[i - 1] \
                        and _good_sentence(ss[i - 1]):
                    x = f"{ss[i - 1]} {x}"
                ctx.append({"kind": "name_meaning", "layer": 2, "text": x,
                            "source": src, "specific": True})
                break
        if ctx and ctx[-1]["text"].find("hence the name") >= 0 or any(
                "illusion" in c["text"] for c in ctx):
            break
    # the page's own folklore section -> layer 3 (a legend, to be disclosed)
    for h, b in secs:
        if re.search(r"(?i)^(?:in\s+culture|folklore|legends?|mythology|culture|in\s+popular\s+culture)$", h or ""):
            ss = [_clean_sentence(x) for x in _split_sentences(b)]
            ss = [x for x in ss if x and _good_sentence(x, lo=25)]
            if ss and _LEGEND_CUE_RE.search(ss[0]) or (ss and re.search(r"(?i)\btells\b", ss[0])):
                leg.append({"kind": "legend", "layer": 3, "text": " ".join(ss[:3]),
                            "source": src, "specific": True})
                break
    return ctx[:6], leg[:2]


_NARRATIVE_VERB_RE = re.compile(
    r"(?i)\b(gave|given|grew|grow|killed|slew|slain|slayed|turned|became|received|saw|found|"
    r"lived|came|ate|fell|died|rescued|saved|wished|rolled|laid|hatched|fought|"
    r"transformed|sprang|planted|buried|dropped|wept|fled|protected|defeated|"
    r"stabbed|witnessing|terroriz\w+|connects|is\s+about|tells\s+of)\b")
_STORYTIME_RE = re.compile(
    r"(?i)\b(story\s+(?:tells|goes)|tale\s+(?:tells|goes)|long\s+ago|a\s+long\s+time\s+ago|"
    r"there\s+(?:was|lived)|once\s+upon)\b")
_ANNOUNCE_RE = re.compile(
    r"(?i)(tells\s+the\s+(?:story|tale)\s+of|the\s+legend\s+of\b|discover\b|enchanting|"
    r"how\s+to\b|recipe|benefits|buy\b|follow\s+\w+\s+through|distinguishing|"
    r"\bpdf\b|\bonce\s+upon\s+a\s+time\s+in\s+the\s+kingdom\b)")


def _legend_facts(word: str, serp_fn, calls: Dict, log=None) -> List[Dict]:
    """A folk tale tied to the name.  Snippet text only (never a page title), cut
    back to a whole clause, and it must actually TELL something (a narrative verb),
    not announce a legend ('Discover the legend of ...')."""
    q = f'{word} legend folk tale origin of the name'
    out: List[Dict] = []
    for r in _serp(q, serp_fn, calls, log):
        snippet = _trim_truncated(r.get("snippet") or "")
        for s in _split_sentences(snippet):
            s = _clean_sentence(s)
            if not _good_sentence(s, lo=60):
                continue
            f = _ffold(s)
            if word not in f.split() and not (word == "longan" and "dragon" in f):
                continue
            if _ANNOUNCE_RE.search(s):
                continue
            if not (_NARRATIVE_VERB_RE.search(s) or _STORYTIME_RE.search(s)):
                continue
            if not (_LEGEND_CUE_RE.search(s) or _STORYTIME_RE.search(s)
                    or "name" in f.split()):
                continue
            if all(_ffold(o["text"]) != f for o in out):
                out.append({"kind": "legend", "layer": 3, "text": s,
                            "source": r.get("link") or r.get("url") or "serper_search:legend",
                            "specific": True})
                break
        if len(out) >= 2:
            break
    return out


_WORK_RE = re.compile(r"(?i)\b(film|movie|song|album|novel|musical|television|play|opera)\b")


def _name_work_facts(name: str, wiki_fn, wiki_search_fn, calls: Dict) -> List[Dict]:
    """A venue whose name (3+ words) is the title of a well-known work shares its
    name with it.  We state THAT as context (layer 2) and, separately, that we
    could not confirm the venue was named for it (layer 3, disclosed)."""
    toks = _ffold(name).split()
    if len(toks) < 3 or len(toks) > 6:
        return []
    calls["wiki"] = calls.get("wiki", 0) + 1
    page = wiki_fn(name)
    if not page or _ffold(page["title"]) != _ffold(name):
        return []
    text = page["text"]
    if page.get("disambiguation"):
        # "A Star Is Born may refer to: A Star Is Born (1937 film) ... remakes"
        years = sorted({m.group(1) for m in re.finditer(r"\((1[89]\d{2}|20\d{2})\s+(?:film|soundtrack)\)", text)})
        if not years or not re.search(r"(?i)\bfilm\b", text):
            return []
        phrase = ", ".join(years[:-1]) + (" and " if len(years) > 1 else "") + years[-1]
        ctx = (f'The words "{name}" are also the title of a film, first made in {years[0]} '
               f'and remade in {phrase.split(" and ")[-1] if len(years) > 1 else years[0]}.')
        if len(years) > 2:
            ctx = (f'The words "{name}" are also the title of a film, first made in {years[0]} '
                   f'and remade several times, most recently in {years[-1]}.')
    else:
        lead = _clean_sentence(_split_sentences(next((b for h, b in _sections(text) if not h), ""))[0]
                               if text.strip() else "")
        if not lead or not _WORK_RE.search(lead):
            return []
        ctx = f'The words "{name}" are also the title of a work: {lead}'
    extra: List[Dict] = []
    stars = re.findall(r"\((1[89]\d{2}|20\d{2})\s+film\),\s+starring\s+([^,\n]+?)(?:\s+and\s+[^,\n]+)?,", text)
    if page.get("disambiguation") and len(stars) >= 2:
        first = [f"{n.strip()} in {y}" for y, n in stars[1:4]]
        listed = ", ".join(first[:-1]) + (", and " if len(first) > 2 else " and ") + first[-1]
        extra.append({"kind": "name_meaning", "layer": 2, "specific": True,
                      "source": page["url"],
                      "text": f"The remakes starred {listed}."})
    return [
        {"kind": "name_meaning", "layer": 2, "text": ctx, "source": page["url"],
         "specific": True}, *extra,
        {"kind": "unconfirmed", "layer": 3, "specific": True, "source": page["url"],
         "text": (f'The venue may have taken its name from that title, but no source we '
                  f'found says so.')},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# layer 2b — the street / district
# ─────────────────────────────────────────────────────────────────────────────

_ADMIN_PART_RE = re.compile(
    r"(?i)\b(district|qu[ậa]n|ward|ph[ưu][ờo]ng|city|ho\s+chi\s+minh|h[ồo]\s+ch[íi]\s+minh|"
    r"vi[ệe]t\s*nam|vietnam|th[àa]nh\s+ph[ốo]|tp\.?|province|saigon|s[àa]i\s+g[òo]n)\b")


def street_from_address(addr: str) -> str:
    """The street name out of 'Label: ' free address text ('224 Đề Thám, Phường …')."""
    for part in (addr or "").split(","):
        p = part.strip()
        if not p or ":" in p or _ADMIN_PART_RE.search(p):
            continue
        p = re.sub(r"^(?:s[ốo]\s+)?\d+[A-Za-z]?(?:[/-]\d+[A-Za-z]?)*\s+", "", p)
        p = re.sub(r"(?i)^(đường|duong|phố|pho|street|st\.?)\s+", "", p).strip()
        if len(p) >= 3 and not re.fullmatch(r"[\d\W]+", p):
            return p
    return ""


_STREET_STOP = {"street", "walking", "road", "duong", "pho", "st", "the", "boulevard",
                "avenue", "ho", "chi", "minh", "city", "saigon", "vietnam"}


def _street_tokens(street: str) -> List[str]:
    return [t for t in _ffold(street).split() if t not in _STREET_STOP and len(t) >= 2]


def _street_candidates(poi: Dict, place: Optional[Dict], alias: str) -> List[str]:
    out: List[str] = []
    name = (poi.get("name") or poi.get("title") or "").strip()
    for cand in (alias, name):
        if cand and re.search(r"(?i)\b(street|road|walking)\b", cand):
            base = re.sub(r"(?i)\b(walking\s+street|street|road)\b", "", cand).strip()
            if len(_street_tokens(base)) >= 1 and base not in out:
                out.append(base)
    for addr in ((place or {}).get("_serper_address"), poi.get("address")):
        st = street_from_address(addr or "")
        if st and st not in out:
            out.append(st)
    return out[:2]


def _street_wiki_facts(street: str, city: str, wiki_fn, wiki_search_fn,
                       calls: Dict) -> List[Dict]:
    toks = _street_tokens(street)
    if not toks:
        return []
    calls["wiki"] = calls.get("wiki", 0) + 1
    titles = wiki_search_fn(f"{street} Street {city}".strip()) or []
    for t in titles:
        ft = set(_ffold(t).split())
        if not all(x in ft for x in toks):
            continue
        page = wiki_fn(t)
        calls["wiki"] += 1
        if not page or page.get("disambiguation"):
            continue
        secs = _sections(page["text"])
        lead = next((b for h, b in secs if not h), "")
        lead_s = [_clean_sentence(s) for s in _split_sentences(lead)]
        lead_s = [s for s in lead_s if _good_sentence(s)]
        if not lead_s or not re.search(r"(?i)\b(street|road|boulevard|avenue|quarter|district)\b",
                                       lead_s[0]):
            continue
        facts = [{"kind": "street", "layer": 2, "text": s, "source": page["url"],
                  "specific": True} for s in lead_s[:2]]
        hist = next((b for h, b in secs if re.search(r"(?i)histor|name|origin", h or "")), "")
        for s in _split_sentences(hist)[:2]:
            s = _clean_sentence(s)
            if _good_sentence(s):
                facts.append({"kind": "street", "layer": 2, "text": s,
                              "source": page["url"], "specific": True})
        return facts[:4]
    return []


def _snippet_sentences(results, must_words: List[str], cue_re, locality_re,
                       max_n: int, kind: str, layer: int, default_src: str) -> List[Dict]:
    """Whole sentences out of search SNIPPETS (never titles - a title is a headline,
    not a fact), cut back to a complete clause, no questions or link-bait."""
    out: List[Dict] = []
    for r in results:
        snippet = _trim_truncated(r.get("snippet") or "")
        picked = 0
        for s in _split_sentences(snippet):
            s = _clean_sentence(s)
            if not _good_sentence(s, lo=50) or s.endswith("?"):
                continue
            if re.search(r"(?i)\b(click|book now|tour|ticket|price from|read more|"
                         r"subscribe|top\s+\d+|best\s+\w+\s+in\b)\b", s):
                continue
            f = _ffold(s)
            toks = set(f.split())
            if must_words and not all(w in toks or w in f for w in must_words):
                continue
            if cue_re is not None and not cue_re.search(s):
                continue
            if locality_re is not None and not locality_re.search(s):
                continue
            if all(_ffold(o["text"]) != f for o in out):
                out.append({"kind": kind, "layer": layer, "text": s,
                            "source": r.get("link") or r.get("url") or default_src,
                            "specific": True})
                picked += 1
            if picked >= 2 or len(out) >= max_n:
                break
        if len(out) >= max_n:
            break
    return out


_LOCAL_RE = re.compile(r"(?i)\b(vietnam\w*|saigon|sai\s+gon|ho\s+chi\s+minh|hcmc)\b")


def _street_serp_facts(street: str, city: str, serp_fn, calls: Dict, log=None) -> List[Dict]:
    toks = _street_tokens(street)
    if not toks:
        return []
    q = f'"{street}" street {city} history'.strip()
    res = _serp(q, serp_fn, calls, log)
    return _snippet_sentences(
        res, toks, re.compile(r"(?i)\b(street|road|quarter|alley|district|backpacker|"
                              r"named|history|known)\b"), None, 2, "street", 2,
        "serper_search:street")


# ─────────────────────────────────────────────────────────────────────────────
# layer 2d - the district (from the stop's address) or, failing that, the city
# ─────────────────────────────────────────────────────────────────────────────

_DISTRICT_RE = re.compile(r"(?i)\b(?:district|qu[ậa]n)\s+(\d{1,2})\b")
_NUMERIC_SENT_RE = re.compile(r"(?i)\b(km2|sq\s*mi|population|inhabitants|density)\b|\d{1,3}(?:,\d{3})+")


def _lead_story_sentences(page: Dict, max_n: int) -> List[str]:
    secs = _sections(page["text"])
    lead = next((b for h, b in secs if not h), "")
    out = []
    for s in _split_sentences(lead):
        s = _clean_sentence(s)
        if s and _good_sentence(s) and not _NUMERIC_SENT_RE.search(s):
            out.append(s)
        if len(out) >= max_n:
            break
    return out


def _place_story_facts(poi: Dict, place: Optional[Dict], city: str, wiki_fn,
                       wiki_search_fn, calls: Dict) -> List[Dict]:
    """The district's documented story when the stop's address names one.  Text is
    Wikipedia's own; population/area figures are skipped.  There is deliberately NO
    city-level fallback: the city's GDP, rivers and airport are padding, not a
    story that connects to the venue."""
    addr = " , ".join(a for a in ((place or {}).get("_serper_address"), poi.get("address")) if a)
    m = _DISTRICT_RE.search(addr or "")
    facts: List[Dict] = []
    if m and city:
        n = m.group(1)
        calls["wiki"] = calls.get("wiki", 0) + 1
        for t in (wiki_search_fn(f"District {n} {city}") or [])[:3]:
            ft = _ffold(t)
            if f"district {n}" in ft and _ffold(city).split()[0] in ft:
                page = wiki_fn(t)
                calls["wiki"] += 1
                if page and not page.get("disambiguation"):
                    for s in _lead_story_sentences(page, 2):
                        facts.append({"kind": "district", "layer": 2, "text": s,
                                      "source": page["url"], "specific": True})
                    break
        if facts:
            return facts
    return facts


# ─────────────────────────────────────────────────────────────────────────────
# layer 2c — the tradition behind what the venue offers
# ─────────────────────────────────────────────────────────────────────────────

# (kind words that select it, topic word the snippet must mention, query template)
_TRADITIONS = (
    ({"karaoke"}, r"karaoke", "karaoke Vietnam culture popular"),
    ({"massage", "spa", "wellness"}, r"massage|spa|acupressure|herbal",
     "traditional Vietnamese massage history"),
    ({"acoustic", "live"}, r"acoustic|live\s+music|singer|songwriter|unplugged",
     "live acoustic music cafes {city} scene history"),
    ({"cafe", "café", "coffee"}, r"coffee|cafe|café", "Vietnamese cafe coffee culture {city} history"),
    ({"gay", "lgbt", "lgbtq", "drag"}, r"gay|lgbt|drag", "{city} gay nightlife scene history"),
    ({"bar", "pub", "club", "lounge", "nightlife", "street"}, r"bars?|nightlife|pubs?|beer|clubs?",
     "{city} bar nightlife scene history"),
    ({"restaurant", "bistro", "eatery", "diner", "grill"}, r"restaurant|food|dining|cuisine",
     "{city} restaurant dining scene history"),
)


def _tradition_for(kind_tokens: set):
    for words, topic, tmpl in _TRADITIONS:
        if kind_tokens & words:
            return words, topic, tmpl
    return None


def _tradition_facts(kind_tokens: set, location: str, serp_fn, calls: Dict, log=None) -> List[Dict]:
    t = _tradition_for(kind_tokens)
    if not t:
        return []
    _words, topic, tmpl = t
    city = city_from_scope(location) or ""
    country = "Vietnam" if _LOCAL_RE.search(location or "") or not city else city
    q = tmpl.format(city=city, country=country).strip()
    res = _serp(q, serp_fn, calls, log)
    return _snippet_sentences(res, [], re.compile(r"(?i)\b(?:" + topic + r")"),
                              _LOCAL_RE if _LOCAL_RE.search(location or "") else None,
                              3, "tradition", 2, "serper_search:tradition")


# ─────────────────────────────────────────────────────────────────────────────
# the entry point
# ─────────────────────────────────────────────────────────────────────────────

def gather_context(poi: Dict, location: str, *, place: Optional[Dict] = None,
                   alias: str = "", kind_tokens: Optional[set] = None,
                   wiki_fn: Callable = None, wiki_search_fn: Callable = None,
                   serp_fn: Callable = None, allow_search: bool = True,
                   log=None) -> Dict:
    """Layer-2 and layer-3 facts for ONE user stop.

    Returns {"facts": [{"kind","layer","text","source","specific"}],
             "calls": {"wiki": n, "serp": n}}.  Never raises."""
    calls: Dict = {"wiki": 0, "serp": 0}
    facts: List[Dict] = []
    if not allow_search:
        return {"facts": facts, "calls": calls}
    wiki_fn = wiki_fn or _default_wiki_fn
    wiki_search_fn = wiki_search_fn or _default_wiki_search_fn
    name = (poi.get("name") or poi.get("title") or "").strip()
    city = city_from_scope(location) or ""
    kind_tokens = set(kind_tokens or ())

    # 2a — the name as a word
    words_with_page: List[str] = []
    try:
        for w in name_words(name):
            ctx, leg = _name_meaning_facts(w, wiki_fn, calls)
            if ctx or leg:
                words_with_page.append(w)
            facts.extend(ctx)
            facts.extend(leg)
    except Exception as e:  # pragma: no cover
        if log:
            log(f"[LOCAL-862B] name-meaning failed for {name!r}: {e}")

    # 3 — a folk tale tied to the name (only for a name that IS a word)
    try:
        have_legend = any(f["layer"] == 3 for f in facts)
        for w in words_with_page:
            if not have_legend:
                facts.extend(_legend_facts(w, serp_fn, calls, log))
    except Exception as e:  # pragma: no cover
        if log:
            log(f"[LOCAL-862B] legend search failed for {name!r}: {e}")

    # 2a' — the whole name is also the title of a work (A Star Is Born)
    try:
        facts.extend(_name_work_facts(name, wiki_fn, wiki_search_fn, calls))
    except Exception as e:  # pragma: no cover
        if log:
            log(f"[LOCAL-862B] name-work context failed for {name!r}: {e}")

    # 2b — the street / district
    try:
        street_facts: List[Dict] = []
        for st in _street_candidates(poi, place, alias):
            street_facts = _street_wiki_facts(st, city, wiki_fn, wiki_search_fn, calls)
            if not street_facts:
                street_facts = _street_serp_facts(st, city, serp_fn, calls, log)
            if street_facts:
                break
        facts.extend(street_facts)
    except Exception as e:  # pragma: no cover
        if log:
            log(f"[LOCAL-862B] street context failed for {name!r}: {e}")

    # 2d — the district named by the address, else the city
    try:
        facts.extend(_place_story_facts(poi, place, city, wiki_fn, wiki_search_fn, calls))
    except Exception as e:  # pragma: no cover
        if log:
            log(f"[LOCAL-862B] place context failed for {name!r}: {e}")

    # 2c — the tradition behind what it offers
    try:
        facts.extend(_tradition_facts(kind_tokens, location, serp_fn, calls, log))
    except Exception as e:  # pragma: no cover
        if log:
            log(f"[LOCAL-862B] tradition context failed for {name!r}: {e}")

    # de-duplicate
    seen, uniq = set(), []
    for f in facts:
        k = _ffold(f["text"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(f)
    if log:
        c2 = sum(1 for f in uniq if f["layer"] == 2)
        c3 = sum(1 for f in uniq if f["layer"] == 3)
        log(f"[LOCAL-862B] context {name!r}: layer2={c2} layer3={c3} calls={calls}")
    return {"facts": uniq, "calls": calls}


# ─────────────────────────────────────────────────────────────────────────────
# fact-line tags (so the verifier knows which layer a source line belongs to)
# ─────────────────────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"^\[(venue|context|legend|unconfirmed)\]\s*")


def layer_tag(fact: Dict) -> str:
    k = fact.get("kind")
    if k == "legend":
        return "legend"
    if k == "unconfirmed":
        return "unconfirmed"
    return "context" if fact.get("layer") == 2 else "venue"


def strip_layer_tag(line: str) -> str:
    return _TAG_RE.sub("", line or "")


# ─────────────────────────────────────────────────────────────────────────────
# verifier gate — deterministic, runs AFTER the model's labels
# ─────────────────────────────────────────────────────────────────────────────

_LEGEND_VOCAB_RE = re.compile(
    r"(?i)\b(dragons?|legends?|myths?|mythical|folk\s*tales?|folktales?|fables?|"
    r"fairy\s*tales?|hatched|goddess|spirits?|demons?|serpents?|magical|enchanted|"
    r"folklore|once\s+upon)\b")
_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b(?!\s*(?:reviews?|ratings?|meters?|metres?|km|m\b|people|visitors))")
_FIRSTS_RE = re.compile(r"(?i)\b(first[- ]ever|the\s+first|first\s+to|oldest|earliest|pioneer\w*|"
                        r"original\s+(?:home|birthplace))\b")
_GEO_RE = re.compile(
    r"(?i)\b(sea|south\s+china\s+sea|coast|coastal|ocean|harbou?r|beach|mountains?|"
    r"island|river|delta|lake|bay)\b")
_STOP = {"that", "this", "with", "from", "have", "were", "their", "there", "which",
         "about", "into", "when", "where", "also", "been", "your", "says", "tells",
         "tale", "legend", "folk", "story", "goes", "said", "according", "unconfirmed",
         "confirm", "couldn", "could", "verify", "stop", "place"}


def _content_tokens(s: str) -> set:
    return {t for t in _ffold(s).split() if len(t) >= 4 and t not in _STOP}


def layer_gate(sentence: str, name: str, source_lines: List[str]) -> Optional[str]:
    """Return a drop reason, or None to keep.  ``source_lines`` are the fact-sheet
    source lines for the stop, each optionally tagged [venue]/[context]/[legend]/
    [unconfirmed] (untagged = venue).

    * disclosure licenses ONLY the layer-3 content: a marked sentence must draw on
      a [legend]/[unconfirmed] line (>= 2 shared content words), else it is an
      invention wearing a marker;
    * legend vocabulary that no source line carries is invention; vocabulary that
      only a layer-3 line carries needs the marker (undisclosed legend);
    * a year, a "first", or geography that no source line contains is dropped
      whether or not the sentence is marked (invented specific / invented geography).
    """
    plain, l3 = [], []
    for ln in source_lines or []:
        m = _TAG_RE.match(ln or "")
        tag = m.group(1) if m else "venue"
        (l3 if tag in ("legend", "unconfirmed") else plain).append(strip_layer_tag(ln))
    plain_f = " " + _ffold(" ".join(plain) + " " + name) + " "
    l3_f = " " + _ffold(" ".join(l3)) + " "
    all_f = plain_f + l3_f
    disclosed = has_disclosure(sentence)

    if disclosed:
        base_t = _content_tokens(" ".join(plain) + " " + name)
        sent_t = _content_tokens(sentence) - base_t
        best = max((len(sent_t & (_content_tokens(x) - base_t)) for x in l3), default=0)
        loose_t = _content_tokens(sentence) - _content_tokens(name)
        best_loose = max((len(loose_t & _content_tokens(x)) for x in l3), default=0)
        if best < 2 and best_loose < 2:
            return "disclosure marker without a layer-3 source"
    else:
        # retelling a layer-3 line (>= 3 shared content words) without a marker
        if l3 and not is_name_meaning_sentence(sentence, name):
            base_t = _content_tokens(" ".join(plain) + " " + name)
            sent_t = _content_tokens(sentence) - base_t
            if max((len(sent_t & (_content_tokens(x) - base_t)) for x in l3), default=0) >= 2:
                return "undisclosed legend (layer-3 content without a marker)"
        for m in _LEGEND_VOCAB_RE.finditer(sentence):
            w = _ffold(m.group(1)).split()[0]
            if f" {w}" in plain_f or w.rstrip("s") in plain_f:
                continue                      # stated by a layer-1/2 source line
            if is_name_meaning_sentence(sentence, name):
                continue
            if w in l3_f or w.rstrip("s") in l3_f:
                return "undisclosed legend (layer-3 content without a marker)"
            return "legend vocabulary no source carries"
    for m in _YEAR_RE.finditer(sentence):
        if m.group(1) not in all_f:
            return f"year {m.group(1)} no source carries"
    for m in _FIRSTS_RE.finditer(sentence):
        w = _ffold(m.group(1)).split()[-1]
        if w not in all_f:
            return f"claim of '{m.group(1)}' no source carries"
    for m in _GEO_RE.finditer(sentence):
        w = _ffold(m.group(1)).split()[-1]
        if f" {w}" not in all_f and w not in all_f:
            return f"geography '{m.group(1)}' no source carries"
    return None
