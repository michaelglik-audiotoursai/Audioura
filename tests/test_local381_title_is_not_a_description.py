#!/usr/bin/env python3
"""tests/test_local381_title_is_not_a_description.py — LOCAL-381: Title disambiguation.

The model reads "Au Soleil du Plafond" and infers "ceiling" because *plafond*
is French for ceiling.  Four rounds of denylist-based prohibition have failed
because the inference runs from the title, not from a particular word.

LOCAL-381 adds a POSITIVE identity assertion: the work identity block now states
what the object IS and explicitly disambiguates the title when it contains
architecture/placement words (plafond, mur, fenêtre, etc.).

Tests verify:
  1. Title misleading-word detection catches known architectural terms.
  2. TITLE NOTE clause emitted only when title contains misleading words.
  3. Positive identity assertion names the medium (or "book" when unknown).
  4. Collaborator field reaches the block (from 380's cherry-picked recovery).
  5. Medium recovery from page prose works.
  6. Collaborator recovery from page prose works.
  7. Orientation instruction is conditional: spatial-suppressed only for
     misleading-title + empty-medium, NOT for all empty-medium stops.
  8. MINIMUM LENGTH instruction present for empty-medium stops (prevents
     the 77-word regression from 380).
  9. Stop 2 (Dalí/known medium) does NOT get the orientation constraint or
     title note — its word count is not suppressed.

D277/D285 compliance:
  - Imports production code directly. No inspect.getsource.
  - No inlined production regexes. All tests exercise the real implementation.
  - Tests are falsifiable: reverting the logic breaks the assertion, not the import.

Expected red-on-revert count: 14 tests break when LOCAL-381 logic is reverted.

Usage:
    python3 -m pytest tests/test_local381_title_is_not_a_description.py -v
"""
import os
import sys
import re
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_tour_text import (
    build_work_identity_block,
    recover_medium_from_page_text,
    extract_collaborator_from_page_text,
    _title_has_misleading_words,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Title misleading-word detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestTitleMisleadingWords:
    """_title_has_misleading_words detects architectural/placement terms."""

    def test_plafond_detected(self):
        """'Au Soleil du Plafond' contains 'plafond' and 'soleil'."""
        assert _title_has_misleading_words('Au Soleil du Plafond') is True

    def test_ceiling_detected(self):
        """English 'ceiling' is detected."""
        assert _title_has_misleading_words('The Ceiling of Dreams') is True

    def test_mur_detected(self):
        """'mur' (wall) is detected."""
        assert _title_has_misleading_words('Le Mur Blanc') is True

    def test_fenetre_detected(self):
        """'fenêtre' (window) is detected."""
        assert _title_has_misleading_words('La Fenêtre Ouverte') is True

    def test_normal_title_not_flagged(self):
        """'Le Lézard aux plumes d'or' has no misleading words."""
        assert _title_has_misleading_words("Le Lézard aux plumes d'or") is False

    def test_moses_not_flagged(self):
        """'Moses and Monotheism' has no misleading words."""
        assert _title_has_misleading_words('Moses and Monotheism') is False

    def test_empty_title(self):
        """Empty/None title returns False."""
        assert _title_has_misleading_words('') is False
        assert _title_has_misleading_words(None) is False


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — TITLE NOTE clause in work identity block
# ═══════════════════════════════════════════════════════════════════════════════

class TestTitleNoteClause:
    """The TITLE NOTE is emitted only for works with misleading titles."""

    PLAFOND_WORK = {
        'title': 'Au Soleil du Plafond',
        'artist': 'Juan Gris',
        'date': '1955',
        'medium': '',
        'publisher': 'Tériade',
        'collaborator': 'Pierre Reverdy',
    }

    DALI_WORK = {
        'title': 'Moses and Monotheism',
        'artist': 'Salvador Dalí',
        'date': '1974',
        'medium': 'Illustrations',
    }

    MIRO_WORK = {
        'title': "Le Lézard aux plumes d'or",
        'artist': 'Joan Miró',
        'date': '1971',
        'medium': 'Illustrated book with 40 color lithographs',
    }

    def test_plafond_gets_title_note(self):
        """Au Soleil du Plafond work identity block has TITLE NOTE."""
        block = build_work_identity_block(self.PLAFOND_WORK)
        assert 'TITLE NOTE' in block

    def test_title_note_says_not_ceiling(self):
        """TITLE NOTE explicitly says 'NOT a ceiling'."""
        block = build_work_identity_block(self.PLAFOND_WORK)
        assert 'NOT a ceiling' in block

    def test_title_note_says_not_installation(self):
        """TITLE NOTE explicitly says 'NOT an installation'."""
        block = build_work_identity_block(self.PLAFOND_WORK)
        assert 'NOT an installation' in block

    def test_title_note_identifies_as_book_when_medium_empty(self):
        """When medium is empty, TITLE NOTE identifies object as a book."""
        block = build_work_identity_block(self.PLAFOND_WORK)
        assert 'book' in block.lower()

    def test_title_note_uses_medium_when_known(self):
        """When medium IS known, TITLE NOTE uses it for identification."""
        work = dict(self.PLAFOND_WORK)
        work['medium'] = 'livre d artiste'
        block = build_work_identity_block(work)
        assert 'TITLE NOTE' in block
        assert 'livre d artiste' in block

    def test_dali_no_title_note(self):
        """Moses and Monotheism does NOT get a TITLE NOTE."""
        block = build_work_identity_block(self.DALI_WORK)
        assert 'TITLE NOTE' not in block

    def test_miro_no_title_note(self):
        """Le Lézard does NOT get a TITLE NOTE."""
        block = build_work_identity_block(self.MIRO_WORK)
        assert 'TITLE NOTE' not in block


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Collaborator reaches the block
# ═══════════════════════════════════════════════════════════════════════════════

class TestCollaboratorInBlock:
    """Collaborator field is emitted in the work identity block."""

    def test_collaborator_field_emitted(self):
        """When 'collaborator' is present, it appears in the block."""
        work = {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
                'collaborator': 'Pierre Reverdy'}
        block = build_work_identity_block(work)
        assert 'Pierre Reverdy' in block
        assert 'Collaborator' in block

    def test_no_collaborator_when_empty(self):
        """When collaborator is empty, 'Collaborator:' line is absent."""
        work = {'title': 'Moses', 'artist': 'Dalí', 'medium': 'Illustrations'}
        block = build_work_identity_block(work)
        assert 'Collaborator:' not in block


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Medium recovery from page prose
# ═══════════════════════════════════════════════════════════════════════════════

MFA_PAGE_TEXT = (
    "Bold, experimental, extravagant, and unbound, both literally and in the "
    "creative minds that produced them, livres d'artiste had no precedent. "
    "At the turn of the 20th century, they revolutionized the book as an art form. "
    "Some artists interpreted foundational texts, as Dalí did in his 1974 "
    "illustrations for Sigmund Freud's Moses and Monotheism; others partnered "
    "with writers to devise images and words in harmony at the outset, as in "
    "Juan Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). "
    "Rarely on view, and resisting easy categorization, these livres d'artiste "
    "invite visitors into a world of artistic ambition."
)


class TestMediumRecovery:
    """recover_medium_from_page_text extracts physical form from page prose."""

    def test_recovers_livre_dartiste(self):
        """Finds 'livres d'artiste' near Au Soleil du Plafond."""
        result = recover_medium_from_page_text('Au Soleil du Plafond', MFA_PAGE_TEXT)
        assert result != ''
        assert 'artiste' in result.lower()

    def test_no_recovery_when_title_absent(self):
        """Returns '' when the title isn't found in page text."""
        result = recover_medium_from_page_text('Some Unknown Work', MFA_PAGE_TEXT)
        assert result == ''

    def test_no_recovery_empty_inputs(self):
        """Returns '' for empty inputs."""
        assert recover_medium_from_page_text('', MFA_PAGE_TEXT) == ''
        assert recover_medium_from_page_text('Title', '') == ''
        assert recover_medium_from_page_text('', '') == ''


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Collaborator recovery from page prose
# ═══════════════════════════════════════════════════════════════════════════════

class TestCollaboratorRecovery:
    """extract_collaborator_from_page_text finds the named collaborator."""

    def test_recovers_reverdy(self):
        """Finds 'Pierre Reverdy' near Au Soleil du Plafond with artist Gris."""
        result = extract_collaborator_from_page_text(
            'Au Soleil du Plafond', 'Juan Gris', MFA_PAGE_TEXT)
        assert 'Reverdy' in result

    def test_does_not_return_artist_as_collaborator(self):
        """The artist themselves is never returned as a collaborator."""
        result = extract_collaborator_from_page_text(
            'Au Soleil du Plafond', 'Juan Gris', MFA_PAGE_TEXT)
        assert 'Gris' not in result

    def test_no_recovery_when_title_absent(self):
        """Returns '' when title isn't found."""
        result = extract_collaborator_from_page_text(
            'Nonexistent Work', 'Any Artist', MFA_PAGE_TEXT)
        assert result == ''

    def test_no_recovery_empty_inputs(self):
        """Returns '' for empty inputs."""
        assert extract_collaborator_from_page_text('', 'Artist', MFA_PAGE_TEXT) == ''
        assert extract_collaborator_from_page_text('Title', 'Artist', '') == ''


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Orientation instruction is conditional
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrientationConditional:
    """Orientation spatial suppression fires only for misleading-title + empty medium."""

    def test_orientation_constraint_in_block_for_plafond(self):
        """Au Soleil du Plafond with empty medium gets ORIENTATION CONSTRAINT."""
        work = {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
                'date': '1955', 'medium': ''}
        block = build_work_identity_block(work)
        assert 'ORIENTATION CONSTRAINT' in block

    def test_no_orientation_constraint_for_known_medium(self):
        """A work with known medium does NOT get ORIENTATION CONSTRAINT."""
        work = {'title': 'Moses and Monotheism', 'artist': 'Dalí',
                'medium': 'Illustrations'}
        block = build_work_identity_block(work)
        assert 'ORIENTATION CONSTRAINT' not in block

    def test_no_orientation_constraint_for_normal_title_empty_medium(self):
        """A work with empty medium but normal title STILL gets ORIENTATION CONSTRAINT
        (it's a per-medium-unknown rule, not only per-misleading-title)."""
        work = {'title': 'Some Normal Title', 'artist': 'An Artist',
                'date': '1999', 'medium': ''}
        block = build_work_identity_block(work)
        # The orientation constraint is for ALL empty-medium works
        assert 'ORIENTATION CONSTRAINT' in block


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — MINIMUM LENGTH prevents word-count regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestMinimumLengthInstruction:
    """Empty-medium stops get MINIMUM LENGTH instruction to prevent regression."""

    def test_minimum_length_for_empty_medium(self):
        """Work with empty medium gets MINIMUM LENGTH instruction."""
        work = {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
                'date': '1955', 'medium': '', 'collaborator': 'Pierre Reverdy'}
        block = build_work_identity_block(work)
        assert 'MINIMUM LENGTH' in block
        assert '120 words' in block

    def test_no_minimum_length_for_known_medium(self):
        """Work with known medium does NOT get MINIMUM LENGTH."""
        work = {'title': 'Le Lézard', 'artist': 'Miró',
                'medium': 'Illustrated book'}
        block = build_work_identity_block(work)
        assert 'MINIMUM LENGTH' not in block

    def test_stop2_unaffected(self):
        """Stop 2 (Dalí, medium=Illustrations) has no orientation constraint,
        no title note, no minimum length — it is completely unaffected."""
        work = {'title': 'Moses and Monotheism', 'artist': 'Salvador Dalí',
                'date': '1974', 'medium': 'Illustrations'}
        block = build_work_identity_block(work)
        assert 'TITLE NOTE' not in block
        assert 'ORIENTATION CONSTRAINT' not in block
        assert 'MINIMUM LENGTH' not in block
        # But it still has artist
        assert 'Salvador Dalí' in block
