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

# ── [LOCAL-692B / D659 addendum] THE STORY-SOURCE LADDER ──────────────────────
# Michael corrected LOCAL-692: do not "say so briefly" when nothing human is
# found. Instead KEEP SEARCHING down a ladder of story sources until an
# emotionally-charged story — a decision, a loss, a conflict, a surprise — is
# found, then write the stop. The rungs for a museum stop, highest-signal first:
#
#     1. exhibit  — the EXHIBIT'S OWN story (the work: commission, acquisition,
#                   what was shown instead, controversy, theft, destruction).
#     2. artist   — the ARTIST'S life (where they learned, a turning point, why).
#     3. museum   — the MUSEUM'S own story (its founding, a famous episode).
#     4. culture  — the CULTURE/COUNTRY story the work belongs to.
#
# We walk DOWN the rungs, adding queries (and other languages), until the
# extractor returns a story the charge-detector judges emotionally charged, OR
# the EXTRA-QUERY CAP (MAX_EXTRA_QUERIES beyond the first rung's base queries)
# is reached. The rung the story came from is returned as out['rung'] and logged.
MAX_EXTRA_QUERIES = int(os.environ.get('ARTIST_LIFE_MAX_EXTRA_QUERIES', '6'))

# Words that signal an emotionally-charged story: a DECISION, a LOSS, a CONFLICT,
# or a SURPRISE (Michael's four). Deterministic, multilingual-friendly (English
# + a few Vietnamese tokens, since local-language pages are read). If the
# extracted story contains one of these in a sourced sentence, the ladder stops.
_CHARGE_WORDS = re.compile(
    r"(?i)\b("
    # decision / defiance
    r"decided|refused|chose|vowed|insisted|defied|rejected|abandoned|"
    r"gave up|turned down|resolved|secretly|"
    # loss / death / hardship
    r"died|death|lost|destroyed|burned|burnt|grief|mourning|exile|exiled|"
    r"fled|imprisoned|arrested|war|wounded|poverty|starv|illness|widow|orphan|"
    # conflict
    r"banned|censored|accused|betrayed|rival|quarrel|dispute|conflict|"
    r"persecut|forbidden|clash|"
    # surprise / reversal
    r"surprise|unexpected|discovered|hidden|turned out|only later|against all|"
    r"miracle|rediscovered|forgotten|"
    # Vietnamese tokens for the same (local-language pages)
    r"quyết định|từ chối|chiến tranh|lưu vong|qua đời|mất|bị bắt"
    r")\b")


def _is_emotionally_charged(text: str) -> bool:
    """True when the extracted story carries at least one marker of a decision,
    a loss, a conflict, or a surprise (Michael's four). Pure/deterministic."""
    if not text or len(text.strip()) < 40:
        return False
    return bool(_CHARGE_WORDS.search(text))


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


# ── [LOCAL-692B] rung query builders: exhibit / museum / culture-country ──────

def _exhibit_story_queries(title: str, artist: str, local_code: str,
                           max_q: int = 2) -> List[str]:
    """RUNG 1 — the EXHIBIT'S OWN story: the work's commission, controversy,
    theft, destruction, what was shown instead, how it was acquired. Charged
    angles first (these are the ones that carry a decision/loss/conflict)."""
    if not title:
        return []
    t = title.split('(')[0].strip()
    out = [
        f'"{t}" controversy OR destroyed OR refused OR scandal OR stolen',
        f'"{t}" {artist} why painted OR commission OR story'.strip(),
    ]
    if local_code == 'vi':
        out.append(f'"{t}" câu chuyện OR tranh cãi')  # story / controversy
    return out[:max_q]


def _museum_story_queries(venue: str, max_q: int = 2) -> List[str]:
    """RUNG 3 — the MUSEUM'S own story: founding, a famous episode, a dramatic
    moment in its history (wartime, a theft, a bequest)."""
    v = (venue or '').split(',')[0].strip()
    if not v:
        return []
    out = [
        f'"{v}" history founded story OR war OR theft OR bequest',
        f'"{v}" famous episode OR dramatic OR saved',
    ]
    return out[:max_q]


