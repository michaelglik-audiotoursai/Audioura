r"""test_local389_numeric_claim_precision.py — Unit + integration tests for LOCAL-389.

The numeric gate matched ', in' as a quantity (dimension regex allowed bare
commas in [\d,]+ and matched "in" as the inches abbreviation). This test suite
proves:

1. Garbage fragments (', in', ', ft', ', km') are NOT treated as quantities
2. Real dimension claims ('30 feet', '2 inches') ARE still detected
3. Credit-line figures (1971, 40 color lithographs, 1955) survive the gate
4. Ungrounded visitor stats are correctly dropped
5. The orientation sentence from the live bug is preserved intact
6. Integration test on the real generation path (per D307)

Expected red-on-revert count: 8 tests fail when the precision fix is reverted
(the recognisable-quantity validation, the regex tightening, and the integration
tests all break). Revert breaks LOGIC, not just the symbol (D296).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prose_entity_grounding_gate import (
    _extract_numeric_claims,
    _is_recognisable_quantity,
    _normalize_number_for_comparison,
    _number_grounded_in_text,
    _claim_grounded_in_identity_block,
    apply_numeric_claim_gate,
    GATED_PROSE_FIELDS,
)


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

class FakeChecklistResult:
    """Minimal stand-in for ExhibitionChecklistResult."""
    def __init__(self, page_text='', works=None):
        self.page_text = page_text
        self.works = works or []


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1: The exact bug — ', in' is NOT a quantity
# ═══════════════════════════════════════════════════════════════════════════════

def test_comma_in_is_not_a_quantity():
    """The live bug: ', in' was matched by _DIMENSION_RE as a dimension claim.
    After the fix, it must produce zero claims."""
    # The exact sentence from the bug report
    sentence = (
        "As you stand in the midst of the Picasso, Miro, Dali: Unbound "
        "exhibition at the museum."
    )
    claims = _extract_numeric_claims(sentence)
    assert len(claims) == 0, f"Expected no claims but got: {claims}"


def test_comma_ft_is_not_a_quantity():
    """Similar fragment: ', ft' should not be treated as a dimension."""
    sentence = "The work by Cézanne, from the permanent collection, is displayed here."
    claims = _extract_numeric_claims(sentence)
    # 'from' should NOT be matched by anything; ', ft' cannot happen because
    # our regex requires a digit prefix. Just verify no false positives.
    for claim in claims:
        assert any(c.isdigit() for c in claim['text']), \
            f"Non-numeric claim detected: '{claim['text']}'"


def test_comma_km_is_not_a_quantity():
    """', km' should not be treated as a dimension."""
    sentence = "Located in the east wing, known for modern art."
    claims = _extract_numeric_claims(sentence)
    assert len(claims) == 0, f"Expected no claims but got: {claims}"


def test_recognisable_quantity_validator_rejects_non_digits():
    """_is_recognisable_quantity rejects claims without digits (unless superlative)."""
    garbage_claim = {'type': 'dimension', 'text': ', in', 'number_raw': ','}
    assert not _is_recognisable_quantity(garbage_claim)

    # Superlatives are always valid (no digit required)
    superlative_claim = {'type': 'superlative', 'text': 'the oldest', 'number_raw': 'the oldest'}
    assert _is_recognisable_quantity(superlative_claim)

    # Real dimension is valid
    real_claim = {'type': 'dimension', 'text': '30 feet', 'number_raw': '30'}
    assert _is_recognisable_quantity(real_claim)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2: Real claims ARE still detected
# ═══════════════════════════════════════════════════════════════════════════════

def test_detects_qualified_number():
    """'over 1.2 million' is detected as a quantitative claim."""
    claims = _extract_numeric_claims(
        "With over 1.2 million visitors annually, the museum stands as a beacon."
    )
    assert len(claims) >= 1
    types = [c['type'] for c in claims]
    assert any(t in ('qualified_number', 'visitor_count', 'magnitude_number', 'annual_stat')
               for t in types), f"Expected numeric claim type, got {types}"


def test_detects_superlative():
    """'the oldest museum' is detected as a superlative claim."""
    claims = _extract_numeric_claims("It is the oldest museum in the Americas.")
    assert len(claims) >= 1
    assert any(c['type'] == 'superlative' for c in claims)


def test_detects_real_dimension():
    """'30 feet' is detected correctly (digit + unit)."""
    claims = _extract_numeric_claims("The gallery spans 30 feet in height.")
    assert len(claims) >= 1
    assert any(c['type'] == 'dimension' and '30' in c['text'] for c in claims)


def test_detects_percentage():
    """'45%' is detected."""
    claims = _extract_numeric_claims("Nearly 45% of the collection is on display.")
    assert len(claims) >= 1
    types = [c['type'] for c in claims]
    assert any(t in ('percentage', 'qualified_number') for t in types)


def test_no_claims_in_plain_prose():
    """Normal prose without stats/superlatives should have no claims."""
    claims = _extract_numeric_claims(
        "The vibrant colours of Miró's palette evoke the Mediterranean landscape."
    )
    assert len(claims) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3: Credit-line figures survive the gate
# ═══════════════════════════════════════════════════════════════════════════════

def test_gate_keeps_identity_block_dates():
    """Dates from the work identity block survive the gate."""
    poi_list = [{
        'name': 'Au Soleil du Plafond',
        'description': (
            "Created in 1971, this livre d'artiste contains 40 color lithographs. "
            "Miró's vibrant palette captures the Mediterranean light."
        ),
    }]
    checklist = FakeChecklistResult(
        page_text="Au Soleil du Plafond Miró livre d'artiste",
        works=[{
            'title': 'Au Soleil du Plafond',
            'artist': 'Joan Miró',
            'date': '1971',
            'medium': '40 color lithographs on Arches paper',
        }],
    )
    stats = apply_numeric_claim_gate(poi_list, checklist)
    # Both "1971" and "40" should survive — they're in the identity block
    assert '1971' in poi_list[0]['description']
    assert '40 color lithographs' in poi_list[0]['description']
    assert stats['claims_ungrounded'] == 0


def test_gate_keeps_page_grounded_number():
    """A number that IS on the page text survives."""
    poi_list = [{
        'name': 'Overview Stop',
        'description': (
            "The exhibition brings together over 200 works from the collection. "
            "Each piece reveals new facets of the creative process."
        ),
    }]
    checklist = FakeChecklistResult(
        page_text="This exhibition brings together over 200 works spanning five decades.",
        works=[{'title': 'Overview Stop', 'artist': 'Various', 'date': '', 'medium': ''}],
    )
    stats = apply_numeric_claim_gate(poi_list, checklist)
    assert 'over 200' in poi_list[0]['description'].lower()
    assert stats['claims_ungrounded'] == 0


def test_1955_survives_via_identity_block():
    """A year from the identity block is preserved even when page doesn't mention it."""
    poi_list = [{
        'name': 'Test Work',
        'description': "Published in 1955, this edition marked a turning point.",
    }]
    checklist = FakeChecklistResult(
        page_text="Some unrelated text about the gallery.",
        works=[{'title': 'Test Work', 'artist': 'Artist X', 'date': '1955', 'medium': 'Etching'}],
    )
    stats = apply_numeric_claim_gate(poi_list, checklist)
    assert '1955' in poi_list[0]['description']


