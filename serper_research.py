"""serper_research.py — a research backend that answers a story-lead question with
Serper + page fetch + a cheap model, instead of Gemini grounded search.

LOCAL-648. Gemini costs ~$0.28 per 3-stop tour, of which **$0.245 is Google's
per-request search fee** (7 search-enabled requests × $0.035; price card r4,
`_meter/paid_api_meter.py` RATE_TAG 2026-10-08-r4). Serper costs **$0.001 per
query** and we already use it everywhere else in the pipeline.

This module answers the SAME question `story_leads.gemini_with_sources(grounded=
True)` answers, by doing the retrieval ourselves and letting a cheap model write
only from what we fetched:

    1. QUERY   turn the prompt into 2-3 Serper queries ($0.001 each)
    2. FETCH   fetch the top 3-5 result pages (free; reuse the existing polite,
               robots/Retry-After-aware, cached fetch helper)
    3. EXTRACT pull clean text from each page
    4. ANSWER  gpt-4.1-mini, CONSTRAINED to the fetched text (no memory), and
               told to cite the page each sentence came from

It returns the EXACT shape `gemini_with_sources` returns —
`{text, sources:[{domain,url}], supports:[{text, sources:[{domain,url}]}],
queries:[str], error:str}` — so it is a drop-in alternative anywhere a grounded
answer-with-sources is consumed (the D511 per-stop narrate, the offline A/B).

Every paid call it makes (Serper queries, the gpt-4.1-mini completion) goes out
through the project's network meter (`_meter/paid_api_meter.py`), so the spend of
a Serper arm is read straight from `paid_api_calls` like any other.

NOTHING here runs unless the caller asks for it: the backend is selected by
`RESEARCH_BACKEND=serper` through the thin router in `story_leads.py`. The default
(`gemini`) never reaches this module, so default behaviour is byte-for-byte
unchanged.
"""
import json
import os
import re
import sys
import time
from typing import Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


# ── tunables (env-overridable; defaults match the ticket's "2-3 / 3-5") ───────
RESEARCH_MODEL = os.environ.get('SERPER_RESEARCH_MODEL', 'gpt-4.1-mini')
MAX_QUERIES = int(os.environ.get('SERPER_RESEARCH_MAX_QUERIES', '3'))
MAX_PAGES = int(os.environ.get('SERPER_RESEARCH_MAX_PAGES', '5'))
PER_PAGE_CHARS = int(os.environ.get('SERPER_RESEARCH_PER_PAGE_CHARS', '2500'))
ANSWER_MAX_TOKENS = int(os.environ.get('SERPER_RESEARCH_MAX_TOKENS', '700'))


def _blank() -> Dict:
    """The gemini_with_sources shape, empty."""
    return {'text': '', 'sources': [], 'supports': [], 'queries': [], 'error': ''}


# ── 1. prompt -> Serper queries ───────────────────────────────────────────────

_QUOTED = re.compile(r'[“"\u201c\u201d]([^"\u201c\u201d]{3,80})[”"\u201c\u201d]')
_YEAR = re.compile(r'\b(1[4-9]\d{2}|20[0-3]\d)\b')
# The pipeline's per-stop prompt (story_query.compile_for_seed) always carries a
# structured "Context — the work this concerns:" block with these labelled
# fields. They are the strongest retrieval signal — far better than scraping the
# free text — so we parse them first.
_CTX_FIELD = re.compile(r'(?mi)^\s*(canonical_title|artist|venue_name|'
                        r'credit_line|publication_year|medium)\s*:\s*(.+?)\s*$')
# Instruction boilerplate that must never become a query term.
_BOILER_PHRASES = ('no reliable information', 'no material found',
                   'using google search', 'google search')


def _parse_context(text: str) -> dict:
    """Pull the labelled context fields out of a compile_for_seed prompt."""
    ctx = {}
    for m in _CTX_FIELD.finditer(text or ''):
        k = m.group(1).lower()
        v = m.group(2).strip()
        if v and v.lower() not in ('', 'not specified', 'n/a'):
            ctx.setdefault(k, v)
    return ctx


def _strip_gloss(title: str) -> str:
    """Drop a parenthetical English gloss, mirroring story_query._bare_title."""
    return re.sub(r'\s*\([^)]*\)\s*', ' ', title or '').strip() or (title or '')


