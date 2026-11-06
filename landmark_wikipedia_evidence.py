#!/usr/bin/env python3
"""landmark_wikipedia_evidence.py -- LOCAL-872B: the stop's own Wikipedia article
as claim-gate evidence.

LOCAL-872's claim gate dropped TRUE, important facts (Notre-Dame Cathedral built
1863-1880 and consecrated 1959, Independence Palace's architect) only because the
stop's research snippets lacked them.  A landmark's Wikipedia article (lead +
infobox: built, architect, opened, style, capacity...) is the authority for exactly
those facts, so the gate must be handed it.

  fetch_article(name, lang)  -> {'title','lead','infobox'} | None  (free MediaWiki API)
  evidence_for(name, ...)    -> [str, ...]  one item per language: lead + infobox facts

Languages: English always, plus the local language of the tour's country (vi for
Vietnam).  Results (hits AND misses) are CACHED in the venue-cache database, the same
connection and TTL discipline as the P625 lookup (``landmark_coord_cache``), in table
``landmark_wiki_cache``.  Silent no-op when no DB is configured.

The article must NAME-MATCH the stop (``landmark_second_authority.name_matches``) so a
search for "Notre-Dame Cathedral Basilica of Saigon" never feeds the gate an unrelated
page.  ``fetch_fn`` is injectable so the module is unit-tested offline.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Callable, Dict, List, Optional, Sequence

__all__ = ["fetch_article", "evidence_for", "local_languages", "parse_infobox"]

CACHE_TTL_DAYS = int(os.environ.get("LANDMARK_WIKI_CACHE_TTL_DAYS", "90"))
CACHE_NEG_TTL_DAYS = int(os.environ.get("LANDMARK_WIKI_CACHE_NEG_TTL_DAYS", "3"))
_MAX_LEAD = 6000
_MAX_INFOBOX = 2500
_INFOBOX_KEYS = (
    "built", "construction", "construction_start", "construction_end", "completed",
    "completion_date", "opened", "opening", "opening_date", "open", "established",
    "founded", "date", "dedicated", "consecrated", "inaugurated", "start_date",
    "end_date", "architect", "architects", "architectural_style", "style", "designer",
    "builder", "engineer", "capacity", "seating_capacity", "owner", "built_for",
    "years_built", "year_built", "yearbuilt", "year_completed", "designation",
    "namesake", "former_names", "restored", "renovated", "height", "floors",
    "kiến_trúc_sư", "kiến trúc sư", "phong_cách", "khởi_công", "hoàn_thành",
    "xây_dựng", "khánh_thành", "ngày_khởi_công", "ngày_hoàn_thành", "thành_lập",
    "ngày_khánh_thành", "năm_xây_dựng", "kiến_trúc", "thiết_kế",
)

_COUNTRY_LANG = (
    (("vietnam", "viet nam", "việt nam", "hanoi", "hà nội", "ho chi minh", "saigon",
      "hcmc", "hue", "huế", "da nang", "đà nẵng", "hoi an"), "vi"),
    (("france", "paris", "lyon", "marseille", "nice"), "fr"),
    (("spain", "madrid", "barcelona", "seville"), "es"),
    (("italy", "rome", "venice", "florence", "milan"), "it"),
    (("germany", "berlin", "munich"), "de"),
    (("portugal", "lisbon", "porto"), "pt"),
    (("japan", "tokyo", "kyoto", "osaka"), "ja"),
    (("thailand", "bangkok"), "th"),
)


def local_languages(location: str) -> List[str]:
    """['en', 'vi'] for an HCMC / Hanoi tour; ['en'] when no local language is known."""
    loc = (location or "").lower()
    out = ["en"]
    for keys, lang in _COUNTRY_LANG:
        if any(k in loc for k in keys) and lang not in out:
            out.append(lang)
            break
    return out


# ---- infobox parsing ---------------------------------------------------------
def _clean_wikitext(v: str) -> str:
    v = re.sub(r"<!--.*?-->", " ", v or "", flags=re.S)
    v = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", " ", v, flags=re.S)
    v = re.sub(r"<br\s*/?>", ", ", v, flags=re.I)
    v = re.sub(r"<[^>]+>", " ", v)
    for _ in range(4):                       # nested templates
        v = re.sub(r"\{\{\s*(?:start date|end date|birth date|death date|start-date|"
                   r"nowrap|convert|ubl|plainlist|flatlist|hlist)\s*\|([^{}]*)\}\}",
                   lambda m: " ".join(p for p in m.group(1).split("|")
                                      if "=" not in p), v, flags=re.I)
        v = re.sub(r"\{\{[^{}|]*\|([^{}]*)\}\}",
                   lambda m: " ".join(p for p in m.group(1).split("|") if "=" not in p), v)
    v = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"'{2,}", "", v)
    v = re.sub(r"[{}\[\]]", " ", v)
    v = re.sub(r"\s+", " ", v).strip(" ,;|")
    return v


def parse_infobox(wikitext: str) -> str:
    """'built: 1863-1880; architect: Jules Bourard; ...' from the first infobox in the
    wikitext (en 'Infobox ...' or vi 'Thông tin ...').  '' when none."""
    if not wikitext:
        return ""
    m = re.search(r"\{\{\s*(?:Infobox|Thông tin|Hộp thông tin)", wikitext, flags=re.I)
    if not m:
        return ""
    block = wikitext[m.start(): m.start() + 12000]
    facts: List[str] = []
    for line in re.split(r"\n\s*\|", block):
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        key = re.sub(r"\s+", "_", k.strip().lower())
        if key not in _INFOBOX_KEYS and key.replace("_", " ") not in _INFOBOX_KEYS:
            continue
        val = _clean_wikitext(v)
        if val and len(val) < 400:
            facts.append(f"{key.replace('_', ' ')}: {val}")
    return "; ".join(facts)[:_MAX_INFOBOX]


# ---- live fetch --------------------------------------------------------------
def _http_json(lang: str, params: dict) -> Optional[dict]:
    try:
        from venue_resolver import _request_with_backoff, _USER_AGENT
        r = _request_with_backoff(
            f"https://{lang}.wikipedia.org/w/api.php", params=params,
            headers={"User-Agent": _USER_AGENT}, timeout=12,
            host_for_cold=f"{lang}.wikipedia.org", label="LOCAL-872B wiki")
        if r is None or getattr(r, "status_code", 0) != 200:
            return None
        return r.json()
    except Exception:
        return None


def _pages_from(data):
    pages = ((data or {}).get("query") or {}).get("pages") or []
    pages = sorted((p for p in pages if isinstance(p, dict)), key=lambda p: p.get("index", 99))
    return [{
        "title": p.get("title", ""), "lead": p.get("extract", "") or "",
        "wikitext": (((p.get("revisions") or [{}])[0].get("slots") or {})
                     .get("main") or {}).get("content", "") or "",
        "langlinks": [l.get("title", "") for l in (p.get("langlinks") or [])],
    } for p in pages if not p.get("missing")]


_CONTENT = {"prop": "extracts|revisions", "exintro": "1", "explaintext": "1",
            "exlimit": "3", "rvprop": "content", "rvslots": "main", "rvsection": "0"}


def _default_fetch(name: str, lang: str) -> Optional[Dict]:
    """Search hits for ``name`` on <lang>.wikipedia.org -> lead extract + section-0
    wikitext (infobox).  For a non-English language the English article's
    interlanguage link is followed first (a vi title rarely string-matches the English
    stop name); that page is 'trusted'."""
    base = {"action": "query", "format": "json", "formatversion": "2"}
    if lang != "en":
        d = _http_json("en", dict(base, generator="search", gsrsearch=name, gsrlimit="3",
                                  prop="langlinks", lllang=lang, lllimit="10"))
        if d is None:
            return None
        for p in _pages_from(d):
            if _name_ok(name, p["title"]) and p["langlinks"]:
                got = _pages_from(_http_json(lang, dict(base, titles=p["langlinks"][0], **_CONTENT)))
                if got:
                    return {"pages": got, "trusted": True}
    data = _http_json(lang, dict(base, generator="search", gsrsearch=name, gsrlimit="3",
                                 **_CONTENT))
    if data is None:
        return None
    return {"pages": _pages_from(data)}


def _name_ok(stop: str, page_title: str) -> bool:
    try:
        from landmark_second_authority import name_matches
        return bool(name_matches(stop, page_title))
    except Exception:
        return False


def _lead_names(name: str, lead: str) -> bool:
    """The article's own lead gives the stop's name as an alias ("also the Municipal
    Theatre ... Saigon Opera House") -- the lead is the first 400 chars only."""
    try:
        from landmark_second_authority import _fold
    except Exception:
        return False
    n = _fold(name)
    return len(n) >= 8 and n in _fold((lead or "")[:400])


def _pick(name: str, raw: Optional[Dict]) -> Optional[Dict[str, str]]:
    for p in (raw or {}).get("pages") or []:
        if (raw or {}).get("trusted") or _name_ok(name, p.get("title", "")) \
                or _lead_names(name, p.get("lead", "")):
            return {"title": p["title"], "lead": (p.get("lead") or "")[:_MAX_LEAD],
                    "infobox": parse_infobox(p.get("wikitext", ""))}
    return None


# ---- cache (venue-cache DB, like landmark_coord_cache) -------------------------
_TABLE_OK = False


def _key(name: str, lang: str) -> str:
    return hashlib.sha1(f"{name.strip().lower()}|{lang}".encode("utf-8")).hexdigest()


def _conn():
    try:
        from venue_resolver import _get_db_connection
        return _get_db_connection()
    except Exception:
        return None


def _ensure(conn) -> bool:
    global _TABLE_OK
    if _TABLE_OK:
        return True
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS landmark_wiki_cache (
                cache_key TEXT PRIMARY KEY, name TEXT NOT NULL, language VARCHAR(10),
                payload TEXT, found BOOLEAN NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL)""")
        try:
            conn.commit()
        except Exception:
            pass
        _TABLE_OK = True
    except Exception:
        return False
    return True


def _cache_get(name: str, lang: str):
    """(found, article|None) for a live row, else None."""
    conn = _conn()
    if not conn:
        return None
    try:
        if not _ensure(conn):
            return None
        with conn.cursor() as cur:
            cur.execute("SELECT payload, found FROM landmark_wiki_cache "
                        "WHERE cache_key = %s AND expires_at > NOW()", (_key(name, lang),))
            row = cur.fetchone()
        if not row:
            return None
        return (True, json.loads(row[0])) if row[1] else (False, None)
    except Exception:
        return None


def _cache_put(name: str, lang: str, art: Optional[Dict[str, str]]) -> None:
    conn = _conn()
    if not conn:
        return
    from datetime import datetime, timedelta
    ttl = CACHE_TTL_DAYS if art else CACHE_NEG_TTL_DAYS
    try:
        if not _ensure(conn):
            return
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO landmark_wiki_cache
                (cache_key, name, language, payload, found, expires_at)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (cache_key) DO UPDATE SET payload = EXCLUDED.payload,
                found = EXCLUDED.found, created_at = CURRENT_TIMESTAMP,
                expires_at = EXCLUDED.expires_at""",
                        (_key(name, lang), name, lang, json.dumps(art) if art else None,
                         bool(art), datetime.utcnow() + timedelta(days=ttl)))
        try:
            conn.commit()
        except Exception:
            pass
    except Exception:
        pass


