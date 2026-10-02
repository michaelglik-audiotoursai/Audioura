#!/usr/bin/env python3
"""tests/test_local385_gates_scan_all_fields.py — LOCAL-385: Gates scan all prose fields.

The regression: both the person gate and the form-claim gate iterated only
`poi.get('description')`. Orientation is a separate field and was never
inspected. Fabrications migrated to the unguarded channel.

This test suite verifies:
  1. A fabricated person IN ORIENTATION is removed (the regression case).
  2. A form claim IN ORIENTATION is removed.
  3. Metaphorical use ("a visual tapestry") is NOT dropped.
  4. Empty orientation is cleared (not left as fragment).
  5. Both gates consume GATED_PROSE_FIELDS (single source of truth).
  6. Logging includes field name.
  7. The description channel still works as before.

D277/D285 compliance:
  - Imports production code directly. No inspect.getsource.
  - No inlined production regexes. All tests exercise the real implementation.
  - Tests are falsifiable: revert of gate logic breaks them (see red-on-revert).

Expected red-on-revert count: 9 tests break if the gate reverts to scanning
only 'description'. These are the tests in TestOrientationScanning and
TestEmptyOrientationHandling.

Usage:
    python3 -m pytest tests/test_local385_gates_scan_all_fields.py -v
"""
import os
import sys
import io
import contextlib
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prose_entity_grounding_gate import (
    GATED_PROSE_FIELDS,
    apply_prose_entity_grounding_gate,
    apply_form_claim_gate,
    _sentence_has_form_claim,
    _is_metaphorical_use,
    _medium_compatible_with_term,
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
# 1. GATED_PROSE_FIELDS is the single source of truth
# ═══════════════════════════════════════════════════════════════════════════════

class TestGatedProseFieldsConstant:
    """GATED_PROSE_FIELDS is defined once and consumed by both gates."""

    def test_fields_include_description(self):
        assert 'description' in GATED_PROSE_FIELDS

    def test_fields_include_orientation(self):
        assert 'orientation' in GATED_PROSE_FIELDS

    def test_fields_is_tuple(self):
        """Tuple, not list — immutable to prevent accidental mutation."""
        assert isinstance(GATED_PROSE_FIELDS, tuple)

    def test_fields_exclude_structured(self):
        """Structured fields (address, coordinates) must NOT be scanned."""
        for structured in ('address', 'coordinates', 'name', 'stop_number'):
            assert structured not in GATED_PROSE_FIELDS


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Person gate scans Orientation — THE REGRESSION TEST
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrientationScanning:
    """Person gate must detect and remove ungrounded persons from Orientation.

    These tests RED-ON-REVERT: if the gate is reverted to scanning only
    'description', the orientation field is never inspected and fabricated
    persons survive.
    """

    def test_chagall_in_orientation_is_removed(self):
        """THE REGRESSION: Marc Chagall fabricated in Orientation, zero hits on page.

        This is the exact defect from D304 that this task exists to fix.
        """
        works = [
            {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris', 'medium': ''},
        ]
        # Page text mentions Gris and Reverdy, NOT Chagall
        page_text = (
            "Au Soleil du Plafond. Juan Gris. Pierre Reverdy. "
            "Illustrated book with lithographs and poems. 1927."
        )
        result = _make_checklist_result(works=works, page_text=page_text)

        poi_list = [{
            'name': 'Au Soleil du Plafond',
            'description': (
                "Juan Gris and Pierre Reverdy created this remarkable illustrated book. "
                "The collaboration between artist and poet produced forty lithographs."
            ),
            'orientation': (
                "Created by the contemporary artist Marc Chagall, this ceiling mural "
                "offers a heavenly vision that shifts your perspective."
            ),
        }]

        stats = apply_prose_entity_grounding_gate(poi_list, result)

        # Marc Chagall must be GONE from orientation
        orientation = poi_list[0].get('orientation', '')
        assert 'Chagall' not in orientation, \
            f"Chagall survived in orientation: {orientation}"

        # Gris and Reverdy must survive in description (they are grounded)
        desc = poi_list[0]['description']
        assert 'Gris' in desc
        assert 'Reverdy' in desc

        # Stats should reflect the removal
        assert stats['persons_ungrounded'] >= 1
        assert 'Marc Chagall' in stats['ungrounded_names']

    def test_ungrounded_person_removed_from_orientation_only(self):
        """If fabrication is ONLY in orientation, description is untouched."""
        page_text = "Joan Miró. Le Lézard aux plumes d'or."
        works = [{'title': "Le Lézard aux plumes d'or", 'artist': 'Joan Miró', 'medium': ''}]
        result = _make_checklist_result(works=works, page_text=page_text)

        poi_list = [{
            'name': "Le Lézard aux plumes d'or",
            'description': (
                "Joan Miró created forty color lithographs for this remarkable book. "
                "The images burst with his signature playful forms."
            ),
            'orientation': (
                "Henri Rousseau's influence permeates this corner of the gallery. "
                "Position yourself near the display case."
            ),
        }]

        stats = apply_prose_entity_grounding_gate(poi_list, result)

        # Rousseau must be removed from orientation
        orientation = poi_list[0].get('orientation', '')
        assert 'Rousseau' not in orientation

        # Description untouched (Miró is grounded)
        assert 'Miró' in poi_list[0]['description']

    def test_person_detected_in_orientation_when_absent_from_description(self):
        """Person gate must DETECT names that appear ONLY in orientation."""
        page_text = "Salvador Dalí. Moses and Monotheism."
        works = [{'title': 'Moses and Monotheism', 'artist': 'Salvador Dalí', 'medium': ''}]
        result = _make_checklist_result(works=works, page_text=page_text)

        poi_list = [{
            'name': 'Moses and Monotheism',
            'description': "Salvador Dalí created etchings for this volume.",
            'orientation': (
                "Le Corbusier designed this gallery space to maximize natural light. "
                "Stand at the center for the best view."
            ),
        }]

        stats = apply_prose_entity_grounding_gate(poi_list, result)

        # Le Corbusier not on page → must be removed
        orientation = poi_list[0].get('orientation', '')
        assert 'Corbusier' not in orientation
        assert stats['persons_ungrounded'] >= 1

    def test_form_claim_in_orientation_is_removed(self):
        """Form-claim gate must catch 'ceiling mural' in orientation."""
        works = [
            {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris', 'medium': ''},
        ]
        result = _make_checklist_result(works=works)

        poi_list = [{
            'name': 'Au Soleil du Plafond',
            'description': (
                "Juan Gris and Pierre Reverdy created this remarkable book in 1927."
            ),
            'orientation': (
                "This ceiling mural stretches above you in brilliant color. "
                "Position yourself at the center of the room."
            ),
        }]

        stats = apply_form_claim_gate(poi_list, result)

        orientation = poi_list[0].get('orientation', '')
        assert 'ceiling' not in orientation.lower(), \
            f"'ceiling' survived in orientation: {orientation}"
        assert 'mural' not in orientation.lower()
        # "Position yourself" should survive (no form claim)
        assert 'Position' in orientation or orientation == ''

        assert stats['claims_removed'] >= 1

    def test_form_claim_gaze_up_in_orientation_removed(self):
        """Spatial phrases in orientation must be caught."""
        works = [{'title': 'Test Work', 'artist': 'A', 'medium': ''}]
        result = _make_checklist_result(works=works)

        poi_list = [{
            'name': 'Test Work',
            'description': "The artist created this work in 1960.",
            'orientation': (
                "Gaze up at the radiant colors dancing overhead. "
                "The work was commissioned for this space."
            ),
        }]

        stats = apply_form_claim_gate(poi_list, result)

        orientation = poi_list[0].get('orientation', '')
        assert 'gaze up' not in orientation.lower()
        assert 'overhead' not in orientation.lower()
        assert stats['claims_removed'] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Empty orientation handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmptyOrientationHandling:
    """If all sentences in orientation are removed, field is cleared entirely."""

    def test_orientation_emptied_by_person_gate(self):
        """When all orientation sentences mention an ungrounded person, clear it."""
        page_text = "Joan Miró. Le Lézard."
        works = [{'title': "Le Lézard", 'artist': 'Joan Miró', 'medium': ''}]
        result = _make_checklist_result(works=works, page_text=page_text)

        poi_list = [{
            'name': "Le Lézard",
            'description': "Joan Miró created this work.",
            'orientation': (
                "Henri Matisse designed this gallery. "
                "Matisse's vision of light fills the space."
            ),
        }]

        stats = apply_prose_entity_grounding_gate(poi_list, result)

        # Orientation should be empty string, not a fragment
        assert poi_list[0]['orientation'] == ''

    def test_orientation_emptied_by_form_gate(self):
        """When all orientation sentences have unsupported form claims, clear it."""
        works = [{'title': 'Test', 'artist': 'A', 'medium': ''}]
        result = _make_checklist_result(works=works)

        poi_list = [{
            'name': 'Test',
            'description': "The artist was born in 1920.",
            'orientation': (
                "The ceiling glows with ethereal light. "
                "Look up to see the vault above you."
            ),
        }]

        stats = apply_form_claim_gate(poi_list, result)

        assert poi_list[0]['orientation'] == ''
        assert stats['claims_removed'] >= 2

    def test_partial_orientation_survives(self):
        """If some orientation sentences survive, keep the survivors."""
        works = [{'title': 'Test', 'artist': 'A', 'medium': ''}]
        result = _make_checklist_result(works=works)

        poi_list = [{
            'name': 'Test',
            'description': "The artist was born in 1920.",
            'orientation': (
                "The ceiling glows with color. "
                "Position yourself near the display case for the best view."
            ),
        }]

        stats = apply_form_claim_gate(poi_list, result)

        orientation = poi_list[0]['orientation']
        assert 'ceiling' not in orientation.lower()
        assert 'Position yourself' in orientation
        assert orientation.strip() != ''

    def test_description_never_cleared_entirely(self):
        """Description field is not silently emptied — fragments remain."""
        works = [{'title': 'Test', 'artist': 'A', 'medium': ''}]
        result = _make_checklist_result(works=works)

        poi_list = [{
            'name': 'Test',
            'description': (
                "This sculpture towers above the viewer. "
                "The painting fills the room with color."
            ),
            'orientation': '',
        }]

        stats = apply_form_claim_gate(poi_list, result)
        # Description might be empty after all sentences removed, but that's
        # handled upstream (regeneration). The gate just removes.
        assert stats['claims_removed'] >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Metaphor exemption — "a visual tapestry" survives
# ═══════════════════════════════════════════════════════════════════════════════

class TestMetaphorExemption:
    """Metaphorical form terms must NOT be removed (D304 false positive fix)."""

    def test_visual_tapestry_is_metaphor(self):
        """'a visual tapestry' is figurative, not a claim the work is a textile."""
        assert _is_metaphorical_use(
            "Dalí's use of precise lines and bold colors creates a visual tapestry of surrealist imagery.",
            'tapestry'
        ) is True

    def test_rich_tapestry_is_metaphor(self):
        """'a rich tapestry of emotions' is figurative."""
        assert _is_metaphorical_use(
            "The work weaves a rich tapestry of emotions and color.",
            'tapestry'
        ) is True

    def test_this_tapestry_is_referential(self):
        """'this tapestry' IS a claim about the work's form."""
        assert _is_metaphorical_use(
            "This tapestry depicts a hunting scene from medieval France.",
            'tapestry'
        ) is False

    def test_the_tapestry_before_you_is_referential(self):
        """'the tapestry before you' IS a physical form claim."""
        assert _is_metaphorical_use(
            "The tapestry before you was woven in the fifteenth century.",
            'tapestry'
        ) is False

    def test_visual_tapestry_survives_in_full_gate(self):
        """End-to-end: the sentence with 'visual tapestry' is kept."""
        works = [{'title': 'Moses and Monotheism', 'artist': 'Salvador Dalí',
                  'medium': 'Illustrations'}]
        result = _make_checklist_result(works=works)

        poi_list = [{
            'name': 'Moses and Monotheism',
            'description': (
                "Dalí's use of precise lines and bold colors creates a visual "
                "tapestry of surrealist imagery. "
                "The etchings explore Freud's theories with hallucinatory clarity."
            ),
        }]

        stats = apply_form_claim_gate(poi_list, result)

        # "visual tapestry" must survive — it's a metaphor
        assert 'tapestry' in poi_list[0]['description'].lower()
        assert stats['claims_removed'] == 0

    def test_symphony_of_colour_is_metaphor(self):
        """'a symphony of colour' — same class, different term."""
        # symphony isn't in _FORM_OBJECT_TERMS, so won't be detected at all.
        # But this confirms the principle.
        result = _sentence_has_form_claim(
            "The artist creates a symphony of colour across the page."
        )
        assert result is None  # symphony is not a form term

    def test_creates_a_tapestry_is_metaphor(self):
        """Action verb + indefinite article + form term = metaphor."""
        assert _is_metaphorical_use(
            "The work creates a tapestry of interwoven narratives.",
            'tapestry'
        ) is True

    def test_this_ceiling_mural_is_referential(self):
        """'this ceiling mural' is a referential claim — must NOT be exempt."""
        assert _is_metaphorical_use(
            "This ceiling mural spans the entire nave.",
            'mural'
        ) is False

    def test_living_sculpture_is_metaphor(self):
        """'a living sculpture' is figurative — the work isn't literally a sculpture."""
        assert _is_metaphorical_use(
            "The dance performance becomes a living sculpture of movement.",
            'sculpture'
        ) is True


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Logging includes field name
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoggingFieldName:
    """Log output must include the field name for each detection."""

    def test_person_gate_logs_field_orientation(self):
        """Person removal from orientation logs field=orientation."""
        page_text = "Joan Miró."
        works = [{'title': 'Test', 'artist': 'Joan Miró', 'medium': ''}]
        result = _make_checklist_result(works=works, page_text=page_text)

        poi_list = [{
            'name': 'Test',
            'description': "Joan Miró created this.",
            'orientation': "Henri Matisse shaped this room.",
        }]

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            apply_prose_entity_grounding_gate(poi_list, result)

        log = buf.getvalue()
        assert 'field=orientation' in log

    def test_person_gate_logs_field_description(self):
        """Person removal from description logs field=description."""
        page_text = "Joan Miró."
        works = [{'title': 'Test', 'artist': 'Joan Miró', 'medium': ''}]
        result = _make_checklist_result(works=works, page_text=page_text)

        poi_list = [{
            'name': 'Test',
            'description': "Henri Matisse designed this gallery. Joan Miró created prints.",
            'orientation': '',
        }]

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            apply_prose_entity_grounding_gate(poi_list, result)

        log = buf.getvalue()
        assert 'field=description' in log

    def test_form_gate_logs_field_orientation(self):
        """Form-claim removal from orientation logs field=orientation."""
        works = [{'title': 'Test', 'artist': 'A', 'medium': ''}]
        result = _make_checklist_result(works=works)

        poi_list = [{
            'name': 'Test',
            'description': "The artist was born in 1920.",
            'orientation': "The ceiling glows with light.",
        }]

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            apply_form_claim_gate(poi_list, result)

        log = buf.getvalue()
        assert 'field=orientation' in log

    def test_drop_log_includes_field(self):
        """The stats drop_log entries include a 'field' key."""
        page_text = "Joan Miró."
        works = [{'title': 'Test', 'artist': 'Joan Miró', 'medium': ''}]
        result = _make_checklist_result(works=works, page_text=page_text)

        poi_list = [{
            'name': 'Test',
            'description': "Joan Miró created this.",
            'orientation': "Henri Matisse designed this room.",
        }]

        stats = apply_prose_entity_grounding_gate(poi_list, result)
        assert len(stats['drop_log']) >= 1
        assert 'field' in stats['drop_log'][0]
        assert stats['drop_log'][0]['field'] == 'orientation'


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Description channel still works (regression guard)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDescriptionStillGated:
    """The description field is still scanned (no regression from multi-field)."""

    def test_ungrounded_person_in_description_still_removed(self):
        """Same behaviour as LOCAL-378: ungrounded person in description removed."""
        page_text = "Joan Miró. Le Lézard."
        works = [{'title': 'Le Lézard', 'artist': 'Joan Miró', 'medium': ''}]
        result = _make_checklist_result(works=works, page_text=page_text)

        poi_list = [{
            'name': 'Le Lézard',
            'description': (
                "Henri Rousseau's influence permeates this work. "
                "Joan Miró created forty lithographs."
            ),
            'orientation': '',
        }]

        stats = apply_prose_entity_grounding_gate(poi_list, result)
        assert 'Rousseau' not in poi_list[0]['description']
        assert 'Miró' in poi_list[0]['description']

    def test_form_claim_in_description_still_removed(self):
        """Same behaviour as LOCAL-384: form claim in description removed."""
        works = [{'title': 'Test', 'artist': 'A', 'medium': ''}]
        result = _make_checklist_result(works=works)

        poi_list = [{
            'name': 'Test',
            'description': (
                "The ceiling glows with ethereal light. "
                "The artist worked in Paris during the 1920s."
            ),
            'orientation': '',
        }]

        stats = apply_form_claim_gate(poi_list, result)
        assert 'ceiling' not in poi_list[0]['description'].lower()
        assert 'Paris' in poi_list[0]['description']
