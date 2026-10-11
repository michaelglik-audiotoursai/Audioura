"""serper_plus_research.py — LOCAL-674.

A research backend for WALKING tours that answers the SAME per-stop story-lead
question `story_leads.gemini_with_sources(grounded=True)` answers — at Serper
prices, not Gemini's ($0.053 per grounded request, 81% of the bill; price card
r5). It is the "serper_plus" arm of the WALKING_RESEARCH flag.

WHY A SECOND SERPER BACKEND. The LOCAL-648 `serper_research` backend was built
for MUSEUM OBJECTS: it keys its queries on a work's canonical_title / artist /
credit_line, and museums carry a rich Wikidata catalogue + a venue corpus. On
WALKING stops — a building, a square, a monument — that context is thin, the
queries fall back to generic content words, and the top Serper results are
SEO/listing pages (tripadvisor, "15 best things to do"). The measured result
(COST_TIME_RESULTS 2026-10-10): walking stops fell to filler ("$26.5 million …
1969") and repeated stories; Serper 5.0 vs Gemini 7.5 Kiro on Boston.

WHAT serper_plus DOES DIFFERENTLY, in order (cheapest, highest-signal first):

  1. WIKIPEDIA FIRST (free).  Resolve the stop to its Wikidata item, read the
     FULL English article extract AND the local-language article (via the item's
     sitelinks) through the Wikipedia action API. A place's own Wikipedia article
     is dense with dated, named, consequential history — exactly what a walking
     stop's story needs — and it costs nothing.
  2. BETTER WEB PAGES.  Serper top 5 → fetch the best 3, SKIPPING SEO/listing/UGC
     domains (the exhibition_checklist blocklist) and PREFERRING the stop's own
     official site. One extra Serper query (reused helper, $0.001 each).
  3. NEWS PASS, only where current affairs apply.  A Serper news query is issued
     ONLY when the question/context mentions recent/ongoing matters (LOCAL-655),
     so a historic building does not pay for news it will not use.
  4. ONE EXTRACTOR over everything gathered.  gpt-4.1-mini by default; gpt-4.1
     when SERPER_PLUS_EXTRACTOR=gpt-4.1 (set when the measurements show mini
     misses stories). Constrained to the gathered text — no parametric memory.

Returns the EXACT shape gemini_with_sources returns —
`{text, sources:[{domain,url}], supports:[{text,sources:[{domain,url}]}],
queries:[str], error:str}` — so it is a drop-in anywhere a grounded
answer-with-sources is consumed.

Every PAID call it makes (Serper queries, the OpenAI completion) goes out through
the project network meter (`_meter/paid_api_meter.py`); Wikipedia/Wikidata are
free. NOTHING here runs unless the caller selects it (WALKING_RESEARCH=serper_plus,
routed in story_leads.research_with_sources). The default never reaches this
module, so default behaviour is byte-for-byte unchanged.
"""
import json
import os
import re
import sys
import time
from typing import Callable, Dict, List, Optional, Tuple

# ── LOCAL-651: [TIMING-SUB] decorator (safe no-op if phase_timer unavailable).
try:
    from phase_timer import timed_step as _sub_timed
except Exception:  # pragma: no cover
    def _sub_timed(_name):
        def _wrap(fn):
            return fn
        return _wrap

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Reuse the LOCAL-648 primitives: context parsing, gloss stripping, citation
# attribution, domain extraction. serper_plus is the walking-stop sibling of
# serper_research, not a rewrite of its machinery.
import serper_research as _sr  # noqa: E402