def fetch_article(name: str, lang: str = "en", fetch_fn: Optional[Callable] = None,
                  use_cache: bool = True) -> Optional[Dict[str, str]]:
    """The name-matched Wikipedia article for a stop, or None.  Cached (hit and miss)
    when the live fetcher is used."""
    nm = (name or "").strip()
    if not nm:
        return None
    live = fetch_fn is None
    if use_cache and live:
        c = _cache_get(nm, lang)
        if c is not None:
            return c[1]
    try:
        raw = (fetch_fn or _default_fetch)(nm, lang)
    except Exception:
        raw = None
    art = _pick(nm, raw)
    # only cache a real answer: a transport failure (raw None) must be retried
    if use_cache and live and raw is not None:
        _cache_put(nm, lang, art)
    return art


def evidence_for(name: str, location: str = "", langs: Optional[Sequence[str]] = None,
                 fetch_fn: Optional[Callable] = None, use_cache: bool = True,
                 extra_names: Sequence[str] = ()) -> List[str]:
    """Evidence strings for the claim gate: per language, '<title>. <lead> Infobox: ...'.
    ``extra_names`` are alternative names to try when the stop's own title finds none
    (the user's wording, the Places name)."""
    out: List[str] = []
    for lang in (langs or local_languages(location)):
        art = None
        for nm in [name] + [x for x in extra_names if x and x != name]:
            art = fetch_article(nm, lang, fetch_fn=fetch_fn, use_cache=use_cache)
            if art:
                break
        if art:
            txt = f"{art['title']} - Wikipedia ({lang}). {art['lead']}"
            if art.get("infobox"):
                txt += f"\nInfobox: {art['infobox']}"
            out.append(txt)
    return out