def _clean_name(v: str) -> str:
    """Surname-or-short-name for an agent, dropping donor verbs."""
    v = re.sub(r'^(gift|bequest|loan|promised gift)\s+of\s+', '', v or '',
               flags=re.IGNORECASE)
    v = v.split('.')[0].split(',')[0].strip()
    toks = [t for t in v.split() if len(t) > 1]
    if not toks:
        return ''
    return toks[-1] if len(toks) > 1 and len(toks[-1]) > 3 else ' '.join(toks)


def derive_queries(prompt: str, max_queries: int = MAX_QUERIES) -> List[str]:
    """Turn a story-lead prompt into a few focused web queries.

    PREFERRED path: the pipeline's prompt carries a labelled context block
    (canonical_title / artist / venue_name / credit_line / year). We build the
    queries from those strong signals — the quoted title + artist, the title +
    venue, the title + year — the same encoding story_query.compile_for_serper
    proved. FALLBACK (an ad-hoc prompt with no context block): quoted title, then
    a proper-noun phrase, then content words. Deterministic and free.
    """
    text = (prompt or '').strip()
    ctx = _parse_context(text)
    queries: List[str] = []

    if ctx.get('canonical_title'):
        title = _strip_gloss(ctx['canonical_title'])
        artist = _clean_name(ctx.get('artist', ''))
        venue = (ctx.get('venue_name') or '').strip()
        donor = _clean_name(ctx.get('credit_line', ''))
        year = ''
        ym = _YEAR.search(ctx.get('publication_year', '') or
                          ctx.get('credit_line', '') or '')
        if ym:
            year = ym.group(1)

        # Q1: title (quoted) + artist + year — the object itself.
        q1 = f'"{title}"'
        if artist:
            q1 += f' {artist}'
        if year:
            q1 += f' {year}'
        queries.append(q1)
        # Q2: title + venue — the venue's holding / acquisition of it.
        if venue:
            queries.append(f'"{title}" {venue}')
        # Q3: title + donor/collection + "history" — provenance angle.
        if donor and donor.lower() not in (artist.lower(), venue.lower()):
            queries.append(f'"{title}" {donor} history')
        elif artist:
            queries.append(f'"{title}" {artist} history')

    # Fallback / top-up when there is no context block or too few queries.
    if len(queries) < max_queries:
        quoted = [m.group(1).strip() for m in _QUOTED.finditer(text)]
        years = _YEAR.findall(text)
        if quoted:
            q = quoted[0] + (f' {years[0]}' if years else '')
            queries.append(q)
        words = re.findall(r"[A-Za-zÀ-ÿ'’\-]{5,}", text)
        stop = {'using', 'google', 'search', 'research', 'museum', 'venue',
                'works', 'facts', 'sources', 'checkable', 'events', 'visitor',
                'tour', 'about', 'their', 'which', 'there', 'these', 'those',
                'please', 'provide', 'specific', 'history', 'notable', 'story',
                'visitors', 'reliable', 'information', 'context', 'concerns',
                'exhibition', 'answer', 'bracket', 'brackets', 'sentence',
                'maximum', 'prefer', 'standing', 'front', 'cannot', 'praise',
                'describe', 'looks', 'nothing'}
        content = [w for w in words if w.lower() not in stop]
        if content:
            queries.append(' '.join(content[:6]))

    # Drop any query that is pure boilerplate, then de-dupe / cap.
    seen, out = set(), []
    for q in queries:
        q = re.sub(r'\s+', ' ', q).strip()
        k = q.lower()
        if not q or k in seen:
            continue
        # A query that is nothing but an instruction phrase retrieves garbage.
        bare = k.replace('"', '').strip()
        if any(bare.startswith(b) or b == bare for b in _BOILER_PHRASES):
            continue
        seen.add(k)
        out.append(q)
        if len(out) >= max_queries:
            break
    return out


# ── 2+3. Serper -> fetch top pages -> extract clean text ──────────────────────

def _default_serp(query: str) -> List[Dict]:
    """Run one Serper query, returning [{title,url,snippet}]. Reuses the project
    Serper caller (work_story_searcher._serp_search), which is metered at the
    network layer ($0.001/query) and keyed on SERP_API_KEY."""
    try:
        from work_story_searcher import _serp_search
    except Exception:
        return []
    try:
        results, _latency_ms = _serp_search(query)
        return results or []
    except Exception:
        return []


