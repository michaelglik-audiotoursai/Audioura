#!/usr/bin/env python3
"""tests/test_local384_form_claim_gate.py — LOCAL-384: Form-claim gate.

Tests the form-claim gate that removes unsupported physical form and placement
claims from delivered tour text. The model repeatedly infers physical form from
titles (e.g. "Au Soleil du Plafond" → "ceiling mural"). Five prompt-level
rounds failed to stop it. This gate enforces at the output level.

Rules tested:
  1. Medium EMPTY/UNKNOWN → any form claim is unsupported → remove sentence
  2. Medium KNOWN and INCOMPATIBLE → remove sentence
  3. Medium KNOWN and COMPATIBLE → keep sentence (Palais Lascaris control)
  4. Spatial phrases (look up, stand beneath, etc.) are caught
  5. Fragment cleanup after removal
  6. Gate scope: only exhibition-scoped museum tours

D277/D285 compliance:
  - Imports production code directly. No inspect.getsource.
  - No inlined production regexes. All tests exercise the real implementation.
  - Tests are falsifiable: revert of gate logic breaks them.

Usage:
    python3 -m pytest tests/test_local384_form_claim_gate.py -v
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prose_entity_grounding_gate import (
    apply_form_claim_gate,
    _sentence_has_form_claim,
    _medium_compatible_with_term,
    _split_sentences,
    _is_fragment,
)


def _make_checklist_result(works=None, page_text=''):
    """Create a minimal object that quacks like ExhibitionChecklistResult."""
    class FakeResult:
        pass
    r = FakeResult()
    r.page_text = page_text
    r.works = works or []
    return r


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Medium EMPTY → form claims removed
# ═══════════════════════════════════════════════════════════════════════════════

class TestMediumEmptyRemoval:
    """When medium is empty/unknown, ALL form claims must be removed."""

    def test_ceiling_removed_when_medium_empty(self):
        """The 'ceiling' claim that defeated five prompt rounds."""
        works = [{'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris', 'medium': ''}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Au Soleil du Plafond',
            'description': (
                "Juan Gris transforms the ceiling into a radiant canvas of color. "
                "The collaboration with Pierre Reverdy produced remarkable poetry."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'ceiling' not in poi_list[0]['description'].lower()
        assert 'Reverdy' in poi_list[0]['description']
        assert stats['claims_removed'] >= 1

    def test_mural_removed_when_medium_empty(self):
        works = [{'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris', 'medium': ''}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Au Soleil du Plafond',
            'description': (
                "This stunning mural spans the entire north gallery. "
                "Juan Gris created this work in 1927."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'mural' not in poi_list[0]['description'].lower()
        assert 'Juan Gris' in poi_list[0]['description']

    def test_installation_removed_when_medium_empty(self):
        works = [{'title': 'Test Work', 'artist': 'Artist', 'medium': ''}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Test Work',
            'description': (
                "This contemporary installation fills the room with light. "
                "The artist explored new materials in the 1960s."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'installation' not in poi_list[0]['description'].lower()
        assert 'artist' in poi_list[0]['description'].lower()

    def test_glass_removed_when_medium_empty(self):
        works = [{'title': 'Test Work', 'artist': 'Artist', 'medium': ''}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Test Work',
            'description': (
                "The vibrant glass panels catch the morning light beautifully. "
                "This work dates from the early twentieth century."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'glass' not in poi_list[0]['description'].lower()

    def test_sculpture_removed_when_medium_empty(self):
        works = [{'title': 'Test Work', 'artist': 'Artist', 'medium': ''}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Test Work',
            'description': (
                "This sculpture stands three meters tall. "
                "The artist was born in Barcelona."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'sculpture' not in poi_list[0]['description'].lower()

    def test_multiple_claims_all_removed(self):
        """Multiple form claims in different sentences all removed."""
        works = [{'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris', 'medium': ''}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Au Soleil du Plafond',
            'description': (
                "Dance across the ceiling in radiant hues. "
                "The painting utilizes the ceiling as a canvas. "
                "Juan Gris created lithographs for this book in 1927."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'ceiling' not in poi_list[0]['description'].lower()
        assert 'painting' not in poi_list[0]['description'].lower()
        assert 'Juan Gris' in poi_list[0]['description']


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Medium KNOWN and INCOMPATIBLE → remove
# ═══════════════════════════════════════════════════════════════════════════════

class TestMediumIncompatibleRemoval:
    """Known medium that contradicts the claim → remove."""

    def test_ceiling_incompatible_with_book(self):
        """A book is not a ceiling."""
        works = [{'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
                  'medium': 'Illustrated book with lithographs'}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Au Soleil du Plafond',
            'description': (
                "Colors dance across the ceiling in this remarkable space. "
                "Juan Gris and Pierre Reverdy created this illustrated book in 1927."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'ceiling' not in poi_list[0]['description'].lower()
        assert 'Reverdy' in poi_list[0]['description']

    def test_sculpture_incompatible_with_book(self):
        works = [{'title': 'Test', 'artist': 'A', 'medium': 'Illustrated book'}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Test',
            'description': (
                "This sculpture dominates the gallery entrance. "
                "The artist created prints for this volume."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'sculpture' not in poi_list[0]['description'].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Medium KNOWN and COMPATIBLE → keep (Palais Lascaris control)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMediumCompatibleKept:
    """When medium is known and compatible, form claims MUST survive."""

    def test_ceiling_kept_for_fresco(self):
        """A fresco on a ceiling is legitimate — gate must not fire."""
        works = [{'title': 'Ceiling Fresco', 'artist': 'Giovanni Carlone',
                  'medium': 'ceiling fresco'}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Ceiling Fresco',
            'description': (
                "Look up to behold the magnificent ceiling fresco by Carlone. "
                "The figures seem to float overhead in a celestial scene."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        # MUST survive — ceiling is compatible with fresco
        assert 'ceiling' in poi_list[0]['description'].lower()
        assert 'look up' in poi_list[0]['description'].lower()
        assert stats['claims_kept'] >= 1
        assert stats['claims_removed'] == 0

    def test_wall_kept_for_fresco(self):
        works = [{'title': 'Wall Painting', 'artist': 'Artist',
                  'medium': 'fresco on plaster'}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Wall Painting',
            'description': (
                "The wall before you displays a magnificent fresco. "
                "The artist painted this mural in the seventeenth century."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'wall' in poi_list[0]['description'].lower()
        assert 'mural' in poi_list[0]['description'].lower()
        assert stats['claims_removed'] == 0

    def test_painting_kept_for_oil_on_canvas(self):
        works = [{'title': 'Still Life', 'artist': 'Artist',
                  'medium': 'Oil on canvas'}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Still Life',
            'description': "This painting captures light in extraordinary ways.",
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'painting' in poi_list[0]['description'].lower()
        assert stats['claims_removed'] == 0

    def test_sculpture_kept_for_bronze(self):
        works = [{'title': 'Figure', 'artist': 'Artist', 'medium': 'Bronze cast'}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Figure',
            'description': "This sculpture was cast in bronze by the artist in 1965.",
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'sculpture' in poi_list[0]['description'].lower()
        assert stats['claims_removed'] == 0

    def test_glass_kept_for_stained_glass(self):
        works = [{'title': 'Window', 'artist': 'Artist',
                  'medium': 'Stained glass panel'}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Window',
            'description': "The glass panel filters sunlight into the nave.",
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'glass' in poi_list[0]['description'].lower()
        assert stats['claims_removed'] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Spatial phrases
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpatialPhrases:
    """Spatial instructions (look up, stand beneath, etc.) are caught."""

    def test_look_up_removed_when_medium_empty(self):
        works = [{'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris', 'medium': ''}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Au Soleil du Plafond',
            'description': (
                "Look up to admire the radiant colors above. "
                "The collaboration dates from 1927."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'look up' not in poi_list[0]['description'].lower()
        assert '1927' in poi_list[0]['description']

    def test_stand_beneath_removed(self):
        works = [{'title': 'Test', 'artist': 'A', 'medium': ''}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Test',
            'description': (
                "Stand beneath this work and feel its presence. "
                "The artist worked in Paris during the 1920s."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'stand beneath' not in poi_list[0]['description'].lower()

    def test_above_you_removed(self):
        works = [{'title': 'Test', 'artist': 'A', 'medium': ''}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Test',
            'description': (
                "The work stretches above you in brilliant color. "
                "It was created in the early twentieth century."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'above you' not in poi_list[0]['description'].lower()

    def test_overhead_removed(self):
        works = [{'title': 'Test', 'artist': 'A', 'medium': ''}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Test',
            'description': (
                "Colors bloom overhead like a garden in spring. "
                "The poet and artist collaborated closely."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'overhead' not in poi_list[0]['description'].lower()

    def test_spatial_kept_for_fresco(self):
        """Spatial phrases are legitimate for actual frescoes."""
        works = [{'title': 'Great Hall Fresco', 'artist': 'Artist',
                  'medium': 'ceiling fresco'}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Great Hall Fresco',
            'description': (
                "Look up to witness the glory of the Baroque ceiling. "
                "Stand beneath the central figure for the best view."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'look up' in poi_list[0]['description'].lower()
        assert 'stand beneath' in poi_list[0]['description'].lower()
        assert stats['claims_removed'] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Fragment cleanup
# ═══════════════════════════════════════════════════════════════════════════════

class TestFragmentCleanup:
    """After form-claim removal, dangling fragments must also be removed."""

    def test_short_conjunction_fragment_dropped(self):
        works = [{'title': 'Test', 'artist': 'A', 'medium': ''}]
        result = _make_checklist_result(works=works)
        poi_list = [{
            'name': 'Test',
            'description': (
                "The ceiling glows with radiant light. "
                "And so. "
                "The artist was born in Madrid in 1881."
            ),
        }]
        stats = apply_form_claim_gate(poi_list, result)
        assert 'ceiling' not in poi_list[0]['description'].lower()
        # "And so." should also be removed as a fragment
        assert 'And so.' not in poi_list[0]['description']
        assert 'Madrid' in poi_list[0]['description']


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Sentence-level claim detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestClaimDetection:
    """Unit tests for _sentence_has_form_claim."""

    def test_ceiling_detected(self):
        assert _sentence_has_form_claim("The ceiling glows with color.") == 'ceiling'

    def test_mural_detected(self):
        assert _sentence_has_form_claim("This mural spans the gallery.") == 'mural'

    def test_look_up_detected(self):
        result = _sentence_has_form_claim("Look up to see the colors.")
        assert result is not None and result.lower() == 'look up'

    def test_stand_beneath_detected(self):
        result = _sentence_has_form_claim("Stand beneath this for the best view.")
        assert result is not None and result.lower() == 'stand beneath'

    def test_no_claim_clean_sentence(self):
        assert _sentence_has_form_claim(
            "The artist created this work in 1927.") is None

    def test_no_claim_book_description(self):
        assert _sentence_has_form_claim(
            "This illustrated book contains forty color lithographs.") is None

    def test_painting_detected(self):
        assert _sentence_has_form_claim(
            "This painting captures the essence of spring.") == 'painting'


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Medium compatibility
# ═══════════════════════════════════════════════════════════════════════════════

class TestMediumCompatibility:
    """Unit tests for _medium_compatible_with_term."""

    def test_fresco_compatible_with_ceiling(self):
        assert _medium_compatible_with_term('ceiling fresco', 'ceiling') is True

    def test_fresco_compatible_with_look_up(self):
        assert _medium_compatible_with_term('fresco', 'look up') is True

    def test_fresco_compatible_with_mural(self):
        assert _medium_compatible_with_term('fresco', 'mural') is True

    def test_book_incompatible_with_ceiling(self):
        assert _medium_compatible_with_term(
            'Illustrated book with lithographs', 'ceiling') is False

    def test_book_incompatible_with_sculpture(self):
        assert _medium_compatible_with_term(
            'Illustrated book with lithographs', 'sculpture') is False

    def test_oil_on_canvas_compatible_with_painting(self):
        assert _medium_compatible_with_term('Oil on canvas', 'painting') is True

    def test_bronze_compatible_with_sculpture(self):
        assert _medium_compatible_with_term('Bronze cast', 'sculpture') is True

    def test_empty_medium_incompatible_with_everything(self):
        assert _medium_compatible_with_term('', 'ceiling') is False
        assert _medium_compatible_with_term('', 'painting') is False
        assert _medium_compatible_with_term('', 'look up') is False

    def test_stained_glass_compatible_with_glass(self):
        assert _medium_compatible_with_term('Stained glass', 'glass') is True


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Integration — full MFA Unbound scenario
# ═══════════════════════════════════════════════════════════════════════════════

class TestMFAUnboundIntegration:
    """End-to-end test simulating the MFA Unbound scenario where the model
    inferred 'ceiling' from the title 'Au Soleil du Plafond'."""

    def test_full_mfa_scenario(self):
        """All ceiling/mural/glass/installation claims removed from Plafond stop."""
        works = [
            {'title': "Le Lézard aux plumes d'or", 'artist': 'Joan Miró',
             'medium': 'Illustrated book with 40 color lithographs'},
            {'title': 'Moses and Monotheism', 'artist': 'Salvador Dalí',
             'medium': 'Illustrations'},
            {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
             'medium': ''},
        ]
        result = _make_checklist_result(works=works)

        poi_list = [
            {
                'name': "Le Lézard aux plumes d'or",
                'description': (
                    "Joan Miró created forty color lithographs for this remarkable book. "
                    "The images burst with Miró's signature playful forms."
                ),
            },
            {
                'name': 'Moses and Monotheism',
                'description': (
                    "Salvador Dalí's etchings for this volume explore Freud's theories. "
                    "The illustrations capture Dalí's surrealist vision."
                ),
            },
            {
                'name': 'Au Soleil du Plafond',
                'description': (
                    "Juan Gris transforms the ceiling into a radiant canvas of color. "
                    "Dance across the ceiling in hues of gold and blue. "
                    "The collaboration invites viewers to look up and experience light. "
                    "Gris and Reverdy created this work together in 1927."
                ),
            },
        ]

        stats = apply_form_claim_gate(poi_list, result)

        # Stop 3 (Plafond) must have ceiling/look up removed
        desc3 = poi_list[2]['description'].lower()
        assert 'ceiling' not in desc3
        assert 'look up' not in desc3
        assert 'reverdy' in desc3 or 'gris' in desc3

        # Stops 1-2 have known mediums with no incompatible claims — untouched
        assert 'lithographs' in poi_list[0]['description'].lower()
        assert 'dalí' in poi_list[1]['description'].lower()

        assert stats['claims_removed'] >= 3
        assert stats['stops_affected'] >= 1
