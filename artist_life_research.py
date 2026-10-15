"""artist_life_research.py — LOCAL-692.

A research backend for MUSEUM stops that answers the per-stop story-lead question
with the ARTIST'S LIFE, not just the object's catalogue facts — at Serper prices.

WHY THIS EXISTS (D659 — Michael's listening verdict, 2026-10-14)
----------------------------------------------------------------
The HCMC Museum of Fine Arts cheap-arm tours (serper_research, LOCAL-648) were
"practically not even informative" — endurance, women's roles, national identity
— because that backend keys its queries on the OBJECT only (canonical_title /
artist / credit_line / year). It never asks WHO the artist is, where they lived,
where they learned, what changed their life, why they dedicated their life to
art, or the work's own story (commission, acquisition, what was shown instead).
Michael named those six questions and said generic themes put the listener to
sleep. He also said "using Wikipedia is a great mistake as it is too formal for
interesting stories."

WHAT THIS DOES DIFFERENTLY, in order (highest-signal first)
-----------------------------------------------------------
  1. ARTIST-LIFE WEB PAGES (Serper, the STORY source). Targeted queries about the
     PERSON — biography / "studied at" / "graduated" / turning point / "why I
     paint" / interview / where they lived and worked — in ENGLISH AND the
     venue's LOCAL LANGUAGE (Vietnamese for HCMC). Prefer interviews, artist
     profiles, museum/gallery/auction pages, news features and art magazines;
     SKIP SEO/listing/UGC domains (the exhibition_checklist blocklist).
  2. WORK-STORY WEB PAGES (Serper). The work's own story: commission, how the
     museum acquired it, exhibition history — reusing serper_research's proven
     object queries so object facts are not lost.
  3. WIKIPEDIA, FACT-CHECK ONLY (free). The artist's EN + local-language
     Wikipedia article is fetched for date/name verification, but every
     Wikipedia page is MARKED in the corpus ("[WIKIPEDIA — FACT-CHECK ONLY: use
     to verify dates/names, NOT as the story source]") and the extractor is told
     to treat it as a check, never as the narrative. This answers Michael's
     "Wikipedia is a mistake" directly: the human story must come from the web
     pages, Wikipedia only confirms a date or the spelling of a name.
  4. ONE EXTRACTOR over everything gathered. gpt-4.1-mini by default (the cheap
     arm's model), constrained to the gathered text — no parametric memory —
     told to LEAD with the person and a concrete moment (place, year, decision)
     and to answer the life questions it can, and to say so briefly when nothing
     human was found rather than pad with themes.

Returns the EXACT shape gemini_with_sources / serper_research return —
``{text, sources:[{domain,url}], supports:[{text,sources:[{domain,url}]}],
queries:[str], error:str}`` — so it is a drop-in anywhere a grounded
answer-with-sources is consumed. The ``supports`` list carries a per-sentence
``wikipedia`` flag derived from the cited page's origin, so a downstream reader
can tell which sentences lean on Wikipedia.

Every PAID call it makes (Serper queries, the OpenAI completion) goes out through
the project network meter; Wikipedia/Wikidata are free. NOTHING here runs unless
the museum research router selects it (MUSEUM_RESEARCH=artist_life, routed in
story_leads.research_with_sources for museum tours on the cheap arm). The default
never reaches this module, so default behaviour is byte-for-byte unchanged.
"""
import os
import re
import sys
import time
from typing import Callable, Dict, List, Optional, Tuple

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

# Reuse the LOCAL-648 object primitives and the LOCAL-674 Wikipedia primitives.
# artist_life is the museum sibling of serper_research + serper_plus_research,
# not a rewrite of their machinery.
import serper_research as _sr  # noqa: E402
import serper_plus_research as _spr  # noqa: E402


# ── tunables (env-overridable) ────────────────────────────────────────────────
EXTRACTOR_MODEL = os.environ.get('ARTIST_LIFE_EXTRACTOR', 'gpt-4.1-mini')
MAX_LIFE_QUERIES = int(os.environ.get('ARTIST_LIFE_MAX_LIFE_QUERIES', '4'))
MAX_WORK_QUERIES = int(os.environ.get('ARTIST_LIFE_MAX_WORK_QUERIES', '2'))
MAX_WEB_PAGES = int(os.environ.get('ARTIST_LIFE_MAX_PAGES', '6'))
PER_PAGE_CHARS = int(os.environ.get('ARTIST_LIFE_PER_PAGE_CHARS', '2800'))
WIKI_CHARS = int(os.environ.get('ARTIST_LIFE_WIKI_CHARS', '3500'))
# [LOCAL-692B / D659 addendum] Michael reverted the length increase: shorter
# stories "feel of the right size", so the extractor budget is the SHORT one
# (same as serper_research's object backend, 700), NOT the padded 900. The fix
# for a thin stop is a SECOND short story (the ladder/second-story path), never
# a longer first story.
ANSWER_MAX_TOKENS = int(os.environ.get('ARTIST_LIFE_MAX_TOKENS', '700'))

