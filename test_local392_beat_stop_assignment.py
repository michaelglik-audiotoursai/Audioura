#!/usr/bin/env python3
"""test_local392_beat_stop_assignment.py — Unit tests for LOCAL-392: beat-to-stop attribution.

Verifies:
  - A beat derived from work A is NEVER assigned to work B's stop.
  - Exhibition-wide beats (gallery patron, circumstance) are NOT demanded as required content.
  - attribute_beats_to_works correctly tags beats with source_work_index.
  - Retries only chase facts that are true of that stop.

Expected red-on-revert:
  Reverting LOCAL-392 logic (attribute_beats_to_works and source_work_index handling
  in assign_beats_to_stops) causes test_beat_never_crosses_works and
  test_attribution_prevents_wrong_stop_demand to fail — the LOGIC of correct
  assignment breaks, not a symbol rename.
"""
import os
import sys
import io
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from story_beat_injector import (
    extract_story_beats,
    assign_beats_to_stops,
    attribute_beats_to_works,
    get_required_beat_names,
    check_required_beats_present,
    build_story_beat_prompt_block,
)


# === Test fixtures ===

# Simulates the MFA "Picasso, Miró, Dalí: Unbound" exhibition works
MFA_WORKS = [
    {
        'title': 'Le Lézard aux plumes d\'or',
        'artist': 'Joan Miró',
        'publisher': 'Louis Broder',
        'credit_line': 'Gift of Boris Fridman. Printed by Mourlot Frères.',
    },
    {
        'title': 'Les Chants de Maldoror',
        'artist': 'Salvador Dalí',
        'collaborator': '',
        'credit_line': 'Museum purchase. Illustrations for Sigmund Freud\'s theories.',
    },
    {
        'title': 'Au Soleil du Plafond',
        'artist': 'Juan Gris',
        'collaborator': 'Pierre Reverdy',
        'credit_line': 'Gift of the artist\'s estate.',
    },
]

MFA_STOP_NAMES = [
    'Le Lézard aux plumes d\'or',
    'Les Chants de Maldoror',
    'Au Soleil du Plafond',
]

# Simulated page text containing people from all three works
MFA_PAGE_TEXT = """
Picasso, Miró, Dalí: Unbound showcases the livre d'artiste tradition.

Le Lézard aux plumes d'or was published by Louis Broder and printed by Mourlot Frères
in Paris. Gift of Boris Fridman to the Museum of Fine Arts.

Salvador Dalí illustrated Les Chants de Maldoror, influenced by Sigmund Freud's
psychoanalytic theories. The surrealist master created etchings that explored the unconscious.

Au Soleil du Plafond is a collaboration between Juan Gris and French poet Pierre Reverdy.
Gris and Reverdy's poetry created a harmonious dialogue between image and word.

The exhibition is displayed in the Torf Gallery, named for a generous benefactor.
"""


# === Tests ===

def test_attribution_assigns_correct_source_work_index():
    """attribute_beats_to_works must tag each beat with the correct work index."""
    beats = extract_story_beats(MFA_PAGE_TEXT)
    # Suppress derivation log output
    f = io.StringIO()
    with redirect_stdout(f):
        attributed = attribute_beats_to_works(beats, MFA_WORKS)

    # Find key people
    person_map = {b['person'].split()[-1].lower(): b for b in attributed
                  if b['role'] not in ('circumstance', 'stakes')}

    # Broder/Mourlot/Fridman -> work 0 (Le Lézard / Miró)
    for name in ['broder', 'mourlot', 'fridman']:
        if name in person_map:
            assert person_map[name].get('source_work_index') == 0, \
                f"{name} should be work 0 (Le Lézard), got {person_map[name].get('source_work_index')}"

    # Freud -> work 1 (Les Chants / Dalí)
    if 'freud' in person_map:
        assert person_map['freud'].get('source_work_index') == 1, \
            f"Freud should be work 1 (Les Chants), got {person_map['freud'].get('source_work_index')}"

    # Reverdy -> work 2 (Au Soleil / Gris)
    if 'reverdy' in person_map:
        assert person_map['reverdy'].get('source_work_index') == 2, \
            f"Reverdy should be work 2 (Au Soleil), got {person_map['reverdy'].get('source_work_index')}"

    print("  ✓ test_attribution_assigns_correct_source_work_index PASSED")


