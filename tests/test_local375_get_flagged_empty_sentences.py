#!/usr/bin/env python3
"""Tests for LOCAL-375: get_flagged_empty_sentences helper.

Per D294: this test goes red when the helper is reverted.
Expected red count when get_flagged_empty_sentences is removed: 3 tests fail.

Verifies:
  1. Known-empty sentences are returned by the helper.
  2. Known-factual sentences are NOT returned.
  3. The helper uses the same splitting logic as analyze_stop
     (short fragments ≤15 chars are excluded even if they would technically
     flag as empty).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tour_rubric_scorer import get_flagged_empty_sentences, _is_empty_sentence


class TestGetFlaggedEmptySentences:
    """get_flagged_empty_sentences must extract exactly the sentences
    that _is_empty_sentence flags from a multi-sentence body."""

    # Known-empty: no entity, no number, no orientation, no attribution
    EMPTY_BODY = (
        "The atmosphere here is truly captivating and deeply moving. "
        "A sense of wonder pervades the space around you. "
        "The artistry on display speaks volumes about the human spirit."
    )

    # Known-factual: proper nouns, dates, measurements
    FACTUAL_BODY = (
        "Built in 1648 by the Lascaris-Ventimiglia family, this Baroque palace "
        "features a monumental staircase decorated with 17th-century frescoes. "
        "The collection includes a Stradivarius violin from 1738."
    )

    # Mixed: one empty, two factual
    MIXED_BODY = (
        "The experience here is truly unforgettable and deeply stirring. "
        "Jean-Baptiste Carpeaux sculpted this piece in 1872. "
        "The marble stands 2.4 meters tall."
    )

    def test_known_empty_all_flagged(self):
        """All sentences in EMPTY_BODY must be returned by the helper."""
        flagged = get_flagged_empty_sentences(self.EMPTY_BODY)
        assert len(flagged) == 3, (
            f"Expected 3 flagged sentences, got {len(flagged)}: {flagged}"
        )

    def test_known_factual_none_flagged(self):
        """No sentences in FACTUAL_BODY should be returned."""
        flagged = get_flagged_empty_sentences(self.FACTUAL_BODY)
        assert len(flagged) == 0, (
            f"Expected 0 flagged sentences, got {len(flagged)}: {flagged}"
        )

    def test_mixed_only_empty_flagged(self):
        """Only the empty sentence in MIXED_BODY is returned."""
        flagged = get_flagged_empty_sentences(self.MIXED_BODY)
        assert len(flagged) == 1, (
            f"Expected 1 flagged sentence, got {len(flagged)}: {flagged}"
        )
        assert "unforgettable" in flagged[0]

    def test_short_fragments_excluded(self):
        """Fragments ≤15 chars are not checked (consistent with analyze_stop)."""
        body = "Wow. So short. The atmosphere of this place is something remarkable."
        flagged = get_flagged_empty_sentences(body)
        # Only the long sentence should be eligible for flagging
        # "Wow." and "So short." are ≤15 chars and excluded
        assert all(len(s) > 15 for s in flagged)

    def test_empty_body_returns_empty_list(self):
        """An empty string body returns no flagged sentences."""
        assert get_flagged_empty_sentences("") == []
        assert get_flagged_empty_sentences("   ") == []
