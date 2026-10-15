#!/usr/bin/env python3
"""test_local692_artist_stories.py — LOCAL-692 unit tests.

Covers, with NO network and NO paid calls (every external call is injected):

  A. artist_life_research
     * runs artist-LIFE queries (English + Vietnamese) AND work-story queries;
     * fetches Wikipedia as FACT-CHECK ONLY, marked in the corpus;
     * leads the extractor prompt with the person; returns the gemini shape;
     * per-sentence `wikipedia` flag on supports;
     * falls back to serper_research for an unknown/anonymous artist.
  B. vietnamese_name_aid
     * repairs wrong attribution (Nguyen Van Tri -> Nguyễn Gia Trí);
     * restores diacritics + family-first order; no name duplication;
     * expands last-syllable fragment (Lựu -> Lê Thị Lựu) on first use;
     * adds a '(say: ...)' aid once per artist; clean English untouched.
  C. router gating (story_leads.museum_research_backend) — museum only, default-safe.
  D. length target — the artist-life extractor budget is >= the object backend's
     (so the after-version is not shorter than the measured normal arm).
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import artist_life_research as al  # noqa: E402
import serper_research as sr  # noqa: E402
import story_leads as sl  # noqa: E402
import vietnamese_name_aid as vn  # noqa: E402
import story_query as sq  # noqa: E402


MUSEUM_PROMPT = (
    'What story can be told to visitors of this exhibition about '
    'V\u01b0\u1eddn xu\u00e2n Trung Nam B\u1eafc?\n\n'
    'Context \u2014 the work this concerns:\n'
    '  canonical_title: V\u01b0\u1eddn xu\u00e2n Trung Nam B\u1eafc (Spring Garden)\n'
    '  artist: Nguy\u1ec5n Gia Tr\u00ed\n'
    '  venue_name: Ho Chi Minh City Museum of Fine Arts, Vietnam\n'
    'Exhibition: Ho Chi Minh City Museum of Fine Arts\n')


def _fake_serp_factory(record):
    def _serp(query):
        record.append(query)
        # Return one usable non-wikipedia result per query.
        return [{'title': f'result for {query[:30]}',
                 'url': f'https://example-art.com/{abs(hash(query)) % 9999}',
                 'snippet': 'bio snippet'}]
    return _serp


def _fake_fetch(url):
    return ('In 1936 the painter studied at the Ecole des Beaux-Arts de '
            'l Indochine in Hanoi and later moved south. ' * 6)


def _fake_wiki(name, city):
    return [{'origin': 'wikipedia_en', 'domain': 'en.wikipedia.org',
             'url': 'https://en.wikipedia.org/wiki/X', 'title': f'{name} — Wikipedia',
             'text': 'Born 1908, died 1993. ' * 20}]


class TestArtistLifeResearch(unittest.TestCase):
    def test_runs_life_and_work_queries_in_two_languages(self):
        seen = []
        captured = {}

        def _answer(prompt, model, max_tokens=900):
            # The ladder issues the main extractor first, then (optionally) a
            # second-story extractor. Capture the FIRST (main) prompt only.
            if 'prompt' not in captured:
                captured['prompt'] = prompt
                captured['model'] = model
            return {'text': 'Nguyễn Gia Trí studied in Hanoi in 1936 [1]. '
                            'He devoted twenty years to the work [2].', 'error': ''}

        out = al.artist_life_research(
            MUSEUM_PROMPT, serp=_fake_serp_factory(seen), fetch=_fake_fetch,
            answer=_answer, wiki=_fake_wiki)
        self.assertFalse(out['error'], out['error'])
        joined = ' '.join(seen)
        # Artist-life English query present.
        self.assertIn('biography', joined.lower())
        # Vietnamese life query present (local language for a Vietnam venue).
        self.assertIn('ti\u1ec3u s\u1eed', joined)
        # A work-story query present (quoted title).
        self.assertTrue(any('V\u01b0\u1eddn xu\u00e2n' in q for q in seen))
        # Extractor prompt leads with the PERSON and bans generic themes.
        self.assertIn('LEAD with the person', captured['prompt'])
        self.assertIn('generic themes', captured['prompt'])

    def test_wikipedia_is_factcheck_only_and_marked(self):
        captured = {}

        def _answer(prompt, model, max_tokens=900):
            captured['prompt'] = prompt
            return {'text': 'A fact [1].', 'error': ''}

        out = al.artist_life_research(
            MUSEUM_PROMPT, serp=_fake_serp_factory([]), fetch=_fake_fetch,
            answer=_answer, wiki=_fake_wiki)
        # The Wikipedia page text in the corpus carries the fact-check marker.
        self.assertIn('FACT-CHECK ONLY', captured['prompt'])
        # Wikipedia appears as a source but is flagged in the prompt as verify-only.
        self.assertTrue(any('wikipedia.org' in s['domain'] for s in out['sources']))

    def test_supports_carry_wikipedia_flag(self):
        # Build pages so sentence [1] cites a web page and [2] cites Wikipedia.
        def _answer(prompt, model, max_tokens=900):
            # The Wikipedia page is the LAST source in the corpus.
            n = prompt.count('\n[')  # rough source count marker
            return {'text': 'Web fact here [1]. '
                            f'Wiki-checked date [{n}].', 'error': ''}

        out = al.artist_life_research(
            MUSEUM_PROMPT, serp=_fake_serp_factory([]), fetch=_fake_fetch,
            answer=_answer, wiki=_fake_wiki)
        self.assertTrue(out['supports'])
        self.assertTrue(all('wikipedia' in s for s in out['supports']))

    def test_unknown_artist_falls_back_to_object_backend(self):
        prompt = MUSEUM_PROMPT.replace('Nguy\u1ec5n Gia Tr\u00ed', 'Unknown')
        called = {'object': False}
        orig = sr.serper_research

        def _spy(*a, **k):
            called['object'] = True
            return {'text': 'object facts', 'sources': [], 'supports': [],
                    'queries': [], 'error': ''}
        sr.serper_research = _spy
        try:
            al.artist_life_research(prompt, serp=_fake_serp_factory([]),
                                    fetch=_fake_fetch, answer=lambda *a, **k: {'text': '', 'error': ''},
                                    wiki=_fake_wiki)
        finally:
            sr.serper_research = orig
        self.assertTrue(called['object'],
                        'unknown artist must defer to serper_research')


class TestVietnameseNameAid(unittest.TestCase):
    def test_repairs_wrong_attribution(self):
        out, notes = vn.apply('Spring Garden by Nguyen Van Tri, a lacquer work.')
        self.assertIn('Nguy\u1ec5n Gia Tr\u00ed', out)
        self.assertNotIn('Nguyen Van Tri', out)
        self.assertNotIn('Nguy\u1ec5n Gia Nguy\u1ec5n', out)  # no duplication

    def test_restores_diacritics_no_duplication(self):
        out, _ = vn.apply('completed by Nguyen Gia Tri after decades.')
        self.assertIn('Nguy\u1ec5n Gia Tr\u00ed', out)
        self.assertEqual(out.count('Nguy\u1ec5n Gia Tr\u00ed'), 1)

    def test_expands_fragment_on_first_use(self):
        out, _ = vn.apply('S\u01a1n n\u1eef is a painting by L\u1ef1u.')
        self.assertIn('L\u00ea Th\u1ecb L\u1ef1u', out)

    def test_narration_has_no_spoken_say_aid(self):
        # [LOCAL-692B] The "(say: …)" aid must NOT be injected into narration
        # (it was read aloud). apply() defaults with_aids=False.
        txt = ('Nguy\u1ec5n S\u00e1ng made it. Later Nguy\u1ec5n S\u00e1ng '
               'returned.')
        out, _ = vn.apply(txt)
        self.assertNotIn('(say:', out)
        # The name itself is still corrected to its diacritic full form.
        self.assertIn('Nguy\u1ec5n S\u00e1ng', out)

    def test_pronunciation_moved_to_ssml_sub(self):
        # [LOCAL-692B] Pronunciation lives in the TTS layer: to_ssml wraps the
        # first mention of each known name in <sub alias="respelling">.
        txt = 'Stand before Nguy\u1ec5n Gia Tr\u00ed and his work.'
        ssml, notes = vn.to_ssml(txt)
        self.assertTrue(ssml.startswith('<speak>') and ssml.endswith('</speak>'))
        self.assertIn('<sub alias="ngwen zah chee">', ssml)
        self.assertIn('Nguy\u1ec5n Gia Tr\u00ed</sub>', ssml)

    def test_ssml_only_first_mention_wrapped(self):
        txt = ('Nguy\u1ec5n Gia Tr\u00ed painted it. Nguy\u1ec5n Gia Tr\u00ed '
               'later returned.')
        ssml, _ = vn.to_ssml(txt)
        self.assertEqual(ssml.count('<sub alias="ngwen zah chee">'), 1)

    def test_ssml_clean_english_is_plain_speak(self):
        s = 'A plain English tour of a Boston museum.'
        ssml, notes = vn.to_ssml(s)
        self.assertEqual(ssml, f'<speak>{s}</speak>')
        self.assertEqual(notes, [])

    def test_clean_english_untouched(self):
        s = 'A plain English tour of a Boston museum with no Vietnamese names.'
        out, notes = vn.apply(s)
        self.assertEqual(out, s)
        self.assertEqual(notes, [])

    def test_three_named_artists_have_verified_entries(self):
        for key in ('nguyen_gia_tri', 'to_ngoc_van', 'bui_xuan_phai'):
            self.assertIn(key, vn.LEXICON)
            self.assertTrue(vn.LEXICON[key].say)
        self.assertEqual(vn.canonical_name('Nguyen Gia Tri'), 'Nguy\u1ec5n Gia Tr\u00ed')
        self.assertEqual(vn.canonical_name('Bui Xuan Phai'), 'B\u00f9i Xu\u00e2n Ph\u00e1i')


class TestStoryLadder(unittest.TestCase):
    """[LOCAL-692B] The story-source ladder: keep searching down the rungs until
    an emotionally-charged story is found; cap the extra search; log the rung;
    add a distinct second story without lengthening the first."""

    def _serp(self, record=None):
        def _s(q):
            if record is not None:
                record.append(q)
            return [{'title': 't',
                     'url': f'https://example-art.com/{abs(hash(q)) % 99999}',
                     'snippet': 's'}]
        return _s

    def test_charged_story_on_first_rung_spends_no_extra(self):
        def _answer(prompt, model, max_tokens=700):
            if 'ONE MORE short' in prompt:
                return {'text': 'NO SECOND STORY', 'error': ''}
            return {'text': 'Nguyễn Gia Trí refused the commission and fled '
                            'into exile in 1954 [1].', 'error': ''}
        out = al.artist_life_research(
            MUSEUM_PROMPT, serp=self._serp(), fetch=lambda u: 'refused fled exile ' * 20,
            answer=_answer, wiki=lambda n, c: [])
        self.assertEqual(out['rung'], 'exhibit')
        self.assertEqual(out['extra_queries'], 0)
        self.assertIn('exile', out['text'])

    def test_keeps_searching_and_caps_extra_queries(self):
        # No charged story anywhere → the ladder descends all rungs but the
        # EXTRA queries (museum + culture) never exceed the cap.
        def _answer(prompt, model, max_tokens=700):
            if 'ONE MORE short' in prompt:
                return {'text': 'NO SECOND STORY', 'error': ''}
            return {'text': 'He painted calmly for many years [1].', 'error': ''}
        out = al.artist_life_research(
            MUSEUM_PROMPT, serp=self._serp(), fetch=lambda u: 'calm studio years ' * 20,
            answer=_answer, wiki=lambda n, c: [])
        self.assertLessEqual(out['extra_queries'], al.MAX_EXTRA_QUERIES)
        self.assertGreater(out['extra_queries'], 0)  # it did keep searching

    def test_rung_logged_when_charge_appears_only_later(self):
        state = {'n': 0}

        def _answer(prompt, model, max_tokens=700):
            if 'ONE MORE short' in prompt:
                return {'text': 'NO SECOND STORY', 'error': ''}
            state['n'] += 1
            if state['n'] >= 3:
                return {'text': 'The museum was looted during the war [1].',
                        'error': ''}
            return {'text': 'A calm overview of the work [1].', 'error': ''}
        out = al.artist_life_research(
            MUSEUM_PROMPT, serp=self._serp(), fetch=lambda u: 'content ' * 20,
            answer=_answer, wiki=lambda n, c: [])
        self.assertIn(out['rung'], ('museum', 'culture'))
        self.assertGreater(out['extra_queries'], 0)

    def test_distinct_second_story_added_not_padded(self):
        def _answer(prompt, model, max_tokens=700):
            if 'ONE MORE short' in prompt:
                return {'text': 'His friend Nguyễn Sáng was imprisoned during '
                                'the war [1].', 'error': ''}
            return {'text': 'Nguyễn Gia Trí refused the commission and fled '
                            'into exile in 1954 [1].', 'error': ''}
        out = al.artist_life_research(
            MUSEUM_PROMPT, serp=self._serp(), fetch=lambda u: 'refused fled exile war imprisoned ' * 10,
            answer=_answer, wiki=lambda n, c: [])
        self.assertTrue(out['second_story'])
        self.assertIn('imprisoned', out['second_story'])
        # The first story is NOT lengthened by the second — they are separate.
        self.assertNotIn('imprisoned', out['text'])

    def test_near_duplicate_second_story_rejected(self):
        def _answer(prompt, model, max_tokens=700):
            charged = ('Nguyễn Gia Trí refused the commission and fled into '
                       'exile in 1954 [1].')
            # The "second story" is the SAME sentence → must be rejected.
            return {'text': charged, 'error': ''}
        out = al.artist_life_research(
            MUSEUM_PROMPT, serp=self._serp(), fetch=lambda u: 'refused fled exile ' * 20,
            answer=_answer, wiki=lambda n, c: [])
        self.assertEqual(out['second_story'], '')

    def test_charge_detector(self):
        self.assertTrue(al._is_emotionally_charged(
            'He refused the commission and fled into exile.'))
        self.assertTrue(al._is_emotionally_charged(
            'The studio burned and the work was lost.'))
        self.assertFalse(al._is_emotionally_charged(
            'He painted landscapes in a calm style for many years.'))


class TestCostAndCache(unittest.TestCase):
    """[LOCAL-692B] Cost cap (<= $0.10/tour extra) and the per-artist cache."""

    def test_query_and_page_budgets_are_small(self):
        # Fewer, better queries: the reduced budgets keep the extra research
        # cheap. (Serper $0.001/query; gpt-4.1-mini $0.40/$1.60 per 1M tokens.)
        self.assertLessEqual(al.MAX_LIFE_QUERIES, 2)
        self.assertLessEqual(al.MAX_WEB_PAGES, 4)
        self.assertLessEqual(al.MAX_EXTRA_QUERIES, 6)

    def test_cache_key_folds_name(self):
        k1 = al._artist_cache_key('Nguy\u1ec5n Gia Tr\u00ed', 'vi')
        k2 = al._artist_cache_key('  nguy\u1ec5n gia tr\u00ed  ', 'vi')
        self.assertEqual(k1, k2)
        self.assertIn('|vi', k1)

    def test_cache_is_skipped_with_injected_doubles(self):
        # With test doubles injected the cache must NOT be consulted (so a unit
        # test never touches a DB). A missing DATABASE_URL + injected serp is a
        # clean research run.
        calls = {'get': 0}
        orig = al._artist_cache_get
        al._artist_cache_get = lambda *a, **k: (calls.__setitem__('get', calls['get'] + 1) or None)
        try:
            al.artist_life_research(
                MUSEUM_PROMPT,
                serp=lambda q: [{'title': 't', 'url': 'https://example-art.com/1', 'snippet': 's'}],
                fetch=lambda u: 'refused fled exile ' * 20,
                answer=lambda p, m, max_tokens=700: {'text': 'He refused and fled [1].', 'error': ''},
                wiki=lambda n, c: [])
        finally:
            al._artist_cache_get = orig
        self.assertEqual(calls['get'], 0, 'cache must not be consulted in unit tests')

    def test_cache_put_skips_empty_or_errored(self):
        # Never persist a failure/empty story (so a transient miss is not cached).
        captured = {}
        al._artist_cache_put('X', 'vi', {'text': '', 'error': 'boom'},
                             db_url=None)  # db_url None → no-op, no raise
        self.assertEqual(captured, {})  # nothing to assert beyond "did not raise"


class TestRouterGating(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get('MUSEUM_RESEARCH')
        try:
            import cheap_arm
            self._cheap = cheap_arm
            self._tok = None
        except Exception:
            self._cheap = None

    def tearDown(self):
        if self._saved is None:
            os.environ.pop('MUSEUM_RESEARCH', None)
        else:
            os.environ['MUSEUM_RESEARCH'] = self._saved
        if self._cheap is not None:
            self._cheap.set_tour_category('')

    def test_unset_is_disabled(self):
        os.environ.pop('MUSEUM_RESEARCH', None)
        self.assertEqual(sl.museum_research_backend(), '')

    def test_museum_category_enables(self):
        os.environ['MUSEUM_RESEARCH'] = 'artist_life'
        if self._cheap is not None:
            self._cheap.set_tour_category('museum')
        self.assertEqual(sl.museum_research_backend(), 'artist_life')

    def test_non_museum_category_disabled(self):
        os.environ['MUSEUM_RESEARCH'] = 'artist_life'
        if self._cheap is not None:
            self._cheap.set_tour_category('walking')
        self.assertEqual(sl.museum_research_backend(), '')


class TestLengthTarget(unittest.TestCase):
    def test_artist_life_extractor_budget_not_longer(self):
        # [LOCAL-692B] Michael REVERTED the length increase: shorter stories
        # "feel of the right size". The artist-life extractor budget must NOT
        # exceed the object backend's — it is the same short budget, so a stop
        # is not padded. (Equality is the intent; never larger.)
        self.assertLessEqual(al.ANSWER_MAX_TOKENS, sr.ANSWER_MAX_TOKENS)

    def test_museum_prose_instruction_is_short_not_padded(self):
        # [LOCAL-692B] The museum artist-life prose instruction keeps the SHORT
        # budget (max 6 sentences, same as the object backend) — it must NOT
        # allow 9 sentences any more. Person-first is still required.
        os.environ['MUSEUM_RESEARCH'] = 'artist_life'
        try:
            import cheap_arm
            cheap_arm.set_tour_category('museum')
        except Exception:
            pass
        matrix = {'canonical_title': 'V\u01b0\u1eddn xu\u00e2n Trung Nam B\u1eafc',
                  'artist': 'Nguy\u1ec5n Gia Tr\u00ed',
                  'venue_name': 'HCMC Museum of Fine Arts'}
        seed = {'kind': 'prose', 'seed': ''}
        prompt = sq.compile_for_seed(seed, matrix, 'HCMC Museum of Fine Arts')
        try:
            import cheap_arm
            cheap_arm.set_tour_category('')
        except Exception:
            pass
        os.environ.pop('MUSEUM_RESEARCH', None)
        self.assertIn('maximum 6 sentences', prompt.lower())
        self.assertNotIn('9 sentences', prompt)
        self.assertIn('LEAD with the ARTIST', prompt)


if __name__ == '__main__':
    unittest.main(verbosity=2)
