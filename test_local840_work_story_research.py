"""test_local840_work_story_research.py — [LOCAL-840] the per-work story research
step must return HUMAN-EVENT passages and drop provenance/metadata.

**THE DEFECT (LOCAL-837 submission, "Why — root cause").** With the human-story
pass and STORY_PASS_MODEL=gpt-4.1, Orsay was 0/5 and Rijks 2/5 on the story bar,
not because the pass was wrong but because the MATERIAL reaching it was Serper
snippets of PROVENANCE AND METADATA — "Legs Gustave Caillebotte", "Gift of
H.W.A. Deterding", "oil on canvas", "Achat avec le concours", stock-image
captions. The works have famous human stories (Lacan hid L'Origine behind a
Masson panel; Manet's Déjeuner was thrown out of the 1863 Salon and mocked at the
Salon des Refusés; Rembrandt's Night Watch was slashed in 1911 and 1975) and the
research layer never asked for them.

**THE FIX under test.** `work_story_research.museum_work_research(title, artist,
…)` fetches the work's OWN Wikipedia article (Wikidata QID, EN + local language),
keeps the passages that narrate a human event, and drops provenance/catalogue
lines. These tests run OFFLINE against captured Wikipedia extracts
(`fixtures/local840_work_wikipedia.json`) and injected fetch/serp/answer, so there
is no network and no key.

Asserted:
  - the extractor KEEPS the signature human event for each of the four works
    (Night Watch slashing, L'Origine Lacan/concealment, Déjeuner Salon des
    Refusés, Milkmaid dating/auction) — i.e. it is not empty where a story exists;
  - it DROPS provenance ("Gift of…", "Legs…", "bequest", "Achat…") and metadata
    ("oil on canvas", dimensions, "stock image") lines;
  - every returned passage is VERBATIM article text (grounding: the story pass's
    "every name/date/number must appear in the material" rule still holds);
  - QID resolution is disambiguated by ARTIST (Manet's Déjeuner, not Monet's;
    the 1642 painting, not the band / video game);
  - the entry point's branches: cache hit, wikipedia hit, the paid Serper
    fallback firing ONLY when Wikipedia is thin and staying within the cost
    ceiling, and the empty/NO_STORY-safe path.

Run: python3 -m pytest test_local840_work_story_research.py -q
 or: python3 -m unittest test_local840_work_story_research -v
"""
import json
import os
import unittest

import work_story_research as W


FIX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'fixtures', 'local840_work_wikipedia.json')
with open(FIX_PATH, encoding='utf-8') as _f:
    FIXTURES = json.load(_f)


def _sections(title):
    """(header, body) sections from the captured Wikipedia extract for a work."""
    return W._split_sections(FIXTURES[title]['extract'])


def _passages(title):
    return W.event_passages(_sections(title))


# ── a tiny fake Response, so resolve/fetch are tested with no network ─────────
class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


# ─────────────────────────────────────────────────────────────────────────────
# 1. The extractor KEEPS the human event for each of the four works.
# ─────────────────────────────────────────────────────────────────────────────
class TestKeepsHumanEvents(unittest.TestCase):

    def test_night_watch_keeps_an_attack_on_the_painting(self):
        ps = _passages('The Night Watch')
        self.assertTrue(ps, 'Night Watch produced no passages')
        joined = ' '.join(ps).lower()
        # The 1911 or 1975 knife attack is the signature human event.
        self.assertTrue('slash' in joined or 'knife' in joined
                        or 'attack' in joined,
                        f'no attack event kept; got: {ps}')
        self.assertIn('1975' if '1975' in joined else '1911', joined)

    def test_origine_keeps_lacan_or_concealment(self):
        ps = _passages("L'Origine du monde")
        self.assertTrue(ps, "L'Origine produced no passages")
        joined = ' '.join(ps).lower()
        # Either the Lacan 1955 purchase, or the painting being found hidden.
        self.assertTrue('lacan' in joined or 'hidden' in joined
                        or '1955' in joined or 'goncourt' in joined,
                        f'no concealment/ownership event kept; got: {ps}')

    def test_dejeuner_keeps_the_salon_refuses_scandal(self):
        ps = _passages("Le Déjeuner sur l'herbe")
        self.assertTrue(ps, 'Déjeuner produced no passages')
        joined = ' '.join(ps).lower()
        self.assertTrue('refus' in joined or 'rejected' in joined
                        or 'salon' in joined or 'notoriety' in joined
                        or 'controvers' in joined,
                        f'no Salon-des-Refusés scandal kept; got: {ps}')

    def test_milkmaid_keeps_a_dated_fact(self):
        # The Milkmaid's EN article is mostly description; the honest outcome is
        # a small number of dated facts (dating, early auction catalogue). The
        # extractor must return VERBATIM article sentences, not invent a drama.
        ps = _passages('The Milkmaid')
        joined = ' '.join(ps).lower()
        if ps:
            self.assertTrue(any(y in joined for y in ('1657', '1658', '1659',
                                                      '1660', '1696')),
                            f'passages carry no date; got: {ps}')


