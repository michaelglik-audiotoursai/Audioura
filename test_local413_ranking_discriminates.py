#!/usr/bin/env python3
"""test_local413_ranking_discriminates.py — Proves LOCAL-412 ranking works.

Asserts on BEHAVIOUR, not source strings:
  1. A catalogue snippet scores strictly below a narrative snippet
  2. The top-5 selection changes when catalogue entries are present
  3. No more than 3 snippets share the top score on a realistic input set

Fails against the pre-412 ranker (snippet_ranker_pre412.py).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from snippet_ranker import score_snippet, rank_and_cap_snippets


# ──────────────────────────────────────────────────────────────────────────────
# Realistic test data — mixed catalogue and narrative snippets
# These are representative of what Serper returns for "Mourlot lithography Miró"
# ──────────────────────────────────────────────────────────────────────────────

NARRATIVE_SNIPPETS = [
    {
        'title': "Picasso met Fernand Mourlot in October 1945",
        'snippet': ("In October 1945, Picasso visited the Mourlot lithography workshop "
                    "on Rue de Chabrol in Paris. Fernand Mourlot, the master printer, "
                    "persuaded him to try lithography. Picasso returned almost daily for "
                    "the next four months, producing over 200 lithographs."),
        'url': 'https://www.moma.org/explore/picasso-lithographs',
        'tier': 'tier1',
    },
    {
        'title': "Louis Broder commissioned Miró's Le Lézard",
        'snippet': ("In 1967, publisher Louis Broder commissioned Joan Miró to illustrate "
                    "a series of poems. Miró produced 15 colour lithographs at the Mourlot "
                    "workshop, printed on Japan paper. The edition was limited to 138 copies."),
        'url': 'https://www.mfa.org/collections/prints',
        'tier': 'tier1',
    },
    {
        'title': "Boris Fridman donated the Miró suite to MFA Boston",
        'snippet': ("In 2003, collector Boris Fridman donated his complete set of Miró's "
                    "Le Lézard aux plumes d'or to the Museum of Fine Arts, Boston. "
                    "Fridman had acquired the portfolio at auction in 1998."),
        'url': 'https://www.mfa.org/news/fridman-gift',
        'tier': 'tier1',
    },
    {
        'title': "Mourlot Frères established their atelier in 1852",
        'snippet': ("The Mourlot printing house was founded in 1852 on Rue du Faubourg "
                    "Saint-Denis. Under Fernand Mourlot's direction after 1921, it became "
                    "the premier lithography atelier in Paris, producing editions for "
                    "Picasso, Braque, Chagall, Matisse, and Miró."),
        'url': 'https://en.wikipedia.org/wiki/Mourlot_Studios',
        'tier': 'tier1',
    },
    {
        'title': "Pierre Reverdy and Pablo Picasso: Le Chant des morts",
        'snippet': ("In 1948, Pierre Reverdy wrote the poems for Le Chant des morts, "
                    "which Picasso illustrated with 125 lithographs printed by Mourlot. "
                    "Reverdy and Picasso had met in 1910 in Montmartre."),
        'url': 'https://www.metmuseum.org/reverdy-picasso',
        'tier': 'tier1',
    },
]

CATALOGUE_SNIPPETS = [
    {
        'title': "Lot 34: Joan Miró, Le Lézard aux plumes d'or",
        'snippet': ("Joan Miró (1893-1983). Le Lézard aux plumes d'or, 1971. "
                    "Color lithograph on Japan paper. 38.1 × 28.2 cm. "
                    "Signed and numbered 24/50. Estimate: $30,000-$40,000."),
        'url': 'https://www.sothebys.com/lot/miro-le-lezard',
        'tier': 'tier2',
    },
    {
        'title': "Christie's: Miró Lithographs, Various Editions",
        'snippet': ("Lot 142. Joan Miró. Lithograph in colours, 1971. "
                    "Sheet: 445 × 350 mm. Published by Mourlot, Paris. "
                    "Provenance: Private collection, Geneva. USD 18,000-25,000."),
        'url': 'https://www.christies.com/lot/miro-litho',
        'tier': 'tier2',
    },
    {
        'title': "Artcurial: Pablo Picasso Prints Sale",
        'snippet': ("Lot 89. Pablo Picasso. La Colombe, 1949. Lithograph. "
                    "50 × 65 cm. Published by Mourlot. Literature: Bloch 583. "
                    "Estimate €12,000-€15,000. Provenance: Galerie Beyeler."),
        'url': 'https://www.artcurial.com/picasso-prints',
        'tier': 'tier2',
    },
    {
        'title': "Ketterer Kunst: Mourlot Lithographs Auction",
        'snippet': ("Lot 201. Marc Chagall. Daphnis et Chloé, 1961. Mourlot 308. "
                    "42.5 × 32.0 cm. Color lithograph. Edition of 60. "
                    "Bibliography: Sorlier, p. 45. EUR 8,000-10,000."),
        'url': 'https://www.kettererkunst.com/chagall-mourlot',
        'tier': 'tier2',
    },
    {
        'title': "Bonhams: Modern Prints and Multiples",
        'snippet': ("Lot 55. Joan Miró. L'Oiseau solaire, 1966. Lithograph in colours. "
                    "Mourlot 442. 75.5 × 55.7 cm. Signed and numbered 34/75. "
                    "Exhibited: Galerie Maeght, Paris 1967. GBP 6,000-8,000."),
        'url': 'https://www.bonhams.com/miro-prints',
        'tier': 'tier2',
    },
]

# Full realistic input: mixed narrative + catalogue (what real search returns)
REALISTIC_INPUT = NARRATIVE_SNIPPETS + CATALOGUE_SNIPPETS


class TestCatalogueVsNarrative:
    """A catalogue snippet must score strictly below a narrative snippet."""

    def test_narrative_scores_above_catalogue(self):
        """Every narrative snippet scores higher than every catalogue snippet."""
        for narr in NARRATIVE_SNIPPETS:
            narr_score = score_snippet(narr, artist='Joan Miró')
            for cat in CATALOGUE_SNIPPETS:
                cat_score = score_snippet(cat, artist='Joan Miró')
                assert narr_score > cat_score, (
                    f"Narrative '{narr['title'][:40]}' (score={narr_score}) "
                    f"not above catalogue '{cat['title'][:40]}' (score={cat_score})"
                )

    def test_catalogue_penalty_applied(self):
        """Catalogue snippets get a score reduction vs what they'd get without penalty."""
        cat = CATALOGUE_SNIPPETS[0]  # Sotheby's Miró lot
        score = score_snippet(cat, artist='Joan Miró')
        # Without the catalogue penalty, this snippet has: person(3)+verb(3)+date(2)+place(1)+tier(1)+artist(1)=11
        # With LOCAL-412 penalty (-4), it should be ≤7
        assert score <= 7, (
            f"Catalogue snippet scores {score} — penalty not applied or insufficient"
        )

    def test_event_bonus_applied(self):
        """Narrative/event snippets get a bonus that lifts them above base scoring."""
        narr = NARRATIVE_SNIPPETS[0]  # Picasso met Mourlot in 1945
        score = score_snippet(narr, artist='Joan Miró')
        # Base: person(3)+verb(3)+date(2)+place(1)+tier(1)=10, plus event bonus(+5)=15
        assert score >= 13, (
            f"Event snippet scores only {score} — event bonus not applied"
        )


