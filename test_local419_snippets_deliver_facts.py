"""LOCAL-419: Test that production-fact snippets reach the prompt.

Tests bind to the PRODUCTION call sites:
  - snippet_ranker.rank_and_cap_snippets (called from generate_tour_text.py:9132)
  - snippet_ranker._has_production_fact_content (used inside score_snippet)
  - generate_tour_text.build_snippet_block (called from generate_tour_text.py:9207)

Fails on current storied (where catalogue snippets with production facts
get penalized -4 and irrelevant event snippets outrank them).
Passes with the LOCAL-419 fix (production-fact bonus, title relevance).
"""
import pytest
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from snippet_ranker import (
    rank_and_cap_snippets,
    score_snippet,
    _has_production_fact_content,
    SNIPPET_CAP_PER_STOP,
)
from generate_tour_text import build_snippet_block


# ─── Fixture: realistic snippets from the MFA Unbound eval (dump evidence) ───

# Stop 3 (Au Soleil du Plafond) — the fact-rich snippets that LOCAL-419 rescues
STOP3_SNIPPETS = [
    {
        'title': 'La Lampe. From au Soleil du Plafond. First edition | Juan Gris',
        'snippet': 'La Lampe. From au Soleil du Plafond. First edition. Paris: '
                   'Tériade Editeur, 1955. Color lithograph. 43 x 33 cm. '
                   'One of 220 impressions printed by Mourlot.',
        'url': 'https://www.art-books.com/la-lampe',
        'tier': 'tier3',
    },
    {
        'title': 'Au soleil du plafond – Works – eMuseum - Toledo Museum',
        'snippet': 'Au soleil du plafond ; Artist Juan Gris (Spanish, 1887-1927) ; '
                   'Publisher Éditions Verve, Paris, 1955 (Tériade) ; Printer '
                   'Mourlot Frères, Paris ; Author Pierre Reverdy',
        'url': 'https://emuseum.toledomuseum.org/au-soleil',
        'tier': 'tier3',
    },
    {
        'title': 'Designed by Juan Gris - Au Soleil du Plafond',
        'snippet': 'Title: Au Soleil du Plafond; Designer: Designed by Juan Gris '
                   '(Spanish, Madrid 1887–1927 Boulogne-sur-Seine); Date: 1955; '
                   'Medium: Lithographs (for both handwritten text and illustrations)',
        'url': 'https://www.metmuseum.org/art/collection/search/123',
        'tier': 'tier1',
    },
    # An irrelevant snippet that should NOT rank above the fact-rich ones
    {
        'title': 'Museum of Fine Arts, Boston, to Unveil New Galleries',
        'snippet': 'This major renovation project was made possible by a $25 million '
                   'gift from the Wyss Foundation, which also funded two new staff '
                   'positions in the department of Art of the Americas.',
        'url': 'https://www.mfa.org/news/galleries',
        'tier': 'tier3',
    },
    # A snippet about a DIFFERENT topic that is an "event" but irrelevant
    {
        'title': 'Joan Miro | Icon of 20th Century Modernism',
        'snippet': 'Fundació Joan Miró in Barcelona, founded with a substantial '
                   'donation of works from his family in 1975.',
        'url': 'https://www.dtrmodern.com/miro',
        'tier': 'tier3',
    },
]

