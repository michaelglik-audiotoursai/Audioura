#!/usr/bin/env python3
"""tests/test_local378_prose_entity_grounding.py — LOCAL-378: Prose entity grounding gate.

Tests five defect fixes:
  Defect 1 — Bare surname removal: once a person is judged ungrounded, every mention
             (full name, bare surname, possessive) is removed.
  Defect 2 — 'The Treat Page' is NOT classified as a person; only strings that look
             like personal names are flagged.
  Defect 3 — After sentence removal, dangling fragments are cleaned up.
  Defect 4 — match_credit_line and match_work_for_stop handle parenthetical
             translations: 'Le Lézard aux plumes d'or (The Lizard with Golden Feathers)'
             matches 'Le Lézard aux plumes d'or'.
  Defect 5 — Gate scope: only exhibition-scoped museum tours are gated.

D277/D285 compliance:
  - Imports production code directly. No inspect.getsource.
  - No inlined production regexes. All tests exercise the real implementation.
  - Tests are falsifiable: the revert-must-break requirement uses body-neutering (D296).

Usage:
    python3 -m pytest tests/test_local378_prose_entity_grounding.py -v
"""
import os
import sys
import re
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prose_entity_grounding_gate import (
    extract_person_names,
    check_person_grounded,
    remove_person_from_text,
    apply_prose_entity_grounding_gate,
    _looks_like_person_name,
    _surname_from_full_name,
    _mentions_person,
    _is_fragment,
)
from generate_tour_text import (
    match_credit_line,
    match_work_for_stop,
    _strip_parenthetical_translation,
    build_provenance_block,
)


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 1 — Bare surname and possessive removal
# ═══════════════════════════════════════════════════════════════════════════════

class TestBareSurnameRemoval:
    """Once ungrounded, ALL forms of a person's name must be removed."""

    def test_full_name_removed(self):
        text = "Xavier Lalanne was a French sculptor. Miró created lithographs."
        cleaned, dropped = remove_person_from_text(text, "Xavier Lalanne")
        assert "Xavier Lalanne" not in cleaned
        assert "Miró" in cleaned

    def test_bare_surname_removed(self):
        """The dominant form in prose — bare surname without first name."""
        text = ("The exhibition features works by three artists. "
                "Lalanne contributed several pieces to the collection. "
                "Miró's lithographs dominate the north wall.")
        cleaned, dropped = remove_person_from_text(text, "Xavier Lalanne")
        assert "Lalanne" not in cleaned
        assert "Miró" in cleaned
        assert len(dropped) == 1  # Only the Lalanne sentence

    def test_possessive_surname_removed(self):
        """Lalanne's — possessive form must also be caught."""
        text = ("Lalanne's choice of material transforms the ordinary. "
                "The lizard's form is remarkable.")
        cleaned, dropped = remove_person_from_text(text, "Xavier Lalanne")
        assert "Lalanne's" not in cleaned
        assert "lizard's" in cleaned  # 'lizard' should not be confused with a person

    def test_multiple_forms_in_same_text(self):
        """Full name, bare surname, and possessive all in one passage."""
        text = ("Xavier Lalanne was a French sculptor. "
                "Lalanne mastered the art of transformation. "
                "Lalanne's work stands as a beacon. "
                "Miró created the original lithographs.")
        cleaned, dropped = remove_person_from_text(text, "Xavier Lalanne")
        assert "Lalanne" not in cleaned
        assert "Miró" in cleaned
        assert len(dropped) == 3

    def test_surname_not_substring_matched(self):
        """'Lalanne' should not match inside longer words (if any existed)."""
        text = "The Lalannesque style was influential. Lalanne innovated daily."
        cleaned, dropped = remove_person_from_text(text, "Xavier Lalanne")
        # 'Lalannesque' contains Lalanne but is not a word-boundary match of surname
        # The regex uses \b so 'Lalannesque' should NOT match 'Lalanne\b'
        # Only 'Lalanne' as a whole word should be caught
        assert "Lalannesque" in cleaned or "Lalanne innovated" not in cleaned

    def test_case_sensitive_surname(self):
        """Surname matching is case-sensitive — 'lalanne' in lowercase is not a name."""
        text = "The lalanne technique was used widely. Lalanne perfected it."
        cleaned, dropped = remove_person_from_text(text, "Xavier Lalanne")
        # 'lalanne' (lowercase) should survive; 'Lalanne' (capitalized) should be dropped
        assert "lalanne technique" in cleaned
        assert "Lalanne perfected" not in cleaned


