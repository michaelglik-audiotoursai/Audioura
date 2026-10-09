"""tests/test_local648_serper_research.py — LOCAL-648.

Fully OFFLINE (serp/fetch/answer injected; no network, no paid calls). Proves:

  1. serper_research returns the EXACT gemini_with_sources shape
     ({text, sources, supports, queries, error}), with sources as {domain,url}
     and supports as {text, sources:[{domain,url}]}.
  2. Per-sentence [n] citations become supports[].sources, and the markers are
     stripped from the displayed text (no "1971 ." artefact).
  3. derive_queries pulls the quoted title + year and drops the instruction
     boilerplate ("Using Google Search").
  4. Honest-empty: no fetchable pages -> text '' and an error, never a guess;
     a NO MATERIAL FOUND model reply -> text ''.
  5. The RESEARCH_BACKEND router in story_leads dispatches to serper_research
     only when RESEARCH_BACKEND=serper AND grounded=True; default (gemini) and
     the ungrounded path call gemini_with_sources unchanged.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import serper_research as sr  # noqa: E402


PROMPT = ('Using Google Search, research the work "Le Lézard aux plumes d\'or" '
          'by Joan Miró at the Museum of Fine Arts, Boston, 1971, and cite your '
          'sources.')


def _serp(_q):
    return [
        {'title': 'MFA object page', 'url': 'https://mfa.org/collections/object/lezard',
         'snippet': 'Miró, 1971'},
        {'title': 'Wikipedia', 'url': 'https://en.wikipedia.org/wiki/Joan_Miro',
         'snippet': 'Spanish artist'},
    ]


def _fetch(url):
    if 'mfa.org' in url:
        return ('The Museum of Fine Arts, Boston holds Le Lezard aux plumes d or, '
                'a 1971 artist book by Joan Miro with text by Alfred Jarry. ') * 10
    return 'Joan Miro was a Spanish painter and sculptor born in 1893. ' * 10


def _answer(_prompt, model=None):
    return {'text': 'The MFA holds the 1971 artist book [1]. Miró was born in '
                    '1893 [2].', 'error': ''}


class SerperResearchShape(unittest.TestCase):
    def test_shape_matches_gemini_with_sources(self):
        res = sr.serper_research(PROMPT, serp=_serp, fetch=_fetch, answer=_answer)
        self.assertEqual(set(res.keys()),
                         {'text', 'sources', 'supports', 'queries', 'error'})
        self.assertEqual(res['error'], '')
        for s in res['sources']:
            self.assertEqual(set(s.keys()), {'domain', 'url'})
        for sp in res['supports']:
            self.assertEqual(set(sp.keys()), {'text', 'sources'})
            for s in sp['sources']:
                self.assertEqual(set(s.keys()), {'domain', 'url'})

    def test_citations_become_supports_and_are_stripped(self):
        res = sr.serper_research(PROMPT, serp=_serp, fetch=_fetch, answer=_answer)
        self.assertNotIn('[1]', res['text'])
        self.assertNotIn('[2]', res['text'])
        self.assertNotIn(' .', res['text'])  # no "1971 ." artefact
        # First sentence attributed to source [1] = the MFA page.
        self.assertTrue(res['supports'][0]['sources'])
        self.assertIn('mfa.org', res['supports'][0]['sources'][0]['url'])
        self.assertIn('wikipedia.org', res['supports'][1]['sources'][0]['url'])

    def test_derive_queries(self):
        qs = sr.derive_queries(PROMPT)
        self.assertTrue(qs)
        self.assertIn("Le Lézard aux plumes d'or 1971", qs[0])
        joined = ' | '.join(qs).lower()
        self.assertNotIn('using google search', joined)
        self.assertNotIn('google search', joined)

    def test_no_pages_is_honest_empty(self):
        res = sr.serper_research(PROMPT, serp=_serp,
                                 fetch=lambda u: '', answer=_answer)
        self.assertEqual(res['text'], '')
        self.assertTrue(res['error'])  # explains why (no pages fetched)

    def test_no_material_found_reply_is_empty(self):
        res = sr.serper_research(
            PROMPT, serp=_serp, fetch=_fetch,
            answer=lambda p, model=None: {'text': 'NO MATERIAL FOUND', 'error': ''})
        self.assertEqual(res['text'], '')

    def test_sources_deduped_preserve_order(self):
        def dup_serp(_q):
            return _serp(_q) + _serp(_q)  # same two urls twice
        res = sr.serper_research(PROMPT, serp=dup_serp, fetch=_fetch, answer=_answer)
        urls = [s['url'] for s in res['sources']]
        self.assertEqual(len(urls), len(set(urls)))


class ResearchBackendRouter(unittest.TestCase):
    """The router in story_leads dispatches by RESEARCH_BACKEND + grounded."""

    def setUp(self):
        import story_leads
        self.sl = story_leads
        self._saved_gws = story_leads.gemini_with_sources
        self._saved_env = os.environ.get('RESEARCH_BACKEND')
        self.calls = {'gemini': 0, 'serper': 0}

        def fake_gws(prompt, model=None, resolve=True, timeout=90, grounded=True):
            self.calls['gemini'] += 1
            return {'text': 'G', 'sources': [], 'supports': [], 'queries': [],
                    'error': ''}
        story_leads.gemini_with_sources = fake_gws

        # Patch the serper backend the router imports.
        self._saved_sr = sr.serper_research

        def fake_sr(prompt, model=None, resolve=True, timeout=90, grounded=True,
                    **kw):
            self.calls['serper'] += 1
            return {'text': 'S', 'sources': [], 'supports': [], 'queries': [],
                    'error': ''}
        sr.serper_research = fake_sr

    def tearDown(self):
        self.sl.gemini_with_sources = self._saved_gws
        sr.serper_research = self._saved_sr
        if self._saved_env is None:
            os.environ.pop('RESEARCH_BACKEND', None)
        else:
            os.environ['RESEARCH_BACKEND'] = self._saved_env

    def test_default_is_gemini(self):
        os.environ.pop('RESEARCH_BACKEND', None)
        out = self.sl.research_with_sources('q', grounded=True)
        self.assertEqual(out['text'], 'G')
        self.assertEqual(self.calls, {'gemini': 1, 'serper': 0})

    def test_serper_backend_routes_to_serper_when_grounded(self):
        os.environ['RESEARCH_BACKEND'] = 'serper'
        out = self.sl.research_with_sources('q', grounded=True)
        self.assertEqual(out['text'], 'S')
        self.assertEqual(self.calls, {'gemini': 0, 'serper': 1})

    def test_serper_backend_ungrounded_still_gemini(self):
        # An explicitly ungrounded call is class-knowledge; it must NOT pay for
        # retrieval. It stays on gemini_with_sources(grounded=False).
        os.environ['RESEARCH_BACKEND'] = 'serper'
        out = self.sl.research_with_sources('q', grounded=False)
        self.assertEqual(out['text'], 'G')
        self.assertEqual(self.calls, {'gemini': 1, 'serper': 0})

    def test_backend_name_helper(self):
        os.environ['RESEARCH_BACKEND'] = 'serper'
        self.assertEqual(self.sl.research_backend(), 'serper')
        os.environ['RESEARCH_BACKEND'] = 'GEMINI'
        self.assertEqual(self.sl.research_backend(), 'gemini')
        os.environ.pop('RESEARCH_BACKEND', None)
        self.assertEqual(self.sl.research_backend(), 'gemini')


if __name__ == '__main__':
    unittest.main(verbosity=2)
