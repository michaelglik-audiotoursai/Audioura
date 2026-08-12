#!/usr/bin/env python3
"""LOCAL-437: Gate exemption bound to a module-scope predicate.

KEY DIFFERENCE from LOCAL-436: this test IMPORTS should_exempt_from_existence_gate
from generate_tour_text. It does NOT re-type the expression. If the predicate is
neutralised (returns False unconditionally), these tests FAIL.

Binding per D242 #1, D277, D376.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from generate_tour_text import should_exempt_from_existence_gate


class TestExemptionPredicateBound:
    """The predicate at module scope IS the exemption logic. Tests import it."""

    def test_checklist_source_exempt(self):
        """Stops from 'checklist' source with deterministic fill → exempt."""
        assert should_exempt_from_existence_gate(True, 'checklist') is True

    def test_partial_source_exempt(self):
        """Stops from 'partial' source with deterministic fill → exempt."""
        assert should_exempt_from_existence_gate(True, 'partial') is True

    def test_prose_llm_source_exempt(self):
        """Stops from 'prose_llm' source with deterministic fill → exempt."""
        assert should_exempt_from_existence_gate(True, 'prose_llm') is True

    def test_creator_filter_not_exempt(self):
        """Stops from 'creator_filter' are NOT exempt — GPT-generated."""
        assert should_exempt_from_existence_gate(True, 'creator_filter') is False

    def test_none_source_not_exempt(self):
        """No exhibition source → not exempt."""
        assert should_exempt_from_existence_gate(True, 'none') is False

    def test_non_deterministic_not_exempt(self):
        """Non-deterministic fill → not exempt regardless of source."""
        assert should_exempt_from_existence_gate(False, 'checklist') is False
        assert should_exempt_from_existence_gate(False, 'prose_llm') is False

    def test_both_false_not_exempt(self):
        """Neither condition met → not exempt."""
        assert should_exempt_from_existence_gate(False, 'none') is False


class TestExemptionRedWhenNeutralised:
    """D277: Verify that neutralising the predicate makes tests fail.

    This class documents the red. To verify:
      1. Change should_exempt_from_existence_gate to return False unconditionally
      2. Run: pytest tests/test_local437_gate_exemption.py -v
      3. Three tests in TestExemptionPredicateBound MUST fail:
         - test_checklist_source_exempt
         - test_partial_source_exempt
         - test_prose_llm_source_exempt
    """

    def test_predicate_is_callable(self):
        """Sanity: the predicate exists and is callable."""
        assert callable(should_exempt_from_existence_gate)

    def test_predicate_returns_bool(self):
        """Return type is boolean, not truthy."""
        result = should_exempt_from_existence_gate(True, 'checklist')
        assert isinstance(result, bool)