# A Wikipedia page is kept as a FACT-CHECK source only — never the story. This
# marker is prepended to its text in the corpus so the extractor can tell.
WIKI_MARK = ('[WIKIPEDIA — FACT-CHECK ONLY: use ONLY to verify dates and the '
             'spelling of names; do NOT take the story or any narrative from '
             'this source]')


def _blank() -> Dict:
    return {'text': '', 'sources': [], 'supports': [], 'queries': [], 'error': ''}


# ── 1. artist identity from the per-stop context block ────────────────────────

def _full_artist(ctx: dict) -> str:
    """The artist's FULL name as the catalogue gives it (diacritics intact, name
    order untouched). We do NOT reduce it to a surname here — for retrieval about
    a PERSON the full name is the stronger signal, and for a Vietnamese name the
    'surname' is the family name shared by millions, which retrieves noise."""
    v = (ctx.get('artist') or '').strip()
    # Drop a donor/credit verb if the field was mis-mapped, but keep the name.
    v = re.sub(r'^(gift|bequest|loan|promised gift)\s+of\s+', '', v,
               flags=re.IGNORECASE)
    v = v.split(';')[0].split('(')[0].strip(' .,;')
    return v


def _is_placeholder_artist(name: str) -> bool:
    """True when the artist field is empty or a non-name placeholder (unknown /
    anonymous / unattributed), so we must not run person queries on it."""
    n = (name or '').strip().lower()
    if not n:
        return True
    return any(p in n for p in (
        'unknown', 'anonymous', 'unattributed', 'not specified', 'n/a',
        'various', 'unidentified'))


# ── 2. the life + work query sets (English AND local language) ────────────────

# English life-question templates. {a} = artist full name. These map directly to
# Michael's six questions; kept short and quoted so Google acts on the name.
_LIFE_EN = [
    '"{a}" painter biography life',
    '"{a}" artist "studied at" OR graduated OR trained',
    '"{a}" interview OR "in his own words" OR "why" art',
    '"{a}" artist life story turning point',
]

# Vietnamese life-question templates (read via the translation path downstream;
# the extractor is multilingual). {a} = artist full name with diacritics.
_LIFE_VI = [
    '"{a}" tiểu sử họa sĩ cuộc đời',          # biography / painter / life
    '"{a}" học tại OR tốt nghiệp OR theo học',  # studied at / graduated / trained
]

# Local-language life templates by language code. Only 'vi' is needed for HCMC;
# others are best-effort and easily extended.
_LIFE_LOCAL = {
    'vi': _LIFE_VI,
}


def _life_queries(artist: str, local_code: str,
                  max_en: int = MAX_LIFE_QUERIES) -> List[str]:
    """Targeted artist-LIFE queries, English first then local language. The
    English set is capped at ``max_en``; the local set adds up to its own list.
    Deterministic and free (query strings only)."""
    out: List[str] = []
    for t in _LIFE_EN[:max_en]:
        out.append(t.format(a=artist))
    for t in _LIFE_LOCAL.get(local_code, []):
        out.append(t.format(a=artist))
    # de-dupe, preserve order
    seen, uniq = set(), []
    for q in out:
        k = re.sub(r'\s+', ' ', q).strip().lower()
        if k and k not in seen:
            seen.add(k)
            uniq.append(re.sub(r'\s+', ' ', q).strip())
    return uniq


def _work_queries(prompt: str, max_q: int = MAX_WORK_QUERIES) -> List[str]:
    """The work's own story: reuse serper_research.derive_queries (title+artist+
    year, title+venue, title+donor history) so object/acquisition facts are still
    gathered. Capped at ``max_q``."""
    try:
        return _sr.derive_queries(prompt, max_queries=max_q)
    except Exception:
        return []


# ── 3. gather pages: artist-life web + work web, skipping junk ────────────────

def _artist_is_wikipedia(url: str) -> bool:
    return 'wikipedia.org' in (url or '')