def _fetch(url: str) -> str:
    """Fetch a page's clean text, reusing the polite/cached/robots-respecting
    fetch helper (exhibition_checklist._fetch_page: 1.5s per-host delay,
    retry/backoff, Retry-After, Cloudflare->Wayback, 1h per-host cache). Returns
    '' on any failure. The helper already returns extracted text; if it ever
    returns HTML we clean it with robust_text_extractor."""
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
        # Looks like raw HTML slipped through — clean it.
        try:
            from robust_text_extractor import extract_clean_text
            text = extract_clean_text(text) or text
        except Exception:
            pass
    return text


def gather_pages(queries: List[str], max_pages: int = MAX_PAGES,
                 serp: Optional[Callable[[str], List[Dict]]] = None,
                 fetch: Optional[Callable[[str], str]] = None,
                 ) -> Tuple[List[Dict], List[str]]:
    """Run the queries, fetch the top unique pages, extract their text.

    Returns (pages, used_queries) where each page is
    {domain, url, title, snippet, text}. `serp`/`fetch` are injectable for tests;
    they default to the metered project helpers. Only `max_pages` pages are
    fetched in total across all queries (budget), de-duplicated by URL."""
    serp = serp or _default_serp
    fetch = fetch or _fetch
    used_queries: List[str] = []
    ranked: List[Dict] = []
    seen_urls = set()

    for q in queries:
        used_queries.append(q)
        for r in serp(q):
            url = (r.get('url') or r.get('link') or '').strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            ranked.append({
                'url': url,
                'title': r.get('title', '') or '',
                'snippet': r.get('snippet', '') or '',
            })

    pages: List[Dict] = []
    for r in ranked:
        if len(pages) >= max_pages:
            break
        text = fetch(r['url'])
        if not text or len(text) < 120:
            continue
        pages.append({
            'domain': _domain(r['url']),
            'url': r['url'],
            'title': r['title'],
            'snippet': r['snippet'],
            'text': text[:PER_PAGE_CHARS],
        })
    return pages, used_queries


def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc or ''
        return host[4:] if host.startswith('www.') else host
    except Exception:
        return url[:40]


# ── 4. cheap model, CONSTRAINED to the fetched text ───────────────────────────

_ANSWER_PROMPT = """\
You are a museum-tour fact researcher. Answer the research request below using \
ONLY the numbered SOURCES that follow. Do NOT use any prior knowledge: if a fact \
is not in the sources, do not state it.

Write 3-6 short sentences of specific, checkable facts (names, dates, events, \
how the venue acquired a work). End EVERY sentence with the number of the source \
it came from, in brackets, like [2]. If the sources contain nothing relevant to \
the request, reply with exactly: NO MATERIAL FOUND

RESEARCH REQUEST:
{prompt}

SOURCES:
{sources}
"""


def _openai_chat(prompt: str, model: str = RESEARCH_MODEL,
                 max_tokens: int = ANSWER_MAX_TOKENS) -> Dict:
    """One OpenAI chat completion. Returns {'text', 'error'}. The request goes out
    through requests (so the network meter prices it from the response body's
    model+usage — gpt-4.1-mini at $0.40/$1.60 per 1M, cached $0.10)."""
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


_CITE = re.compile(r'\[(\d+)\]')
_NO_MATERIAL = 'NO MATERIAL FOUND'


def _strip_cites(s: str) -> str:
    """Remove [n] citation markers and tidy the whitespace they leave behind
    (e.g. 'in 1971 [1].' -> 'in 1971.')."""
    s = _CITE.sub('', s or '')
    s = re.sub(r'\s+([.,;:!?])', r'\1', s)   # space before punctuation
    s = re.sub(r'\s{2,}', ' ', s)            # collapsed double spaces
    return s.strip()


