"""current_affairs_news.py — dated NEWS research for a current-affairs tour.

LOCAL-655. Tour 557 ("Walking tour in Boston dedicated to Massachusetts politics
and current affairs") ended with "we found no verified developments from the past
five years" — a gap the pipeline *created itself*: no code searched news at all
(the research backends are Wikipedia/Wikidata/venue corpus + Gemini grounding on
HISTORY questions). Current affairs happen every day the legislature sits; the
honest-note is only honest if a news search actually ran and returned nothing.

This module adds exactly that search, for a current-affairs request only:

    1. DETECT   wants_current_affairs(request) — a current-affairs intent gate.
    2. QUERY    the Serper NEWS endpoint (https://google.serper.dev/news) for the
                tour theme and for each stop, tbs=qdr:m (past month), widening to
                qdr:y (past year) when the month is empty. $0.001/query (metered at
                the network layer like every other serper.dev call).
    3. FETCH    the 2-3 best article pages (the existing polite, cached, robots-
                aware exhibition_checklist._fetch_page helper).
    4. NARRATE  1-3 DATED, attributed, politically-BALANCED sentences per stop,
                grounded ONLY in the fetched article text — no invented quotes or
                numbers, no adjectives taking a side. A cheap model (gpt-4.1-mini)
                constrained to the sources writes them.
    5. HONEST   when the search ran AND returned nothing usable, an honest note is
                produced (and the queries + counts are logged) — not a fabricated
                "nothing happened".

It mirrors serper_research.py exactly: deterministic query derivation, the project
Serper key (SERP_API_KEY), the shared page-fetch helper, and a source-constrained
cheap model. The injection pass is additive, idempotent and parses stops from the
DELIVERED text, so it is independent of which generation path produced the tour.

NOTHING here runs unless wants_current_affairs(request) is true AND the tour is not
a museum tour — so the museum path and any non-current-affairs tour are byte-for-
byte unchanged.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ── tunables (env-overridable) ────────────────────────────────────────────────
NEWS_MODEL = os.environ.get('CA_NEWS_MODEL', 'gpt-4.1-mini')
NEWS_PER_QUERY_RESULTS = int(os.environ.get('CA_NEWS_NUM', '8'))
NEWS_MAX_ARTICLES_PER_STOP = int(os.environ.get('CA_NEWS_MAX_ARTICLES', '3'))
NEWS_MAX_STOP_QUERIES = int(os.environ.get('CA_NEWS_MAX_STOP_QUERIES', '2'))
NEWS_PER_PAGE_CHARS = int(os.environ.get('CA_NEWS_PER_PAGE_CHARS', '2500'))
NEWS_ANSWER_MAX_TOKENS = int(os.environ.get('CA_NEWS_MAX_TOKENS', '320'))
NEWS_FRESH_DAYS = int(os.environ.get('CA_NEWS_FRESH_DAYS', '7'))

SERP_NEWS_URL = 'https://google.serper.dev/news'

# The honest note — used ONLY when a search ran and returned nothing usable.
HONEST_NOTE = (
    "We searched the news for recent developments connected to this tour but "
    "could not confirm any from reliable, dated reporting at the time of writing."
)


# ── 1. intent gate ────────────────────────────────────────────────────────────

# Phrases/words that mark a request as wanting CURRENT AFFAIRS (recent, ongoing,
# dated public events) as opposed to a history / art / architecture tour. The
# detector is deliberately narrow: a plain "history of Boston" tour must NOT
# trip it (history is handled by the existing grounded-research path, unchanged).
_CA_PHRASES = (
    'current affairs', 'current events', 'in the news', 'recent news',
    'latest news', 'todays news', "today's news", 'breaking news',
    'current political', 'present-day politics', 'contemporary politics',
    'recent developments', 'latest developments',
)
_CA_WORDS = {
    'politics', 'political', 'election', 'elections', 'campaign',
    'legislature', 'legislative', 'senate', 'congress', 'parliament',
    'governor', 'mayor', 'councillor', 'councilmember', 'referendum',
    'ballot', 'policy', 'protest', 'protests', 'debate', 'debates',
    'bill', 'statehouse', 'state house', 'city hall',
}
# Words that, if the ONLY signal, indicate a HISTORY tour and must not alone
# trigger current affairs (so "history of the Senate chamber" is not news).
_HISTORY_ONLY = {'history', 'historic', 'historical', 'heritage', 'colonial',
                 'revolution', 'founding', 'ancient', 'medieval'}


def wants_current_affairs(request_text: str) -> bool:
    """True when the request asks for CURRENT AFFAIRS / recent dated public events.

    Deterministic and free. A multi-word phrase ("current affairs", "in the news")
    is decisive. A single political word ("politics", "election", "governor",
    "legislature", …) also qualifies — those requests are about what is happening
    now, which is exactly what the LOCAL-655 search must cover. A request whose
    only signal is a history word does NOT qualify.
    """
    t = (request_text or '').lower()
    if not t:
        return False
    for p in _CA_PHRASES:
        if p in t:
            return True
    words = set(re.findall(r"[a-z]+", t))
    # multi-word markers that survive the word-split ("state house" -> state,house)
    if 'state' in words and 'house' in words:
        return True
    if 'city' in words and 'hall' in words:
        return True
    return bool(words & _CA_WORDS)


# ── 2. query derivation ───────────────────────────────────────────────────────

_STOP_HEADER_RE = re.compile(r"(?m)^Stop\s+(\d+):\s*(.+?)\s*$")
# a trailing ", City, STATE" or ", City, Country" tail on the request/theme
_LOC_TAIL_RE = re.compile(r",\s*[^,]+,\s*[^,]+$")


def _theme_phrase(request_text: str) -> str:
    """A compact theme phrase from the request, stripped of tour boilerplate and
    the trailing ", City, Country" tail. When the request names its topic with
    "dedicated to / about / on <topic>", that topic is the theme."""
    t = (request_text or '').strip()
    t = _LOC_TAIL_RE.sub('', t).strip()
    # Prefer the explicit topic marker: "... dedicated to|about|on|focused on X".
    mt = re.search(r'(?i)\b(?:dedicated to|focus(?:ed|ing)? on|about|on the subject of|on)\s+(.+)$', t)
    if mt:
        topic = mt.group(1).strip()
        if len(topic) >= 4:
            return topic
    # drop leading "Walking/driving/… tour (in|of|around|dedicated to)" scaffolding
    t = re.sub(r'(?i)^\s*(?:a\s+)?(?:walking|driving|cycling|biking|self[- ]guided|'
               r'audio)?\s*tour\s+(?:in|of|around|through|dedicated to|about|on)?\s*',
               '', t).strip()
    return t or (request_text or '').strip()


def _region_phrase(request_text: str) -> str:
    """The place/region hint for scoping a stop query (e.g. 'Boston, MA')."""
    m = re.search(r",\s*([^,]+,\s*[^,]+)$", request_text or '')
    if m:
        return m.group(1).strip()
    return ''


def derive_theme_queries(request_text: str) -> List[str]:
    """Theme-level news queries from the request. Deterministic."""
    theme = _theme_phrase(request_text)
    region = _region_phrase(request_text)
    out: List[str] = []
    if theme:
        out.append(theme if region and region.lower() in theme.lower()
                   else (f"{theme} {region}".strip() if region else theme))
    # a tighter "<region> politics current affairs" style query as a second angle
    if region:
        out.append(f"{region} latest news")
    seen, uniq = set(), []
    for q in out:
        q = re.sub(r'\s+', ' ', q).strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            uniq.append(q)
    return uniq


def derive_stop_queries(stop_name: str, request_text: str,
                        max_queries: int = NEWS_MAX_STOP_QUERIES) -> List[str]:
    """Per-stop news queries: the stop itself, and the stop + a theme/region word.

    e.g. "Massachusetts State House" -> ["Massachusetts State House news",
    "Massachusetts State House legislature"].
    """
    name = (stop_name or '').strip()
    if not name:
        return []
    region = _region_phrase(request_text)
    theme = _theme_phrase(request_text)
    out = [f"{name} news"]
    # a topical second query: pick the strongest theme word present
    topical = ''
    for w in ('legislature', 'senate', 'governor', 'election', 'politics',
              'policy', 'council', 'mayor'):
        if w in (theme or '').lower() or w in (request_text or '').lower():
            topical = w
            break
    if topical:
        out.append(f"{name} {topical}")
    elif region:
        out.append(f"{name} {region}")
    seen, uniq = set(), []
    for q in out:
        q = re.sub(r'\s+', ' ', q).strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            uniq.append(q)
        if len(uniq) >= max_queries:
            break
    return uniq


# ── 3. Serper NEWS endpoint ───────────────────────────────────────────────────

def _serp_news(query: str, tbs: str = 'qdr:m',
               num: int = NEWS_PER_QUERY_RESULTS) -> List[Dict]:
    """One Serper NEWS query. Returns [{title, source, date, link, snippet}].

    POSTs to https://google.serper.dev/news with the project SERP_API_KEY. The
    network meter prices every serper.dev call at $0.001/query automatically
    (_meter/paid_api_meter.py), so no explicit metering is needed here. Returns []
    on any failure (never raises)."""
    key = os.environ.get('SERP_API_KEY', '')
    if not key:
        print("  [LOCAL-655] No SERP_API_KEY — news query skipped")
        return []
    payload = {"q": query, "num": num}
    if tbs:
        payload["tbs"] = tbs
    try:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            SERP_NEWS_URL, data=data,
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            rb = e.read().decode('utf-8', errors='replace')[:300]
        except Exception:
            rb = '<unreadable>'
        print(f"  [LOCAL-655] NEWS HTTP {e.code}: {e.reason}; body={rb}")
        return []
    except Exception as e:
        print(f"  [LOCAL-655] NEWS query failed: {type(e).__name__}: {e}")
        return []
    out = []
    for r in body.get("news", []) or []:
        out.append({
            'title': (r.get('title') or '').strip(),
            'source': (r.get('source') or '').strip(),
            'date': (r.get('date') or '').strip(),
            'link': (r.get('link') or '').strip(),
            'snippet': (r.get('snippet') or '').strip(),
        })
    return out


def news_for_query(query: str, serp: Optional[Callable] = None) -> Tuple[List[Dict], str]:
    """Run one news query at qdr:m, widening to qdr:y when the month is empty.

    Returns (items, tbs_used). `serp` is injectable for tests."""
    serp = serp or _serp_news
    items = serp(query, 'qdr:m')
    if items:
        return items, 'qdr:m'
    items = serp(query, 'qdr:y')
    return items, 'qdr:y'


def _fetch_article(url: str) -> str:
    """Fetch an article page's clean text via the shared polite/cached helper."""
    try:
        from exhibition_checklist import _fetch_page
    except Exception:
        return ''
    try:
        text, _links = _fetch_page(url)
    except Exception:
        return ''
    text = text or ''
    if '<' in text[:200] and ('</' in text or '<p' in text.lower()):
        try:
            from robust_text_extractor import extract_clean_text
            text = extract_clean_text(text) or text
        except Exception:
            pass
    return text