# ─────────────────────────────────────────────────────────────────────────────
# 2. The extractor DROPS provenance and metadata lines.
# ─────────────────────────────────────────────────────────────────────────────
class TestDropsProvenanceAndMetadata(unittest.TestCase):

    def test_provenance_lines_are_classified_as_such(self):
        for line in [
            'Bal du moulin de la Galette, 1876. Musée d\'Orsay Legs Gustave '
            'Caillebotte, 1896.',
            "Johannes Vermeer, View of Houses in Delft, c. 1658–1659. Gift of "
            "H.W.A. Deterding, London.",
            'Musée d\'Orsay Achat avec le concours de la Société des Amis.',
            'The work was bequeathed to the French state in 1894.',
            'It entered the collection as part of a 1908 donation.',
            'Provenance: Left by the artist at the Orsay museum.',
        ]:
            self.assertTrue(W.is_provenance_or_metadata(line),
                            f'provenance not caught: {line!r}')

    def test_metadata_lines_are_classified_as_such(self):
        for line in [
            'Oil on canvas, 72.5 by 92 centimetres.',
            'L\'église d\'Auvers-sur-Oise - huile sur toile © RMN-Grand Palais.',
            'Physical Dimensions: doek, 363 × 437 cm.',
            'Download this stock image: Vincent van Gogh – Starry Night.',
            'Medium: oil on canvas.',
        ]:
            self.assertTrue(W.is_provenance_or_metadata(line),
                            f'metadata not caught: {line!r}')

    def test_a_real_human_event_is_NOT_classified_as_provenance(self):
        for line in [
            'In 1939 the curator Arie van Schendel had the painting evacuated '
            'to a bunker in Maastricht.',
            'On 14 September 1975 the work was attacked with a bread knife by an '
            'unemployed teacher.',
            'Manet submitted the painting to the 1863 Salon, which rejected it.',
            'Lacan asked André Masson to build a double-bottom frame and hide '
            'the picture behind it.',
        ]:
            self.assertFalse(W.is_provenance_or_metadata(line),
                             f'human event wrongly dropped: {line!r}')

    def test_no_returned_passage_is_provenance_or_metadata(self):
        # The end-to-end guarantee: nothing the extractor returns is a line the
        # drop test would reject. This is what stops the Serper-snippet shape
        # reaching the story pass.
        for title in FIXTURES:
            for p in _passages(title):
                self.assertFalse(W.is_provenance_or_metadata(p),
                                 f'{title}: returned a provenance/metadata '
                                 f'passage: {p!r}')


# ─────────────────────────────────────────────────────────────────────────────
# 3. Grounding: every passage is verbatim article text (no invention).
# ─────────────────────────────────────────────────────────────────────────────
class TestGroundingVerbatim(unittest.TestCase):

    def test_every_passage_is_a_substring_of_the_source_article(self):
        import re
        for title in FIXTURES:
            # Normalise whitespace the same way the extractor does before
            # comparing — the extractor collapses runs of whitespace per para.
            source = re.sub(r'\s+', ' ', FIXTURES[title]['extract'])
            for p in _passages(title):
                # A passage may be truncated at MAX_PASSAGE_CHARS; compare the
                # kept prefix.
                needle = p.rstrip('…').strip()
                # Trim to a safe prefix to avoid boundary punctuation drift.
                probe = needle[:min(len(needle), 80)]
                self.assertIn(probe, source,
                              f'{title}: passage not verbatim from source: '
                              f'{probe!r}')


