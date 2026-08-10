#!/usr/bin/env python3
"""tests/test_local380_medium_constraint_gaps.py — LOCAL-380: Medium constraint gaps.

Tests three fixes:
  Defect 1 — When medium is empty, the WORK IDENTITY block carries an explicit
             negative: prohibits medium/spatial claims AND spatial instructions
             (do not tell the visitor where to stand or look). The constraint
             must be strong enough that silence ≠ permission.
  Defect 2 — The Orientation field receives the same medium constraint. When
             medium is unknown, the orientation format instruction suppresses
             spatial directions.
  Also — Collaborator/co-author naming when the page prose mentions one.

D277/D285 compliance:
  - Imports production code directly. No inspect.getsource.
  - No inlined production regexes. All tests exercise the real implementation.
  - Tests are falsifiable: reverting the logic breaks the assertion, not the import.

Expected red-on-revert count: 9 tests break when LOCAL-380 logic is reverted.

Usage:
    python3 -m pytest tests/test_local380_medium_constraint_gaps.py -v
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
)


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 1 — Empty medium carries explicit negative constraint
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmptyMediumNegativeConstraint:
    """When medium is empty, the block must prohibit spatial instructions."""

    def test_empty_medium_prohibits_where_to_stand(self):
        """Empty medium block must say 'Do NOT tell the visitor where to stand'."""
        work = {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
                'date': '1955', 'medium': ''}
        block = build_work_identity_block(work)
        assert 'NOT tell the visitor where to stand or look' in block

    def test_empty_medium_prohibits_look_up(self):
        """Empty medium block must prohibit 'look up' / 'positioned above'."""
        work = {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
                'date': '1955', 'medium': ''}
        block = build_work_identity_block(work)
        assert 'look up' in block.lower()
        assert 'positioned above' in block.lower() or 'stand beneath' in block.lower()

    def test_empty_medium_prohibits_glass(self):
        """Empty medium block must list 'glass' among prohibited medium terms."""
        work = {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
                'date': '1955', 'medium': ''}
        block = build_work_identity_block(work)
        # The block must mention 'glass' as a prohibited term
        assert 'glass' in block.lower()

    def test_empty_medium_prefers_known_facts(self):
        """Empty medium block must instruct to focus on what IS known."""
        work = {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
                'date': '1955', 'medium': '', 'publisher': 'Tériade'}
        block = build_work_identity_block(work)
        assert 'what IS known' in block or 'what is known' in block.lower()

    def test_known_medium_has_no_spatial_prohibition(self):
        """When medium IS present, the block does NOT prohibit spatial instructions."""
        work = {'title': 'Le Lézard', 'artist': 'Joan Miró',
                'medium': 'Illustrated book with 40 color lithographs'}
        block = build_work_identity_block(work)
        assert 'do NOT tell the visitor where to stand' not in block
        assert 'UNKNOWN' not in block


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 2 — Orientation receives medium constraint
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrientationReceivesMediumConstraint:
    """Orientation must obey the same prohibition when medium is unknown."""

    def test_empty_medium_block_has_orientation_constraint(self):
        """The WORK IDENTITY block for unknown medium must include ORIENTATION CONSTRAINT."""
        work = {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
                'date': '1955', 'medium': ''}
        block = build_work_identity_block(work)
        assert 'ORIENTATION CONSTRAINT' in block

    def test_orientation_constraint_prohibits_spatial_in_orientation(self):
        """ORIENTATION CONSTRAINT must prohibit spatial directions in the Orientation section."""
        work = {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
                'date': '1955', 'medium': ''}
        block = build_work_identity_block(work)
        # Must mention that orientation must NOT give spatial directions
        orientation_section = block[block.index('ORIENTATION CONSTRAINT'):]
        assert 'NOT' in orientation_section
        assert 'stand' in orientation_section.lower() or 'look' in orientation_section.lower()

    def test_known_medium_no_orientation_constraint(self):
        """When medium IS known, there is no ORIENTATION CONSTRAINT."""
        work = {'title': 'Le Lézard', 'artist': 'Joan Miró',
                'medium': 'Illustrated book with 40 color lithographs'}
        block = build_work_identity_block(work)
        assert 'ORIENTATION CONSTRAINT' not in block


# ═══════════════════════════════════════════════════════════════════════════════
# COLLABORATOR EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

class TestCollaboratorExtraction:
    """Collaborators named in page prose must be extracted and named."""

    # Simulated page text for MFA Unbound exhibition
    MFA_PAGE_TEXT = (
        "Picasso, Miró, Dalí: Unbound features works by three iconic Spanish artists. "
        "Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 "
        "showcases the artist's mastery of color lithography. Salvador Dalí created "
        "illustrations for Moses and Monotheism exploring Sigmund Freud's theories. "
        "Juan Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955) is a "
        "remarkable livre d'artiste that brings together visual art and poetry. "
        "The exhibition runs through September 2026."
    )

    def test_reverdy_extracted_for_au_soleil(self):
        """Pierre Reverdy must be extracted as collaborator for Au Soleil du Plafond."""
        collab = extract_collaborator_from_page_text(
            'Au Soleil du Plafond', 'Juan Gris', self.MFA_PAGE_TEXT)
        assert 'Reverdy' in collab

    def test_no_collaborator_for_miro(self):
        """Miró's Le Lézard has no collaborator mentioned in this text."""
        collab = extract_collaborator_from_page_text(
            "Le Lézard aux plumes d'or", 'Joan Miró', self.MFA_PAGE_TEXT)
        # Should be empty or not be the artist themselves
        assert collab == '' or 'Miró' not in collab

    def test_collaborator_in_block(self):
        """When collaborator is set, it appears in the WORK IDENTITY block."""
        work = {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
                'date': '1955', 'medium': '', 'collaborator': 'Pierre Reverdy'}
        block = build_work_identity_block(work)
        assert 'Pierre Reverdy' in block
        assert 'Collaborator' in block