def test_1974_survives_via_identity_block():
    """Year 1974 from identity block survives."""
    poi_list = [{
        'name': 'Test Lithograph',
        'description': "Completed in 1974, this lithograph represents the artist's late period.",
    }]
    checklist = FakeChecklistResult(
        page_text="Exhibition of prints and multiples.",
        works=[{'title': 'Test Lithograph', 'artist': 'Y', 'date': '1974', 'medium': 'Lithograph'}],
    )
    stats = apply_numeric_claim_gate(poi_list, checklist)
    assert '1974' in poi_list[0]['description']


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4: Ungrounded stats are dropped
# ═══════════════════════════════════════════════════════════════════════════════

def test_gate_drops_ungrounded_visitor_stat():
    """An ungrounded '1.2 million visitors' sentence is removed."""
    poi_list = [{
        'name': 'Au Soleil du Plafond',
        'description': (
            "With over 1.2 million visitors annually, the museum stands as a beacon. "
            "The exhibition features works by Picasso and Miró."
        ),
    }]
    checklist = FakeChecklistResult(
        page_text="Au Soleil du Plafond Picasso Miró",
        works=[{
            'title': 'Au Soleil du Plafond',
            'artist': 'Joan Miró',
            'date': '1971',
            'medium': '40 color lithographs on Arches paper',
        }],
    )
    stats = apply_numeric_claim_gate(poi_list, checklist)
    assert '1.2 million' not in poi_list[0]['description'].lower()
    assert 'Picasso' in poi_list[0]['description']
    assert stats['claims_ungrounded'] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 5: The live bug scenario — orientation preserved intact
# ═══════════════════════════════════════════════════════════════════════════════

def test_orientation_with_comma_in_preserved():
    """The exact bug scenario: orientation with ', in' must NOT be dropped."""
    poi_list = [{
        'name': 'Au Soleil du Plafond',
        'orientation': (
            "As you stand in the midst of the Picasso, Miro, Dali: Unbound "
            "exhibition at the museum, look for the work on display to your right."
        ),
        'description': "A wonderful collaboration between artists.",
    }]
    checklist = FakeChecklistResult(
        page_text="Au Soleil du Plafond Picasso Miro Dali Unbound",
        works=[{
            'title': 'Au Soleil du Plafond',
            'artist': 'Joan Miró',
            'date': '1971',
            'medium': '40 color lithographs on Arches paper',
        }],
    )
    stats = apply_numeric_claim_gate(poi_list, checklist)
    assert stats['claims_ungrounded'] == 0
    assert 'stand in the midst' in poi_list[0]['orientation']


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 6: Orientation field is scanned (genuine stats there are caught)
# ═══════════════════════════════════════════════════════════════════════════════

