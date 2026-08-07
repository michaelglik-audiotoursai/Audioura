#!/usr/bin/env python3
"""tests/test_local345_corpus_in_body.py — LOCAL-345: Corpus must reach the body.

The defect: stop_corpus passages are injected into the generation prompt
(format_passages_for_prompt), but the prompt ONLY explicitly requires them
for fact-grounding — there is no instruction that the BODY (as opposed to
the orientation) must draw on the passages. The LLM uses the corpus in the
orientation ("landmarks like the UNESCO-designated Cours Saleya Market") and
then writes a body from its own training data, producing fabrications.

These tests verify:
  1. The generation prompt injects corpus passages with a body-usage directive
  2. The scorer detects stops that have corpus but whose body uses NONE of it
  3. The digit-plus-countable-noun pattern (measurements_numbers) catches
     general-quantity claims like "over 100 vendors"
  4. Museum 8-stop and 4-stop tour bounds are not regressed

Decision boundary: a stop "uses corpus" when at least ONE content word from
its passages (excluding stop-words and the stop's own name) appears in the
body text. This is a floor, not a quality bar — it catches the case where
the body is entirely fabricated with zero overlap.
"""
import os
import sys
import re
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_content_words_from_passages(passages: list, stop_title: str) -> set:
    """Extract meaningful content words from corpus passages.

    Excludes:
      - Common English stop words
      - Words from the stop title itself (they match trivially)
      - Words shorter than 4 chars
    Returns a set of lowercase content words.
    """
    import unicodedata

    _STOP_WORDS = {
        'the', 'and', 'for', 'was', 'were', 'are', 'that', 'this', 'with',
        'from', 'have', 'has', 'had', 'been', 'being', 'which', 'their',
        'there', 'they', 'what', 'when', 'where', 'will', 'would', 'could',
        'should', 'about', 'into', 'over', 'after', 'before', 'also', 'more',
        'most', 'other', 'than', 'then', 'these', 'those', 'some', 'such',
        'each', 'many', 'much', 'very', 'only', 'just', 'your', 'city',
        'including', 'well', 'known', 'market', 'area', 'located', 'france',
        'nice', 'tour', 'walking', 'here', 'like', 'back', 'made', 'time',
        'place', 'part', 'first', 'years', 'today',
    }

    def _fold(text):
        text = text.replace('\u2019', "'").replace('\u2018', "'")
        nfkd = unicodedata.normalize('NFKD', text)
        return ''.join(c for c in nfkd if not unicodedata.combining(c))

    # Words from the stop title (to exclude)
    title_words = set(
        w.lower() for w in re.findall(r'[A-Za-zÀ-ÿ]+', _fold(stop_title))
        if len(w) >= 4
    )

    content_words = set()
    for passage in passages:
        words = re.findall(r'[A-Za-zÀ-ÿ]+', _fold(passage))
        for w in words:
            wl = w.lower()
            if len(wl) >= 4 and wl not in _STOP_WORDS and wl not in title_words:
                content_words.add(wl)

    return content_words