# ---- LOCAL-872C: the evidence feeds the NARRATOR, and is the authority ---------
# Wave 35 (gen 00037-k2h): the Opera House said only "French architects" although its
# Wikipedia evidence (Olivier, Guichard, Ferret; opened 1900) was fetched, because the
# evidence fed the GATE only: the narrator wrote from memory and the gate could only
# subtract.  Independence Palace shipped "built in 1885" (evidence: 1962-1966, architect
# Ngo Viet Thu).  These helpers (a) memoise the fetch so narrator and gate share ONE
# lookup, (b) render the evidence as the narrator's primary source, (c) extract the
# AUTHORITY facts (built years, architects) the gate uses to tell a claim that is merely
# unsourced from one that CONTRADICTS the evidence, (d) compose the evidence-based
# short form used instead of an empty stop.
import unicodedata as _ud

_MEMO: Dict[tuple, List[str]] = {}
_HEAD_RE = re.compile(r"^(?P<title>.*?) - Wikipedia \((?P<lang>[A-Za-z\-]+)\)\.\s*(?P<rest>.*)$", re.S)
_BUILT_KEYS = ("built", "construction", "construction start", "construction end", "completed",
               "completion date", "opened", "opening", "opening date", "open", "inaugurated",
               "years built", "year built", "yearbuilt", "year completed", "start date",
               "end date", "khởi công", "hoàn thành", "xây dựng", "khánh thành",
               "ngày khởi công", "ngày hoàn thành", "ngày khánh thành", "năm xây dựng")
