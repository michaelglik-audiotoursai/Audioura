"""LOCAL-866: structural stop lines survive a retry; distances are not heights."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scorer_retry as sr
import stop_headers as sh
import tour_quality as tq

POIS = [
    {'stop_number': 1, 'name': 'Rambutan', 'coordinates': '10.767200, 106.693000',
     'type_specialty': 'Bar', 'address': '1 Test St'},
    {'stop_number': 2, 'name': 'Acoustic Bar', 'coordinates': '10.781195, 106.689920',
     'type_specialty': 'Live music bar'},
]

TOUR = (
    "Step-by-Step Audio Guided Tour: Ho Chi Minh City, Vietnam - Cycling Tour\n\n"
    "Stop 1: Rambutan\n\nAddress: 1 Test St\n\nCoordinates: 10.767200, 106.693000\n\n"
    "Type/Specialty: Bar\n\nOrientation: Rambutan is a bar.\n\nIt is roughly 100 meters away.\n\n"
    "Directions: Cycle north for about 1000 meters, and you'll reach Acoustic Bar.\n\n"
    "Stop 2: Acoustic Bar\n\nCoordinates: 10.781195, 106.689920\n\n"
    "Type/Specialty: Live music bar\n\nOrientation: Acoustic Bar is a live music bar.\n\n"
    "A long original story about the bar goes here.\n\nThat's 2 stops in all.\n"
)


def _coord_line(text, stop):
    blk = text.split(f'Stop {stop}:')[1].split('Stop ')[0]
    return [ln for ln in blk.split('\n') if ln.startswith('Coordinates:')]


def test_distance_pair_is_not_a_height_contradiction():
    assert tq._find_self_contradictions(TOUR) == []


def test_real_height_conflict_still_detected():
    t = 'The tower is 100 meters tall. Later: the tower is 300 meters tall.'
    assert tq._find_self_contradictions(t)


def test_retry_that_drops_headers_keeps_coordinates_equal_to_poi():
    # force a REQUIRED_CLEAN defect via a stubbed scorer so a retry runs
    calls = {'n': 0}
    real = tq.score_tour

    def fake_score(text, *a, **k):
        r = real(text, *a, **k)
        calls['n'] += 1
        if calls['n'] == 1:
            r = dict(r)
            r['defects'] = dict(r['defects'])
            r['defects']['self_contradiction'] = '1 contradiction(s): "A long original story about the bar goes here."'
        return r

    def regen(target, full):
        # the LLM rewrite: short prose, NO header lines at all
        return "Stop 2: Acoustic Bar\n\nOrientation: Short.\n\nThat's 2 stops in all.", \
            {'total_cost': 0.0, 'total_tokens': 0}

    tq.score_tour = fake_score
    try:
        res = sr.score_and_retry(
            TOUR, requested_stops=2, regenerate_section=regen, log=lambda m: None,
            repair_text=lambda t: sh.restore_stop_headers(t, POIS))
    finally:
        tq.score_tour = real
    assert res['retried']
    assert _coord_line(res['text'], 2) == ['Coordinates: 10.781195, 106.689920']
    assert 'Type/Specialty: Live music bar' in res['text']
    # without the repair the line is gone (guards the test itself)
    assert _coord_line(sr.apply_regenerated_section(
        TOUR, (TOUR.index('Stop 2:'), len(TOUR)), regen(None, None)[0]), 2) == []


def test_wrong_coordinate_is_replaced_and_clean_text_is_unchanged():
    assert sh.restore_stop_headers(TOUR, POIS) == TOUR
    bad = TOUR.replace('10.781195, 106.689920', '1.0, 2.0')
    assert _coord_line(sh.restore_stop_headers(bad, POIS), 2) == \
        ['Coordinates: 10.781195, 106.689920']


def test_every_stop_restored_in_order_after_title():
    stripped = ("Stop 1: Rambutan\n\nOrientation: x.\n\nStop 2: Acoustic Bar\n\nOrientation: y.\n")
    out = sh.restore_stop_headers(stripped, POIS)
    assert out.index('Address: 1 Test St') < out.index('Coordinates: 10.767200') \
        < out.index('Type/Specialty: Bar') < out.index('Orientation: x.')
    assert 'Coordinates: 10.781195, 106.689920' in out


def test_user_pin_address_stub_is_not_reintroduced():
    pois = [{'stop_number': 1, 'name': 'Rambutan', 'address': '15 Đ.',
             'coord_source': 'user_share_link', 'coordinates': '1.000000, 2.000000'}]
    out = sh.restore_stop_headers("Stop 1: Rambutan\n\nOrientation: x.\n", pois,
                                  clean_address=lambda a: '')
    assert 'Address:' not in out and 'Coordinates: 1.000000, 2.000000' in out