def test_beat_never_crosses_works():
    """A beat from work A must NEVER be assigned to work B's stop."""
    beats = extract_story_beats(MFA_PAGE_TEXT)
    f = io.StringIO()
    with redirect_stdout(f):
        attributed = attribute_beats_to_works(beats, MFA_WORKS)

    assigned = assign_beats_to_stops(
        attributed, MFA_STOP_NAMES,
        matched_works=MFA_WORKS,
        framing_case='exhibition',
    )

    # Check each stop's required beats belong to that stop's work
    for stop_idx in range(3):
        stop_beats = assigned[stop_idx]
        for beat in stop_beats:
            if beat.get('exhibition_wide') or beat['role'] in ('circumstance', 'stakes'):
                continue  # exhibition-wide beats are allowed anywhere
            src = beat.get('source_work_index')
            if src is not None:
                assert src == stop_idx, (
                    f"CROSS-CONTAMINATION: beat '{beat['person']}' (source_work={src}) "
                    f"was assigned to stop {stop_idx}. This is the exact bug LOCAL-392 fixes."
                )

    print("  ✓ test_beat_never_crosses_works PASSED")


def test_exhibition_wide_beats_not_required():
    """Exhibition-wide beats (gallery_patron, circumstance) must NOT be in required names."""
    beats = extract_story_beats(MFA_PAGE_TEXT)
    f = io.StringIO()
    with redirect_stdout(f):
        attributed = attribute_beats_to_works(beats, MFA_WORKS)

    assigned = assign_beats_to_stops(
        attributed, MFA_STOP_NAMES,
        matched_works=MFA_WORKS,
        framing_case='exhibition',
    )

    for stop_idx, stop_beats in enumerate(assigned):
        required = get_required_beat_names(stop_beats)
        for beat in stop_beats:
            if beat.get('exhibition_wide'):
                surname = beat['person'].split()[-1]
                assert surname not in required, (
                    f"Exhibition-wide beat '{beat['person']}' should NOT be in "
                    f"required names for stop {stop_idx + 1}, but found '{surname}' in {required}"
                )

    print("  ✓ test_exhibition_wide_beats_not_required PASSED")


def test_attribution_prevents_wrong_stop_demand():
    """The retry mechanism must not demand a person of a stop they don't belong to.

    Simulates what LOCAL-391 logging exposed: Reverdy demanded of stop 1,
    Freud demanded of stop 3. With LOCAL-392, these demands should never happen.
    """
    beats = extract_story_beats(MFA_PAGE_TEXT)
    f = io.StringIO()
    with redirect_stdout(f):
        attributed = attribute_beats_to_works(beats, MFA_WORKS)

    assigned = assign_beats_to_stops(
        attributed, MFA_STOP_NAMES,
        matched_works=MFA_WORKS,
        framing_case='exhibition',
    )

    # Stop 1 (Miró): should NOT demand Reverdy, Freud
    stop1_required = get_required_beat_names(assigned[0])
    stop1_required_lower = [n.lower() for n in stop1_required]
    assert 'reverdy' not in stop1_required_lower, \
        f"Stop 1 must NOT demand Reverdy (belongs to stop 3). Required: {stop1_required}"
    assert 'freud' not in stop1_required_lower, \
        f"Stop 1 must NOT demand Freud (belongs to stop 2). Required: {stop1_required}"

    # Stop 2 (Dalí): should NOT demand Mourlot, Fridman, Broder, Reverdy
    stop2_required = get_required_beat_names(assigned[1])
    stop2_required_lower = [n.lower() for n in stop2_required]
    for name in ['mourlot', 'fridman', 'broder', 'reverdy']:
        assert name not in stop2_required_lower, \
            f"Stop 2 must NOT demand {name}. Required: {stop2_required}"

    # Stop 3 (Gris): should NOT demand Freud, Mourlot, Fridman, Broder
    stop3_required = get_required_beat_names(assigned[2])
    stop3_required_lower = [n.lower() for n in stop3_required]
    for name in ['freud', 'mourlot', 'fridman', 'broder']:
        assert name not in stop3_required_lower, \
            f"Stop 3 must NOT demand {name}. Required: {stop3_required}"

    print("  ✓ test_attribution_prevents_wrong_stop_demand PASSED")


def test_correct_positive_assignments():
    """Verify the positive case: the right people ARE assigned to the right stops."""
    beats = extract_story_beats(MFA_PAGE_TEXT)
    f = io.StringIO()
    with redirect_stdout(f):
        attributed = attribute_beats_to_works(beats, MFA_WORKS)

    assigned = assign_beats_to_stops(
        attributed, MFA_STOP_NAMES,
        matched_works=MFA_WORKS,
        framing_case='exhibition',
    )

    # Stop 1 required should include at least one of: Broder, Mourlot, Fridman
    stop1_required = [n.lower() for n in get_required_beat_names(assigned[0])]
    stop1_people = set(stop1_required)
    assert stop1_people & {'broder', 'mourlot', 'fridman', 'frères'}, \
        f"Stop 1 should require at least one of Broder/Mourlot/Fridman. Got: {stop1_required}"

    # Stop 2 required should include Freud (or Dalí as artist)
    stop2_required = [n.lower() for n in get_required_beat_names(assigned[1])]
    # Freud was extracted as a beat
    if any('freud' in b['person'].lower() for b in beats):
        assert 'freud' in stop2_required, \
            f"Stop 2 should require Freud. Got: {stop2_required}"

    # Stop 3 required should include Reverdy
    stop3_required = [n.lower() for n in get_required_beat_names(assigned[2])]
    if any('reverdy' in b['person'].lower() for b in beats):
        assert 'reverdy' in stop3_required, \
            f"Stop 3 should require Reverdy. Got: {stop3_required}"

    print("  ✓ test_correct_positive_assignments PASSED")