_DATE_KEYS = _BUILT_KEYS + ("established", "founded", "dedicated", "consecrated", "thành lập")
_ARCH_KEYS = ("architect", "architects", "designer", "kiến trúc sư", "thiết kế")
_BUILT_CUE_RE = re.compile(
    r"(?i)\b(built|construct\w*|completed|finished|opened|inaugurat\w+|erected|"
    r"groundbreaking|ground was broken|foundation stone|began)\b")
_YEAR_RE2 = re.compile(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})(?!\d)")


def _fold2(s: str) -> str:
    s = _ud.normalize("NFKD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if not _ud.combining(c)).lower()


def cached_evidence(name: str, location: str = "", aliases: Sequence[str] = ()) -> List[str]:
    """``evidence_for`` memoised per process (the DB cache sits underneath), so the
    narrator prompt and the claim gate read ONE lookup."""
    key = (name or "", location or "", tuple(aliases or ()))
    if key not in _MEMO:
        try:
            _MEMO[key] = list(evidence_for(name, location, None, None, True, list(aliases or ())) or [])
        except Exception:
            _MEMO[key] = []
    return list(_MEMO[key])


def split_item(item: str) -> Dict[str, str]:
    m = _HEAD_RE.match(item or "")
    title, lang, rest = (m.group("title"), m.group("lang"), m.group("rest")) if m else ("", "", item or "")
    lead, _, box = rest.partition("\nInfobox:")
    return {"title": title.strip(), "lang": lang, "lead": lead.strip(), "infobox": box.strip()}


def _infobox_map(box: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in re.split(r";\s+(?=[^;:]{2,40}:\s)", box or ""):
        k, _, v = part.partition(":")
        if k.strip() and v.strip():
            out.setdefault(k.strip().lower(), v.strip())
    return out


def _years_in(text: str) -> set:
    ys: set = set()
    for m in re.finditer(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})\s*(?:-|–|—|to|and)\s*(1[0-9]{3}|20[0-9]{2})(?!\d)", text):
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b and b - a <= 60:
            ys.update(str(y) for y in range(a, b + 1))
    ys.update(_YEAR_RE2.findall(text))
    return ys


def _lead_sentences(lead: str) -> List[str]:
    lead = re.sub(r"\s*\([^)]{0,200}\)", "", lead or "")
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỹ\"“])", lead) if len(s.strip()) > 20]


