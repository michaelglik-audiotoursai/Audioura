#!/usr/bin/env python3
"""thin_stop_search.py — LOCAL-873 / D766: a THIN stop escalates to a real web
search + page fetch before the narrator ever sees it.

Michael (2026-11-06): "we rely on Wikipedia way too much instead or in addition
to Serper. When stop comes up small we should always try to find other sources. A
simple search on Google with 'what do you know about bạch đằng pier in hcmc
vietnam' comes up full of interesting details. What prevented us doing so in the
first place?"

WHAT PREVENTED IT (the Bạch Đằng Pier trace, answered in SUBMISSION_LOCAL-873.md):
  * the user-stop retrieval ran ONE Serper query (D759 cost cap) and kept only
    SNIPPETS — no page was ever fetched;
  * ``user_stop_verify._snippet_names_venue`` required the English kind word
    ("Pier") as a distinctive token, so "Bach Dang Wharf" / "Bến Bạch Đằng" /
    "Bach Dang Quay" were all rejected;
  * worse, its fold leaves the Vietnamese letter "đ" intact (NFKD does not
    decompose đ — it is a distinct letter, not a combining mark), so "Đằng" folds
    to "đang" and never matches "dang" in an English snippet — EVERY English
    snippet for a đ-name was rejected, even an exact "Bach Dang Pier";
  * the LOCAL-872 claim gate then dropped from the narration whatever little was
    written from memory.

THIS MODULE, for a stop with fewer than ``THIN_THRESHOLD`` sourced specifics:
  1. THIN DETECTION — count sourced specifics already gathered; <3 is thin
     (``[LOCAL-873] thin stop <name>: K specifics``).
  2. ESCALATION — up to ``MAX_QUERIES`` (4) Serper ORGANIC queries built from name
     variants (English / Vietnamese, with and without diacritics, kind-word
     synonyms pier/wharf/quay/bến, "+ history", and a natural question
     "what is <name> in <city>"). The local language, the local kind words, the
     gl/hl and the local alias come from ``local_language.escalate_local_language``
     (LOCAL-875).
  3. ACCEPT snippets by DISTINCTIVE-TOKEN match (đ folded to d), NOT by the exact
     English kind word — so "Bach Dang Wharf" is accepted for "Bạch Đằng Pier".
  4. FETCH the top 2-3 result PAGES (robots respected, <= 200 KB each, 6 s
     timeout — reusing the project's polite/cached/robots fetch helper), extract
     readable text, keep only passages that NAME the stop.
  5. EXTRACT — one cheap gpt-4.1-mini pass turns those passages into a FACT LIST,
     each fact carrying the source URL it came from.
  6. GEO-GATE — every new source (each fetched page) must pass the SAME pin-city
     check as LOCAL-878 Wikipedia evidence: a page that names a famous same-name
     place in another city and never names the tour's city is dropped, so a
     same-name place elsewhere can never feed a stop (how 547 narrated the Sydney
     Opera House).

The facts feed the NARRATOR and the LOCAL-872 claim-gate evidence.

COST CAP ≈ $0.01 per thin stop (``COST_CAP_USD``): up to 4 Serper queries
($0.004) + up to 3 page fetches (free) + one gpt-4.1-mini extraction
(~$0.002-0.004). Queries, pages and cost are logged and returned.

Everything is injectable (``serp_fn``, ``fetch_fn``, ``llm_fn``, ``escalate_fn``),
so the module unit-tests OFFLINE and makes NO network / paid call unless a real
backend is wired in. Pure helpers never raise.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata as _ud
from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "THIN_THRESHOLD", "MAX_QUERIES", "MAX_PAGES", "COST_CAP_USD", "GEO_GATE_KM",
    "count_specifics", "is_thin", "fold", "name_tokens", "snippet_names_stop",
    "name_variant_queries", "escalate_thin_stop", "Fact",
]

# ── tunables (env-overridable) ────────────────────────────────────────────────
THIN_THRESHOLD = int(os.environ.get("THIN_STOP_MIN_SPECIFICS", "3"))
MAX_QUERIES = int(os.environ.get("THIN_STOP_MAX_QUERIES", "4"))
MAX_PAGES = int(os.environ.get("THIN_STOP_MAX_PAGES", "3"))
COST_CAP_USD = float(os.environ.get("THIN_STOP_COST_CAP_USD", "0.01"))
GEO_GATE_KM = float(os.environ.get("THIN_STOP_GEO_GATE_KM",
                                   os.environ.get("LANDMARK_WIKI_GEO_GATE_KM", "2.0")))
PER_PAGE_BYTES = int(os.environ.get("THIN_STOP_PER_PAGE_BYTES", str(200 * 1024)))
FETCH_TIMEOUT_S = int(os.environ.get("THIN_STOP_FETCH_TIMEOUT_S", "6"))
EXTRACT_MODEL = os.environ.get("THIN_STOP_EXTRACT_MODEL", "gpt-4.1-mini")
PER_PAGE_CHARS = int(os.environ.get("THIN_STOP_PER_PAGE_CHARS", "2500"))


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Folding — unlike user_stop_narration._fold, this ALSO folds the Vietnamese
# letter đ/Đ to d (NFKD leaves đ intact because it is a distinct letter, not a
# combining mark; that is the exact bug that rejected every English snippet for
# "Bạch Đằng Pier"). Mirrors landmark_wikipedia_evidence._fold2.
# ═══════════════════════════════════════════════════════════════════════════
def fold(text) -> str:
    """Accent-fold a string to lowercase ASCII words, folding đ/Đ -> d first."""
    s = _ud.normalize("NFKD", str(text or "").replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if not _ud.combining(c))
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return " ".join(s.split())


# Generic / kind words that do NOT by themselves identify a venue. A superset of
# user_stop_verify._GENERIC_NAME_TOKENS plus the maritime kind words, so the
# distinctive tokens of "Bạch Đằng Pier" are {bach, dang} and "pier"/"wharf"/
# "quay" never count as the distinctive token that a snippet must carry.
_GENERIC_TOKENS = {
    "the", "a", "an", "and", "of", "at", "in", "on", "de", "du", "la", "le",
    "bar", "spa", "cafe", "restaurant", "club", "lounge", "shop", "store",
    "street", "city", "house", "pub", "venue", "studio", "salon", "market",
    "hotel", "hostel", "museum", "temple", "pagoda", "church", "palace",
    # maritime / waterfront kind words (en + common transliterations)
    "pier", "wharf", "quay", "quai", "boardwalk", "jetty", "harbour", "harbor",
    "dock", "docks", "esplanade", "waterfront", "promenade", "landing",
    "ferry", "terminal", "port", "marina", "riverside", "embankment",
    # vietnamese kind words (folded)
    "ben", "tau", "cau", "cang", "pho", "duong",
}


def name_tokens(name: str) -> List[str]:
    """Distinctive folded tokens of a stop name (>=2 chars, not generic/kind).
    "Bạch Đằng Pier" -> ['bach', 'dang']; the kind word is intentionally NOT a
    distinctive token, so a snippet that uses a SYNONYM kind word still matches."""
    out: List[str] = []
    for w in fold(name).split():
        if len(w) >= 2 and w not in _GENERIC_TOKENS:
            out.append(w)
    return out


def snippet_names_stop(name: str, title: str, snippet: str,
                       aliases: Sequence[str] = ()) -> bool:
    """True when a search result (title + snippet) is about THIS stop, judged by
    DISTINCTIVE-TOKEN match (đ folded), NOT by the exact English kind word.

    Accepts "Bach Dang Wharf", "Bến Bạch Đằng", "Bach Dang Quay" for the stop
    "Bạch Đằng Pier": all carry the distinctive tokens {bach, dang}. A name with
    no distinctive token at all (only generic/kind words, e.g. a bare "Pier")
    cannot be matched this way and returns False (the caller keeps the exact-name
    behaviour for such names)."""
    hay = fold(f"{title} {snippet}")
    if not hay:
        return False
    hay_tokens = set(hay.split())
    candidates = [name] + [a for a in aliases if a]
    for cand in candidates:
        full = fold(cand)
        if full and full in hay:
            return True
        toks = name_tokens(cand)
        if toks and all(t in hay_tokens for t in toks):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# 1. Thin detection
# ═══════════════════════════════════════════════════════════════════════════
_YEAR_RE = re.compile(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})(?!\d)")
_SPECIFIC_CUE = re.compile(
    r"(?i)\b(built|construct\w*|completed|opened|founded|established|designed|"
    r"architect|renovat\w*|named after|named for|length|metres?|meters?|"
    r"kilomet\w*|wide|high|tall|capacity|population|dynasty|century|war|battle|"
    r"river|bridge|statue|monument|trade|port|ferry|market|temple|emperor|king|"
    r"french|colonial|reunification)\b")


def count_specifics(facts: Sequence) -> int:
    """Count SOURCED specifics in a stop's gathered material. A "specific" is a
    fact string that carries a year OR a concrete cue word (built, architect,
    length, battle, river…). Generic boilerplate ("a lovely place to relax")
    does not count. Accepts strings or dicts with a 'text'/'fact' field.

    Deterministic — it is a property of the words, not the model."""
    n = 0
    seen = set()
    for f in facts or []:
        if isinstance(f, dict):
            text = str(f.get("text") or f.get("fact") or f.get("snippet") or "")
        else:
            text = str(f or "")
        text = text.strip()
        if len(text) < 15:
            continue
        key = fold(text)[:80]
        if key in seen:
            continue
        if _YEAR_RE.search(text) or _SPECIFIC_CUE.search(text):
            seen.add(key)
            n += 1
    return n


def is_thin(facts: Sequence, threshold: int = THIN_THRESHOLD) -> bool:
    """True when the stop has fewer than ``threshold`` sourced specifics."""
    return count_specifics(facts) < threshold


# ═══════════════════════════════════════════════════════════════════════════
# 2. Name-variant query generation
# ═══════════════════════════════════════════════════════════════════════════
def _strip_diacritics_keep_case(name: str) -> str:
    """ASCII form of a name, folding đ/Đ and stripping combining marks, but
    keeping word case/order ("Bạch Đằng Pier" -> "Bach Dang Pier")."""
    s = _ud.normalize("NFKD", str(name or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if not _ud.combining(c))


def name_variant_queries(name: str, city: str, *, local_name: str = "",
                         kind_words_en: Sequence[str] = (),
                         kind_words_local: Sequence[str] = (),
                         local_lang: str = "", max_queries: int = MAX_QUERIES,
                         topics: Sequence[str] = ()
                         ) -> List[str]:
    """Build up to ``max_queries`` distinct Serper ORGANIC queries from name
    variants: English + local, with and without diacritics, kind-word synonyms,
    "+ history", and a natural question "what is <name> in <city>".

    Deterministic and free (no network). The strongest, most specific queries
    come first so a tight ``max_queries`` still carries the best signals."""
    name = (name or "").strip()
    city = (city or "").strip()
    ascii_name = _strip_diacritics_keep_case(name).strip()
    queries: List[str] = []

    def _add(q: str) -> None:
        q = re.sub(r"\s+", " ", (q or "")).strip()
        if q and q not in queries:
            queries.append(q)

    # 1. the name (as given) + city
    _add(f"{name} {city}")
    # 2. the diacritic-stripped name + city (English search engines index both)
    if ascii_name and ascii_name.lower() != name.lower():
        _add(f"{ascii_name} {city}")
    # [LOCAL-894] The topics the REQUEST asked this stop to cover ("how dragon fruit is
    # grown", "the pilgrimage tradition"): searched by name + topic so the evidence
    # can support them. Generic; at most two, placed right after the plain name query.
    for _tp in list(topics or [])[:2]:
        _tp = re.sub(r"^(?:the|its)\s+", "", (_tp or "").split("\u2014")[-1].strip(), flags=re.I)
        if _tp:
            _add(f"{ascii_name or name} {_tp} {city}")
    # 3. the local-language alias + city
    if local_name and fold(local_name) != fold(name):
        _add(f"{local_name} {city}")
    # 4. natural question (Michael's example: "what is <name> in <city>")
    _add(f"what is {ascii_name or name} in {city}".strip())
    # 5. kind-word synonyms: build "<core> <synonym> <city>"
    base_ascii = ascii_name or name
    base_toks = base_ascii.split()
    distinctive = name_tokens(name)
    if distinctive:
        core = " ".join(w for w in base_toks
                        if fold(w) in distinctive) or base_ascii
        for kw in list(kind_words_en)[:3] + list(kind_words_local)[:2]:
            _add(f"{core} {kw} {city}")
    # 6. "+ history"
    if local_lang == "vi":
        _add(f"{local_name or name} lịch sử {city}".strip())
    _add(f"{ascii_name or name} {city} history")

    return queries[:max_queries]


# ═══════════════════════════════════════════════════════════════════════════
# Geo-gate helper (LOCAL-878 parity) — a fetched page must not describe a
# DIFFERENT city than the tour's.
# ═══════════════════════════════════════════════════════════════════════════
# Other-city words that, if a page names one PROMINENTLY and the tour's city is
# absent, mark the page as about a same-name place elsewhere (how 547 narrated
# the Sydney Opera House). Kept small and high-precision.
_FAMOUS_ELSEWHERE = {
    "sydney", "london", "paris", "new york", "chicago", "san francisco",
    "seattle", "brighton", "santa monica", "blackpool", "scheveningen",
}


def _page_city_conflict(text: str, title: str, city: str,
                        city_aliases: Sequence[str] = ()) -> bool:
    """True when a page's title/lead names a FAMOUS same-name location in another
    city AND does NOT name the tour's city (or any alias) — so it is dropped.
    Conservative: only fires on a known-elsewhere city word."""
    hay = fold(f"{title} . {text[:1200]}")
    if not hay:
        return False
    city_forms = {fold(city)} | {fold(a) for a in city_aliases if a}
    city_forms = {c for c in city_forms if len(c) >= 3}
    if any(c in hay for c in city_forms):
        return False  # the tour's city is named -> not a conflict
    for elsewhere in _FAMOUS_ELSEWHERE:
        if fold(elsewhere) in hay:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Passage selection — keep only sentences that NAME the stop
# ═══════════════════════════════════════════════════════════════════════════
def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9À-Ỹ\"“])", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def _passages_naming_stop(text: str, name: str, aliases: Sequence[str],
                          max_passages: int = 8) -> List[str]:
    """Sentences from a page that NAME the stop (distinctive-token match), kept
    verbatim, de-duplicated, length-bounded."""
    out: List[str] = []
    seen = set()
    for raw in re.split(r"\n+", text or ""):
        chunk = " ".join(raw.split())
        if not chunk:
            continue
        for s in _split_sentences(chunk):
            s = s.strip()
            if not (25 <= len(s) <= 400):
                continue
            if not snippet_names_stop(name, "", s, aliases=aliases):
                continue
            key = fold(s)[:100]
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
            if len(out) >= max_passages:
                return out
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 5. LLM fact extraction (one cheap pass; each fact carries its source URL)
# ═══════════════════════════════════════════════════════════════════════════
class Fact:
    """A single extracted fact and the source URL it came from."""

    __slots__ = ("text", "url", "passage")

    def __init__(self, text: str, url: str = "", passage: str = ""):
        self.text = (text or "").strip()
        self.url = (url or "").strip()
        # [LOCAL-906J] the SOURCE text the fact was read from (a page passage / the search snippet). ``text`` may be
        # the model's paraphrase; only ``passage`` is ever delivery evidence.
        self.passage = (passage or "").strip()

    def as_dict(self) -> Dict[str, str]:
        d = {"text": self.text, "url": self.url}
        if self.passage:
            d["passage"] = self.passage
        return d

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"Fact({self.text[:40]!r}, {self.url!r})"


_EXTRACT_SYSTEM = (
    "You extract FACTS about a specific place from web page passages. You are "
    "given a place name and numbered passages, each tagged with its source URL. "
    "Return ONLY facts that the passages state about THIS place — its history, "
    "construction, people, events, size, trade, what it is and what happens "
    "there. Do NOT add anything from your own memory. Each fact must be a single "
    "plain sentence and must carry the index of the passage it came from.\n"
    'Return ONLY JSON of the exact shape: '
    '{"facts":[{"text":"<one sentence>","from":<passage index int>}]}'
)


def _build_extract_user(name: str, city: str,
                        passages: List[Tuple[str, str]]) -> str:
    lines = [f'PLACE: "{name}"' + (f" in {city}" if city else ""), "",
             "PASSAGES (index. [source URL] text):"]
    for i, (url, text) in enumerate(passages):
        lines.append(f"  {i}. [{url}] {text}")
    lines.append("")
    lines.append("Extract the facts this place's passages state. JSON only.")
    return "\n".join(lines)


def _default_llm(system: str, user: str, model: str,
                 timeout: int = 40, max_tokens: int = 900
                 ) -> Tuple[Optional[dict], int, int]:
    """One gpt-4.1-mini JSON call. Returns (parsed|None, in_tokens, out_tokens).
    The project network meter bills the call. Never raises."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None, 0, 0
    try:
        import requests
    except Exception:
        return None, 0, 0
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            data=json.dumps({
                "model": model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": 0.0, "seed": 7, "max_tokens": int(max_tokens),
                "response_format": {"type": "json_object"},
            }),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None, 0, 0
        body = resp.json()
        usage = body.get("usage", {}) or {}
        content = body["choices"][0]["message"]["content"]
        return (json.loads(content),
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)))
    except Exception:
        return None, 0, 0