# ═══════════════════════════════════════════════════════════════════════════════
# MEDIUM RECOVERY FROM PAGE PROSE
# ═══════════════════════════════════════════════════════════════════════════════

class TestMediumRecoveryFromPageProse:
    """When structured medium is empty but page prose describes the form, recover it."""

    MFA_PAGE_TEXT = (
        "Juan Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955) is a "
        "remarkable livre d'artiste that brings together visual art and poetry. "
        "Joan Miró created Le Lézard aux plumes d'or as an illustrated book with "
        "40 color lithographs in 1971."
    )

    def test_livre_dartiste_recovered(self):
        """'livre d'artiste' should be recovered from page prose."""
        medium = recover_medium_from_page_text('Au Soleil du Plafond', self.MFA_PAGE_TEXT)
        assert medium != ''
        assert 'livre' in medium.lower() or 'book' in medium.lower()

    def test_illustrated_book_recovered(self):
        """'illustrated book' or 'livre d'artiste' should be recovered for Le Lézard."""
        # The page text mentions Le Lézard near both "illustrated book" and "livre d'artiste"
        page_text = (
            "Joan Miró created Le Lézard aux plumes d'or as an illustrated book with "
            "40 color lithographs in 1971."
        )
        medium = recover_medium_from_page_text("Le Lézard aux plumes d'or", page_text)
        assert medium != ''
        assert 'book' in medium.lower() or 'lithograph' in medium.lower()

    def test_no_recovery_for_absent_title(self):
        """No recovery when the title is not in the page text."""
        medium = recover_medium_from_page_text('Nonexistent Work', self.MFA_PAGE_TEXT)
        assert medium == ''

    def test_no_recovery_from_empty_page(self):
        """No recovery when page text is empty."""
        medium = recover_medium_from_page_text('Au Soleil du Plafond', '')
        assert medium == ''
