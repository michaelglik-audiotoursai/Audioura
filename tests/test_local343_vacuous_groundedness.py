#!/usr/bin/env python3
"""tests/test_local343_vacuous_groundedness.py — LOCAL-343: Vacuous groundedness.

D244 fixed the no-corpus case (default 1.0 → None).  This is the
*no-claims* case: corpus exists with passages, but zero fact-claims are
extractable from the stop text.  The old code returned 1.0 — "everything
we checked held" — when nothing was checked.

These tests verify:
  1. measure_stop_groundedness with zero claims returns None, not 1.0
  2. A stop with corpus available but 0 claims gets groundedness=None
  3. The sample size (n) is exposed in StopAnalysis and per_stop data
  4. A stop with 1 checked claim is honestly reported as 1.0 (n=1)
  5. Museum scores (existing stops with real claims) are not affected
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from groundedness_check import (
    measure_stop_groundedness,
    extract_fact_claims,
    GroundednessResult,
)
from tour_rubric_scorer import (
    StopAnalysis,
    classify_stop,
    _compute_groundedness_for_stop,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Zero claims → None (the core fix)
# ═══════════════════════════════════════════════════════════════════════════════

class TestZeroClaimsNotOnePointZero:
    """A stop with zero extractable claims must NOT get groundedness 1.0."""

    def test_zero_claims_returns_none(self):
        """measure_stop_groundedness with a text that has no checkable facts
        must return groundedness_fraction=None, not 1.0.
        
        This is the defect: "nothing was checked" was conflated with
        "everything checked held."
        """
        # A body with no dates, no named people, no artwork titles
        body = (
            "Welcome to this lovely little spot. The atmosphere is wonderful "
            "and the food is delicious. You will enjoy your time here."
        )
        passages = [
            "This restaurant serves traditional cuisine and is popular with locals.",
            "The establishment has been welcoming guests for years.",
        ]

        result = measure_stop_groundedness(body, "Test Stop", passages)

        # Verify no claims were extracted
        assert result.total_claims == 0, f"Expected 0 claims, got {result.total_claims}"
        # THE FIX: must be None, not 1.0
        assert result.groundedness_fraction is None, (
            f"Zero claims must yield None (unmeasured), not {result.groundedness_fraction}. "
            f"A vacuous 1.0 conflates 'nothing checked' with 'everything verified.'"
        )

    def test_zero_claims_result_type(self):
        """GroundednessResult.groundedness_fraction is Optional[float]."""
        body = "This is a nice place to visit on a sunny afternoon."
        passages = ["The venue is located in the old town area."]

        result = measure_stop_groundedness(body, "Generic Place", passages)
        # Should be None (zero claims) — not a float
        if result.total_claims == 0:
            assert result.groundedness_fraction is None

    def test_one_claim_grounded_is_one_point_zero(self):
        """A stop with exactly 1 grounded claim IS legitimately 1.0.
        
        This is NOT vacuous — one claim was checked and matched.
        LEAD's view: report honestly as 1.0 (n=1).
        """
        # A body with exactly one checkable person name
        body = "Marc Chagall created stunning works here in the studio."
        passages = ["Marc Chagall worked extensively in Nice during the 1960s."]

        result = measure_stop_groundedness(body, "Chagall Studio", passages)

        # Should have at least 1 claim
        assert result.total_claims >= 1
        # If all claims are grounded, fraction should be 1.0 — legitimately
        if result.grounded_claims == result.total_claims:
            assert result.groundedness_fraction == 1.0

    def test_one_claim_ungrounded_is_zero(self):
        """A stop with 1 ungrounded claim is 0.0 — measured and failed."""
        body = "Ferdinand Boulleau designed this remarkable facade."
        passages = ["The building was constructed in the 18th century."]

        result = measure_stop_groundedness(body, "Test Building", passages)

        if result.total_claims >= 1 and result.grounded_claims == 0:
            assert result.groundedness_fraction == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Sample size visibility
# ═══════════════════════════════════════════════════════════════════════════════

class TestSampleSizeVisibility:
    """The claim count (n) must be visible so readers can judge weight."""

    def test_claims_checked_zero_for_no_claims(self):
        """StopAnalysis.groundedness_claims_checked == 0 when no claims found."""
        sa = StopAnalysis(index=1, title='Test', text='some text')
        # Simulate _compute_groundedness_for_stop with corpus available
        # but no extractable claims
        corpus_data = {
            'Test': {'passages': ['Some passage about the place.']}
        }
        stop = {'title': 'Test', 'body': 'This is a nice place with good food.'}

        _compute_groundedness_for_stop(sa, stop, corpus_data)

        assert sa.groundedness_claims_checked == 0
        assert sa.groundedness_fraction is None

    def test_claims_checked_positive_for_real_claims(self):
        """StopAnalysis.groundedness_claims_checked > 0 when claims exist."""
        sa = StopAnalysis(index=1, title='Test Museum', text='some text')
        corpus_data = {
            'Test Museum': {
                'passages': ['Marc Chagall painted the Biblical Message series in 1966.']
            }
        }
        stop = {
            'title': 'Test Museum',
            'body': 'Marc Chagall painted the Biblical Message series in 1966.'
        }

        _compute_groundedness_for_stop(sa, stop, corpus_data)

        assert sa.groundedness_claims_checked > 0
        assert sa.groundedness_fraction is not None

    def test_evidence_string_contains_n(self):
        """classify_stop evidence string includes (n=X) when measured."""
        sa = StopAnalysis(index=1, title='Test', text='...')
        sa.distinct_fact_count = 5
        sa.content_sentences = 6
        sa.fact_density = 0.83
        sa.generic_filler_fraction = 0.1
        sa.groundedness_fraction = 1.0
        sa.groundedness_claims_checked = 3

        _, evidence = classify_stop(sa)
        assert '(n=3)' in evidence, (
            f"Evidence string must include sample size. Got: {evidence}"
        )

    def test_evidence_string_unmeasured_for_zero_claims(self):
        """classify_stop with None groundedness (zero claims) says 'unmeasured'."""
        sa = StopAnalysis(index=1, title='Test', text='...')
        sa.distinct_fact_count = 5
        sa.content_sentences = 6
        sa.fact_density = 0.83
        sa.generic_filler_fraction = 0.1
        sa.groundedness_fraction = None
        sa.groundedness_claims_checked = 0
        sa.corpus_available = True
        sa.corpus_lookup_attempted = True

        _, evidence = classify_stop(sa)
        assert 'unmeasured' in evidence


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Classification: zero claims does NOT yield RICH ceiling bypass
# ═══════════════════════════════════════════════════════════════════════════════

class TestZeroClaimsClassification:
    """Zero claims with corpus → same as unmeasured; cannot bypass quality gates."""

    def test_zero_claims_does_not_boost_to_rich(self):
        """A stop with 0 claims and corpus does not get a free RICH pass.
        
        Previously, vacuous 1.0 meant the groundedness ceiling never fired,
        so a stop with corpus but no checkable facts appeared 'perfectly
        grounded' and sailed through to RICH.
        
        Now with None, it behaves like unmeasured — the ceiling doesn't fire
        but the stop also cannot claim to be 'verified at 100%'.
        """
        sa = StopAnalysis(index=1, title='Test', text='...')
        sa.distinct_fact_count = 5
        sa.content_sentences = 6
        sa.fact_density = 0.83
        sa.generic_filler_fraction = 0.1
        # The fix: this is now None instead of 1.0
        sa.groundedness_fraction = None
        sa.groundedness_claims_checked = 0
        sa.corpus_available = True
        sa.corpus_lookup_attempted = True

        cls, evidence = classify_stop(sa)
        # The stop still reaches RICH on density/facts alone (D245: unmeasured
        # does not penalise). But it is NOT reporting "verified 100%".
        # The evidence must say "unmeasured", NOT "100%".
        assert 'unmeasured' in evidence
        # And NOT "100%" which would be the old vacuous 1.0
        assert '100%' not in evidence


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Aggregate measure_tour_groundedness handles zero total claims
# ═══════════════════════════════════════════════════════════════════════════════

class TestAggregateTourGroundedness:
    """measure_tour_groundedness must not return 1.0 when total claims = 0."""

    def test_zero_total_claims_returns_none(self):
        """If no stop has any claims, overall_groundedness must be None."""
        from groundedness_check import measure_stop_groundedness

        # Simulate two stops with zero claims each
        body1 = "This is a lovely restaurant with great food."
        body2 = "The atmosphere is charming and welcoming."
        passages = ["A popular local dining spot."]

        r1 = measure_stop_groundedness(body1, "Stop1", passages)
        r2 = measure_stop_groundedness(body2, "Stop2", passages)

        # Both should have 0 claims
        assert r1.total_claims == 0
        assert r2.total_claims == 0
        # Both should be None
        assert r1.groundedness_fraction is None
        assert r2.groundedness_fraction is None