def authority(items: Sequence[str]) -> Dict:
    """What the Wikipedia evidence itself says about construction and design.
    {'years': set[str], 'built_value': str, 'architects': [str], 'architect_value': str,
     'built_sentence': str, 'architect_sentence': str}.  Empty values when it is silent."""
    years: set = set()
    built_value = arch_value = built_sentence = arch_sentence = ""
    architects: List[str] = []
    date_facts: List[str] = []
    dated: List[tuple] = []
    for it in items or []:
        p = split_item(it)
        box = _infobox_map(p["infobox"])
        for k, v in box.items():
            kk = k.replace("_", " ")
            if kk in _DATE_KEYS:
                years |= _years_in(v)
                date_facts.append(f"{kk}: {v}")
                _ys = _YEAR_RE2.findall(v)
                if _ys:
                    _kind = ("established" if kk in ("established", "thành lập") else
                             "founded" if kk == "founded" else
                             "begun" if kk in ("construction start", "start date", "khởi công", "ngày khởi công") else
                             "opened" if kk in ("opened", "opening", "opening date", "open", "inaugurated", "khánh thành", "ngày khánh thành") else
                             "completed" if kk in ("completed", "completion date", "year completed", "end date", "construction end", "hoàn thành", "ngày hoàn thành") else
                             "built")
                    if (_kind, _ys[0]) not in dated:
                        dated.append((_kind, _ys[0]))
                    if _kind in ("built",) and len(_ys) > 1 and (_kind, _ys[-1]) not in dated:
                        dated.append(("completed", _ys[-1]))
                if kk in _BUILT_KEYS:
                    built_value = built_value or v
            elif kk in _ARCH_KEYS:
                v2 = re.sub(r"\s*\([^)]*\)", "", v)
                arch_value = arch_value or v2
                for nm in re.split(r"\s*(?:,|;|/|&|\band\b|\bvà\b)\s*", v2):
                    nm = nm.strip(" .")
                    if len(nm) >= 4 and nm not in architects:
                        architects.append(nm)
        for s in _lead_sentences(p["lead"]):
            if _BUILT_CUE_RE.search(s) and _years_in(s):
                years |= _years_in(s)
                built_sentence = built_sentence or s
            if re.search(r"(?i)\b(designed by|architects?|plans? (?:by|of))\b", s) and not arch_sentence:
                arch_sentence = s
    rng = None
    for src in (built_value, built_sentence):
        m = re.search(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})\s*(?:-|–|—|to|and)\s*(1[0-9]{3}|20[0-9]{2})(?!\d)", src or "")
        if m and 2 <= int(m.group(2)) - int(m.group(1)) <= 60:
            rng = (m.group(1), m.group(2))
            break
    if not built_value and date_facts:
        built_value = date_facts[0].partition(": ")[2]
    return {"dated": dated, "date_facts": date_facts, "range": rng, "years": years, "built_value": built_value, "architects": architects,
            "architect_value": arch_value, "built_sentence": built_sentence,
            "architect_sentence": arch_sentence}