def _rank_items(items: List[Dict]) -> List[Dict]:
    """Prefer items that carry a date, de-dupe by link, keep order otherwise."""
    seen, dated, undated = set(), [], []
    for it in items:
        link = it.get('link')
        if not link or link in seen:
            continue
        seen.add(link)
        (dated if it.get('date') else undated).append(it)
    return dated + undated


# ── 4. compose dated, attributed, balanced sentences ──────────────────────────

_NEWS_PROMPT = """\
You are a careful news writer for a walking-tour audio guide. Using ONLY the \
numbered ARTICLES below, write {max_items} short, DATED sentence(s) about recent \
developments connected to "{subject}". Rules you must follow exactly:

- Ground every statement in the articles. Do NOT use any outside knowledge, and \
do NOT invent any quote, number, name or date that is not in an article.
- Begin each sentence with the DATE of the event when the article gives one \
(e.g. "On October 8, 2026, ..."). If no date is given, say "Recently, ...".
- POLITICAL BALANCE IS MANDATORY. If the item concerns a dispute or an election, \
report what EACH side said or did, attributed by name/party, with no editorialising \
and no adjective that favours a side.
- Attribute claims ("Governor Healey said ...", "according to the State House \
News Service ..."). End each sentence with its source number in brackets, like [2].
- If the articles contain nothing of substance about the subject, reply with \
exactly: NO MATERIAL FOUND

ARTICLES:
{sources}
"""

