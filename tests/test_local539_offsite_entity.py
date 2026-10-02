"""LOCAL-539 — a place framed as part of the tour that is not a stop.

Round 9 shipped two tours that named a place AS PART OF THE TOUR when it was
neither the venue nor any stop, and `tour_quality.score_tour` reported CLEAN:

  round9/LOGAN_1 (Boston Logan airport), stop-1 orientation:
      "St. Mary's Cathedral, dedicated by pioneer priest Fr John Therry, and
       Gustave Eiffel's iconic Control Tower mark the endpoints."
    St Mary's Cathedral and Fr John Therry are in Sydney, Australia; nothing in
    the tour is in Australia, and the previous sentence already named the real
    endpoints (Main Concourse / Baggage Claim).

  round9/CHURCH_1 (Our Lady Help of Christians, Newton MA), epilog:
      "That's 4 stops — Mary Immaculate of Lourdes showcases collaborative
       stained glass art..."
    Mary Immaculate of Lourdes is a DIFFERENT church, in Newton Upper Falls.

THE DISTINCTION IS FRAMING, NOT DISTANCE. The whole test is one pair: the SAME
church, in the SAME tour (round9/CHURCH_1), named two ways —
  * stop 2 (NEGATIVE control): "A short distance away in Newton Upper Falls...
    At Mary Immaculate of Lourdes, the windows reveal a tale of artistic
    collaboration that never graced Our Lady Help of Christians." — correct
    contrast, must stay CLEAN;
  * epilog (POSITIVE): "That's 4 stops — Mary Immaculate of Lourdes ..." — the
    church put in the itinerary-recap slot, the defect.
Only framing separates them, so only framing may drive the flag.

Every passage below is read from the real file at runtime (sliced, never
retyped) so the test asserts on the exact bytes shipped.
"""
import os
import re
import pytest

from tour_quality import score_tour, find_offsite_entities, REQUIRED_CLEAN

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGAN9 = os.path.join(HERE, 'TOURS_FOR_REVIEW', 'round9', 'LOGAN_1.txt')
CHURCH9 = os.path.join(HERE, 'TOURS_FOR_REVIEW', 'round9', 'CHURCH_1.txt')


def _read(path):
    with open(path, errors='ignore') as fh:
        return fh.read()


def _slice(text, start_marker, end_marker):
    """Verbatim span from the real file: from start_marker to end_marker
    (end exclusive). Raises if either marker is absent, so a test can never
    silently assert on a passage that is not actually in the file."""
    i = text.index(start_marker)
    j = text.index(end_marker, i + len(start_marker))
    return text[i:j]


# ─── The passages, sliced verbatim from the real files ──────────────────────

def logan_orientation_passage():
    """LOGAN_1 stop-1 orientation, up to the end of the endpoints sentence."""
    text = _read(LOGAN9)
    return _slice(text, 'The tour spans from', 'mark the endpoints.') + 'mark the endpoints.'


def church_epilog_passage():
    """CHURCH_1 epilog recap (the "That's 4 stops —" tail to end of file)."""
    text = _read(CHURCH9)
    i = text.index("That's 4 stops")
    return text[i:]


def church_stop2_passage():
    """CHURCH_1 stop-2 body: the Mary Immaculate contrast, verbatim. Runs from
    the "A short distance away" contrast to the end of the Munich-import
    sentence — the whole legitimate mention of the other church."""
    text = _read(CHURCH9)
    return _slice(text, 'A short distance away in Newton Upper Falls',
                  'This stop, with its unique historical footprint')


# ─── Sanity: the slices really contain what the case is about ───────────────

def test_slices_are_the_real_passages():
    assert "St. Mary's Cathedral" in logan_orientation_passage()
    assert 'mark the endpoints' in logan_orientation_passage()
    assert 'Mary Immaculate of Lourdes' in church_epilog_passage()
    assert "That's 4 stops" in church_epilog_passage()
    stop2 = church_stop2_passage()
    assert 'Mary Immaculate of Lourdes' in stop2
    assert 'A short distance away in Newton Upper Falls' in stop2