def _attribute(answer_text: str, pages: List[Dict]) -> List[Dict]:
    """Build the `supports` list — per-sentence attribution — from the model's
    [n] citations, so the output carries the same per-sentence-source structure
    Gemini's groundingSupports gives. A sentence with no [n] marker gets no
    sources (honest: we could not attribute it)."""
    supports = []
    # Split into sentences, keeping the trailing citation markers with each.
    for sent in re.split(r'(?<=[.!?])\s+', (answer_text or '').strip()):
        sent = sent.strip()
        if not sent:
            continue
        idxs = [int(n) for n in _CITE.findall(sent)]
        srcs = []
        for n in idxs:
            if 1 <= n <= len(pages):
                p = pages[n - 1]
                srcs.append({'domain': p['domain'], 'url': p['url']})
        # Strip the citation markers from the displayed sentence text.
        clean = _strip_cites(sent)
        supports.append({'text': clean, 'sources': srcs})
    return supports


def serper_research(prompt: str, model: str = None, resolve: bool = True,
                    timeout: int = 90, grounded: bool = True,
                    *, serp: Optional[Callable] = None,
                    fetch: Optional[Callable] = None,
                    answer: Optional[Callable] = None,
                    max_queries: int = MAX_QUERIES,
                    max_pages: int = MAX_PAGES) -> Dict:
    """Answer a story-lead question with Serper + page fetch + a cheap model.

    Signature is call-compatible with `story_leads.gemini_with_sources` (same
    positional params: prompt, model, resolve, timeout, grounded) so the router
    can dispatch to either with identical arguments. `model` here names the CHEAP
    MODEL (default gpt-4.1-mini), not a Gemini model; `resolve`/`timeout`/
    `grounded` are accepted for signature parity (grounded is implied — this
    backend always does real retrieval).

    Returns the gemini_with_sources shape:
        {text, sources:[{domain,url}], supports:[{text,sources:[{domain,url}]}],
         queries:[str], error:str}

    `serp`/`fetch`/`answer` are injectable for tests (default to the metered
    project helpers). Never raises; failures land in out['error']."""
    out = _blank()
    answer = answer or _openai_chat
    cheap_model = model or RESEARCH_MODEL

    try:
        queries = derive_queries(prompt, max_queries=max_queries)
        if not queries:
            out['error'] = 'no queries derived from prompt'
            return out

        pages, used_queries = gather_pages(
            queries, max_pages=max_pages, serp=serp, fetch=fetch)
        out['queries'] = used_queries
        # De-duplicated source list, order preserved (mirrors gemini_with_sources).
        seen = set()
        for p in pages:
            if p['url'] and p['url'] not in seen:
                seen.add(p['url'])
                out['sources'].append({'domain': p['domain'], 'url': p['url']})

        if not pages:
            # No fetchable evidence. Honest empty answer — NOT a model guess.
            out['text'] = ''
            out['error'] = 'no pages fetched'
            return out

        sources_block = '\n\n'.join(
            f"[{i + 1}] {p['title']} ({p['domain']})\n{p['text']}"
            for i, p in enumerate(pages))
        ans = answer(_ANSWER_PROMPT.format(prompt=prompt, sources=sources_block),
                     model=cheap_model)
        if ans.get('error'):
            out['error'] = ans['error']
            return out

        text = (ans.get('text') or '').strip()
        if _NO_MATERIAL.lower() in text.lower() and len(text) < len(_NO_MATERIAL) + 10:
            # Model found nothing relevant in the fetched pages.
            out['text'] = ''
            return out

        out['text'] = _strip_cites(text)
        out['supports'] = _attribute(text, pages)
        return out
    except Exception as e:
        out['error'] = f'{type(e).__name__}: {e}'
        return out


# ── CLI: answer one prompt and print the result (for spot checks) ─────────────
if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Serper research backend (LOCAL-648)')
    ap.add_argument('prompt', help='the research request / story-lead question')
    ap.add_argument('--model', default=RESEARCH_MODEL)
    ap.add_argument('--max-queries', type=int, default=MAX_QUERIES)
    ap.add_argument('--max-pages', type=int, default=MAX_PAGES)
    a = ap.parse_args()
    t0 = time.time()
    res = serper_research(a.prompt, model=a.model,
                          max_queries=a.max_queries, max_pages=a.max_pages)
    dt = time.time() - t0
    print(json.dumps(res, indent=2, ensure_ascii=False))
    print(f"\n[{dt:.1f}s] queries={res['queries']} "
          f"sources={len(res['sources'])} error={res['error'] or 'none'}")