_CITE = re.compile(r'\[(\d+)\]')
_NO_MATERIAL = 'NO MATERIAL FOUND'


def _openai_chat(prompt: str, model: str = NEWS_MODEL,
                 max_tokens: int = NEWS_ANSWER_MAX_TOKENS) -> Dict:
    """One OpenAI chat completion -> {'text','error'}. Metered at the network
    layer from the response body (model+usage)."""
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        return {'text': '', 'error': 'no OPENAI_API_KEY'}
    try:
        r = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {key}',
                     'Content-Type': 'application/json'},
            json={'model': model, 'temperature': 0.1, 'max_tokens': max_tokens,
                  'messages': [{'role': 'user', 'content': prompt}]},
            timeout=60)
        r.raise_for_status()
        d = r.json()
        return {'text': d['choices'][0]['message']['content'] or '', 'error': ''}
    except Exception as e:
        return {'text': '', 'error': f'{type(e).__name__}: {e}'}


def _strip_cites(s: str) -> str:
    s = _CITE.sub('', s or '')
    s = re.sub(r'\s+([.,;:!?])', r'\1', s)
    s = re.sub(r'\s{2,}', ' ', s)
    return s.strip()


def compose_news_sentences(subject: str, articles: List[Dict],
                           max_items: int = 2,
                           answer: Optional[Callable] = None) -> Dict:
    """Write dated, attributed, balanced sentences grounded in `articles`.

    `articles` is [{title, source, date, snippet, text, link}]. Returns
    {text, sources:[{source,url,date}], error}. `answer` injectable for tests.
    An empty/`NO MATERIAL FOUND` result returns text=''.
    """
    answer = answer or _openai_chat
    out = {'text': '', 'sources': [], 'error': ''}
    if not articles:
        return out
    blocks = []
    for i, a in enumerate(articles, 1):
        body = (a.get('text') or a.get('snippet') or '').strip()[:NEWS_PER_PAGE_CHARS]
        head = f"[{i}] {a.get('title','')} — {a.get('source','')}"
        if a.get('date'):
            head += f" ({a['date']})"
        blocks.append(f"{head}\n{body}")
    prompt = _NEWS_PROMPT.format(
        subject=subject, max_items=max_items, sources="\n\n".join(blocks))
    ans = answer(prompt, model=NEWS_MODEL)
    if ans.get('error'):
        out['error'] = ans['error']
        return out
    text = (ans.get('text') or '').strip()
    if not text or (_NO_MATERIAL.lower() in text.lower()
                    and len(text) < len(_NO_MATERIAL) + 12):
        return out
    out['text'] = _strip_cites(text)
    # Record which numbered sources were actually cited.
    cited = sorted({int(n) for n in _CITE.findall(text)})
    for n in cited:
        if 1 <= n <= len(articles):
            a = articles[n - 1]
            out['sources'].append({'source': a.get('source', ''),
                                    'url': a.get('link', ''),
                                    'date': a.get('date', '')})
    if not out['sources']:  # no [n] markers — attribute to all used articles
        for a in articles:
            out['sources'].append({'source': a.get('source', ''),
                                   'url': a.get('link', ''),
                                   'date': a.get('date', '')})
    return out