# Stop 2 (Moses and Monotheism) — key fact: Sotheby's snippet with technique+edition
STOP2_SNIPPETS = [
    {
        'title': "Salvador Dalí - Moses and Monotheism - Sotheby's",
        'snippet': 'Moses and Monotheism by Salvador Dali, 1974-75. Sold as a set '
                   'of 10. Salvador Dali (Spanish, 1904-1989). Drypoints and '
                   'lithographs on sheepskin.',
        'url': 'https://www.sothebys.com/dali-moses',
        'tier': 'tier3',
    },
    {
        'title': "Illustrations and printed text of Sigmund Freud's Moses and ...",
        'snippet': "This oversize French edition of Sigmund Freud's 1939 published "
                   "work, Moses and Monotheism, contains illustrations based on "
                   "watercolor, pen-and-ink drawings by Salvador Dalí.",
        'url': 'https://collections.museumofthebible.org/moses',
        'tier': 'tier3',
    },
    # Irrelevant snippet about a DIFFERENT exhibition at MFA
    {
        'title': 'Dalí In Context | Museum of Fine Arts Boston',
        'snippet': 'Explore the exhibition "Dalí: Disruption and Devotion" through '
                   'the lens of history, film, photography, and the artists that '
                   'came before and after the celebrated Spanish Surrealist.',
        'url': 'https://www.mfa.org/dali-context',
        'tier': 'tier3',
    },
    {
        'title': 'A Walkthrough of Dalí: Disruption and Devotion in Boston',
        'snippet': 'This exhibit features 30 paintings and prints loaned from the '
                   'Dalí museum collected and donated by American philanthropists '
                   'A. Reynolds Morse and Eleanor Reese Morse.',
        'url': 'https://www.thewellesleynews.com/dali',
        'tier': 'tier3',
    },
    {
        'title': 'Moses and Monotheism',
        'snippet': 'Moses and Monotheism is a 1939 book about the origins of '
                   'monotheism written by Sigmund Freud, the founder of psychoanalysis.',
        'url': 'https://en.wikipedia.org/wiki/Moses_and_Monotheism',
        'tier': 'tier1',
    },
]


class TestProductionFactDetection:
    """_has_production_fact_content correctly identifies snippets with production facts."""

    def test_toledo_museum_snippet_has_facts(self):
        """Toledo Museum snippet names publisher AND printer — 2+ signals."""
        text = STOP3_SNIPPETS[1]['title'] + ' ' + STOP3_SNIPPETS[1]['snippet']
        assert _has_production_fact_content(text), (
            "Toledo Museum snippet with 'Publisher Éditions Verve' and "
            "'Printer Mourlot Frères' should be detected as production-fact-rich"
        )

    def test_sothebys_dali_has_facts(self):
        """Sotheby's snippet names edition + technique on sheepskin — 2+ signals."""
        text = STOP2_SNIPPETS[0]['title'] + ' ' + STOP2_SNIPPETS[0]['snippet']
        assert _has_production_fact_content(text), (
            "Sotheby's snippet with 'set of 10' + 'Drypoints and lithographs on sheepskin' "
            "should be detected as production-fact-rich"
        )

    def test_irrelevant_snippet_no_facts(self):
        """MFA renovation snippet has no production facts."""
        text = STOP3_SNIPPETS[3]['title'] + ' ' + STOP3_SNIPPETS[3]['snippet']
        assert not _has_production_fact_content(text), (
            "MFA renovation snippet should NOT be detected as production-fact-rich"
        )

    def test_different_exhibition_no_facts(self):
        """A snippet about a different exhibition has no production facts."""
        text = STOP2_SNIPPETS[2]['title'] + ' ' + STOP2_SNIPPETS[2]['snippet']
        assert not _has_production_fact_content(text), (
            "'Dalí: Disruption and Devotion' snippet should NOT be production-fact-rich"
        )


