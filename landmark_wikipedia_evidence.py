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