def test_prompt_block_only_demands_work_specific_beats():
    """The prompt block's REQUIRED CONTENT section must only list work-specific beats."""
    beats = extract_story_beats(MFA_PAGE_TEXT)
    f = io.StringIO()
    with redirect_stdout(f):
        attributed = attribute_beats_to_works(beats, MFA_WORKS)

    assigned = assign_beats_to_stops(
        attributed, MFA_STOP_NAMES,
        matched_works=MFA_WORKS,
        framing_case='exhibition',
    )

    # For each stop, the prompt block should only require that stop's beats
    for stop_idx in range(3):
        block = build_story_beat_prompt_block(assigned[stop_idx], framing_case='exhibition')
        # Find names in REQUIRED CONTENT section
        if '━━━ REQUIRED CONTENT' in block:
            required_section = block.split('━━━ REQUIRED CONTENT')[1].split('━━━ END')[0]
            # Check no cross-work names appear
            if stop_idx == 0:
                assert 'Reverdy' not in required_section, "Stop 1 prompt demands Reverdy"
                assert 'Freud' not in required_section, "Stop 1 prompt demands Freud"
            elif stop_idx == 1:
                assert 'Reverdy' not in required_section, "Stop 2 prompt demands Reverdy"
                assert 'Mourlot' not in required_section, "Stop 2 prompt demands Mourlot"
                assert 'Fridman' not in required_section, "Stop 2 prompt demands Fridman"
            elif stop_idx == 2:
                assert 'Freud' not in required_section, "Stop 3 prompt demands Freud"
                assert 'Mourlot' not in required_section, "Stop 3 prompt demands Mourlot"
                assert 'Fridman' not in required_section, "Stop 3 prompt demands Fridman"

    print("  ✓ test_prompt_block_only_demands_work_specific_beats PASSED")


def test_fallback_without_attribution():
    """If beats lack source_work_index, the legacy fallback should still work."""
    beats = extract_story_beats(MFA_PAGE_TEXT)
    # Do NOT call attribute_beats_to_works — simulate old behavior
    assigned = assign_beats_to_stops(
        beats, MFA_STOP_NAMES,
        matched_works=MFA_WORKS,
        framing_case='exhibition',
    )
    # Every stop should have at least one beat
    for i, stop_beats in enumerate(assigned):
        assert len(stop_beats) > 0, f"Stop {i+1} got no beats in fallback mode"

    print("  ✓ test_fallback_without_attribution PASSED")


def test_venue_tour_unaffected():
    """Venue tours (Palais Lascaris) should not be affected — they have no exhibition works."""
    # Venue tours have no matched_works, so beats get distributed round-robin
    venue_page = """
The Palais Lascaris houses a remarkable collection of musical instruments.
A baroque guitar from 1696 was crafted by Jean-Baptiste Voboam in Paris.
The hurdy-gurdy dates to 1780, made by Pierre Louvet.
"""
    beats = extract_story_beats(venue_page)
    assigned = assign_beats_to_stops(
        beats, ['Baroque guitar', 'Hurdy-gurdy', 'Violin', 'Flute'],
        matched_works=None,
        framing_case='venue_purpose',
    )
    # Should distribute without error
    total_beats = sum(len(s) for s in assigned)
    assert total_beats >= len(beats), f"Not all beats were distributed"

    print("  ✓ test_venue_tour_unaffected PASSED")


# === Runner ===

if __name__ == '__main__':
    print("\n=== LOCAL-392: Beat-to-stop assignment tests ===\n")

    test_attribution_assigns_correct_source_work_index()
    test_beat_never_crosses_works()
    test_exhibition_wide_beats_not_required()
    test_attribution_prevents_wrong_stop_demand()
    test_correct_positive_assignments()
    test_prompt_block_only_demands_work_specific_beats()
    test_fallback_without_attribution()
    test_venue_tour_unaffected()

    print("\n=== ALL TESTS PASSED ===\n")
