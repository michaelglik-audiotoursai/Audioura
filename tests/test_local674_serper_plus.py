"""tests/test_local674_serper_plus.py — LOCAL-674 serper_plus walking backend.

Offline, no network, no cost: every external call (Wikipedia/Wikidata, Serper,
page fetch, OpenAI extractor, news) is injected as a stub. Locks in:

  * place-query derivation (history + official site, no object keywords);
  * the current-affairs news trigger (fires on 'recent/renovation/2025…', not on
    a purely historic prompt);
  * local-language selection (only for a non-English locale);
  * SEO/listing/UGC domains are dropped and Wikipedia is fetched separately;
  * the gemini_with_sources output shape (text, sources, supports, queries);
  * the WALKING_RESEARCH router in story_leads dispatches correctly and is
    DEFAULT-SAFE (unset/gemini and non-walking categories are untouched).
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import serper_plus_research as sp  # noqa: E402


_PROMPT = (
    'What story about "Old State House"?\n\n'
    'Context — the work this concerns:\n'
    '  canonical_title: Old State House\n'
    '  venue_name: Old State House\n'
    'Exhibition: Boston, Massachusetts, United States\n\n'
    'Search, then answer with FACTS ONLY.'
)


def _wiki_stub(name='', city=''):
    return [{'origin': 'wikipedia_en', 'domain': 'en.wikipedia.org',
             'url': 'https://en.wikipedia.org/wiki/Old_State_House_(Boston)',
             'title': 'Old State House — Wikipedia',
             'text': ('The Old State House was built in 1713. In 1770 the Boston '
                      'Massacre occurred in front of it, killing five colonists.')}]


def _serp_stub(q):
    return [{'title': 'Official', 'url': 'https://www.bostonhistory.org/osh',
             'snippet': 's'},
            {'title': 'junk', 'url': 'https://www.tripadvisor.com/x', 'snippet': 'y'}]


def _fetch_stub(url):
    if 'bostonhistory' in url:
        return ('The Bostonian Society, founded in 1881, saved the building from '
                'demolition and reopened it in 1882 after a careful restoration.')
    return ''


def _answer_stub(prompt, model, max_tokens=750):
    # The SEO page must have been dropped; Wikipedia + official must be present.
    assert 'tripadvisor' not in prompt
    assert 'Boston Massacre' in prompt
    assert 'Bostonian Society' in prompt
    return {'text': ('The Old State House was built in 1713 [1]. In 1770 the Boston '
                     'Massacre killed five colonists in front of it [1]. The '
                     'Bostonian Society reopened it in 1882 [2].'),
            'error': ''}


def test_place_queries_are_place_oriented():
    qs = sp._derive_place_queries('Boston City Hall', 'Boston, MA', 2)
    assert len(qs) == 2
    assert any('history' in q for q in qs)
    assert any('official' in q for q in qs)
    assert all('Boston City Hall' in q for q in qs)


def test_news_trigger():
    assert sp._needs_news('a recent renovation reopened it', 'x') is True
    assert sp._needs_news('a 2025 restoration', 'x') is True
    assert sp._needs_news('built in 1713, a historic hall', 'x') is False


def test_local_language_only_for_foreign_locale():
    assert sp._local_lang_from_city('Nice, France') == 'fr'
    assert sp._local_lang_from_city('Ho Chi Minh City, Vietnam') == 'vi'
    assert sp._local_lang_from_city('Boston, Massachusetts') == ''


def test_usable_drops_seo_and_ugc():
    assert sp._usable('https://www.tripadvisor.com/x') is False
    assert sp._usable('https://www.reddit.com/r/x') is False
    assert sp._usable('https://www.bostonhistory.org/osh') is True


def test_full_pipeline_shape_and_source_dedup():
    out = sp.serper_plus_research(_PROMPT, serp=_serp_stub, fetch=_fetch_stub,
                                  answer=_answer_stub, wiki=_wiki_stub)
    assert out['error'] == ''
    # Two sources: Wikipedia EN + the official site; the SEO page is gone.
    doms = {s['domain'] for s in out['sources']}
    assert 'en.wikipedia.org' in doms
    assert 'bostonhistory.org' in doms
    assert 'tripadvisor.com' not in doms
    # Output shape matches gemini_with_sources.
    assert set(out.keys()) == {'text', 'sources', 'supports', 'queries', 'error'}
    assert len(out['supports']) == 3
    # No citation markers leak into the displayed text.
    assert '[1]' not in out['text'] and '[2]' not in out['text']


def test_news_pass_adds_a_source_when_current_affairs():
    def news_stub(name, city, **kw):
        return ([{'origin': 'news', 'domain': 'bostonglobe.com',
                  'url': 'https://bostonglobe.com/a', 'title': 't', 'snippet': 's',
                  'text': ('In 2025 the hall reopened after a two-year renovation '
                           'that cost 12 million dollars.')}], ['faneuil news'])

    prompt = _PROMPT.replace('Search, then answer with FACTS ONLY.',
                             'Note any recent renovation. FACTS ONLY.')
    out = sp.serper_plus_research(prompt, serp=_serp_stub, fetch=_fetch_stub,
                                  answer=_answer_stub, wiki=_wiki_stub,
                                  news=news_stub)
    assert any(s['domain'] == 'bostonglobe.com' for s in out['sources'])
    assert 'faneuil news' in out['queries']


def test_no_pages_is_honest_empty():
    out = sp.serper_plus_research(_PROMPT, serp=lambda q: [], fetch=lambda u: '',
                                  answer=_answer_stub, wiki=lambda n, c: [])
    assert out['text'] == ''
    assert out['error'] == 'no pages gathered'


# ── router: WALKING_RESEARCH dispatch + default safety ───────────────────────
def test_router_walking_research_dispatch(monkeypatch=None):
    import story_leads as sl
    import cheap_arm as ca

    def _set(wr):
        if wr is None:
            os.environ.pop('WALKING_RESEARCH', None)
        else:
            os.environ['WALKING_RESEARCH'] = wr

    cases = [
        ('serper_plus', 'walking', 'serper_plus'),
        ('serper_plus', 'museum', ''),       # non-walking untouched
        ('gemini_per_venue', 'walking', 'gemini_per_venue'),
        ('gemini', 'walking', ''),           # explicit default = unchanged
        (None, 'walking', ''),               # unset = unchanged
        ('serper_plus', '', 'serper_plus'),  # unknown category + flag set
        ('bogus', 'walking', ''),            # unrecognised value ignored
    ]
    for wr, cat, expect in cases:
        _set(wr)
        tok = ca.set_tour_category(cat)
        try:
            assert sl.walking_research_backend() == expect, (wr, cat)
            assert sl.walking_gemini_per_venue_selected() == (expect == 'gemini_per_venue')
        finally:
            ca.reset_tour_category(tok)
    os.environ.pop('WALKING_RESEARCH', None)


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print(f'ok  {name}')
    print('all serper_plus tests passed')