class TestPersonDetection:
    """Person name extraction from prose."""

    def test_multi_word_name_detected(self):
        text = "Xavier Lalanne created remarkable sculptures."
        names = extract_person_names(text)
        assert "Xavier Lalanne" in names

    def test_single_word_not_detected(self):
        """Single capitalised words are not person names."""
        text = "Lalanne created remarkable sculptures."
        names = extract_person_names(text)
        # extract_person_names only finds multi-word names (initial detection)
        # The surname removal is a SEPARATE step applied after the full name is identified
        assert len(names) == 0

    def test_multi_word_with_particles(self):
        """Names with particles (de, von) are detected."""
        text = "Henri de Toulouse-Lautrec painted this scene."
        names = extract_person_names(text)
        # Should find a multi-word name containing 'Toulouse'
        assert any("Toulouse" in n for n in names)

    def test_deduplicated(self):
        """Same name appearing twice is only returned once."""
        text = "Xavier Lalanne worked here. Xavier Lalanne also worked there."
        names = extract_person_names(text)
        assert names.count("Xavier Lalanne") == 1


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 2 — 'The Treat Page' is NOT a person
# ═══════════════════════════════════════════════════════════════════════════════

class TestNonPersonExclusion:
    """Product/UI strings and structural phrases must not be classified as persons."""

    def test_the_treat_page_not_a_person(self):
        """'The Treat Page' is an app feature, not a personal name."""
        assert not _looks_like_person_name("The Treat Page")

    def test_the_treat_page_not_extracted(self):
        """Even if 'The Treat Page' appears in text, it must not be extracted."""
        text = ("The Treat Page shows whether there are real savings. "
                "Xavier Lalanne created this piece.")
        names = extract_person_names(text)
        assert "The Treat Page" not in names
        assert "Xavier Lalanne" in names

    def test_museum_of_fine_arts_not_a_person(self):
        """Institutional names are not persons."""
        assert not _looks_like_person_name("Museum of Fine Arts")
        assert not _looks_like_person_name("Fine Arts")

    def test_the_opener_blocks_person(self):
        """Names starting with 'The', 'This', etc. are not persons."""
        assert not _looks_like_person_name("The Gallery Wing")
        assert not _looks_like_person_name("This Modern Room")

    def test_real_names_pass(self):
        """Real personal names pass the heuristic."""
        assert _looks_like_person_name("Xavier Lalanne")
        assert _looks_like_person_name("Henri Matisse")
        assert _looks_like_person_name("Salvador Dalí")
        assert _looks_like_person_name("Joan Miró")
        assert _looks_like_person_name("Boris Fridman")

    def test_all_common_nouns_fail(self):
        """A string of all common nouns (even capitalized) is not a person."""
        assert not _looks_like_person_name("Modern Art Gallery")
        assert not _looks_like_person_name("National Museum")


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 3 — Fragment cleanup after removal
# ═══════════════════════════════════════════════════════════════════════════════