def gather_web(queries: List[str], max_pages: int,
               serp: Optional[Callable] = None,
               fetch: Optional[Callable] = None,
               origin: str = 'web') -> Tuple[List[Dict], List[str]]:
    """Run the queries, fetch the top usable pages (skip SEO/listing/UGC and
    Wikipedia — Wikipedia is fetched separately as fact-check only). Returns
    (pages, used_queries). `serp`/`fetch` injectable for tests."""
    serp = serp or _sr._default_serp
    fetch = fetch or _sr._fetch
    used: List[str] = []
    ranked: List[Dict] = []
    seen_urls = set()
    for q in queries:
        used.append(q)
        for r in serp(q):
            url = (r.get('url') or r.get('link') or '').strip()
            if not url or url in seen_urls:
                continue
            if _artist_is_wikipedia(url):
                continue  # fact-check pass fetches Wikipedia separately
            if not _spr._usable(url):
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
        pages.append({'origin': origin, 'domain': _sr._domain(r['url']),
                      'url': r['url'], 'title': r['title'],
                      'snippet': r['snippet'], 'text': text[:PER_PAGE_CHARS]})
    return pages, used


def gather_wikipedia_factcheck(artist: str, local_code: str,
                               wiki: Optional[Callable] = None) -> List[Dict]:
    """The artist's EN + local-language Wikipedia article, MARKED fact-check only.
    Reuses serper_plus_research.gather_wikipedia (free Wikidata+Wikipedia). Each
    returned page's text is prefixed with WIKI_MARK and origin set to
    'wikipedia_factcheck' so the extractor and the attribution step can tell."""
    if not artist:
        return []
    wiki = wiki or _spr.gather_wikipedia
    # gather_wikipedia takes (name, city); passing a city hint whose language we
    # know lets it pick the right local sitelink. We pass the local language's
    # own country token so _local_lang_from_city resolves to local_code.
    city_hint = {'vi': 'Vietnam'}.get(local_code, '')
    try:
        raw = wiki(artist, city_hint)
    except Exception:
        return []
    out: List[Dict] = []
    for p in raw or []:
        txt = (p.get('text') or '')[:WIKI_CHARS]
        if not txt:
            continue
        out.append({
            'origin': 'wikipedia_factcheck',
            'domain': p.get('domain', 'wikipedia.org'),
            'url': p.get('url', ''),
            'title': p.get('title', ''),
            'snippet': '',
            'text': f'{WIKI_MARK}\n{txt}',
        })
    return out


# ── 4. the extractor prompt (person-first, life questions, honest when empty) ─

_ANSWER_PROMPT = """\
You are a museum-tour researcher writing the raw facts a tour writer will turn \
into one stop about a work of art and the ARTIST who made it. Use ONLY the \
numbered SOURCES below. Do NOT use any prior knowledge: if a fact is not in the \
sources, do not state it.

Your job is to tell the LISTENER who this artist is as a PERSON. In 4-6 short \
sentences (keep it SHORT — a shorter story is the right size), LEAD with the \
person and a concrete moment — a place, a year, a decision — then connect it to \
the work. Prefer facts that answer these \
questions, in roughly this priority:
  1. Where did the artist live and work?
  2. Where did they learn / who trained them (school, teacher, "studied at", \
"graduated")?
  3. What changed their life — a turning point, a move, a war, a meeting?
  4. Why did they dedicate their life to art (motivation, in their own words)?
  5. The work's own story: why it was made, how the museum acquired it, when it \
was first shown.

RULES:
- A source marked "{wiki_mark_short}" is for VERIFICATION ONLY. You may use it \
to confirm a date or the spelling of a name, but you must NOT take the story, a \
quote, or any narrative sentence from it. The human story must come from the \
other sources.
- Do NOT write generic themes (resilience, endurance, women's roles, national \
identity, cultural memory) UNLESS you tie them to a concrete, sourced event in \
this artist's life.
- If the sources contain nothing human about the artist, say so in ONE sentence \
(e.g. "The sources give little about the artist's life.") and spend the rest on \
the work's own documented story. Never pad with themes.
- End EVERY sentence with the number of the source it came from, in brackets, \
like [2]. If the sources contain nothing relevant at all, reply with exactly: \
NO MATERIAL FOUND

RESEARCH REQUEST:
{prompt}

SOURCES:
{sources}
"""


def _answer(prompt: str, model: str, max_tokens: int = ANSWER_MAX_TOKENS) -> Dict:
    return _sr._openai_chat(prompt, model=model, max_tokens=max_tokens)


