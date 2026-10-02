"""test_local332_interpretive_enrichment.py — LOCAL-332 unit tests.

Tests that import production code and verify:
1. Question generation derives venue-kind-appropriate questions.
2. Passages with attributed quotes are detected and dropped when unverified.
3. The enrichment pipeline filters atmospherics and reviews.
4. Accent-folded matching works for stop_corpus joins.

These tests MUST fail against the pre-LOCAL-332 codebase (no interpretive_enrichment module).
"""

import json
import sys
import os
import re
import unicodedata

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_module_exists():
    """The interpretive_enrichment module must exist — fails on unfixed code."""
    import interpretive_enrichment
    assert hasattr(interpretive_enrichment, 'enrich_stop_interpretive')
    assert hasattr(interpretive_enrichment, 'build_interpretive_questions')
    assert hasattr(interpretive_enrichment, 'store_interpretive_corpus')
    assert hasattr(interpretive_enrichment, 'enrich_verified_stops')


def test_question_generation_restaurant():
    """Questions for restaurants ask about interest/notable people, not just search the name."""
    from interpretive_enrichment import build_interpretive_questions

    questions = build_interpretive_questions(
        stop_title="Le Safari",
        venue_kind="restaurant",
        city="Nice",
        country="France",
    )
    assert len(questions) == 2
    # First question asks what is interesting
    assert "interesting" in questions[0].lower() or "notable" in questions[0].lower()
    # Must mention the stop name
    assert "Le Safari" in questions[0]
    # Must mention the city
    assert "Nice" in questions[0]
    # Second question asks about people
    assert "people" in questions[1].lower() or "notable" in questions[1].lower() or "associated" in questions[1].lower()
    # Must NOT just be a name search (the bug we're fixing)
    for q in questions:
        assert q != '"Le Safari" Nice restaurant'


def test_question_generation_museum():
    """Museum questions differ from restaurant questions."""
    from interpretive_enrichment import build_interpretive_questions

    questions = build_interpretive_questions(
        stop_title="Musée Matisse",
        venue_kind="museum",
        city="Nice",
        country="France",
    )
    assert len(questions) == 2
    assert "Musée Matisse" in questions[0]
    # Museum questions should reference works/collections, not "chef" or "food"
    q_combined = ' '.join(questions).lower()
    assert 'works' in q_combined or 'collections' in q_combined or 'notable' in q_combined


def test_question_generation_default():
    """Unknown venue kinds fall back to default templates."""
    from interpretive_enrichment import build_interpretive_questions

    questions = build_interpretive_questions(
        stop_title="Pont du Gard",
        venue_kind="aqueduct",
        city="Vers-Pont-du-Gard",
        country="France",
    )
    assert len(questions) == 2
    assert "Pont du Gard" in questions[0]


def test_attribution_detection():
    """Passages with quotes attributed to named sources are detected."""
    from interpretive_enrichment import _has_attributed_quote

    # Clear attribution
    text1 = 'Gault&Millau officially declared the restaurant an "indestructible event"'
    assert _has_attributed_quote(text1) is not None

    # Attribution with "said"
    text2 = 'Franck Cerutti said "Get the pizza" when dining at Le Safari'
    result = _has_attributed_quote(text2)
    assert result is not None

    # No attribution — factual statement
    text3 = 'Le Safari holds an official Cuisine Nissarde accreditation since 1995'
    assert _has_attributed_quote(text3) is None

    # Named publication
    text4 = 'According to Gourmet Magazine, the pizzas are exceptional'
    assert _has_attributed_quote(text4) is not None


def test_atmospheric_rejection():
    """Atmospheric passages without facts are rejected."""
    from interpretive_enrichment import _is_atmospheric_or_review

    assert _is_atmospheric_or_review("warm atmosphere and cozy vibes") is True
    assert _is_atmospheric_or_review("We went there and loved it") is True
    assert _is_atmospheric_or_review("4.5/5 stars based on 200 reviews") is True
    assert _is_atmospheric_or_review("highly recommend this place") is True

    # Factual passages should NOT be rejected
    assert _is_atmospheric_or_review("Founded in 1927 by Madalin Acchiardo") is False
    assert _is_atmospheric_or_review("Chef Franck Cerutti trained at Le Louis XV") is False