# ── tunables (env-overridable) ────────────────────────────────────────────────
EXTRACTOR_MODEL = os.environ.get('SERPER_PLUS_EXTRACTOR', 'gpt-4.1-mini')
MAX_WEB_QUERIES = int(os.environ.get('SERPER_PLUS_MAX_QUERIES', '2'))
MAX_WEB_PAGES = int(os.environ.get('SERPER_PLUS_MAX_PAGES', '3'))
PER_PAGE_CHARS = int(os.environ.get('SERPER_PLUS_PER_PAGE_CHARS', '3000'))
WIKI_CHARS = int(os.environ.get('SERPER_PLUS_WIKI_CHARS', '6000'))
WIKI_LOCAL_CHARS = int(os.environ.get('SERPER_PLUS_WIKI_LOCAL_CHARS', '3500'))
ANSWER_MAX_TOKENS = int(os.environ.get('SERPER_PLUS_MAX_TOKENS', '750'))
USER_AGENT = os.environ.get('WIKI_USER_AGENT', 'Audioura/2.2 (walking research)')

# Current-affairs trigger words (LOCAL-655): a news pass fires ONLY when the
# question or context signals recent/ongoing matters. A purely historic stop
# does not pay for a news query it will not use.
_CURRENT_AFFAIRS = re.compile(
    r'\b(recent|recently|today|current|ongoing|renovation|renovated|'
    r'reopen|reopening|closed|closure|restoration|protest|controvers|'
    r'20(?:2[4-9]|3\d)|this year|now open|under construction|new exhibit)\b',
    re.IGNORECASE)


def _blank() -> Dict:
    return {'text': '', 'sources': [], 'supports': [], 'queries': [], 'error': ''}


# ── 1. Wikidata QID + Wikipedia full article (EN + local language) ────────────

def _wiki_get(url: str, params: dict, timeout: int = 15):
    """GET a Wikimedia endpoint with 429/5xx retry + Retry-After, reusing the
    battle-tested venue_resolver backoff path (LOCAL-637) — Wikidata/Wikipedia
    throttle this host hard under the concurrent pipeline, and an unretried 429
    is exactly what made the Wikipedia-first idea look empty in a first probe. A
    plain single-shot requests.get is the fallback if that helper is unavailable.
    Returns the Response (any status) or None."""
    headers = {'User-Agent': USER_AGENT}
    try:
        from venue_resolver import _request_with_backoff
        return _request_with_backoff(url, params=params, headers=headers,
                                     timeout=timeout, label='serper_plus wiki')
    except Exception:
        import requests
        import time as _t
        import random as _r
        for i, wait in enumerate((0, 2, 5, 10)):
            if wait:
                _t.sleep(wait + _r.uniform(0, 0.5 * wait))
            try:
                r = requests.get(url, params=params, headers=headers, timeout=timeout)
            except Exception:
                continue
            if r.status_code not in (429, 500, 502, 503, 504):
                return r
        return r if 'r' in dir() else None


def _wikidata_qid(name: str, city: str = '') -> Tuple[str, dict]:
    """Resolve a place name to its Wikidata QID via wbsearchentities. Returns
    (qid, sitelinks_by_wiki) where sitelinks maps 'enwiki'/'frwiki'/... -> title.
    Free (Wikidata API). ('' , {}) on any failure."""
    r = _wiki_get('https://www.wikidata.org/w/api.php',
                  {'action': 'wbsearchentities', 'search': name,
                   'language': 'en', 'format': 'json', 'limit': 5,
                   'type': 'item'}, timeout=12)
    try:
        if r is None or r.status_code != 200:
            return '', {}
        hits = r.json().get('search', []) or []
    except Exception:
        return '', {}
    if not hits:
        return '', {}
    # Prefer a hit whose description looks like a place and (when we have a city)
    # mentions the city; else the first hit.
    qid = ''
    cl = (city or '').lower()
    for h in hits:
        desc = (h.get('description') or '').lower()
        if cl and cl.split(',')[0].strip() and cl.split(',')[0].strip() in desc:
            qid = h.get('id', '')
            break
    if not qid:
        qid = hits[0].get('id', '')
    if not qid:
        return '', {}

    sitelinks = {}
    r2 = _wiki_get('https://www.wikidata.org/w/api.php',
                   {'action': 'wbgetentities', 'ids': qid,
                    'props': 'sitelinks', 'format': 'json'}, timeout=12)
    try:
        if r2 is not None and r2.status_code == 200:
            ent = r2.json().get('entities', {}).get(qid, {}) or {}
            for wiki, info in (ent.get('sitelinks', {}) or {}).items():
                if wiki.endswith('wiki') and not wiki.endswith('wikiquote') \
                        and 'wikinews' not in wiki and 'wikisource' not in wiki \
                        and 'commons' not in wiki and 'wikivoyage' not in wiki:
                    sitelinks[wiki] = info.get('title', '')
    except Exception:
        pass
    return qid, sitelinks