def _attribute_with_wiki(answer_text: str, pages: List[Dict]) -> List[Dict]:
    """Like serper_research._attribute, but also tag each support with whether
    its cited source(s) are Wikipedia fact-check pages, so a downstream reader can
    see which sentences lean on Wikipedia."""
    supports = _sr._attribute(answer_text, pages)
    # _sr._attribute returns [{text, sources:[{domain,url}]}]; add the flag.
    wiki_urls = {p['url'] for p in pages
                 if p.get('origin') == 'wikipedia_factcheck' and p.get('url')}
    for s in supports:
        s['wikipedia'] = any(src.get('url') in wiki_urls
                             for src in s.get('sources', []))
    return supports


@_sub_timed('artist_life_research')
def artist_life_research(prompt: str, model: str = None, resolve: bool = True,
                         timeout: int = 90, grounded: bool = True,
                         *, serp: Optional[Callable] = None,
                         fetch: Optional[Callable] = None,
                         answer: Optional[Callable] = None,
                         wiki: Optional[Callable] = None) -> Dict:
    """Answer a museum per-stop story-lead question with ARTIST-LIFE research.

    Call-compatible with story_leads.gemini_with_sources / serper_research (same
    positional params), returns the same shape. `model` names the EXTRACTOR model
    (default gpt-4.1-mini, or ARTIST_LIFE_EXTRACTOR). Injectables are for tests.
    Never raises; failures land in out['error'].

    When the stop has no attributable artist (unknown/anonymous), it falls back
    to the plain object research (serper_research) so the stop is still grounded.
    """
    out = _blank()
    extractor = model or EXTRACTOR_MODEL
    answer = answer or _answer

    try:
        ctx = _sr._parse_context(prompt)
        artist = _full_artist(ctx)
        venue = (ctx.get('venue_name') or '').strip()
        # Local language from the venue/city string (vietnam -> 'vi').
        local_code = _spr._local_lang_from_city(venue) or \
            _spr._local_lang_from_city(prompt)

        if _is_placeholder_artist(artist):
            # No real person to research — defer to the object backend so the stop
            # is still grounded (it will not invent an artist).
            return _sr.serper_research(
                prompt, model=model, resolve=resolve, timeout=timeout,
                grounded=grounded, serp=serp, fetch=fetch, answer=answer)

        life_q = _life_queries(artist, local_code)
        work_q = _work_queries(prompt)

        pages: List[Dict] = []
        # 1. artist-life web pages (the STORY source) — majority of the budget.
        life_budget = max(1, MAX_WEB_PAGES - MAX_WORK_QUERIES)
        life_pages, used_life = gather_web(
            life_q, life_budget, serp=serp, fetch=fetch, origin='artist_life')
        pages.extend(life_pages)
        out['queries'].extend(used_life)
        # 2. work-story web pages — remaining budget.
        work_pages, used_work = gather_web(
            work_q, MAX_WEB_PAGES - len(pages), serp=serp, fetch=fetch,
            origin='work_story')
        pages.extend(work_pages)
        out['queries'].extend(used_work)
        # 3. Wikipedia, fact-check only (free).
        wiki_pages = gather_wikipedia_factcheck(artist, local_code, wiki=wiki)
        pages.extend(wiki_pages)

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
        ans = answer(_ANSWER_PROMPT.format(
            prompt=prompt, sources=sources_block,
            wiki_mark_short='WIKIPEDIA — FACT-CHECK ONLY'), extractor)
        if ans.get('error'):
            out['error'] = ans['error']
            return out
        text = (ans.get('text') or '').strip()
        if _sr._NO_MATERIAL.lower() in text.lower() \
                and len(text) < len(_sr._NO_MATERIAL) + 10:
            out['text'] = ''
            return out
        out['text'] = _sr._strip_cites(text)
        out['supports'] = _attribute_with_wiki(text, pages)
        return out
    except Exception as e:
        out['error'] = f'{type(e).__name__}: {e}'
        return out


# ── CLI: answer one prompt and print the result (for spot checks) ─────────────
if __name__ == '__main__':
    import argparse
    import json
    ap = argparse.ArgumentParser(description='artist-life museum research (LOCAL-692)')
    ap.add_argument('prompt', help='the research request / story-lead question')
    ap.add_argument('--model', default=EXTRACTOR_MODEL)
    a = ap.parse_args()
    t0 = time.time()
    res = artist_life_research(a.prompt, model=a.model)
    dt = time.time() - t0
    print(json.dumps(res, indent=2, ensure_ascii=False))
    print(f"\n[{dt:.1f}s] queries={res['queries']} sources={len(res['sources'])} "
          f"error={res['error'] or 'none'}")