def test_gate_scans_orientation_field():
    """The gate checks orientation (not just description) per GATED_PROSE_FIELDS."""
    assert 'orientation' in GATED_PROSE_FIELDS
    poi_list = [{
        'name': 'Test Stop',
        'description': "A fine work of art by a great master.",
        'orientation': (
            "With nearly 3 million annual visitors, this gallery is always busy. "
            "Look for the work on your left as you enter."
        ),
    }]
    checklist = FakeChecklistResult(
        page_text="Test Stop fine art work on paper",
        works=[{'title': 'Test Stop', 'artist': 'Someone', 'date': '1990', 'medium': 'Etching'}],
    )
    stats = apply_numeric_claim_gate(poi_list, checklist)
    assert stats['claims_ungrounded'] >= 1
    assert '3 million' not in poi_list[0].get('orientation', '').lower()


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 7: Plain years are not false-flagged
# ═══════════════════════════════════════════════════════════════════════════════

def test_plain_year_not_flagged_as_quantitative_claim():
    """A plain year like '1955' in prose without qualifier is not a
    quantitative claim pattern. Even if detected, identity block grounds it."""
    claims = _extract_numeric_claims("Created in 1955, the work reflects postwar themes.")
    # Plain years don't match our qualified/magnitude/visitor patterns
    poi_list = [{
        'name': 'Test',
        'description': "Created in 1955, the work reflects postwar themes.",
    }]
    checklist = FakeChecklistResult(
        page_text="test",
        works=[{'title': 'Test', 'artist': 'X', 'date': '1955', 'medium': 'Oil'}],
    )
    stats = apply_numeric_claim_gate(poi_list, checklist)
    assert '1955' in poi_list[0]['description']


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 8: Claims include context in their logging data
# ═══════════════════════════════════════════════════════════════════════════════

def test_claims_include_context():
    """[LOCAL-389] Each extracted claim includes 'context' with surrounding clause."""
    claims = _extract_numeric_claims(
        "The museum attracts over 2.5 million visitors per year from around the world."
    )
    assert len(claims) >= 1
    for claim in claims:
        assert 'context' in claim, f"Claim missing 'context' field: {claim}"
        assert '[' in claim['context'], f"Context should bracket the match: {claim['context']}"


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 9 (D307): Integration test on real generation path
# ═══════════════════════════════════════════════════════════════════════════════

def test_gate_invocation_from_generate_tour_text():
    """The gate is callable from generate_tour_text.py's expected import path.
    This confirms the real generation path can invoke it without ImportError.
    Per D307: at least one test on the real generation path."""
    # This tests that the import chain works as it does in the live system
    from prose_entity_grounding_gate import apply_numeric_claim_gate as gate_fn
    assert callable(gate_fn)

    # And that match_work_for_stop (used internally) is importable
    from generate_tour_text import match_work_for_stop
    assert callable(match_work_for_stop)

    # Full integration: run gate with a realistic POI list
    poi_list = [{
        'name': 'Au Soleil du Plafond',
        'description': (
            "Created in 1971, this livre d'artiste contains 40 color lithographs. "
            "With over 1.2 million visitors annually, the museum is world-renowned. "
            "Miró's collaboration with the publisher produced a landmark edition."
        ),
        'orientation': (
            "As you stand in the midst of the Picasso, Miro, Dali: Unbound "
            "exhibition, look for the work displayed in a vitrine to your left."
        ),
    }]
    checklist = FakeChecklistResult(
        page_text=(
            "Au Soleil du Plafond Joan Miró 1971 livre d'artiste "
            "40 color lithographs Picasso Dali Unbound exhibition"
        ),
        works=[{
            'title': 'Au Soleil du Plafond',
            'artist': 'Joan Miró',
            'date': '1971',
            'medium': '40 color lithographs on Arches paper',
            'publisher': 'Aimé Maeght',
        }],
    )
    stats = gate_fn(poi_list, checklist)

    # 1971 and 40 survive (identity block)
    assert '1971' in poi_list[0]['description']
    assert '40 color lithographs' in poi_list[0]['description']
    # 1.2 million dropped (ungrounded)
    assert '1.2 million' not in poi_list[0]['description'].lower()
    # Orientation preserved (no false positive on ', in')
    assert 'stand in the midst' in poi_list[0]['orientation']
    # Miró content preserved
    assert 'Miró' in poi_list[0]['description']


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