def _wiki_extract(lang: str, title: str, max_chars: int) -> str:
    """Full plain-text article extract via the Wikipedia action API. Free.
    Returns '' on any failure."""
    if not title:
        return ''
    r = _wiki_get(f'https://{lang}.wikipedia.org/w/api.php',
                  {'action': 'query', 'prop': 'extracts', 'explaintext': '1',
                   'formatversion': '2', 'titles': title, 'format': 'json',
                   'redirects': '1'}, timeout=15)
    try:
        if r is None or r.status_code != 200:
            return ''
        pages = r.json().get('query', {}).get('pages', []) or []
        for p in pages:
            ext = p.get('extract', '') or ''
            if ext:
                return ext[:max_chars]
    except Exception:
        return ''
    return ''


def _local_lang_from_city(city: str) -> str:
    """Best-effort local Wikipedia language code from a city/country string. Only
    used to PICK which non-English sitelink to read; a wrong guess just means we
    read the EN article (and whichever other sitelink matches). Small, explicit,
    extend as needed."""
    c = (city or '').lower()
    table = [
        (('france', 'french', 'nice', 'paris', 'lyon', 'marseille'), 'fr'),
        (('italy', 'italian', 'rome', 'florence', 'venice', 'milan'), 'it'),
        (('spain', 'spanish', 'madrid', 'barcelona', 'seville'), 'es'),
        (('germany', 'german', 'berlin', 'munich', 'hamburg'), 'de'),
        (('portugal', 'portuguese', 'lisbon', 'porto'), 'pt'),
        (('netherlands', 'dutch', 'amsterdam', 'rotterdam'), 'nl'),
        (('vietnam', 'vietnamese', 'hanoi', 'ho chi minh', 'saigon'), 'vi'),
        (('japan', 'japanese', 'tokyo', 'kyoto', 'osaka'), 'ja'),
        (('china', 'chinese', 'beijing', 'shanghai'), 'zh'),
        (('russia', 'russian', 'moscow', 'petersburg'), 'ru'),
        (('greece', 'greek', 'athens', 'thessaloniki'), 'el'),
        (('poland', 'polish', 'warsaw', 'krakow'), 'pl'),
        (('sweden', 'swedish', 'stockholm'), 'sv'),
    ]
    for keys, code in table:
        if any(k in c for k in keys):
            return code
    return ''


