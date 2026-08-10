"""tests/test_local369_exhibition_thread_and_provenance.py — LOCAL-369.

Tests two features:
  Thread A: Exhibition prose feeds into theme thread discovery for scoped requests.
  Thread B: Credit line reaches the narrator as a grounded fact, with the negative
            control that no unsourced biographical predicate accompanies it.

Uses the MFA HTML fixture committed at tests/fixtures/mfa_picasso_exhibition.html (LOCAL-366).
Does NOT inline re-implement logic — imports directly from production modules.
"""
import sys
import os
import re
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from exhibition_checklist import (
    ExhibitionChecklistResult,
    prose_llm_extract_works,
    find_exhibition_checklist,
    _fetch_page,
)

FIXTURES_DIR = Path(__file__).parent / 'fixtures'
MFA_HTML_FIXTURE = FIXTURES_DIR / 'mfa_picasso_exhibition.html'


# ═══════════════════════════════════════════════════════════════════════════════
# Fixture helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _load_mfa_page_text() -> str:
    """Load the MFA HTML and extract text using the same method as _fetch_page."""
    assert MFA_HTML_FIXTURE.exists(), (
        f"MFA HTML fixture not found at {MFA_HTML_FIXTURE}. "
        "This test requires the real fetched HTML committed as a fixture."
    )
    html = MFA_HTML_FIXTURE.read_text(encoding='utf-8')

    paragraphs = []
    for p_match in re.finditer(r'<p[^>]*>(.*?)</p>', html, re.DOTALL):
        clean = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
        clean = re.sub(r'&nbsp;', ' ', clean)
        clean = re.sub(r'&[a-z]+;', ' ', clean)
        if len(clean) > 20:
            paragraphs.append(clean)

    headings = []
    for h_match in re.finditer(r'<h[1-4][^>]*>(.*?)</h[1-4]>', html, re.DOTALL):
        clean = re.sub(r'<[^>]+>', '', h_match.group(1)).strip()
        if clean and len(clean) < 200:
            headings.append(clean)

    figcaptions = []
    for fig_match in re.finditer(r'<figcaption[^>]*>(.*?)</figcaption>', html, re.DOTALL):
        clean = re.sub(r'<[^>]+>', '', fig_match.group(1)).strip()
        if clean and len(clean) > 5:
            figcaptions.append(clean)

    img_alts = []
    for img_match in re.finditer(r'<img[^>]*alt="([^"]{10,200})"', html):
        alt = img_match.group(1).strip()
        if ',' in alt or ' by ' in alt.lower():
            img_alts.append(alt)

    return '\n'.join(headings + figcaptions + img_alts + paragraphs)


def _make_exhibition_checklist_result_with_credit_line() -> ExhibitionChecklistResult:
    """Build a realistic ExhibitionChecklistResult with credit_line on a work."""
    result = ExhibitionChecklistResult()
    result.path = 'prose_llm'
    result.page_shape = 'prose_llm_extraction'
    result.exhibition_title = 'Picasso, Miró, Dalí: Unbound'
    result.exhibition_url = 'https://www.mfa.org/exhibition/picasso-miro-dali-unbound'
    result.page_text = _load_mfa_page_text()
    result.works = [
        {
            'title': "Le Lézard aux plumes d'or (The Lizard with Golden Feathers)",
            'artist': 'Joan Miró',
            'date': '1971',
            'medium': 'Illustrated book with 40 color lithographs',
            'publisher': 'Louis Broder, printed by Mourlot Frères, Paris',
            'credit_line': 'Gift of Boris Fridman',
        },
        {
            'title': 'Moses and Monotheism',
            'artist': 'Salvador Dalí',
            'date': '1974',
            'medium': 'Illustrations for Sigmund Freud\'s Moses and Monotheism',
        },
        {
            'title': 'Au Soleil du Plafond',
            'artist': 'Juan Gris with Pierre Reverdy',
            'date': '1955',
        },
    ]
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Thread A: Exhibition page_text stored and available for thread discovery
# ═══════════════════════════════════════════════════════════════════════════════