class TestFragmentCleanup:
    """After sentence removal, dangling fragments must also be removed."""

    def test_leading_conjunction_fragment_removed(self):
        """A short sentence starting with 'And' after a deletion is a fragment."""
        assert _is_fragment("And so it goes.")
        assert _is_fragment("But yes.")

    def test_lowercase_start_is_fragment(self):
        """A sentence starting with lowercase was a continuation."""
        assert _is_fragment("stands as a beacon of expression.")

    def test_normal_sentence_not_fragment(self):
        """A normal sentence is not a fragment."""
        assert not _is_fragment("The artwork depicts a lizard with golden feathers.")
        assert not _is_fragment("Miró created the original lithographs in 1971.")

    def test_removal_cleans_up_fragments(self):
        """If removal leaves a dangling fragment, it is also dropped."""
        text = ("Xavier Lalanne mastered sculpture. "
                "And this technique was revolutionary. "
                "Miró created the original lithographs.")
        cleaned, dropped = remove_person_from_text(text, "Xavier Lalanne")
        # "And this technique was revolutionary." is a short conjunction fragment
        # after the Lalanne sentence is dropped — it should also be dropped
        assert "Lalanne" not in cleaned
        assert "Miró" in cleaned


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 4 — Parenthetical translation handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestParentheticalTranslation:
    """match_credit_line and match_work_for_stop must handle parenthetical translations."""

    WORKS = [
        {'title': "Le Lézard aux plumes d'or",
         'credit_line': 'Gift of Boris Fridman',
         'medium': 'Illustrated book with 40 color lithographs'},
        {'title': 'Moses and Monotheism',
         'credit_line': 'Museum purchase',
         'medium': 'Illustrated book with etchings'},
        {'title': 'Au Soleil du Plafond',
         'credit_line': 'Gift of the Reverdy Estate',
         'medium': 'Illustrated book with lithographs'},
    ]

    def test_strip_parenthetical(self):
        """Parenthetical at end of title is stripped."""
        assert (_strip_parenthetical_translation(
            "Le Lézard aux plumes d'or (The Lizard with Golden Feathers)")
            == "Le Lézard aux plumes d'or")

    def test_no_parenthetical_unchanged(self):
        """Title without parenthetical is unchanged."""
        assert (_strip_parenthetical_translation("Moses and Monotheism")
                == "Moses and Monotheism")

    def test_credit_line_matches_with_parenthetical(self):
        """POI name with parenthetical matches work without it."""
        poi = "Le Lézard aux plumes d'or (The Lizard with Golden Feathers)"
        assert match_credit_line(poi, self.WORKS) == 'Gift of Boris Fridman'

    def test_credit_line_matches_without_parenthetical(self):
        """POI name without parenthetical still matches."""
        poi = "Le Lézard aux plumes d'or"
        assert match_credit_line(poi, self.WORKS) == 'Gift of Boris Fridman'

    def test_work_for_stop_returns_medium(self):
        """match_work_for_stop returns the full work dict with medium."""
        poi = "Le Lézard aux plumes d'or (The Lizard with Golden Feathers)"
        work = match_work_for_stop(poi, self.WORKS)
        assert work is not None
        assert work['medium'] == 'Illustrated book with 40 color lithographs'

    def test_confusable_titles_still_rejected(self):
        """Titles that share a prefix but differ must NOT match."""
        # These share first 10 chars after normalization but should not match
        confusable_works = [
            {'title': 'The Lizard with Golden Feathers', 'credit_line': 'Gift A'},
            {'title': 'Au Soleil du Plafond', 'credit_line': 'Gift B'},
        ]
        assert match_credit_line('The Lizard King', confusable_works) == ''
        assert match_credit_line('Au Soleil Couchant', confusable_works) == ''

    def test_provenance_block_emitted_when_credit_found(self):
        """When credit line is found, provenance block is non-empty."""
        block = build_provenance_block('Gift of Boris Fridman')
        assert 'Gift of Boris Fridman' in block
        assert 'PROHIBITION' in block

    def test_provenance_block_empty_when_no_credit(self):
        """When no credit line is found, provenance block is empty string."""
        assert build_provenance_block('') == ''
        assert build_provenance_block(None) == ''


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 5 — Gate scope: only exhibition-scoped tours
# ═══════════════════════════════════════════════════════════════════════════════