def gather_wikipedia(name: str, city: str = '') -> List[Dict]:
    """Return [{origin,domain,url,title,text}] for the stop's Wikipedia articles:
    the English full article, plus ONE local-language article when the item has a
    sitelink in the city/country's language. Free. [] when the item cannot be
    resolved or has no article."""
    if not name:
        return []
    qid, sitelinks = _wikidata_qid(name, city)
    pages: List[Dict] = []

    en_title = sitelinks.get('enwiki') or name
    en_text = _wiki_extract('en', en_title, WIKI_CHARS)
    if en_text:
        pages.append({'origin': 'wikipedia_en', 'domain': 'en.wikipedia.org',
                      'url': f'https://en.wikipedia.org/wiki/{en_title.replace(" ", "_")}',
                      'title': f'{en_title} — Wikipedia', 'text': en_text})

    # Local-language article: ONLY when the city/country implies a non-English
    # language (Old Nice -> fr, HCMC -> vi). For an English-locale stop (Boston),
    # the first non-English sitelink is noise (Asturian, Egyptian Arabic), so we
    # do NOT fetch one — the EN article is the local article.
    local_code = _local_lang_from_city(city)
    if local_code and local_code != 'en':
        local_wiki = f'{local_code}wiki'
        local_title = sitelinks.get(local_wiki, '')
        if local_title:
            loc_text = _wiki_extract(local_code, local_title, WIKI_LOCAL_CHARS)
            if loc_text:
                pages.append({
                    'origin': f'wikipedia_{local_code}',
                    'domain': f'{local_code}.wikipedia.org',
                    'url': f'https://{local_code}.wikipedia.org/wiki/{local_title.replace(" ", "_")}',
                    'title': f'{local_title} — Wikipedia ({local_code})',
                    'text': loc_text})
    return pages


# ── 2. Serper web pages (skip SEO/listing/UGC, prefer official site) ──────────

def _usable(url: str) -> bool:
    """Keep a web result unless it is a known content-farm / listing / UGC
    domain. Reuses the exhibition_checklist blocklist (tripadvisor, yelp, reddit,
    pinterest, blogspot…). Wikipedia is intentionally in that blocklist for the
    exhibition path; here we WANT it, but we fetch Wikipedia separately in step 1,
    so excluding it from the web pass only avoids a duplicate."""
    try:
        from exhibition_checklist import _BLOCKED_DOMAIN_PATTERNS
        from urllib.parse import urlparse
        dom = (urlparse(url).netloc or '').lower()
        return not _BLOCKED_DOMAIN_PATTERNS.search(dom)
    except Exception:
        return True


def _derive_place_queries(name: str, city: str, max_q: int) -> List[str]:
    """Queries for a PLACE (not an object): the place+city history, and the
    place's official/own page. Deterministic and free."""
    out: List[str] = []
    nm = (name or '').strip()
    ct = (city or '').strip()
    if nm:
        out.append(f'"{nm}" {ct} history'.strip())
        out.append(f'"{nm}" {ct} official site'.strip())
    seen, uniq = set(), []
    for q in out:
        k = q.lower()
        if q and k not in seen:
            seen.add(k)
            uniq.append(q)
        if len(uniq) >= max_q:
            break
    return uniq


def gather_web(name: str, city: str, max_q: int = MAX_WEB_QUERIES,
               max_pages: int = MAX_WEB_PAGES,
               serp: Optional[Callable] = None,
               fetch: Optional[Callable] = None) -> Tuple[List[Dict], List[str]]:
    """Serper top results → fetch the best `max_pages`, skipping SEO/listing/UGC
    domains. Returns (pages, used_queries). Each page is {origin,domain,url,
    title,snippet,text}. `serp`/`fetch` injectable for tests (default: metered
    project helpers)."""
    serp = serp or _sr._default_serp
    fetch = fetch or _sr._fetch
    queries = _derive_place_queries(name, city, max_q)
    used: List[str] = []
    ranked: List[Dict] = []
    seen_urls = set()
    for q in queries:
        used.append(q)
        for r in serp(q):
            url = (r.get('url') or r.get('link') or '').strip()
            if not url or url in seen_urls:
                continue
            if 'wikipedia.org' in url:   # fetched in step 1
                continue
            if not _usable(url):
                continue
            seen_urls.add(url)
            ranked.append({'url': url, 'title': r.get('title', '') or '',
                           'snippet': r.get('snippet', '') or ''})

    pages: List[Dict] = []
    for r in ranked:
        if len(pages) >= max_pages:
            break
        text = fetch(r['url'])
        if not text or len(text) < 120:
            continue
        pages.append({'origin': 'web', 'domain': _sr._domain(r['url']),
                      'url': r['url'], 'title': r['title'],
                      'snippet': r['snippet'], 'text': text[:PER_PAGE_CHARS]})
    return pages, used