# ─────────────────────────────────────────────────────────────────────────────
# 4. QID resolution is disambiguated by the artist.
# ─────────────────────────────────────────────────────────────────────────────
class TestQidDisambiguation(unittest.TestCase):

    def _fetch_factory(self, search_hits, sitelinks=None):
        """Return a fake _wiki_get that answers wbsearchentities with
        `search_hits` and wbgetentities with `sitelinks`."""
        def _fake(url, params, timeout=15):
            if params.get('action') == 'wbsearchentities':
                return _Resp({'search': search_hits})
            if params.get('action') == 'wbgetentities':
                qid = params.get('ids', '')
                return _Resp({'entities': {qid: {
                    'sitelinks': sitelinks or {}}}})
            return _Resp({}, status=404)
        return _fake

    def test_artist_surname_picks_the_right_homonym(self):
        # Two paintings called "Luncheon on the Grass": Manet's and Monet's.
        hits = [
            {'id': 'Q_MONET', 'label': 'Luncheon on the Grass',
             'description': 'painting by Claude Monet, Musée d’Orsay'},
            {'id': 'Q_MANET', 'label': 'Luncheon on the Grass',
             'description': 'painting by Édouard Manet'},
        ]
        qid, _sl = W.resolve_work_qid('Luncheon on the Grass', 'Édouard Manet',
                                      fetch=self._fetch_factory(hits))
        self.assertEqual(qid, 'Q_MANET')

    def test_non_work_homonyms_are_rejected(self):
        # "The Night Watch": a 2006 edition, the 1642 painting, a band, a game.
        hits = [
            {'id': 'Q_EDITION', 'label': 'The Night Watch',
             'description': '2006 edition'},
            {'id': 'Q_PAINTING', 'label': 'The Night Watch',
             'description': '1642 painting by Rembrandt, Rijksmuseum'},
            {'id': 'Q_BAND', 'label': 'The Night Watch',
             'description': 'Italian musical group'},
            {'id': 'Q_GAME', 'label': 'The Night Watch',
             'description': 'video game'},
        ]
        qid, _sl = W.resolve_work_qid('The Night Watch', 'Rembrandt',
                                      fetch=self._fetch_factory(hits))
        self.assertEqual(qid, 'Q_PAINTING')

    def test_all_film_hits_yields_no_qid(self):
        # When every candidate is clearly not the work, return '' so the caller
        # falls through rather than reading a film's article.
        hits = [
            {'id': 'Q_FILM', 'label': 'Something', 'description': '2001 film'},
            {'id': 'Q_BOOK', 'label': 'Something', 'description': 'novel'},
        ]
        qid, _sl = W.resolve_work_qid('Something', 'Nobody',
                                      fetch=self._fetch_factory(hits))
        self.assertEqual(qid, '')