def _llm_cost(in_tok: int, out_tok: int, model: str) -> float:
    try:
        from cost_rates import llm_cost
        return float(llm_cost(in_tok, out_tok, model))
    except Exception:
        return round(in_tok / 1e6 * 0.40 + out_tok / 1e6 * 1.60, 6)


def _serper_cost(n_queries: int) -> float:
    try:
        from cost_rates import SERPER_COST_PER_QUERY as spq
    except Exception:
        spq = 0.001
    return round(n_queries * float(spq), 6)


# ═══════════════════════════════════════════════════════════════════════════
# The escalation entry point
# ═══════════════════════════════════════════════════════════════════════════
def escalate_thin_stop(
        name: str, scope: str, *, existing_facts: Sequence = (),
        poi: Optional[Dict] = None, pin: Optional[Tuple[float, float]] = None,
        city: str = "", aliases: Sequence[str] = (),
        places_type: str = "", wikidata_instance_of: str = "",
        threshold: int = THIN_THRESHOLD, max_queries: int = MAX_QUERIES,
        max_pages: int = MAX_PAGES, cost_cap: float = COST_CAP_USD,
        serp_fn: Optional[Callable] = None, fetch_fn: Optional[Callable] = None,
        llm_fn: Optional[Callable] = None, escalate_fn: Optional[Callable] = None,
        wiki_fetch_fn: Optional[Callable] = None, log: Optional[Callable] = None,
        use_cache: bool = True, topics: Sequence[str] = (),
        ) -> Dict:
    """Escalate a THIN stop to a real web search + page fetch, returning a bundle:

        {
          'escalated': bool,          # True when the stop was thin AND we searched
          'thin': bool,               # was the stop thin to begin with
          'specifics_before': int,
          'facts': [{'text','url'}],  # new sourced facts (narrator + 872 gate)
          'narrator_block': str,      # the facts rendered for the narrator prompt
          'evidence': [str],          # facts rendered for the 872 claim gate
          'queries': [str],
          'pages': [{'url','title'}], # pages actually fetched and kept
          'serper_queries': int, 'pages_fetched': int,
          'serper_cost_usd','llm_cost_usd','cost_usd': float,
          'local': {...},             # the local_language escalate bundle summary
        }

    All backends are injectable for offline tests; defaults use the project's
    metered Serper caller, the polite robots-respecting page fetcher, and a
    gpt-4.1-mini extraction. The COST CAP is enforced step by step: queries stop
    when the serper spend would exceed the cap, and the LLM extraction is skipped
    when it would push total cost over the cap. Never raises."""
    log = log or _log
    poi = poi or {}
    name = (name or "").strip()
    city = (city or _city_from_scope(scope)).strip()
    report: Dict = {
        "escalated": False, "thin": False, "specifics_before": 0,
        "facts": [], "narrator_block": "", "evidence": [],
        "queries": [], "pages": [], "serper_queries": 0, "pages_fetched": 0,
        "serper_cost_usd": 0.0, "llm_cost_usd": 0.0, "cost_usd": 0.0,
        "local": {},
    }

    # 1. thin detection
    before = count_specifics(existing_facts)
    report["specifics_before"] = before
    if before >= threshold:
        return report
    report["thin"] = True
    log(f"[LOCAL-873] thin stop {name!r}: {before} specifics")
    if not name:
        return report

    # 2. local-language escalation bundle (LOCAL-875): local language, kind words,
    #    gl/hl, local alias, geo-gated local Wikipedia edition.
    local: Dict = {}
    try:
        _esc = escalate_fn
        if _esc is None:
            import local_language as _ll
            _esc = _ll.escalate_local_language
        _kw = dict(places_type=places_type,
                   wikidata_instance_of=wikidata_instance_of,
                   country_code="", local_name=(aliases[0] if aliases else ""),
                   wiki_fetch_fn=wiki_fetch_fn, use_cache=use_cache)
        try:
            local = _esc(name, scope, pin=pin, **_kw) or {}   # [LOCAL-887] geo-gate
        except TypeError:
            local = _esc(name, scope, **_kw) or {}
    except Exception as e:
        log(f"[LOCAL-873] local-language escalation skipped ({name!r}): {e}")
        local = {}
    # [LOCAL-887] the geo/name-gated LOCAL-language article(s), rendered as evidence
    # items, for the caller to use as the narrator's AND the gate's evidence when no
    # English article was accepted.
    report["local_wikipedia_items"] = []
    try:
        import landmark_wikipedia_evidence as _lwe887
        for _lg, _art in (local.get("wikipedia") or {}).items():
            if _lg != "en" and _art:
                report["local_wikipedia_items"].append(_lwe887.format_item(_art, _lg))
    except Exception:
        pass
    report["local"] = {k: local.get(k) for k in
                       ("dominant", "country_code", "local_alias", "serper")
                       if k in local}
    dominant = local.get("dominant", "") or ""
    local_alias = local.get("local_alias", "") or (aliases[0] if aliases else "")
    all_aliases = list(dict.fromkeys(
        [a for a in list(aliases) + [local_alias] if a and fold(a) != fold(name)]))
    kw_en, kw_local, subtype = _kind_words_for(local, places_type,
                                                wikidata_instance_of)

    # 3. build the name-variant queries
    queries = name_variant_queries(
        name, city, local_name=local_alias, kind_words_en=kw_en,
        kind_words_local=kw_local, local_lang=dominant, max_queries=max_queries,
        topics=topics)
    report["queries"] = queries
    if not queries:
        return report

    serp_fn = serp_fn or _default_serp
    fetch_fn = fetch_fn or _default_fetch

    # 4. run the queries (respect the cost cap), collect venue-naming results
    city_aliases = _city_alias_forms(city)
    ranked: List[Dict] = []
    seen_urls = set()
    for q in queries:
        if _serper_cost(report["serper_queries"] + 1) > cost_cap:
            log(f"[LOCAL-873] query budget reached for {name!r} "
                f"(cap ${cost_cap:.3f}); stopping at {report['serper_queries']} queries")
            break
        report["escalated"] = True
        report["serper_queries"] += 1
        try:
            results = serp_fn(q) or []
        except Exception as e:
            log(f"[LOCAL-873] serper query failed {q!r}: {e}")
            results = []
        for r in results:
            if not isinstance(r, dict):
                continue
            url = (r.get("url") or r.get("link") or "").strip()
            title = r.get("title", "") or ""
            snippet = r.get("snippet", "") or ""
            if not url or url in seen_urls:
                continue
            if not snippet_names_stop(name, title, snippet, aliases=all_aliases):
                continue
            seen_urls.add(url)
            ranked.append({"url": url, "title": title, "snippet": snippet})
    report["serper_cost_usd"] = _serper_cost(report["serper_queries"])
    log(f"[LOCAL-873] escalate {name!r}: {report['serper_queries']} queries -> "
        f"{len(ranked)} venue-naming result(s)")

    # 5. fetch the top pages (robots / <=200KB / 6s), geo-gate, keep passages
    passages: List[Tuple[str, str]] = []   # (url, passage text)
    snippet_facts: List[Fact] = []
    for r in ranked:
        if report["pages_fetched"] >= max_pages:
            break
        url = r["url"]
        try:
            text = fetch_fn(url) or ""
        except Exception as e:
            log(f"[LOCAL-873] page fetch failed {url!r}: {e}")
            text = ""
        if not text or len(text) < 120:
            # fetch failed or too thin — fall back to the snippet (still sourced)
            if r["snippet"]:
                snippet_facts.append(Fact(r["snippet"], url, r["snippet"]))
            continue
        # GEO-GATE: drop a page that names a famous same-name place elsewhere
        # and never names the tour's city (how 547 got Sydney).
        if _page_city_conflict(text, r["title"], city, city_aliases):
            log(f"[LOCAL-873] geo-gate dropped page (other city) {url!r}")
            continue
        report["pages_fetched"] += 1
        report["pages"].append({"url": url, "title": r["title"]})
        kept = _passages_naming_stop(text[:PER_PAGE_CHARS * 4], name, all_aliases)
        for p in kept[:6]:
            passages.append((url, p))
        if not kept and r["snippet"]:
            snippet_facts.append(Fact(r["snippet"], url, r["snippet"]))

    # 6. one cheap LLM extraction pass over the kept passages (respect the cap)
    facts: List[Fact] = list(snippet_facts)
    if passages:
        projected = report["serper_cost_usd"] + 0.004  # conservative LLM estimate
        if projected <= cost_cap:
            llm = llm_fn or _default_llm
            user = _build_extract_user(name, city, passages)
            try:
                parsed, in_tok, out_tok = llm(_EXTRACT_SYSTEM, user, EXTRACT_MODEL)
            except Exception as e:
                log(f"[LOCAL-873] fact extraction failed {name!r}: {e}")
                parsed, in_tok, out_tok = None, 0, 0
            report["llm_cost_usd"] = _llm_cost(in_tok, out_tok, EXTRACT_MODEL)
            for item in ((parsed or {}).get("facts") or []):
                txt = str(item.get("text", "")).strip()
                if not txt:
                    continue
                try:
                    fi = int(item.get("from", -1))
                except Exception:
                    fi = -1
                src = passages[fi][0] if 0 <= fi < len(passages) else ""
                src_passage = passages[fi][1] if 0 <= fi < len(passages) else ""
                # only keep a fact that still names the stop or carries a specific
                if snippet_names_stop(name, "", txt, aliases=all_aliases) or \
                        _YEAR_RE.search(txt) or _SPECIFIC_CUE.search(txt):
                    facts.append(Fact(txt, src, src_passage))
        else:
            log(f"[LOCAL-873] LLM extraction skipped for {name!r} "
                f"(cost cap ${cost_cap:.3f})")
            for url, p in passages[:6]:
                facts.append(Fact(p, url, p))

    facts = _dedupe_facts(facts)
    report["facts"] = [f.as_dict() for f in facts]
    report["cost_usd"] = round(report["serper_cost_usd"] + report["llm_cost_usd"], 6)
    report["narrator_block"] = _render_narrator_block(name, facts)
    report["evidence"] = _render_evidence(name, facts)

    log(f"[LOCAL-873] escalate {name!r} done: {len(facts)} fact(s) from "
        f"{report['pages_fetched']} page(s); cost ${report['cost_usd']:.4f} "
        f"(serper ${report['serper_cost_usd']:.4f} + llm ${report['llm_cost_usd']:.4f})")
    return report


