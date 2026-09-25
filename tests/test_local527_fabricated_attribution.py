"""LOCAL-527 — fabricated builder/founder attribution.

Round 7 and round 8 both shipped tours whose "<built|founded|constructed> in
<YEAR> by <NAME>" frame was filled with a famous-sounding name that nobody
checked, and `tour_quality.score_tour` reported CLEAN for both:

  LOGAN_1 (round 7, ORIENTATION): the Control Tower "constructed in 1887-1889 by
          Gustave Eiffel" — that is the Eiffel Tower, pasted into an airport.
  LOGAN_1 (round 8, BODY): the same man, moved into the stop-1 body — proof a fix
          aimed only at orientations would not hold.
  CHURCH_1 (round 8): "Founded in 1868 by St. Mary Help of Christians" — the
          church's OWN dedication ("Our Lady Help of Christians") rewritten into a
          person who founded it.

Every defect sentence below is verbatim from TOURS_FOR_REVIEW (en-dash included).

What this gate can and cannot do offline (D577), pinned by the tests:
  - dedication-as-founder is caught OFFLINE WITH CERTAINTY — no church is founded
    by the saint it is dedicated to; that is deterministic.
  - a plain builder/founder attribution (Eiffel) is caught OFFLINE ONLY AS
    UNVERIFIED — it is flagged, not refuted. Refuting it needs a source. The
    optional verify_attribution hook is that grounded seam; when it confirms a
    name the frame clears, but it never clears a dedication error.
"""
import os
import pytest

from tour_quality import (
    score_tour,
    _find_fabricated_attributions,
    REQUIRED_CLEAN,
)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─── The three real defect sentences, verbatim ──────────────────────────────
R7_EIFFEL_ORIENTATION = (
    "Orientation: You are about to embark on a walking journey through Boston "
    "Logan International Airport, Boston MA. The tour will take you from Terminal "
    "A Check-In to the iconic Control Tower, a historic structure constructed in "
    "1887\u20131889 by Gustave Eiffel."
)
R8_EIFFEL_BODY = (
    "As you traverse this bustling hub, built in 1887\u20131889 by Gustave "
    "Eiffel, you'll uncover the meticulous planning and coordination that ensures "
    "every passenger's journey."
)
R8_STMARY = (
    "Step-by-Step Audio Guided Tour: Our Lady Help of Christians Catholic Church, "
    "Newton MA\n"
    "Founded in 1868 by St. Mary Help of Christians, this church echoes Monsignor "
    "Capik's 50th Anniversary of Ordination in 2005."
)


# ─── The gate must be wired to actually gate ────────────────────────────────
def test_fabricated_attribution_is_a_required_clean_defect():
    """A defect that is not in REQUIRED_CLEAN does not gate — this one must."""
    assert 'fabricated_attribution' in REQUIRED_CLEAN


# ─── Detection of each real sentence ────────────────────────────────────────
def test_round7_eiffel_orientation_is_flagged_unverified():
    hits = _find_fabricated_attributions(R7_EIFFEL_ORIENTATION)
    assert hits, "the round-7 Eiffel orientation was not flagged"
    kind, verb, year, name = hits[0]
    assert kind == 'unverified'
    assert name == 'Gustave Eiffel'
    assert year == '1887'


def test_round8_eiffel_body_is_flagged_unverified():
    """The defect moved from the orientation to the body between rounds; a fix
    aimed only at orientations would miss this. The frame itself is the target."""
    hits = _find_fabricated_attributions(R8_EIFFEL_BODY)
    assert hits, "the round-8 Eiffel body sentence was not flagged"
    kind, verb, year, name = hits[0]
    assert kind == 'unverified'
    assert name == 'Gustave Eiffel'


def test_round8_stmary_is_flagged_as_dedication():
    """The church's own dedication turned into its founder — a dedication error,
    not merely unverified. It is caught offline with certainty."""
    hits = _find_fabricated_attributions(R8_STMARY)
    assert hits, "the St. Mary dedication-as-founder was not flagged"
    kind, verb, year, name = hits[0]
    assert kind == 'dedication'
    assert 'Help of Christians' in name


# ─── Each real sentence makes score_tour report not-clean ───────────────────
@pytest.mark.parametrize('text', [R7_EIFFEL_ORIENTATION, R8_EIFFEL_BODY, R8_STMARY])
def test_score_tour_gates_each_real_sentence(text):
    result = score_tour(text, requested_stops=4, is_building_tour=True)
    assert 'fabricated_attribution' in result['defects']
    assert result['clean'] is False


# ─── The real tour FILES that scored CLEAN before now gate ──────────────────
@pytest.mark.parametrize('path', [
    'TOURS_FOR_REVIEW/round8/LOGAN_1.txt',
    'TOURS_FOR_REVIEW/round8/CHURCH_1.txt',
    'TOURS_FOR_REVIEW/round7/LOGAN_1.txt',
    'TOURS_FOR_REVIEW/round7/LOGAN_2.txt',
])
def test_previously_clean_tour_files_now_gate(path):
    text = open(os.path.join(HERE, path), errors='ignore').read()
    result = score_tour(text, requested_stops=4, is_building_tour=True)
    assert 'fabricated_attribution' in result['defects'], path
    assert result['clean'] is False, path


# ─── D577: offline behaviour of the grounded seam ───────────────────────────
def test_a_source_clears_an_unverified_attribution():
    """When verify_attribution confirms the name, the unverified frame clears."""
    confirm = lambda name, year, text: True
    result = score_tour(R8_EIFFEL_BODY, verify_attribution=confirm)
    assert 'fabricated_attribution' not in result['defects']


def test_a_source_never_clears_a_dedication_error():
    """A dedication rendered as a founder is wrong regardless of any source, so
    even an all-confirming verifier must not clear it."""
    confirm = lambda name, year, text: True
    result = score_tour(R8_STMARY, verify_attribution=confirm)
    assert 'fabricated_attribution' in result['defects']


# ─── Guarding against false positives ───────────────────────────────────────
def test_a_people_group_is_not_a_fabricated_attribution():
    """"funded by Irish immigrants" is a people-group, not a fabricated person."""
    assert _find_fabricated_attributions(
        "The parish was founded in 1868 by Irish immigrants who settled here.") == []


def test_artwork_creation_is_not_a_venue_founding_claim():
    """"Nu bleu IV, created in 1952 by Henri Matisse" is legitimate art-tour
    content: the founding/construction verbs deliberately exclude created/designed
    so real artwork attributions are not swept up."""
    art = ("Nu bleu IV, created in 1952 by Henri Matisse, is a captivating "
           "representation of a female nude.")
    assert _find_fabricated_attributions(art) == []


def test_a_tour_with_no_attribution_frame_is_clean_here():
    plain = ("Stop 1: Terminal A\nThe building opened in 2005 and was the first "
             "airport terminal to achieve LEED certification.")
    result = score_tour(plain, requested_stops=1, is_building_tour=True)
    assert 'fabricated_attribution' not in result['defects']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