class TestRankingPrioritizesProductionFacts:
    """rank_and_cap_snippets delivers production-fact snippets to the top."""

    def test_stop3_top_snippets_contain_publisher_or_printer(self):
        """Top 5 for Au Soleil du Plafond must contain Tériade or Mourlot."""
        ranked, report = rank_and_cap_snippets(
            STOP3_SNIPPETS, artist='Joan Miró', work_title='Au Soleil du Plafond'
        )
        all_text = ' '.join(s['snippet'] for s in ranked)
        assert 'Tériade' in all_text or 'Mourlot' in all_text, (
            f"Top {len(ranked)} snippets for Au Soleil du Plafond must mention "
            f"publisher (Tériade) or printer (Mourlot). Got: {[s['title'][:40] for s in ranked]}"
        )

    def test_stop3_irrelevant_mfa_news_ranks_below_facts(self):
        """MFA renovation news must rank below production-fact snippets."""
        ranked, report = rank_and_cap_snippets(
            STOP3_SNIPPETS, artist='Joan Miró', work_title='Au Soleil du Plafond'
        )
        # The MFA news snippet should be at the BOTTOM, not the top
        mfa_news_position = None
        for i, s in enumerate(ranked):
            if s['url'] == 'https://www.mfa.org/news/galleries':
                mfa_news_position = i
                break
        if mfa_news_position is not None:
            # It made it in (only 5 in fixture) — but must be last
            assert mfa_news_position >= 3, (
                f"MFA news at position {mfa_news_position} — must be below fact-rich snippets"
            )

    def test_stop2_sothebys_in_top(self):
        """Sotheby's snippet with edition+technique must reach the prompt."""
        ranked, report = rank_and_cap_snippets(
            STOP2_SNIPPETS, artist='Salvador Dalí', work_title='Moses and Monotheism'
        )
        ranked_urls = {s['url'] for s in ranked}
        assert 'https://www.sothebys.com/dali-moses' in ranked_urls, (
            "Sotheby's snippet with 'drypoints and lithographs on sheepskin' "
            "must reach the prompt for Moses and Monotheism"
        )

    def test_stop2_different_exhibition_excluded(self):
        """Snippets about 'Dalí: Disruption and Devotion' must NOT outrank Moses facts."""
        ranked, report = rank_and_cap_snippets(
            STOP2_SNIPPETS, artist='Salvador Dalí', work_title='Moses and Monotheism'
        )
        ranked_urls = {s['url'] for s in ranked}
        # The "Dalí In Context" snippet about a different exhibition must not be #1
        assert ranked[0]['url'] != 'https://www.mfa.org/dali-context', (
            "Different-exhibition snippet must NOT be the top-ranked snippet"
        )


class TestBuildSnippetBlockDemandsNamedFields:
    """build_snippet_block prompt demands specific named fields (LOCAL-419)."""

    def test_prompt_demands_date(self):
        block = build_snippet_block(STOP3_SNIPPETS[:3], artist='Juan Gris', specifics=[])
        assert 'DATE' in block, "Prompt must demand DATE as a named field"

    def test_prompt_demands_publisher(self):
        block = build_snippet_block(STOP3_SNIPPETS[:3], artist='Juan Gris', specifics=[])
        assert 'PUBLISHER' in block, "Prompt must demand PUBLISHER as a named field"

    def test_prompt_demands_printer(self):
        block = build_snippet_block(STOP3_SNIPPETS[:3], artist='Juan Gris', specifics=[])
        assert 'PRINTER' in block, "Prompt must demand PRINTER as a named field"

    def test_prompt_demands_edition(self):
        block = build_snippet_block(STOP3_SNIPPETS[:3], artist='Juan Gris', specifics=[])
        assert 'EDITION' in block, "Prompt must demand EDITION as a named field"

    def test_prompt_warns_against_empty_prose(self):
        """Prompt must explicitly warn against the empty-prose failure mode."""
        block = build_snippet_block(STOP3_SNIPPETS[:3], artist='Juan Gris', specifics=[])
        assert 'FAILURE MODE' in block or 'Do NOT write' in block, (
            "Prompt must warn against empty prose like 'reveals a deep connection'"
        )

    def test_prompt_demands_at_least_two(self):
        """Prompt must ask for at least TWO facts, not just one."""
        block = build_snippet_block(STOP3_SNIPPETS[:3], artist='Juan Gris', specifics=[])
        assert 'TWO' in block or 'at least two' in block.lower(), (
            "Prompt must demand at least TWO named fields (one was not enough for gpt-3.5)"
        )