# ── 3. News pass (only when current affairs apply) ────────────────────────────

def _serper_news(query: str) -> List[Dict]:
    """One Serper NEWS query via the google.serper.dev/news endpoint. Metered at
    the HTTP layer like any Serper call. Returns [{title,url,snippet}]; [] on
    failure."""
    import urllib.request
    key = os.environ.get('SERP_API_KEY') or os.environ.get('SERPER_API_KEY')
    if not key:
        return []
    try:
        data = json.dumps({'q': query, 'num': 5}).encode('utf-8')
        req = urllib.request.Request(
            'https://google.serper.dev/news', data=data,
            headers={'X-API-KEY': key, 'Content-Type': 'application/json'},
            method='POST')
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
        out = []
        for r in body.get('news', []) or []:
            out.append({'title': r.get('title', '') or '',
                        'url': r.get('link', '') or '',
                        'snippet': r.get('snippet', '') or '',
                        'date': r.get('date', '') or ''})
        return out
    except Exception:
        return []


def _needs_news(prompt: str, name: str) -> bool:
    return bool(_CURRENT_AFFAIRS.search(prompt or ''))


def gather_news(name: str, city: str, fetch: Optional[Callable] = None
                ) -> Tuple[List[Dict], List[str]]:
    """A single Serper news query for the stop; fetch the top usable article.
    Returns (pages, used_queries)."""
    fetch = fetch or _sr._fetch
    q = f'{name} {city}'.strip()
    results = _serper_news(q)
    pages: List[Dict] = []
    for r in results:
        url = r.get('url', '')
        if not url or not _usable(url):
            continue
        text = fetch(url)
        if not text or len(text) < 120:
            continue
        pages.append({'origin': 'news', 'domain': _sr._domain(url), 'url': url,
                      'title': r.get('title', ''), 'snippet': r.get('snippet', ''),
                      'text': text[:PER_PAGE_CHARS]})
        break
    return pages, ([q] if results else [])


# ── 4. one extractor over everything gathered ────────────────────────────────

_ANSWER_PROMPT = """\
You are a walking-tour fact researcher. Answer the research request below using \
ONLY the numbered SOURCES that follow. Do NOT use any prior knowledge: if a fact \
is not in the sources, do not state it.

Write 3-6 short sentences of specific, checkable STORY facts about this place — \
prefer dated, named events and their consequences (who built or changed it and \
when, a decision, a fire, a death, a protest, a reconstruction, what it cost or \
caused) over description of how it looks or generic praise. End EVERY sentence \
with the number of the source it came from, in brackets, like [2]. If the \
sources contain nothing relevant, reply with exactly: NO MATERIAL FOUND

RESEARCH REQUEST:
{prompt}

SOURCES:
{sources}
"""


def _answer(prompt: str, model: str, max_tokens: int = ANSWER_MAX_TOKENS) -> Dict:
    """Reuse serper_research._openai_chat (metered OpenAI completion)."""
    return _sr._openai_chat(prompt, model=model, max_tokens=max_tokens)