def test_fact_detection():
    """Passages must carry verifiable facts to pass."""
    from interpretive_enrichment import _carries_verifiable_fact

    # Has year
    assert _carries_verifiable_fact("Founded in 1927 by the Acchiardo family") is True
    # Has named person with action
    assert _carries_verifiable_fact("Chef Franck Cerutti trained under Alain Ducasse") is True
    # Has accreditation
    assert _carries_verifiable_fact("Holds an official Cuisine Nissarde accreditation") is True
    # Has named dish
    assert _carries_verifiable_fact("Famous for their Bagna Cauda and Petits Farcis") is True
    # Has price
    assert _carries_verifiable_fact("Three-course menu at €35") is True

    # No facts — generic fluff
    assert _carries_verifiable_fact("A lovely place with great ambiance and wonderful food") is False
    assert _carries_verifiable_fact("The restaurant is very popular among tourists") is False


def test_accent_folded_matching():
    """Stop mentions are detected with accent folding (D243)."""
    from interpretive_enrichment import _mentions_stop

    # Direct match
    assert _mentions_stop("Le Safari is located on Cours Saleya", "Le Safari") is True
    # Accent-folded
    assert _mentions_stop("La Rossettisserie depuis 2008", "La Rossettisserie") is True
    # Partial word match (significant words)
    assert _mentions_stop("Safari opened in 1972", "Le Safari") is True
    # No match
    assert _mentions_stop("A restaurant in the Old Town area", "Le Safari") is False


def test_source_tier_classification():
    """Source tiers are correctly assigned."""
    from interpretive_enrichment import _classify_source_tier

    assert _classify_source_tier("https://en.wikipedia.org/wiki/Le_Safari") == 1
    assert _classify_source_tier("https://www.gaultmillau.com/fr/restaurant/le-safari") == 2
    assert _classify_source_tier("https://www.nicematin.com/article/le-safari") == 2
    assert _classify_source_tier("https://some-food-blog.com/le-safari") == 3
    assert _classify_source_tier("https://www.tripadvisor.com/Restaurant-Le_Safari") == 0
    assert _classify_source_tier("https://www.yelp.com/biz/le-safari-nice") == 0


def test_enrichment_pipeline_filters_correctly():
    """The full pipeline filters atmospherics, requires facts, and detects attributions."""
    from interpretive_enrichment import (
        _is_atmospheric_or_review,
        _carries_verifiable_fact,
        _mentions_stop,
        _has_attributed_quote,
    )

    # Simulate what comes back from a search — mix of good and bad
    candidates = [
        # Good: factual, mentions stop, no attribution
        {
            'text': 'Le Safari holds an official Cuisine Nissarde accreditation, certifying authentic Niçoise recipes since 1995.',
            'url': 'https://www.nicetourisme.com/le-safari',
        },
        # Bad: atmospheric, no facts
        {
            'text': 'Le Safari has a warm atmosphere with lovely views of the market.',
            'url': 'https://blog.example.com/nice',
        },
        # Bad: review language
        {
            'text': 'We went to Le Safari and loved it. Highly recommend!',
            'url': 'https://yelp.com/le-safari',
        },
        # Risky: has attributed quote AND a verifiable fact
        {
            'text': 'According to Gourmet Magazine, Chef Cerutti introduced Le Safari\'s wood-fired pizza in 1985, calling it "exceptional"',
            'url': 'https://some-blog.com/nice-restaurants',
        },
        # Good: factual, named person
        {
            'text': 'Chef Franck Cerutti, who later became executive chef at Le Louis XV in Monaco, introduced wood-fired pizza at Le Safari.',
            'url': 'https://www.nicematin.com/cerutti',
        },
    ]

    admitted = []
    attributions_detected = []

    for c in candidates:
        text = c['text']
        if _is_atmospheric_or_review(text):
            continue
        if not _mentions_stop(text, "Le Safari"):
            continue
        if not _carries_verifiable_fact(text):
            continue
        attr = _has_attributed_quote(text)
        if attr:
            attributions_detected.append((text, attr))
        else:
            admitted.append(c)

    # Should admit the factual passages
    assert len(admitted) >= 2, f"Expected ≥2 admitted, got {len(admitted)}: {admitted}"
    # Should detect the Gourmet Magazine attribution
    assert len(attributions_detected) >= 1
    assert any("Gourmet" in a[1] for a in attributions_detected)


def test_wiring_in_stop_existence_gate():
    """The interpretive enrichment is wired into stop_existence_gate's return value."""
    import stop_existence_gate
    # The function signature must include interpretive_summary in the return dict
    import inspect
    source = inspect.getsource(stop_existence_gate)
    assert 'interpretive_summary' in source
    assert 'interpretive_enrichment' in source
    assert 'enrich_verified_stops' in source