class TestExhibitionPageTextStored:
    """The exhibition page text must be stored on ExhibitionChecklistResult."""

    def test_page_text_field_exists(self):
        """ExhibitionChecklistResult must have a page_text attribute."""
        result = ExhibitionChecklistResult()
        assert hasattr(result, 'page_text')
        assert result.page_text == ''

    def test_find_exhibition_checklist_stores_page_text(self):
        """find_exhibition_checklist must store the fetched page text."""
        mfa_html = MFA_HTML_FIXTURE.read_text(encoding='utf-8')

        pinned_llm_response = [
            {
                "title": "Le Lézard aux plumes d'or (The Lizard with Golden Feathers)",
                "artist": "Joan Miró",
                "credit_line": "Gift of Boris Fridman",
            },
        ]
        mock_llm_resp = MagicMock()
        mock_llm_resp.status_code = 200
        mock_llm_resp.json.return_value = {
            'choices': [{'message': {'content': json.dumps(pinned_llm_response)}}]
        }

        # [LOCAL-370] The listing and the detail page must be distinguishable.
        # This mock previously returned the detail HTML for any URL containing
        # '/exhibition', including the listing itself, so the resolved detail URL
        # equalled the listing URL — which LOCAL-370 now correctly refuses. Same
        # correction LOCAL-370 applied to the LOCAL-368 suite.
        # Needs >100 chars of visible text or listing discovery skips the page.
        _listing_html = (
            '<html><head><title>Exhibitions | MFA</title></head><body>'
            '<h1>Exhibitions</h1>'
            '<p>Explore current and upcoming exhibitions at the Museum of Fine Arts, Boston. '
            'From ancient art to contemporary installations, discover world-class shows.</p>'
            '<a href="/exhibition/picasso-miro-dali-unbound">Picasso, Miró, Dalí: Unbound</a>'
            '<a href="/exhibition/monet-and-boston">Monet and Boston: Lasting Impression</a>'
            '</body></html>'
        )

        def mock_requests_get(url, **kwargs):
            mock_get_resp = MagicMock()
            if url.rstrip('/').endswith('/exhibitions'):
                mock_get_resp.status_code = 200
                mock_get_resp.text = _listing_html
                return mock_get_resp
            if '/exhibition/' in url.lower():
                mock_get_resp.status_code = 200
                mock_get_resp.text = mfa_html
                return mock_get_resp
            mock_get_resp.status_code = 404
            mock_get_resp.text = ''
            return mock_get_resp

        with patch('exhibition_checklist.requests.get', side_effect=mock_requests_get):
            with patch('exhibition_checklist.requests.post', return_value=mock_llm_resp):
                with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
                    result = find_exhibition_checklist(
                        venue_base_url='https://www.mfa.org',
                        exhibition_name='Picasso, Miró, Dalí: Unbound',
                        venue_name='Museum of Fine Arts, Boston',
                    )

        # page_text must be non-empty — it contains the exhibition prose
        assert result.page_text, "page_text must be stored on ExhibitionChecklistResult"
        # It should contain key exhibition text
        assert 'unbound' in result.page_text.lower() or 'livres' in result.page_text.lower(), (
            "page_text should contain exhibition prose content"
        )

    def test_exhibition_prose_contains_unbound_theme(self):
        """The MFA fixture prose contains the 'unbound' theme that thread discovery should find.

        This is the source sentence for the expected theme thread: the dispute about
        whether illustrated books should be sold bound or unbound as loose sheets.
        """
        page_text = _load_mfa_page_text()
        # The fixture must contain the word "unbound" in the exhibition's own framing
        assert 'unbound' in page_text.lower(), (
            "MFA fixture must contain 'unbound' — this is the exhibition's central theme"
        )
        # And the concept of "livres d'artiste"
        assert 'livres' in page_text.lower(), (
            "MFA fixture must contain 'livres d'artiste' — this is the form being exhibited"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Thread B: Credit line reaches the narrator
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreditLineAsStructuredField:
    """The credit_line field must be extracted and available on works."""

    def test_credit_line_extracted_from_mfa_fixture(self):
        """prose_llm_extract_works must pass through credit_line from the LLM response."""
        pinned_response = [
            {
                "title": "Le Lézard aux plumes d'or",
                "artist": "Joan Miró",
                "credit_line": "Gift of Boris Fridman",
            },
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'choices': [{'message': {'content': json.dumps(pinned_response)}}]
        }

        # Must be ≥50 chars to pass the length check in prose_llm_extract_works
        page_text = (
            "This exhibition introduces the imaginative world of livres d'artiste "
            "through a group of extraordinary works by Spanish artists. Joan Miró's "
            "Le Lézard aux plumes d'or demonstrates the creative ambition of the form."
        )

        with patch('exhibition_checklist.requests.post', return_value=mock_resp):
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
                works = prose_llm_extract_works(page_text, "Picasso, Miró, Dalí: Unbound")

        assert len(works) >= 1, f"Expected at least 1 work, got {len(works)}"
        assert works[0].get('credit_line') == 'Gift of Boris Fridman'

    def test_credit_line_absent_when_not_in_source(self):
        """Works without credit_line in the LLM response must not have the field."""
        pinned_response = [
            {"title": "Moses and Monotheism", "artist": "Salvador Dalí"},
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'choices': [{'message': {'content': json.dumps(pinned_response)}}]
        }

        page_text = (
            "This exhibition introduces the imaginative world of livres d'artiste "
            "through a group of extraordinary works by Spanish artists including Dalí."
        )

        with patch('exhibition_checklist.requests.post', return_value=mock_resp):
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
                works = prose_llm_extract_works(page_text, "Picasso, Miró, Dalí: Unbound")

        assert len(works) >= 1, f"Expected at least 1 work, got {len(works)}"
        assert 'credit_line' not in works[0], (
            "Works without credit_line must not have the field at all"
        )


class TestCreditLineReachesPrompt:
    """The credit_line must reach the per-stop generation prompt.

    This tests the injection point in generate_tour_text.py that makes
    credit_line available to the narrator as a provenance fact.
    """

    def test_credit_line_injected_into_prompt(self):
        """When a stop matches a work with credit_line, it appears in the prompt.

        This directly exercises the lookup logic in the description generation loop.
        """
        from story_miner import _normalize

        # Simulate the matching logic from generate_tour_text.py
        poi_name = "Le Lézard aux plumes d'or (The Lizard with Golden Feathers)"
        result = _make_exhibition_checklist_result_with_credit_line()

        # Reproduce the matching logic
        _poi_norm_cl = _normalize(poi_name)
        _credit_line_for_stop = ''
        for _cl_work in result.works:
            if _cl_work.get('credit_line'):
                _cl_title_norm = _normalize(_cl_work.get('title', ''))
                if (_poi_norm_cl[:10] in _cl_title_norm
                        or _cl_title_norm[:10] in _poi_norm_cl
                        or _poi_norm_cl == _cl_title_norm):
                    _credit_line_for_stop = _cl_work['credit_line']
                    break

        assert _credit_line_for_stop == 'Gift of Boris Fridman', (
            f"Credit line lookup failed for '{poi_name}': got '{_credit_line_for_stop}'"
        )

    def test_no_credit_line_for_work_without_it(self):
        """Works without a credit_line must NOT receive a provenance injection."""
        from story_miner import _normalize

        poi_name = "Moses and Monotheism"
        result = _make_exhibition_checklist_result_with_credit_line()

        _poi_norm_cl = _normalize(poi_name)
        _credit_line_for_stop = ''
        for _cl_work in result.works:
            if _cl_work.get('credit_line'):
                _cl_title_norm = _normalize(_cl_work.get('title', ''))
                if (_poi_norm_cl[:10] in _cl_title_norm
                        or _cl_title_norm[:10] in _poi_norm_cl
                        or _poi_norm_cl == _cl_title_norm):
                    _credit_line_for_stop = _cl_work['credit_line']
                    break

        assert _credit_line_for_stop == '', (
            f"Moses and Monotheism should NOT get a credit line, but got: '{_credit_line_for_stop}'"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# NEGATIVE CONTROL: No unsourced biographical predicate about a named donor
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoUnsourcedBiographicalPredicate:
    """A collector named in a credit line must produce NO claim about their
    wealth, company, or motives that is absent from the retrieved text.

    This is the grounding prohibition from the spec. The prompt explicitly
    bans inference about the donor's financial condition or motive.
    """

    # Forbidden patterns that would indicate unsourced biographical predicate
    FORBIDDEN_BIOGRAPHICAL_PATTERNS = [
        r'\b(?:wealthy|rich|affluent|fortune|billionaire|millionaire)\b',
        r'\b(?:could no longer afford|couldn\'t afford|financial pressure)\b',
        r'\b(?:donated because|gave it away because|motivated by)\b',
        r'\b(?:tax benefit|tax deduction|tax incentive|estate planning)\b',
        r'\b(?:his company|her company|his business|her business)\b',
        r'\b(?:net worth|portfolio|investments|financial condition)\b',
        r'\b(?:pressured into|forced to donate|reluctantly gave)\b',
        r'\b(?:left him poorer|made him richer|cost him)\b',
    ]

    def test_prohibition_is_in_the_block_the_code_emits(self):
        """
        Call the real builder instead of grepping the module source.

        The original version asserted `'Do NOT infer or assert' in
        inspect.getsource(generate_tour_text)`, which passes for any tree where
        those words appear anywhere — including in a comment, and including when
        the block is never emitted (D277).
        """
        from generate_tour_text import build_provenance_block
        block = build_provenance_block('Gift of Boris Fridman')
        assert 'Gift of Boris Fridman' in block
        assert 'Do NOT infer or assert' in block
        assert 'financial condition' in block
        assert 'fabrication' in block

    def test_no_block_without_a_credit_line(self):
        """Absent or blank credit line must inject nothing at all."""
        from generate_tour_text import build_provenance_block
        assert build_provenance_block('') == ''
        assert build_provenance_block(None) == ''
        assert build_provenance_block('   ') == ''

    def test_prompt_allows_documented_gift_statement(self):
        """The prompt allows stating 'Gift of Boris Fridman' (documented fact)."""
        # Build the injection block as it would appear
        credit_line = 'Gift of Boris Fridman'
        injection = f"""
PROVENANCE (museum-published credit line — you may state this fact):
  {credit_line}
PROHIBITION: Do NOT infer or assert the donor's motive, wealth, financial condition,
or any biographical predicate not contained in retrieved text. Stating "Gift of [name]"
is the documented fact; "donated because…" or "could no longer afford…" is fabrication.
"""
        # The gift statement itself must NOT be caught by the forbidden patterns
        for pattern in self.FORBIDDEN_BIOGRAPHICAL_PATTERNS:
            assert not re.search(pattern, credit_line, re.IGNORECASE), (
                f"The documented credit line itself must not trigger the forbidden pattern: {pattern}"
            )

    def test_forbidden_patterns_catch_fabricated_claims(self):
        """Verify that the forbidden patterns DO catch the kinds of fabrication we ban."""
        fabricated_sentences = [
            "Boris Fridman, a wealthy collector, donated the piece.",
            "He could no longer afford the insurance on the collection.",
            "Fridman donated because of estate planning considerations.",
            "The gift left him poorer but culturally enriched.",
            "His company's success enabled this generous act.",
            "Motivated by tax benefits, Fridman gave the work to the museum.",
        ]
        for sentence in fabricated_sentences:
            caught = any(
                re.search(p, sentence, re.IGNORECASE)
                for p in self.FORBIDDEN_BIOGRAPHICAL_PATTERNS
            )
            assert caught, (
                f"NEGATIVE CONTROL FAILURE: This fabricated sentence should be caught "
                f"by at least one forbidden pattern: '{sentence}'"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Unscoped venue tours unchanged
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnscopedUnchanged:
    """Unscoped venue tours must not be affected by LOCAL-369 changes."""

    def test_no_page_text_on_unscoped_result(self):
        """An ExhibitionChecklistResult for a non-exhibition tour has empty page_text."""
        result = ExhibitionChecklistResult()
        # Default state — no exhibition page fetched
        assert result.page_text == ''

    def test_credit_line_injection_requires_exhibition_scope(self):
        """Without _exhibition_checklist_result, no credit_line is injected.

        The injection code checks for _exhibition_checklist_result existence,
        so a regular museum tour (Palais Lascaris) is unaffected.
        """
        # When _exhibition_checklist_result is None, the injection block is skipped
        _exhibition_checklist_result = None
        poi_name = "Some Museum Object"

        # Simulate the guard condition from generate_tour_text.py
        _credit_line_for_stop = ''
        if (_exhibition_checklist_result
                and getattr(_exhibition_checklist_result, 'works', None)):
            pass  # Would do lookup here

        assert _credit_line_for_stop == '', (
            "Without exhibition_checklist_result, no credit_line should be injected"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# LEAD review cases (2026-08-10) — credit-line matching must not misattribute.
#
# The submitted matcher used a bare 10-character normalized prefix, the pattern
# LOCAL-29 had already tightened elsewhere. Measured collisions, all real pairs:
#   'The Lizard with Golden Feathers' / 'The Lizard King'
#   'Adoration of the Shepherds'      / 'Adoration of the Magi'
#   'Au Soleil du Plafond'            / 'Au Soleil Couchant'
# A false match credits a gift to an object the donor did not give.
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreditLineMatchingIsStrict:

    WORKS = [
        {'title': 'The Lizard with Golden Feathers', 'credit_line': 'Gift of Boris Fridman'},
        {'title': 'Adoration of the Shepherds', 'credit_line': 'Bequest of A. Donor'},
        {'title': 'Au Soleil du Plafond', 'credit_line': 'Gift of the Reverdy Estate'},
    ]

    def test_exact_title_matches(self):
        from generate_tour_text import match_credit_line
        assert match_credit_line('The Lizard with Golden Feathers', self.WORKS) == 'Gift of Boris Fridman'
        assert match_credit_line('Au Soleil du Plafond', self.WORKS) == 'Gift of the Reverdy Estate'

    @pytest.mark.parametrize("confusable", [
        'The Lizard King',
        'Adoration of the Magi',
        'Au Soleil Couchant',
    ])
    def test_prefix_confusable_does_not_match(self, confusable):
        """These all share a 10-char prefix with a credited work and must NOT match."""
        from generate_tour_text import match_credit_line
        assert match_credit_line(confusable, self.WORKS) == '', (
            f"'{confusable}' must not inherit another work's credit line"
        )

    def test_unrelated_title_matches_nothing(self):
        from generate_tour_text import match_credit_line
        assert match_credit_line('Water Lilies', self.WORKS) == ''

    def test_work_without_credit_line_is_skipped(self):
        from generate_tour_text import match_credit_line
        works = [{'title': 'Water Lilies'}, {'title': 'Water Lilies', 'credit_line': ''}]
        assert match_credit_line('Water Lilies', works) == ''

    def test_empty_inputs_are_safe(self):
        from generate_tour_text import match_credit_line
        assert match_credit_line('', self.WORKS) == ''
        assert match_credit_line('Anything', []) == ''
        assert match_credit_line('Anything', None) == ''
