#!/usr/bin/env python3
"""tests/test_local371_fragment_repair.py — LOCAL-371: Fragment repair predicate fix.

Verifies that _take_in_handler:
  1. Refuses to supply a predicate when the tail is already broken (mangled NPs).
  2. Uses "stretches out before you" only for vista/landscape subjects.
  3. Uses "is displayed here" for object/artifact subjects.
  4. Case 1 and Case 2 (relative clause hoisting) are unaffected.

D277/D285 compliance:
  - Calls _take_in_handler directly (module-scope, importable).
  - No inspect.getsource or string assertions on source code.
  - Tests are falsifiable: they fail against the pre-fix code.
"""
import os
import sys
import re
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style_validator_detector import _take_in_handler, _take_in_tail_is_unrepairable, _tail_is_vista_subject


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeMatch:
    """Simulate re.Match for _take_in_handler (group(1) = tail)."""
    def __init__(self, tail):
        self._tail = tail

    def group(self, n):
        if n == 1:
            return self._tail
        return ''


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Broken tails are declined (return None → deletion)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBrokenTailsDeclined:
    """LOCAL-371: The handler must refuse when the tail is unrepairable."""

    def test_guitar_participial_pile(self):
        """The exact Palais Lascaris guitar sentence from the ticket."""
        tail = (
            'this guitar for its influence on future string instruments, '
            'marking a crucial moment in the history of guitar-making'
        )
        result = _take_in_handler(_FakeMatch(tail))
        assert result is None, (
            f"Expected None (deletion) for mangled guitar tail, got: {result!r}"
        )

    def test_remarkable_piece_with_understanding(self):
        """The exact Palais Lascaris 'remarkable piece' sentence from the ticket."""
        tail = 'this remarkable piece with an understanding of its historical context'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is None, (
            f"Expected None (deletion) for mangled 'remarkable piece' tail, got: {result!r}"
        )

    def test_participial_pile_making(self):
        """Comma + 'making' participial signals broken input."""
        tail = 'this illustrated manuscript, making it a key example of 15th-century art'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is None

    def test_participial_pile_representing(self):
        """Comma + 'representing' participial signals broken input."""
        tail = 'this ceramic vessel, representing a significant cultural exchange'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is None

    def test_for_its_influence(self):
        """'for its influence' without a long head NP is a dangling purpose clause."""
        tail = 'this harp for its contribution to Baroque chamber music'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is None

    def test_with_appreciation_of(self):
        """'with an appreciation of' is an abstract clause, not an object attribute."""
        tail = 'this sculpture with an appreciation of its cultural significance'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Vista subjects get "stretches out before you"
# ═══════════════════════════════════════════════════════════════════════════════

class TestVistaSubjectPredicate:
    """Vista/landscape subjects must still get the 'stretches out' predicate."""

    def test_panoramic_view(self):
        tail = 'the panoramic view of the Mediterranean coastline'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'stretches out before you' in result
        assert result == 'The panoramic view of the Mediterranean coastline stretches out before you.'

    def test_coastline(self):
        tail = 'the stunning coastline of the Riviera'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'stretches out before you' in result

    def test_valley(self):
        tail = 'the verdant valley below'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'stretches out before you' in result

    def test_azure_waters(self):
        tail = 'the azure waters of the bay'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'stretches out before you' in result

    def test_landscape_plural(self):
        tail = 'the rolling landscapes of Provence'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'stretches out before you' in result


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Object/artifact subjects get "is displayed here"
# ═══════════════════════════════════════════════════════════════════════════════

class TestObjectSubjectPredicate:
    """Museum objects/artifacts must get 'is displayed here', not 'stretches out'."""

    def test_harpsichord(self):
        tail = 'the ornate harpsichord'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'is displayed here' in result
        assert 'stretches out' not in result

    def test_painting(self):
        tail = 'the Baroque painting by Caravaggio'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        # Case 1 might fire if there's a relative clause — here there isn't,
        # so it should get 'is displayed here'
        assert 'is displayed here' in result

    def test_bust(self):
        tail = 'the marble bust of Emperor Augustus'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'is displayed here' in result

    def test_tapestry(self):
        tail = 'the intricate Flemish tapestry'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'is displayed here' in result

    def test_ancient_sword(self):
        tail = 'the ceremonial sword from the 14th century'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'is displayed here' in result


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Cases 1 & 2 (relative clause hoisting) still work
# ═══════════════════════════════════════════════════════════════════════════════

class TestRelativeClauseHoisting:
    """Cases 1 and 2 should be completely unaffected by this change."""

    def test_case1_that_stretches(self):
        """'that VERB' relative clause is hoisted to main verb."""
        tail = 'the breathtaking views of the azure waters that stretch across the bay'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'stretch across the bay' in result
        # The "that" is removed, verb becomes main clause
        assert 'that' not in result

    def test_case1_that_overlooks(self):
        tail = 'the terrace that overlooks the harbour'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'overlooks the harbour' in result

    def test_case2_which_extends(self):
        """'which VERB' relative clause is hoisted to main verb."""
        tail = 'the valley which extends to the distant mountains'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'extends to the distant mountains' in result
        assert 'which' not in result

    def test_case2_which_rises(self):
        tail = 'the cathedral spire which rises above the rooftops'
        result = _take_in_handler(_FakeMatch(tail))
        assert result is not None
        assert 'rises above the rooftops' in result


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Helper function unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestHelperFunctions:
    """Unit tests for the two LOCAL-371 helpers."""

    def test_tail_is_unrepairable_participial(self):
        assert _take_in_tail_is_unrepairable(
            'this guitar for its influence, marking a moment'
        ) is True

    def test_tail_is_unrepairable_for_its(self):
        assert _take_in_tail_is_unrepairable(
            'this harp for its contribution to music'
        ) is True

    def test_tail_is_unrepairable_with_understanding(self):
        assert _take_in_tail_is_unrepairable(
            'this piece with an understanding of its context'
        ) is True

    def test_tail_is_repairable_clean_np(self):
        assert _take_in_tail_is_unrepairable(
            'the ornate harpsichord'
        ) is False

    def test_tail_is_repairable_vista(self):
        assert _take_in_tail_is_unrepairable(
            'the panoramic view of the coast'
        ) is False

    def test_vista_subject_view(self):
        assert _tail_is_vista_subject('The panoramic view of the coast') is True

    def test_vista_subject_coastline(self):
        assert _tail_is_vista_subject('The stunning coastline') is True

    def test_not_vista_harpsichord(self):
        assert _tail_is_vista_subject('The ornate harpsichord') is False

    def test_not_vista_guitar(self):
        assert _tail_is_vista_subject('This guitar') is False

    def test_not_vista_painting(self):
        assert _tail_is_vista_subject('The Baroque painting by Caravaggio') is False