def _culture_country_queries(ctx: dict, local_code: str, max_q: int = 2) -> List[str]:
    """RUNG 4 — the CULTURE/COUNTRY story the work belongs to: the tradition,
    the moment in the country's art history, the human stakes behind the form
    (e.g. Vietnamese lacquer during the war). Last resort on the ladder."""
    venue = (ctx.get('venue_name') or '')
    medium = (ctx.get('medium') or ctx.get('canonical_title') or '')
    country = ''
    for tok in ('Vietnam', 'France', 'Italy', 'Japan', 'China', 'Spain',
                'Boston', 'USA'):
        if tok.lower() in (venue + ' ' + medium).lower():
            country = tok
            break
    base = (medium.split('(')[0].strip() or 'art')
    out = [
        f'{country} {base} tradition history war struggle story'.strip(),
        f'{country} artists {base} hardship OR exile OR revolution'.strip(),
    ]
    return out[:max_q]


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
    """Answer a museum per-stop story-lead question with ARTIST-LIFE research,
    walking the STORY-SOURCE LADDER (LOCAL-692B / D659 addendum).

    Call-compatible with story_leads.gemini_with_sources / serper_research (same
    positional params), returns the same shape PLUS three extra keys:
      out['rung']          which ladder rung the story came from
                           ('exhibit' | 'artist' | 'museum' | 'culture' | '')
      out['extra_queries'] how many EXTRA queries (beyond the first two rungs)
                           the ladder walk spent (<= MAX_EXTRA_QUERIES)
      out['second_story']  an optional short SECOND story (LOCAL-692B), '' if none

    The ladder walks DOWN the rungs — exhibit's own story > artist > museum >
    culture/country — re-running the extractor as sources accumulate, and STOPS
    as soon as the extracted story is emotionally charged (a decision, a loss, a
    conflict, a surprise), or when the extra-query cap is reached. `model` names
    the EXTRACTOR model (default gpt-4.1-mini). Injectables are for tests. Never
    raises; failures land in out['error'].

    When the stop has no attributable artist (unknown/anonymous), it falls back
    to the plain object research (serper_research) so the stop is still grounded.
    """
    out = _blank()
    out['rung'] = ''
    out['extra_queries'] = 0
    out['second_story'] = ''
    extractor = model or EXTRACTOR_MODEL
    answer = answer or _answer

    def _extract(pages: List[Dict]) -> Dict:
        """Run the extractor over the accumulated pages; return {text, supports,
        error}. Keeps the fact-check / person-first prompt."""
        if not pages:
            return {'text': '', 'supports': [], 'error': 'no pages gathered'}
        sources_block = '\n\n'.join(
            f"[{i + 1}] {p.get('title', '')} ({p['domain']})\n{p['text']}"
            for i, p in enumerate(pages))
        ans = answer(_ANSWER_PROMPT.format(
            prompt=prompt, sources=sources_block,
            wiki_mark_short='WIKIPEDIA — FACT-CHECK ONLY'), extractor)
        if ans.get('error'):
            return {'text': '', 'supports': [], 'error': ans['error']}
        text = (ans.get('text') or '').strip()
        if _sr._NO_MATERIAL.lower() in text.lower() \
                and len(text) < len(_sr._NO_MATERIAL) + 10:
            return {'text': '', 'supports': [], 'error': ''}
        return {'text': text, 'supports': _attribute_with_wiki(text, pages),
                'error': ''}

    try:
        ctx = _sr._parse_context(prompt)
        artist = _full_artist(ctx)
        venue = (ctx.get('venue_name') or '').strip()
        title = (ctx.get('canonical_title') or '').strip()
        # Local language from the venue/city string (vietnam -> 'vi').
        local_code = _spr._local_lang_from_city(venue) or \
            _spr._local_lang_from_city(prompt)

        if _is_placeholder_artist(artist):
            # No real person to research — defer to the object backend so the stop
            # is still grounded (it will not invent an artist). Only the exhibit
            # rung is meaningful; mark it so the caller can log.
            res = _sr.serper_research(
                prompt, model=model, resolve=resolve, timeout=timeout,
                grounded=grounded, serp=serp, fetch=fetch, answer=answer)
            if isinstance(res, dict):
                res.setdefault('rung', 'exhibit')
                res.setdefault('extra_queries', 0)
                res.setdefault('second_story', '')
            return res

        # Wikipedia (free, fact-check only) is gathered ONCE up front and kept in
        # the corpus on every rung — it only verifies dates/names, never the story.
        wiki_pages = gather_wikipedia_factcheck(artist, local_code, wiki=wiki)

        # ── the ladder: (rung name, query list, is_base) ─────────────────────
        # The first two rungs (exhibit + artist) are the BASE search — the normal
        # LOCAL-692 research. Rungs 3-4 (museum, culture) are the EXTRA search
        # Michael asked for: we only descend to them when nothing charged has
        # been found yet, and every query they issue counts toward the cap.
        rungs = [
            ('exhibit', _exhibit_story_queries(title, artist, local_code)
                        + _work_queries(prompt), True),
            ('artist', _life_queries(artist, local_code), True),
            ('museum', _museum_story_queries(venue), False),
            ('culture', _culture_country_queries(ctx, local_code), False),
        ]

        pages: List[Dict] = []
        best = {'text': '', 'supports': [], 'rung': ''}
        extra_queries = 0
        chosen_rung = ''

        for rung_name, queries, is_base in rungs:
            if not queries:
                continue
            # Enforce the extra-query cap on the NON-base rungs: trim the rung's
            # queries so the running extra total never exceeds MAX_EXTRA_QUERIES.
            if not is_base:
                remaining = MAX_EXTRA_QUERIES - extra_queries
                if remaining <= 0:
                    break  # cap reached — stop descending
                queries = queries[:remaining]

            budget = max(1, MAX_WEB_PAGES - len(pages))
            new_pages, used = gather_web(
                queries, budget, serp=serp, fetch=fetch, origin=rung_name)
            pages.extend(new_pages)
            out['queries'].extend(used)
            if not is_base:
                extra_queries += len(used)

            # Extract over everything gathered so far (+ Wikipedia fact-check).
            res = _extract(pages + wiki_pages)
            if res['error'] and not best['text']:
                # Remember the error only if we have nothing better yet.
                out['error'] = res['error']
            if res['text']:
                # Keep the most recent non-empty story; prefer a charged one.
                if _is_emotionally_charged(res['text']):
                    best = {'text': res['text'], 'supports': res['supports'],
                            'rung': rung_name}
                    chosen_rung = rung_name
                    out['error'] = ''
                    break  # found a charged story — stop walking the ladder
                if not best['text']:
                    best = {'text': res['text'], 'supports': res['supports'],
                            'rung': rung_name}
                    out['error'] = ''

        # De-duplicated source list, order preserved (all rungs + Wikipedia).
        seen = set()
        for p in pages + wiki_pages:
            if p['url'] and p['url'] not in seen:
                seen.add(p['url'])
                out['sources'].append({'domain': p['domain'], 'url': p['url']})

        out['text'] = _sr._strip_cites(best['text']) if best['text'] else ''
        out['supports'] = best['supports']
        out['rung'] = chosen_rung or best['rung']
        out['extra_queries'] = extra_queries

        # ── [LOCAL-692B] SECOND STORY. When the sources also carry a DISTINCT
        # charged story (a different person/episode than the one just written),
        # extract it as a SHORT add-on — this is how a thin stop gets "one more
        # story" WITHOUT lengthening the first. No extra queries are spent.
        if out['text']:
            out['second_story'] = _extract_second_story(
                pages + wiki_pages, out['text'], answer, extractor)
        return out
    except Exception as e:
        out['error'] = f'{type(e).__name__}: {e}'
        return out