@_sub_timed('serper_plus_research')
def serper_plus_research(prompt: str, model: str = None, resolve: bool = True,
                         timeout: int = 90, grounded: bool = True,
                         *, serp: Optional[Callable] = None,
                         fetch: Optional[Callable] = None,
                         answer: Optional[Callable] = None,
                         wiki: Optional[Callable] = None,
                         news: Optional[Callable] = None) -> Dict:
    """Answer a walking-stop story-lead question with Wikipedia-first + better
    Serper pages + an optional news pass + one extractor.

    Call-compatible with story_leads.gemini_with_sources / serper_research (same
    positional params), returns the same shape. `model` names the EXTRACTOR model
    (default gpt-4.1-mini, or SERPER_PLUS_EXTRACTOR). Injectables are for tests.
    Never raises; failures land in out['error']."""
    out = _blank()
    extractor = model or EXTRACTOR_MODEL
    answer = answer or _answer
    wiki = wiki or gather_wikipedia

    try:
        ctx = _sr._parse_context(prompt)
        name = _sr._strip_gloss(ctx.get('canonical_title', '')) or ''
        city = (ctx.get('venue_name') or '').strip()
        # The walking stop's "venue_name" IS the place; city sits in the prompt's
        # Exhibition line or the request. Pull a city hint from the prompt tail.
        if not name:
            # Ad-hoc prompt (no context block): take the first quoted phrase.
            m = _sr._QUOTED.search(prompt or '')
            name = (m.group(1).strip() if m else '')
        city_hint = _city_hint(prompt, city)

        pages: List[Dict] = []
        # 1. Wikipedia (free, highest signal).
        try:
            pages.extend(wiki(name, city_hint))
        except Exception:
            pass
        # 2. Better web pages (Serper, skip SEO/listing, prefer official).
        web_pages, web_q = gather_web(name, city_hint, serp=serp, fetch=fetch)
        pages.extend(web_pages)
        out['queries'].extend(web_q)
        # 3. News pass only when current affairs apply.
        if _needs_news(prompt, name):
            news_fn = news or gather_news
            try:
                news_pages, news_q = news_fn(name, city_hint, fetch=fetch) \
                    if news is None else news_fn(name, city_hint)
            except TypeError:
                news_pages, news_q = news_fn(name, city_hint)
            pages.extend(news_pages)
            out['queries'].extend(news_q)

        # De-duplicated source list, order preserved.
        seen = set()
        for p in pages:
            if p['url'] and p['url'] not in seen:
                seen.add(p['url'])
                out['sources'].append({'domain': p['domain'], 'url': p['url']})

        if not pages:
            out['error'] = 'no pages gathered'
            return out

        sources_block = '\n\n'.join(
            f"[{i + 1}] {p.get('title', '')} ({p['domain']})\n{p['text']}"
            for i, p in enumerate(pages))
        ans = answer(_ANSWER_PROMPT.format(prompt=prompt, sources=sources_block),
                     extractor)
        if ans.get('error'):
            out['error'] = ans['error']
            return out
        text = (ans.get('text') or '').strip()
        if _sr._NO_MATERIAL.lower() in text.lower() \
                and len(text) < len(_sr._NO_MATERIAL) + 10:
            out['text'] = ''
            return out
        out['text'] = _sr._strip_cites(text)
        out['supports'] = _sr._attribute(text, pages)
        return out
    except Exception as e:
        out['error'] = f'{type(e).__name__}: {e}'
        return out


def _city_hint(prompt: str, venue_name: str) -> str:
    """Pull a city/country hint from the prompt. The per-stop prompt carries an
    'Exhibition:' line (the tour's area/city) and often a venue_name; use the
    richer of the two."""
    m = re.search(r'(?mi)^\s*Exhibition:\s*(.+?)\s*$', prompt or '')
    exhibition = (m.group(1).strip() if m else '')
    if exhibition and exhibition.lower() != 'this exhibition':
        return exhibition
    return venue_name or ''


# ── CLI: answer one prompt and print the result (for spot checks) ─────────────
if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='serper_plus walking research (LOCAL-674)')
    ap.add_argument('prompt', help='the research request / story-lead question')
    ap.add_argument('--model', default=EXTRACTOR_MODEL)
    a = ap.parse_args()
    t0 = time.time()
    res = serper_plus_research(a.prompt, model=a.model)
    dt = time.time() - t0
    print(json.dumps(res, indent=2, ensure_ascii=False))
    print(f"\n[{dt:.1f}s] queries={res['queries']} sources={len(res['sources'])} "
          f"error={res['error'] or 'none'}")