# ─── The gate must actually gate ────────────────────────────────────────────

def test_offsite_entity_is_a_required_clean_defect():
    assert 'offsite_entity' in REQUIRED_CLEAN


# ─── POSITIVE: the two round-9 passages are flagged ─────────────────────────

def test_logan_endpoint_passage_is_flagged():
    hits = find_offsite_entities(logan_orientation_passage())
    assert hits, "St. Mary's Cathedral framed as an endpoint was not flagged"
    place = hits[0][0]
    assert "Mary" in place and "Cathedral" in place, place


def test_church_epilog_passage_is_flagged():
    hits = find_offsite_entities(church_epilog_passage())
    assert hits, "Mary Immaculate of Lourdes in the recap was not flagged"
    assert hits[0][0] == 'Mary Immaculate of Lourdes', hits[0][0]


# ─── NEGATIVE control: the SAME church, framed as elsewhere, stays clean ────

def test_church_stop2_contrast_is_clean():
    """The identical church, correctly framed 'a short distance away in Newton
    Upper Falls', carries no membership frame and MUST NOT be flagged. This is
    the crux: framing, not distance, decides."""
    stop2 = church_stop2_passage()
    assert 'Mary Immaculate of Lourdes' in stop2      # it IS mentioned
    assert find_offsite_entities(stop2) == [], \
        "the legitimate stop-2 contrast was flagged — the check is keying on the " \
        "place, not the framing"


# ─── score_tour on the real FILES: both round-9 files now gate ──────────────

@pytest.mark.parametrize('path,building', [(LOGAN9, True), (CHURCH9, False)])
def test_round9_files_report_offsite_entity(path, building):
    result = score_tour(_read(path), requested_stops=4, is_building_tour=building)
    assert 'offsite_entity' in result['defects'], path
    assert result['clean'] is False, path


# ─── The same CHURCH_1 file: one right, one wrong, in one document ──────────

def test_same_church_one_right_one_wrong_in_the_same_file():
    """The whole point, on the real file: Mary Immaculate of Lourdes appears
    twice — flagged once (epilog), not in the stop-2 contrast."""
    text = _read(CHURCH9)
    assert text.count('Mary Immaculate of Lourdes') >= 2   # stop 2 + epilog
    hits = find_offsite_entities(text)
    frames = [f for _, f in hits]
    assert any("That's 4 stops" in f for f in frames), \
        "the epilog mention was not flagged"
    assert not any('short distance away' in f for f in frames), \
        "the stop-2 contrast mention was wrongly flagged"


# ─── False-positive guards: legitimate contrast/mention stays clean ─────────

def test_bare_mention_of_a_distant_place_is_not_flagged():
    """A tour may talk about anywhere on earth; only a membership frame gates.
    'trained in Paris' / 'a refuge for Irish immigrants' are ordinary history."""
    prose = ("Step-by-Step Audio Guided Tour: Our Lady Help of Christians "
             "Catholic Church, Newton MA\n\nStop 1: Nave\n\n"
             "The founding pastor trained in Paris and the parish was a refuge "
             "for Irish immigrants. Nearby, St. Mary's Cathedral in Sydney is a "
             "famous example of the same Gothic style.")
    assert find_offsite_entities(prose) == []


def test_a_real_stop_in_the_recap_is_not_flagged():
    """The recap slot filled with an actual stop (the normal case) is clean —
    even a partial reference like 'Concourse' for 'Terminal A Main Concourse'."""
    tour = ("Step-by-Step Audio Guided Tour: Boston Logan International Airport, "
            "Boston MA\n\nStop 1: Terminal A Main Concourse\n\nStop 2: Control "
            "Tower\n\nThat's 2 stops — Terminal A Main Concourse and Control "
            "Tower. This tour covered Concourse and Control Tower.")
    assert find_offsite_entities(tour) == []


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