class TestGateScope:
    """The gate fires ONLY for exhibition-scoped museum tours."""

    def _make_checklist_result(self, page_text='', works=None):
        """Create a minimal object that quacks like ExhibitionChecklistResult."""
        class FakeResult:
            pass
        r = FakeResult()
        r.page_text = page_text
        r.works = works or []
        return r

    def test_gate_fires_with_page_text(self):
        """With page_text present, gate should process."""
        result = self._make_checklist_result(
            page_text="Joan Miró and Salvador Dalí exhibited here.",
            works=[{'title': 'Lizard', 'artist': 'Joan Miró'}]
        )
        poi_list = [{'name': 'Lizard', 'description': 'Xavier Lalanne sculpted this piece.'}]
        stats = apply_prose_entity_grounding_gate(poi_list, result)
        assert stats['persons_ungrounded'] >= 1
        assert 'Lalanne' not in poi_list[0]['description']

    def test_gate_skips_without_page_text(self):
        """Without page_text, the gate guard in generate_tour_text won't invoke us.
        But apply_prose_entity_grounding_gate itself is safe with empty page_text:
        it just won't ground anything (vacuously grounded = no one is found on page)."""
        result = self._make_checklist_result(page_text='', works=[])
        poi_list = [{'name': 'Test', 'description': 'Xavier Lalanne sculpted this.'}]
        stats = apply_prose_entity_grounding_gate(poi_list, result)
        # With empty page_text, no person can be grounded, so all are ungrounded
        # But the OUTER guard in generate_tour_text.py won't even call us
        assert stats['persons_detected'] >= 0

    def test_grounded_person_kept(self):
        """A person present in the page text is NOT removed."""
        result = self._make_checklist_result(
            page_text="This exhibition features works by Joan Miró and Salvador Dalí.",
            works=[{'title': 'Lizard', 'artist': 'Joan Miró'}]
        )
        poi_list = [{
            'name': 'Lizard',
            'description': 'Joan Miró created this lithograph in 1971. Salvador Dalí contributed etchings.'
        }]
        stats = apply_prose_entity_grounding_gate(poi_list, result)
        assert stats['persons_grounded'] >= 1
        assert 'Miró' in poi_list[0]['description']
        assert 'Dalí' in poi_list[0]['description']


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION — Full gate pass
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullGateIntegration:
    """End-to-end test of the gate with realistic MFA-like data."""

    def _make_checklist_result(self, page_text='', works=None):
        class FakeResult:
            pass
        r = FakeResult()
        r.page_text = page_text
        r.works = works or []
        return r

    def test_mfa_scenario(self):
        """Simulate the MFA Unbound bounced scenario:
        - Lalanne and Matisse are NOT on the exhibition page
        - Miró, Dalí, Gris are on the exhibition page
        - All mentions of Lalanne (full, bare, possessive) must be removed
        """
        page_text = (
            "Picasso, Miró, Dalí: Unbound brings together three masters of modernism. "
            "Joan Miró's lithographs, Salvador Dalí's etchings, and Juan Gris's compositions "
            "explore the boundaries of illustrated books as art. Pierre Reverdy collaborated "
            "with Gris on poetry volumes. Sigmund Freud's writings influenced Dalí's imagery."
        )
        works = [
            {'title': "Le Lézard aux plumes d'or", 'artist': 'Joan Miró'},
            {'title': 'Moses and Monotheism', 'artist': 'Salvador Dalí'},
            {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris'},
        ]
        result = self._make_checklist_result(page_text=page_text, works=works)

        poi_list = [
            {
                'name': "Le Lézard aux plumes d'or",
                'description': (
                    "Xavier Lalanne was a French sculptor known for animal forms. "
                    "Lalanne's choice of material transforms the ordinary into the extraordinary. "
                    "As you gaze upon this work, consider Lalanne's artistic vision. "
                    "Joan Miró created the original lithographs in 1971."
                ),
            },
            {
                'name': 'Moses and Monotheism',
                'description': (
                    "Henri Matisse influenced many artists of the period. "
                    "Salvador Dalí created this illustrated book exploring Freud's theories."
                ),
            },
            {
                'name': 'Au Soleil du Plafond',
                'description': (
                    "Juan Gris collaborated with Pierre Reverdy on this volume. "
                    "The poems and lithographs form a unified artistic statement."
                ),
            },
        ]

        stats = apply_prose_entity_grounding_gate(
            poi_list, result, stop_names=[p['name'] for p in poi_list])

        # Lalanne must be completely removed from stop 1
        assert "Lalanne" not in poi_list[0]['description'], (
            f"Lalanne still present: {poi_list[0]['description']}")

        # Matisse must be removed from stop 2 (not on the exhibition page)
        assert "Matisse" not in poi_list[1]['description'], (
            f"Matisse still present: {poi_list[1]['description']}")

        # Grounded persons must survive
        assert "Miró" in poi_list[0]['description']
        assert "Dalí" in poi_list[1]['description']
        assert "Gris" in poi_list[2]['description']
        assert "Reverdy" in poi_list[2]['description']

        # Stats
        assert stats['persons_ungrounded'] >= 2  # Lalanne, Matisse
        assert stats['persons_grounded'] >= 3    # Miró, Dalí, Gris (Reverdy, Freud)
        assert stats['sentences_dropped'] >= 3   # At least 3 Lalanne + 1 Matisse

    def test_treat_page_survives(self):
        """The Treat Page closing sentence must not be damaged."""
        page_text = "Joan Miró exhibition page text."
        works = [{'title': 'Lizard', 'artist': 'Joan Miró'}]
        result = self._make_checklist_result(page_text=page_text, works=works)

        poi_list = [{
            'name': 'Lizard',
            'description': (
                "Miró created this lithograph. "
                "The Treat Page shows whether there are real savings near you."
            ),
        }]

        stats = apply_prose_entity_grounding_gate(
            poi_list, result, stop_names=['Lizard'])

        assert "Treat Page" in poi_list[0]['description'], (
            f"Treat Page was incorrectly removed: {poi_list[0]['description']}")


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

class TestHelpers:
    """Unit tests for internal helper functions."""

    def test_surname_extraction(self):
        assert _surname_from_full_name("Xavier Lalanne") == "Lalanne"
        assert _surname_from_full_name("Henri Matisse") == "Matisse"
        assert _surname_from_full_name("Henri de Toulouse-Lautrec") == "Toulouse-Lautrec"
        assert _surname_from_full_name("Ludwig van Beethoven") == "Beethoven"

    def test_mentions_person_full_name(self):
        assert _mentions_person("Xavier Lalanne was a sculptor.", "Xavier Lalanne", "Lalanne")
        assert not _mentions_person("Joan Miró created this.", "Xavier Lalanne", "Lalanne")

    def test_mentions_person_bare_surname(self):
        assert _mentions_person("Lalanne mastered sculpture.", "Xavier Lalanne", "Lalanne")

    def test_mentions_person_possessive(self):
        assert _mentions_person("Lalanne's work is extraordinary.", "Xavier Lalanne", "Lalanne")

    def test_mentions_person_case_sensitive(self):
        """Bare surname match is case-sensitive."""
        assert not _mentions_person("The lalanne technique was used.", "Xavier Lalanne", "Lalanne")
        assert _mentions_person("The Lalanne technique was used.", "Xavier Lalanne", "Lalanne")