# ═══════════════════════════════════════════════════════════════════════════
# rendering + small helpers
# ═══════════════════════════════════════════════════════════════════════════
def _dedupe_facts(facts: List[Fact]) -> List[Fact]:
    out: List[Fact] = []
    seen = set()
    for f in facts:
        if not f.text:
            continue
        key = fold(f.text)[:100]
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _render_narrator_block(name: str, facts: List[Fact]) -> str:
    """Render the sourced facts as the narrator's reference material. Each line
    carries its source URL so the narrator attributes, and the 872 gate matches."""
    if not facts:
        return ""
    lines = [f"\nWEB-SOURCED FACTS FOR \"{name}\" (fetched for this thin stop, "
             f"LOCAL-873; use these, attribute plainly, add nothing from memory):"]
    for f in facts[:12]:
        src = f" [source: {f.url}]" if f.url else ""
        lines.append(f"  - {f.text}{src}")
    lines.append("INSTRUCTIONS: Build the stop from these facts. State the "
                 "specifics (dates, people, purpose, size) as plain statements. "
                 "Do NOT invent a date, person or event these facts do not give.\n")
    return "\n".join(lines)


def _render_evidence(name: str, facts: List[Fact]) -> List[str]:
    """Render the facts as LOCAL-872 claim-gate evidence strings (one per fact,
    URL appended), the same plain shape the gate already consumes."""
    out: List[str] = []
    for f in facts[:12]:
        if not f.text:
            continue
        txt = f.text
        if f.url:
            txt = f"{txt} (source: {f.url})"
        out.append(txt)
    return out


