#!/usr/bin/env python3
"""[LOCAL-565] serper_with_sources — shape parity with gemini_with_sources,
per-sentence attribution, and the drop-unsourced-sentence discipline.

Network is mocked: Serper search, page fetch, and the OpenAI reader/query model
are all stubbed, so the test is offline, deterministic, and free. It verifies the
CONTRACT the replay and scorer depend on, not any live engine behaviour.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault('SERP_API_KEY', 'test-key')  # presence only; search is mocked

import story_leads  # noqa: E402
import work_story_searcher  # noqa: E402


class SerperWithSourcesTest(unittest.TestCase):
    def setUp(self):
        self._orig_serp = work_story_searcher._serp_search
        self._orig_openai = story_leads._openai
        self._orig_fetch = story_leads._fetch_page_text

        # Two distinct-domain results per query.
        def fake_serp(q):
            return ([
                {'title': 'Official site', 'url': 'https://www.example-official.com/x',
                 'snippet': 'Open since 1984, no reservations.'},
                {'title': 'Review site', 'url': 'https://review.example-blog.com/y',
                 'snippet': 'A classic spot, first come first served.'},
            ], 12.0)

        def fake_fetch(url, timeout=12, max_length=6000):
            return f'Full page text for {url}. Open since 1984. No reservations taken.'

        def fake_openai(prompt, model='gpt-4o'):
            if 'turn a research request into web search queries' in prompt.lower() \
                    or 'output 1 to 3 google search queries' in prompt.lower():
                return 'example official hours\nexample reservations'
            # Reader: one sourced sentence, one UNSOURCED sentence (must be dropped).
            return ('The venue opened in 1984 [1]. '
                    'It is widely considered the best in town.')

        work_story_searcher._serp_search = fake_serp
        story_leads._fetch_page_text = fake_fetch
        story_leads._openai = fake_openai

    def tearDown(self):
        work_story_searcher._serp_search = self._orig_serp
        story_leads._openai = self._orig_openai
        story_leads._fetch_page_text = self._orig_fetch

    def test_shape_matches_gemini_with_sources(self):
        out = story_leads.serper_with_sources('When did the venue open?')
        # Same keys as gemini_with_sources.
        self.assertEqual(set(out.keys()),
                         {'text', 'sources', 'supports', 'queries', 'error'})
        self.assertEqual(out['error'], '')
        self.assertTrue(out['queries'])
        self.assertTrue(all('domain' in s and 'url' in s for s in out['sources']))
        self.assertTrue(all('text' in s and 'sources' in s for s in out['supports']))

    def test_unsourced_sentence_is_dropped(self):
        out = story_leads.serper_with_sources('When did the venue open?')
        self.assertIn('1984', out['text'])
        # The unsourced marketing sentence must not survive.
        self.assertNotIn('best in town', out['text'])
        # Exactly one sourced support, pointing at source [1].
        self.assertEqual(len(out['supports']), 1)
        self.assertEqual(out['supports'][0]['sources'][0]['domain'],
                         'example-official.com')

    def test_cost_lands_in_search_and_llm_buckets(self):
        import cost_accumulator
        import openai_cost_wrapper
        # Reader cost is auto-counted only via the HTTP wrapper; here _openai is
        # stubbed so llm is fed by search only. We assert the search bucket, which
        # serper_with_sources feeds directly.
        with cost_accumulator.tour_scope(job_id='t') as acc:
            story_leads.serper_with_sources('When did the venue open?')
            snap = acc.snapshot()
        self.assertGreater(snap['search']['queries'], 0)
        self.assertAlmostEqual(snap['search']['usd'],
                               snap['search']['queries'] * 0.001, places=6)

    def test_no_serp_key_returns_error_shape(self):
        saved = os.environ.pop('SERP_API_KEY', None)
        try:
            out = story_leads.serper_with_sources('x')
            self.assertEqual(out['error'], 'no SERP_API_KEY')
            self.assertEqual(out['text'], '')
        finally:
            if saved is not None:
                os.environ['SERP_API_KEY'] = saved

    def test_default_provider_is_gemini(self):
        saved = os.environ.pop('RESEARCH_PROVIDER', None)
        calls = {}
        orig = story_leads.gemini_with_sources
        story_leads.gemini_with_sources = lambda p, **k: calls.setdefault('g', True) or {}
        try:
            story_leads.research_with_sources('x')
            self.assertTrue(calls.get('g'), 'default provider must be gemini')
        finally:
            story_leads.gemini_with_sources = orig
            if saved is not None:
                os.environ['RESEARCH_PROVIDER'] = saved


if __name__ == '__main__':
    unittest.main(verbosity=2)