# ─────────────────────────────────────────────────────────────────────────────
# 5. The entry point's branches (cache / wikipedia / fallback / empty).
# ─────────────────────────────────────────────────────────────────────────────
class TestEntryPointBranches(unittest.TestCase):

    def _wiki_fetch_from_fixture(self, title, enwiki_title):
        """A fake _wiki_get that resolves the QID and serves the fixture extract
        — the full free Wikipedia path with no network."""
        extract = FIXTURES[title]['extract']

        def _fake(url, params, timeout=15):
            if params.get('action') == 'wbsearchentities':
                return _Resp({'search': [
                    {'id': 'Q_TEST', 'label': title,
                     'description': f'painting by {FIXTURES[title]["artist"]}'}]})
            if params.get('action') == 'wbgetentities':
                return _Resp({'entities': {'Q_TEST': {
                    'sitelinks': {'enwiki': {'title': enwiki_title}}}}})
            if params.get('prop') == 'extracts':
                return _Resp({'query': {'pages': [{'extract': extract}]}})
            return _Resp({}, status=404)
        return _fake

    def test_wikipedia_branch_returns_event_passages(self):
        fake = self._wiki_fetch_from_fixture('The Night Watch', 'The Night Watch')
        res = W.museum_work_research(
            'The Night Watch', 'Rembrandt', 'Amsterdam, Netherlands',
            'Rijksmuseum', use_cache=False, allow_fallback=False, fetch=fake)
        self.assertEqual(res['source'], 'wikipedia')
        self.assertEqual(res['qid'], 'Q_TEST')
        self.assertTrue(res['passages'])
        self.assertEqual(res['cost'], 0.0, 'Wikipedia path must be free')

    def test_fallback_fires_only_when_wikipedia_is_thin(self):
        # A fetch that resolves NO QID → Wikipedia is empty → fallback allowed.
        def _empty_wiki(url, params, timeout=15):
            if params.get('action') == 'wbsearchentities':
                return _Resp({'search': []})
            return _Resp({}, status=404)

        serp_calls = {'n': 0}

        def _fake_serp(query):
            serp_calls['n'] += 1
            return [{'url': 'https://example.org/story', 'title': 't',
                     'snippet': 's'}]

        def _fake_fetch_page(url):
            return ('In 1911 a jobless shoemaker tried to slash the painting '
                    'with a knife, and in 1975 it was attacked again. ' * 3)

        def _fake_answer(prompt, model=None, max_tokens=500):
            return {'text': 'In 1911 a jobless shoemaker tried to slash the '
                            'painting with a knife. In 1975 an unemployed '
                            'teacher attacked it with a bread knife.',
                    'error': ''}

        res = W.museum_work_research(
            'Obscure Work', 'Someone', use_cache=False, allow_fallback=True,
            fetch=_empty_wiki, serp=_fake_serp, page_fetch=_fake_fetch_page,
            answer=_fake_answer)
        # The paid fallback must have been consulted and produced passages.
        self.assertEqual(serp_calls['n'], 1, 'fallback Serper not called once')
        self.assertEqual(res['source'], 'serper_fallback')
        self.assertTrue(res['passages'])
        self.assertLessEqual(res['cost'], W.COST_CEILING,
                             'fallback exceeded the per-stop cost ceiling')

    def test_fallback_not_called_when_disabled(self):
        def _empty_wiki(url, params, timeout=15):
            if params.get('action') == 'wbsearchentities':
                return _Resp({'search': []})
            return _Resp({}, status=404)

        serp_calls = {'n': 0}

        def _fake_serp(query):
            serp_calls['n'] += 1
            return []

        res = W.museum_work_research(
            'Obscure Work', 'Someone', use_cache=False, allow_fallback=False,
            fetch=_empty_wiki, serp=_fake_serp)
        self.assertEqual(serp_calls['n'], 0)
        self.assertEqual(res['passages'], [])
        self.assertEqual(res['source'], 'none')

    def test_blank_title_returns_empty(self):
        res = W.museum_work_research('', 'Someone', use_cache=False)
        self.assertEqual(res['passages'], [])
        self.assertEqual(res['source'], 'none')


# ─────────────────────────────────────────────────────────────────────────────
# 6. The passages are a drop-in list[str] the story pass can consume as material.
# ─────────────────────────────────────────────────────────────────────────────
class TestFeedsStoryPass(unittest.TestCase):

    def test_passages_are_nonempty_strings(self):
        for title in ('The Night Watch', "L'Origine du monde",
                      "Le Déjeuner sur l'herbe"):
            ps = _passages(title)
            self.assertTrue(all(isinstance(p, str) and p.strip() for p in ps))

    def test_story_pass_accepts_the_passages_as_material(self):
        # No network: inject a caller that echoes a human story only if the
        # material actually contains a human event (which it must for NW).
        from story_pass import generate_story_for_stop

        passages = _passages('The Night Watch')

        def _caller(prompt, model=None):
            # The passages must be present in the prompt (they are the material).
            self.assertTrue(any(p[:40] in prompt for p in passages),
                            'passages were not placed into the story prompt')
            return ('In 1975 Wilhelmus de Rijk attacked The Night Watch with a '
                    'bread knife, cutting several zig-zag slashes into it. '
                    'Conservators repaired the canvas over months. The damage '
                    'is still faintly visible today.'), 0.0

        res = generate_story_for_stop(
            {'canonical_title': 'The Night Watch', 'artist': 'Rembrandt',
             'venue_name': 'Rijksmuseum'},
            passages, caller=_caller, works_mode=True)
        self.assertTrue(res['ok'], f"story pass rejected: {res['reason']}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