def _kind_words_for(local: Dict, places_type: str,
                    wikidata_instance_of: str) -> Tuple[List[str], List[str], str]:
    """English + local kind-word synonyms and the subtype for the stop, from the
    local_language bundle (its classification) with a place_kinds fallback."""
    subtype = ""
    try:
        subtype = (local.get("classification") or {}).get("subtype", "") or ""
    except Exception:
        subtype = ""
    kw_en: List[str] = []
    kw_local: List[str] = []
    try:
        import place_kinds as _pk
        if not subtype:
            subtype = _pk.classify(
                "", type_label=places_type or "",
                wikidata_instance_of=wikidata_instance_of or "").get("subtype", "")
        for grp, sub, langs in _pk._T:
            if sub == subtype:
                kw_en = list(langs.get("en") or [])
                dom = (local.get("dominant") or "")
                if dom and dom != "en":
                    kw_local = list(langs.get(dom) or langs.get("vi") or [])
                break
    except Exception:
        pass
    return kw_en, kw_local, subtype


def _city_from_scope(scope: str) -> str:
    """Best-effort city/locality from a tour scope string. Reuses the project's
    helper when available; else the last comma-part that is not a bare country."""
    try:
        from text_polish import city_from_scope
        c = city_from_scope(scope or "")
        if c:
            return c
    except Exception:
        pass
    parts = [p.strip() for p in (scope or "").split(",") if p.strip()]
    return parts[-1] if parts else (scope or "").strip()