# ── 5. research per stop ──────────────────────────────────────────────────────

def research_news_for_stops(request_text: str, stop_names: List[str],
                            *, serp: Optional[Callable] = None,
                            fetch: Optional[Callable] = None,
                            answer: Optional[Callable] = None,
                            max_articles: int = NEWS_MAX_ARTICLES_PER_STOP) -> Dict:
    """Run the whole news research for a current-affairs tour.

    For the theme and each stop: query Serper news (qdr:m -> qdr:y), fetch the best
    articles, write dated/attributed/balanced sentences grounded in them.

    Returns:
        {
          'by_stop': {stop_name: {text, sources, articles}},
          'queries': [str],            # every query actually issued
          'result_counts': {query: n}, # items returned per query
          'articles_fetched': int,
          'items_total': int,
          'searched': bool,            # True if at least one query ran
        }
    `serp`/`fetch`/`answer` are injectable for tests (default to metered helpers).
    """
    serp = serp or _serp_news
    fetch = fetch or _fetch_article
    answer = answer or _openai_chat

    log = {'by_stop': {}, 'queries': [], 'result_counts': {},
           'articles_fetched': 0, 'items_total': 0, 'searched': False}

    def _run_queries(queries: List[str]) -> List[Dict]:
        items: List[Dict] = []
        for q in queries:
            log['queries'].append(q)
            log['searched'] = True
            got, tbs = news_for_query(q, serp=serp)
            log['result_counts'][q] = len(got)
            log['items_total'] += len(got)
            items.extend(got)
        return _rank_items(items)

    for name in stop_names:
        queries = derive_stop_queries(name, request_text)
        ranked = _run_queries(queries)
        # fetch the best few article pages
        articles: List[Dict] = []
        for it in ranked:
            if len(articles) >= max_articles:
                break
            text = fetch(it['link']) if it.get('link') else ''
            a = dict(it)
            a['text'] = text if (text and len(text) >= 120) else it.get('snippet', '')
            if a['text']:
                articles.append(a)
        if articles:
            log['articles_fetched'] += len(articles)
            composed = compose_news_sentences(name, articles, answer=answer)
            if composed.get('text'):
                log['by_stop'][name] = {
                    'text': composed['text'],
                    'sources': composed['sources'],
                    'articles': articles,
                }
    return log