def narrator_block(name: str, items: Sequence[str]) -> str:
    """The stop's Wikipedia lead + infobox as the narrator's PRIMARY source."""
    items = [i for i in (items or []) if i and i.strip()]
    if not items:
        return ""
    en = [i for i in items if "Wikipedia (en)" in i[:200]]
    pick = (en + [i for i in items if i not in en])[:2]
    body = "\n\n".join(i[:3200] for i in pick)
    au = authority(items)
    key = []
    if au["date_facts"]:
        key.append("dates: " + ", ".join(dict.fromkeys(au["date_facts"])))
    elif au["built_value"]:
        key.append(f"built/opened: {au['built_value']}")
    if au["architect_value"]:
        key.append(f"architect(s): {au['architect_value']}")
    keyline = (f"KEY FACTS YOU MUST STATE in the first two paragraphs (exact wording of the years "
               f"and names; say what each date marks, e.g. established / completed / opened): {'; '.join(key)}.\n") if key else ""
    return (
        f"\nPRIMARY SOURCE FOR \"{name}\" (Wikipedia, fetched for this stop; established fact):\n"
        f"{body}\n{keyline}"
        "INSTRUCTIONS FOR THIS SOURCE: State its construction / opening dates, its architect(s) "
        "or designer(s) BY NAME, its style and its capacity, as plain statements, and attribute "
        "them plainly (\"it was designed by ...\", \"according to Wikipedia, ...\"). Use the dates "
        "and names EXACTLY as written there. NEVER put a different year or a different architect "
        "from memory. Add NO built date, architect, performer, production or event that this "
        "source or the other reference material does not give. This block overrides any earlier "
        "note saying no sourced history is available for this stop.\n")


def short_form(name: str, items: Sequence[str]) -> str:
    """2-4 sentences from the lead / infobox, for a stop whose every sentence was
    dropped.  '' when the evidence is empty."""
    items = [i for i in (items or []) if i and i.strip()]
    if not items:
        return ""
    en = [i for i in items if "Wikipedia (en)" in i[:200]]
    p = split_item((en or items)[0])
    sents = _lead_sentences(p["lead"])
    chosen: List[str] = sents[:1]
    for s in sents[1:]:
        if len(chosen) >= 3:
            break
        if _years_in(s) or re.search(r"(?i)\b(designed|architect|style|capacity|seats?|built)\b", s):
            chosen.append(s)
    au = authority(items)
    text = " ".join(chosen)
    extra = []
    if au["architect_value"] and _fold2(au["architect_value"].split(",")[0].split()[-1] if au["architect_value"].split() else "") not in _fold2(text):
        extra.append(f"According to Wikipedia, its architect was {au['architect_value']}.")
    if au["built_value"] and not (au["years"] & _years_in(text)):
        extra.append(f"According to Wikipedia, it was built {au['built_value']}.")
    out = chosen + extra
    out = [s[:400].rstrip() for s in out][:4]
    out = [s if s[-1] in ".!?" else s + "." for s in out if s]
    return " ".join(out)