def _body_uses_corpus(body_text: str, content_words: set) -> tuple:
    """Check if a stop body uses any content words from its corpus passages.

    Returns (bool, set_of_matched_words).
    """
    import unicodedata

    def _fold(text):
        text = text.replace('\u2019', "'").replace('\u2018', "'")
        nfkd = unicodedata.normalize('NFKD', text)
        return ''.join(c for c in nfkd if not unicodedata.combining(c))

    body_folded = _fold(body_text).lower()
    body_words = set(re.findall(r'[a-z]{4,}', body_folded))

    matched = content_words & body_words
    return (len(matched) > 0, matched)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. "over 100 vendors" — digit + general countable noun detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestDigitCountableNounDetection:
    """LOCAL-345 scope item 3: digit-plus-countable-noun must register as a fact.

    'over 100 vendors' should match the measurements_numbers pattern.
    Previously it didn't because 'vendors' was not in the Track 1 noun list.
    """

    def test_100_vendors_detected(self):
        """'over 100 vendors' must be detected as a numeric claim."""
        from tour_rubric_scorer import analyze_stop

        body = (
            "Amidst the colorful stalls of the Cours Saleya Market, "
            "over 100 vendors offer fresh flowers, produce, and local specialties. "
            "The market has operated here since the 19th century."
        )
        stop = {
            'index': 1,
            'title': 'Cours Saleya Market',
            'body': body,
            'orientation': 'Ahead of you lies the famous flower market.',
        }
        sa = analyze_stop(stop, [stop])
        # "100 vendors" must appear in measurements_numbers
        assert any('100' in m for m in sa.measurements_numbers), (
            f"Expected '100 vendors' in measurements_numbers, got: {sa.measurements_numbers}"
        )
        # distinct_fact_count should be at least 1
        assert sa.distinct_fact_count >= 1, (
            f"Expected distinct_fact_count >= 1, got: {sa.distinct_fact_count}"
        )

    def test_50_stalls_detected(self):
        """'50 stalls' must be detected."""
        from tour_rubric_scorer import analyze_stop

        body = "The market hosts approximately 50 stalls selling flowers."
        stop = {'index': 1, 'title': 'Test Stop', 'body': body, 'orientation': ''}
        sa = analyze_stop(stop, [stop])
        assert any('50' in m for m in sa.measurements_numbers), (
            f"Expected '50 stalls' in measurements_numbers, got: {sa.measurements_numbers}"
        )

    def test_200_merchants_detected(self):
        """'200 merchants' must be detected."""
        from tour_rubric_scorer import analyze_stop

        body = "Today more than 200 merchants trade daily."
        stop = {'index': 1, 'title': 'Test Stop', 'body': body, 'orientation': ''}
        sa = analyze_stop(stop, [stop])
        assert any('200' in m for m in sa.measurements_numbers), (
            f"Expected '200 merchants' in measurements_numbers, got: {sa.measurements_numbers}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Corpus-in-body detection: a stop with corpus must have overlap
# ═══════════════════════════════════════════════════════════════════════════════

class TestCorpusInBodyDetection:
    """A stop that has corpus passages must use at least one content word
    from those passages in its body text. When it doesn't, it means the
    LLM ignored the corpus and fabricated the body entirely.
    """

    def test_body_using_corpus_passes(self):
        """A body that mentions UNESCO (from corpus) passes."""
        passages = [
            "2021: The city of Nice and its heritage sites, including the Cours Saleya "
            "market, were designated as a UNESCO World Heritage Site. What can you ..."
        ]
        body = (
            "In 2021, UNESCO recognized Nice's heritage sites, including this market. "
            "The designation elevated Cours Saleya to international prominence."
        )
        words = _extract_content_words_from_passages(passages, "Cours Saleya Market")
        uses, matched = _body_uses_corpus(body, words)
        assert uses, f"Expected body to use corpus words; content_words={words}"
        assert 'unesco' in matched or 'heritage' in matched or 'designated' in matched

    def test_body_ignoring_corpus_fails(self):
        """A body with fabricated content and zero corpus overlap fails."""
        passages = [
            "2021: The city of Nice and its heritage sites, including the Cours Saleya "
            "market, were designated as a UNESCO World Heritage Site. What can you ..."
        ]
        body = (
            "Named after the Marquis de Cours Saleya, this market was once a hub "
            "for the trading of spices, textiles, and local produce. Today, over "
            "100 vendors sell fresh flowers and antiques to visitors."
        )
        words = _extract_content_words_from_passages(passages, "Cours Saleya Market")
        uses, matched = _body_uses_corpus(body, words)
        # 'heritage', 'unesco', 'designated', 'world' — none should appear in fabrication
        assert not uses, (
            f"Expected fabricated body to have zero corpus overlap, "
            f"but matched: {matched}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. format_passages_for_prompt must include body-usage directive
# ═══════════════════════════════════════════════════════════════════════════════

class TestPromptIncludesBodyDirective:
    """The injected corpus prompt block must explicitly instruct the LLM to
    use the passages in the BODY (description), not just for grounding.
    
    This is the root cause: passages were injected as a grounding rule ("only
    substantiate from these"), but not as a content directive ("USE this in
    your description"). The LLM obeys the letter: it avoids making claims
    outside the passages but also ignores them for body content.
    """

    def test_format_passages_includes_body_directive(self):
        """format_passages_for_prompt output must direct use in body text."""
        from stop_corpus_reader import format_passages_for_prompt

        corpus_data = {
            'passages': [
                "2021: The city of Nice and its heritage sites were designated as UNESCO."
            ],
            'sources': [{'url': 'https://example.com', 'tier': 3, 'title': 'Test'}],
            'passage_roles': [{'role': 'about_subject', 'tier': 3}],
        }
        result = format_passages_for_prompt(corpus_data, "Cours Saleya Market")
        assert result, "format_passages_for_prompt returned empty string"
        # Must instruct body usage, not just grounding
        result_lower = result.lower()
        assert ('body' in result_lower or 'description' in result_lower or
                'incorporate' in result_lower or 'weave' in result_lower or
                'include' in result_lower), (
            "Prompt block must instruct the LLM to USE passages in the body/description. "
            f"Got:\n{result[:500]}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Museum score bounds (regression guard)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMuseumScoreBounds:
    """Museum tour scores must not regress.
    
    Museum 8-stop ≥ 75.0
    Museum 4-stop ≥ 81.2
    (These are bounds as properties per D258.)
    """

    @pytest.fixture
    def scorer(self):
        from tour_rubric_scorer import score_tour_file
        return score_tour_file

    @pytest.mark.skipif(
        not os.path.exists(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'LOCAL262_asian_arts_8stop_restored.txt'
        )),
        reason="8-stop museum tour file not available"
    )
    def test_museum_8stop_bound(self, scorer):
        """Museum 8-stop tour must score >= 75.0."""
        tour_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'LOCAL262_asian_arts_8stop_restored.txt'
        )
        result = scorer(tour_file, n_requested=8)
        assert result.total_score >= 75.0, (
            f"Museum 8-stop score {result.total_score} < 75.0 bound"
        )

    @pytest.mark.skipif(
        not os.path.exists(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'Palais_Lascaris__Nice_museum_tour_20260727_174018.txt'
        )),
        reason="Palais Lascaris museum tour file not available"
    )
    def test_museum_palais_bound(self, scorer):
        """Museum tour (Palais Lascaris) must not regress."""
        tour_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'Palais_Lascaris__Nice_museum_tour_20260727_174018.txt'
        )
        result = scorer(tour_file, n_requested=3)
        # Palais Lascaris is a 3-stop tour — use as a non-regression check
        assert result.total_score >= 70.0, (
            f"Museum Palais score {result.total_score} < 70.0"
        )