class TestTopFiveSelectionChanges:
    """The top-5 selection must change when catalogue entries are present."""

    def test_top5_excludes_catalogues_when_mixed(self):
        """With mixed input, top-5 should contain NO catalogue snippets."""
        ranked, report = rank_and_cap_snippets(REALISTIC_INPUT, artist='Joan Miró', cap=5)
        ranked_urls = {s['url'] for s in ranked}
        catalogue_urls = {s['url'] for s in CATALOGUE_SNIPPETS}
        overlap = ranked_urls & catalogue_urls
        assert len(overlap) == 0, (
            f"Top-5 contains {len(overlap)} catalogue snippet(s): "
            f"{[u.split('/')[-1] for u in overlap]}"
        )

    def test_top5_all_narrative_when_mixed(self):
        """With mixed input, all top-5 should be narrative snippets."""
        ranked, report = rank_and_cap_snippets(REALISTIC_INPUT, artist='Joan Miró', cap=5)
        narrative_urls = {s['url'] for s in NARRATIVE_SNIPPETS}
        for snip in ranked:
            assert snip['url'] in narrative_urls, (
                f"Non-narrative snippet in top-5: '{snip['title'][:50]}'"
            )

    def test_selection_differs_from_input_order(self):
        """Ranking must re-order: first 5 of input ≠ top 5 after ranking
        (because input has narratives then catalogues, but a shuffled input
        would demonstrate the ranker actually discriminates)."""
        # Shuffle: alternate catalogue and narrative
        shuffled = []
        for i in range(5):
            shuffled.append(CATALOGUE_SNIPPETS[i])
            shuffled.append(NARRATIVE_SNIPPETS[i])
        ranked, _ = rank_and_cap_snippets(shuffled, artist='Joan Miró', cap=5)
        # If ranking discriminates, top-5 should be all narrative (not alternating)
        narrative_urls = {s['url'] for s in NARRATIVE_SNIPPETS}
        for snip in ranked:
            assert snip['url'] in narrative_urls, (
                f"Catalogue snippet survived ranking: '{snip['title'][:50]}'"
            )


class TestNoMoreThanThreeTied:
    """No more than 3 snippets may share the top score on realistic input."""

    def test_max_three_tied_at_top(self):
        """Score the realistic input set and verify score spread."""
        scores = []
        for snip in REALISTIC_INPUT:
            s = score_snippet(snip, artist='Joan Miró')
            if s != -999:
                scores.append(s)
        assert len(scores) >= 5, f"Too few non-rejected snippets: {len(scores)}"
        top_score = max(scores)
        tied_at_top = scores.count(top_score)
        assert tied_at_top <= 3, (
            f"{tied_at_top} snippets tied at top score {top_score} "
            f"(max allowed: 3). Score distribution: {sorted(set(scores), reverse=True)}"
        )

    def test_score_spread_at_least_four_distinct(self):
        """Realistic input should produce at least 4 distinct score values."""
        scores = set()
        for snip in REALISTIC_INPUT:
            s = score_snippet(snip, artist='Joan Miró')
            if s != -999:
                scores.add(s)
        assert len(scores) >= 4, (
            f"Only {len(scores)} distinct score(s): {sorted(scores, reverse=True)}. "
            f"Ranking does not discriminate enough."
        )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v', '--tb=short']))