# ── [LOCAL-692B] second short story (no lengthening of the first) ─────────────

_SECOND_STORY_PROMPT = """\
You are a museum-tour researcher. The tour already has this story for the stop:

FIRST STORY (already written, do NOT repeat it):
{first}

Using ONLY the numbered SOURCES below, find ONE MORE short, emotionally charged \
story — a decision, a loss, a conflict, or a surprise — that is DISTINCT from \
the first story (a different person, episode, or moment). Write it in 1-3 short \
sentences, each ending with its source number in brackets like [2]. A source \
marked "WIKIPEDIA — FACT-CHECK ONLY" may be used only to confirm a date or a \
name, never as the story. If there is no distinct second story in the sources, \
reply with exactly: NO SECOND STORY

SOURCES:
{sources}
"""


def _extract_second_story(pages: List[Dict], first_story: str,
                          answer: Callable, extractor: str) -> str:
    """Ask for ONE distinct, charged second story from the SAME gathered pages
    (no new queries). Returns '' when none is found or it is not charged. Pure
    add-on: it never touches the first story."""
    try:
        if not pages or not first_story:
            return ''
        sources_block = '\n\n'.join(
            f"[{i + 1}] {p.get('title', '')} ({p['domain']})\n{p['text']}"
            for i, p in enumerate(pages))
        ans = answer(_SECOND_STORY_PROMPT.format(
            first=first_story[:800], sources=sources_block), extractor)
        if not isinstance(ans, dict) or ans.get('error'):
            return ''
        text = (ans.get('text') or '').strip()
        if not text or 'no second story' in text.lower():
            return ''
        # Only keep it if it is itself charged and not a near-duplicate of #1.
        if not _is_emotionally_charged(text):
            return ''
        if _too_similar(text, first_story):
            return ''
        return _sr._strip_cites(text)
    except Exception:
        return ''


def _too_similar(a: str, b: str) -> bool:
    """True when `a` substantially overlaps `b` (so a 'second story' that merely
    restates the first is rejected). Token-set Jaccard on content words >= 0.5."""
    def _toks(s):
        return {w for w in re.findall(r"[A-Za-zÀ-ỹ']{4,}", (s or '').lower())}
    ta, tb = _toks(a), _toks(b)
    if not ta:
        return True
    inter = len(ta & tb)
    return inter / max(1, len(ta)) >= 0.5


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