_CITY_ALIAS_TABLE = (
    ({"ho chi minh city", "ho chi minh", "hcmc", "saigon", "sai gon"},
     {"saigon", "ho chi minh", "hcmc"}),
    ({"hanoi", "ha noi"}, {"hanoi", "ha noi"}),
)


def _city_alias_forms(city: str) -> List[str]:
    c = fold(city)
    forms = {c} if c else set()
    for keys, aliases in _CITY_ALIAS_TABLE:
        if c in keys or any(k in c for k in keys):
            forms |= {fold(a) for a in aliases}
    return [f for f in forms if len(f) >= 3]


# ── default metered backends (lazy imports; offline-safe) ─────────────────────
def _default_serp(query: str) -> List[Dict]:
    """The project's metered Serper organic caller ($0.001/query). [] on failure."""
    try:
        from work_story_searcher import _serp_search
    except Exception:
        return []
    try:
        results, _lat = _serp_search(query)
        return results or []
    except Exception:
        return []


def _default_fetch(url: str) -> str:
    """Fetch a page's readable text through the project's polite, cached,
    robots-respecting helper (<=200 KB enforced here, 6 s per the helper). ''
    on any failure. Reuses serper_research._fetch (exhibition_checklist._fetch_page
    underneath) so robots.txt and per-host backoff are honoured."""
    try:
        from serper_research import _fetch as _sr_fetch
    except Exception:
        _sr_fetch = None
    if _sr_fetch is not None:
        try:
            text = _sr_fetch(url) or ""
            return text[:PER_PAGE_BYTES]
        except Exception:
            return ""
    # last-resort direct fetch with the byte cap + timeout (robots still checked)
    try:
        from user_stop_enrichment import _robots_allows
        if not _robots_allows(url, lambda u: _raw_get(u)):
            return ""
        raw = _raw_get(url)
        if not raw:
            return ""
        from robust_text_extractor import extract_clean_text
        return (extract_clean_text(raw) or "")[:PER_PAGE_BYTES]
    except Exception:
        return ""


def _raw_get(url: str) -> str:
    try:
        import requests
        r = requests.get(url, headers={"User-Agent": "AudiouraTourBot/1.0"},
                         timeout=FETCH_TIMEOUT_S, stream=True)
        if r.status_code != 200:
            return ""
        chunks, total = [], 0
        for chunk in r.iter_content(8192):
            chunks.append(chunk)
            total += len(chunk)
            if total >= PER_PAGE_BYTES:
                break
        return b"".join(chunks).decode("utf-8", errors="replace")
    except Exception:
        return ""