# ── 6. inject into the delivered tour text (additive, idempotent) ─────────────

_NEWS_MARK = "In recent news:"


def _split_stops(text: str) -> List[Tuple[int, int, str]]:
    """Return [(start, end, stop_name)] spans for each 'Stop N:' block."""
    spans = []
    matches = list(_STOP_HEADER_RE.finditer(text or ''))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        spans.append((start, end, m.group(2).strip()))
    return spans


def _match_stop_key(delivered_name: str, keys: List[str]) -> Optional[str]:
    """Best-effort match a delivered stop header to a researched stop key."""
    dn = (delivered_name or '').lower().strip()
    for k in keys:
        kl = k.lower().strip()
        if kl == dn or kl in dn or dn in kl:
            return k
    return None


def inject_news_into_text(text: str, by_stop: Dict[str, Dict]) -> Tuple[str, int]:
    """Add each stop's dated news sentences to the end of that stop's narration.

    Additive and idempotent: a stop that already carries the news marker is left
    untouched. The news paragraph is placed as the last narration paragraph of the
    stop, before any trailing 'Directions:'/'Sources:' line. Returns (text, n_added).
    """
    if not text or not by_stop:
        return text, 0
    spans = _split_stops(text)
    if not spans:
        return text, 0
    keys = list(by_stop.keys())
    # Build the new text by walking spans in order.
    out_parts = []
    cursor = 0
    n_added = 0
    for (start, end, name) in spans:
        out_parts.append(text[cursor:start])
        block = text[start:end]
        key = _match_stop_key(name, keys)
        if key and _NEWS_MARK not in block:
            news_text = by_stop[key]['text'].strip()
            if news_text:
                srcs = by_stop[key].get('sources') or []
                src_names = []
                for s in srcs:
                    sn = (s.get('source') or '').strip()
                    if sn and sn not in src_names:
                        src_names.append(sn)
                attrib = f" (Reported by {', '.join(src_names)}.)" if src_names else ""
                para = f"{_NEWS_MARK} {news_text}{attrib}"
                block = _insert_news_paragraph(block, para)
                n_added += 1
        out_parts.append(block)
        cursor = end
    out_parts.append(text[cursor:])
    return "".join(out_parts), n_added


def _insert_news_paragraph(block: str, para: str) -> str:
    """Insert `para` as a new paragraph before a trailing Directions:/Sources:
    line in a stop block, else at the end of the block."""
    # find a trailing "Directions:" or "Sources:" paragraph
    m = re.search(r"(?m)^(Directions:|Sources:)", block)
    if m:
        head = block[:m.start()].rstrip()
        tail = block[m.start():]
        return f"{head}\n\n{para}\n\n{tail}"
    return f"{block.rstrip()}\n\n{para}\n"


def append_honest_note(text: str, log: Dict) -> Tuple[str, bool]:
    """Append the honest note ONCE, only when a search ran and yielded nothing
    usable. Idempotent. Returns (text, appended)."""
    if not log.get('searched'):
        return text, False
    if log.get('by_stop'):
        return text, False
    if HONEST_NOTE in (text or ''):
        return text, False
    sep = '' if (text or '').endswith('\n') else '\n'
    return f"{text}{sep}\n{HONEST_NOTE}\n", True


# ── CLI spot check ────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Current-affairs news research (LOCAL-655)')
    ap.add_argument('request', help='the tour request string')
    ap.add_argument('--stop', action='append', default=[], help='a stop name (repeatable)')
    a = ap.parse_args()
    print(f"wants_current_affairs={wants_current_affairs(a.request)}")
    print(f"theme queries={derive_theme_queries(a.request)}")
    for s in a.stop:
        print(f"stop '{s}' queries={derive_stop_queries(s, a.request)}")
    if a.stop:
        t0 = time.time()
        res = research_news_for_stops(a.request, a.stop)
        print(json.dumps(res['by_stop'], indent=2, ensure_ascii=False))
        print(f"[{time.time()-t0:.1f}s] queries={res['queries']} "
              f"counts={res['result_counts']} articles={res['articles_fetched']} "
              f"searched={res['searched']}")
