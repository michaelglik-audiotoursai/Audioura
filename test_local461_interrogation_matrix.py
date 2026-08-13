#!/usr/bin/env python3
"""test_local461_interrogation_matrix.py — acceptance tests for LOCAL-461.

Tests the interrogation matrix against the 9 stops swept in D433:
- TOUR_MFA_20260812_2030.txt (museum exhibition) — stops 1, 2, 3
- fruitlands_museum_tour.txt (museum, no exhibition scope) — stops 1, 2, 3
- Beacon_Hill__Boston_walking_tour_20260714_135649.txt (walking tour) — stops 1, 2, 3

Assertions verify values and statuses extracted AT RUNTIME, never constants
copied from the task spec.
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from interrogation_matrix import (
    build_matrix, extract_stops, extract_tour_header, infer_tour_type, SLOTS
)
from story_opportunity_scan import measure


def load_tour(filename):
    path = os.path.join(HERE, filename)
    return open(path, encoding='utf-8').read()


def get_matrix(filename, stop_num, tour_type=''):
    """Load a tour and build the matrix for a specific stop."""
    full_text = load_tour(filename)
    stops = extract_stops(full_text)
    assert stop_num in stops, f"Stop {stop_num} not found in {filename}"
    if not tour_type:
        tour_type = infer_tour_type(
            extract_tour_header(full_text), stops[stop_num]['text'])
    return build_matrix(
        stop_text=stops[stop_num]['text'],
        tour_type=tour_type,
        tour_context=full_text,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MFA EXHIBITION TOUR — stops 1, 2, 3
# ═══════════════════════════════════════════════════════════════════════════════

MFA_FILE = 'TOUR_MFA_20260812_2030.txt'


def test_mfa_stop2_canonical_title():
    """MFA stop 2: canonical_title = Moses and Monotheism."""
    m = get_matrix(MFA_FILE, 2)
    assert m['canonical_title']['value'] == 'Moses and Monotheism', \
        f"Expected 'Moses and Monotheism', got {m['canonical_title']['value']!r}"
    assert m['canonical_title']['status'] == 'STRUCTURAL'
    assert m['canonical_title']['rung'] == 'exhibit'


def test_mfa_stop2_english_title():
    """MFA stop 2: english_title = Moses and Monotheism (already English)."""
    m = get_matrix(MFA_FILE, 2)
    assert m['english_title']['value'] == 'Moses and Monotheism'
    assert m['english_title']['status'] == 'STRUCTURAL'


def test_mfa_stop2_medium_is_exhibition():
    """MFA stop 2: medium = the exhibition name."""
    m = get_matrix(MFA_FILE, 2)
    assert 'Unbound' in m['medium']['value'], \
        f"Expected exhibition name containing 'Unbound', got {m['medium']['value']!r}"
    assert m['medium']['status'] == 'STRUCTURAL'


def test_mfa_stop2_venue():
    """MFA stop 2: venue = Museum of Fine Arts, Boston."""
    m = get_matrix(MFA_FILE, 2)
    assert 'Museum of Fine Arts' in m['venue']['value'] or 'MFA' in m['venue']['value'], \
        f"Expected MFA venue, got {m['venue']['value']!r}"
    assert m['venue']['status'] == 'STRUCTURAL'


def test_mfa_stop2_artist_is_claimed():
    """MFA stop 2: artist is CLAIMED (not GROUNDED or STRUCTURAL)."""
    m = get_matrix(MFA_FILE, 2)
    assert m['artist']['status'] == 'CLAIMED', \
        f"artist should be CLAIMED, got {m['artist']['status']}"
    assert 'Dalí' in m['artist']['value'] or 'Dali' in m['artist']['value'], \
        f"Expected Dalí as artist, got {m['artist']['value']!r}"


def test_mfa_stop2_publisher_is_claimed():
    """MFA stop 2: publisher = The Hogarth Press AND is CLAIMED (it's false!)."""
    m = get_matrix(MFA_FILE, 2)
    assert m['publisher']['status'] == 'CLAIMED', \
        f"publisher should be CLAIMED, got {m['publisher']['status']}"
    assert 'Hogarth' in m['publisher']['value'], \
        f"Expected 'The Hogarth Press' as publisher, got {m['publisher']['value']!r}"


def test_mfa_stop2_credit_line_not_developed():
    """MFA stop 2: credit_line is a real handle, never DEVELOPED."""
    m = get_matrix(MFA_FILE, 2)
    cl = m['credit_line']
    assert cl['status'] != 'ABSENT', "credit_line should not be ABSENT for MFA stop 2"
    # Verify it's actually a handle from story_opportunity_scan
    full_text = load_tour(MFA_FILE)
    stops = extract_stops(full_text)
    scan = measure(stops[2]['text'])
    handle_surfaces = [h['surface'] for h in scan['handles']]
    assert cl['value'] in handle_surfaces, \
        f"credit_line {cl['value']!r} not in scan handles"
    # Verify it's not DEVELOPED
    for h in scan['handles']:
        if h['surface'] == cl['value']:
            assert h['state'] != 'DEVELOPED', \
                f"credit_line handle must not be DEVELOPED, got {h['state']}"
            break


def test_mfa_stop1_gloss():
    """MFA stop 1: Le Lézard has a parenthetical English gloss."""
    m = get_matrix(MFA_FILE, 1)
    assert "Lézard" in m['canonical_title']['value'] or "Lizard" in m['canonical_title']['value']
    assert 'Lizard' in m['english_title']['value'] or 'Feathers' in m['english_title']['value']
    assert m['english_title']['status'] == 'STRUCTURAL'


def test_mfa_stop3_french_title_no_english():
    """MFA stop 3: Au Soleil du Plafond has no English translation available."""
    m = get_matrix(MFA_FILE, 3)
    assert 'Au Soleil' in m['canonical_title']['value']
    # english_title should be ABSENT (can't translate without network)
    assert m['english_title']['status'] == 'ABSENT', \
        f"French title without gloss should have english_title=ABSENT, got {m['english_title']['status']}"


# ═══════════════════════════════════════════════════════════════════════════════
# FRUITLANDS MUSEUM TOUR — stops 1, 2, 3 (no exhibition scope)
# ═══════════════════════════════════════════════════════════════════════════════

FRUITLANDS_FILE = 'fruitlands_museum_tour.txt'


def test_fruitlands_medium_absent():
    """Fruitlands: no exhibition is named, so medium is ABSENT."""
    for stop_num in (1, 2, 3):
        m = get_matrix(FRUITLANDS_FILE, stop_num, tour_type='museum')
        assert m['medium']['status'] == 'ABSENT', \
            f"Fruitlands stop {stop_num}: medium should be ABSENT, got {m['medium']['status']}"


def test_fruitlands_canonical_title_at_exhibit():
    """Fruitlands: canonical_title resolves at the exhibit rung."""
    for stop_num in (1, 2, 3):
        m = get_matrix(FRUITLANDS_FILE, stop_num, tour_type='museum')
        assert m['canonical_title']['rung'] == 'exhibit', \
            f"Fruitlands stop {stop_num}: rung should be 'exhibit', got {m['canonical_title']['rung']!r}"
        assert m['canonical_title']['value'], \
            f"Fruitlands stop {stop_num}: canonical_title should not be empty"


def test_fruitlands_artist_claimed():
    """Fruitlands: artist is filled and CLAIMED."""
    for stop_num in (1, 2, 3):
        m = get_matrix(FRUITLANDS_FILE, stop_num, tour_type='museum')
        assert m['artist']['value'], \
            f"Fruitlands stop {stop_num}: artist should be populated"
        assert m['artist']['status'] == 'CLAIMED', \
            f"Fruitlands stop {stop_num}: artist should be CLAIMED, got {m['artist']['status']}"


def test_fruitlands_generalises_without_exhibition():
    """A matrix that only works when an exhibition exists has not generalised."""
    m = get_matrix(FRUITLANDS_FILE, 1, tour_type='museum')
    # Medium is absent but canonical_title still resolves
    assert m['medium']['status'] == 'ABSENT'
    assert m['canonical_title']['status'] == 'STRUCTURAL'
    assert m['canonical_title']['rung'] == 'exhibit'


# ═══════════════════════════════════════════════════════════════════════════════
# BEACON HILL WALKING TOUR — stops 1, 2, 3
# ═══════════════════════════════════════════════════════════════════════════════

BEACON_FILE = 'Beacon_Hill__Boston_walking_tour_20260714_135649.txt'


def test_beacon_canonical_title_is_place():
    """Beacon Hill: canonical_title is the place (the stop name)."""
    m = get_matrix(BEACON_FILE, 1)
    assert 'State House' in m['canonical_title']['value'] or \
           'Massachusetts' in m['canonical_title']['value'], \
        f"Expected a place name, got {m['canonical_title']['value']!r}"
    assert m['canonical_title']['rung'] == 'exhibit'


def test_beacon_artist_is_person_in_charge():
    """Beacon Hill: artist = whoever is in charge."""
    m = get_matrix(BEACON_FILE, 1)
    # For Massachusetts State House, the architect is Charles Bulfinch
    assert m['artist']['value'], "artist should be populated for walking tour"
    assert m['artist']['status'] == 'CLAIMED'


def test_beacon_venue_is_city():
    """Beacon Hill: venue = the city."""
    for stop_num in (1, 2, 3):
        m = get_matrix(BEACON_FILE, stop_num)
        assert 'Boston' in m['venue']['value'] or 'Beacon Hill' in m['venue']['value'], \
            f"Beacon Hill stop {stop_num}: venue should be city, got {m['venue']['value']!r}"
        assert m['venue']['status'] == 'STRUCTURAL'


def test_beacon_printed_by_absent():
    """Beacon Hill: printed_by is ABSENT on a walking tour — do not invent a filler."""
    for stop_num in (1, 2, 3):
        m = get_matrix(BEACON_FILE, stop_num)
        assert m['printed_by']['status'] == 'ABSENT', \
            f"Beacon Hill stop {stop_num}: printed_by should be ABSENT, got {m['printed_by']['status']}"


# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-TOUR ASSERTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def test_credit_line_never_developed_all_stops():
    """credit_line is never a DEVELOPED handle across ALL 9 stops."""
    tours = [
        (MFA_FILE, 'museum_exhibition', [1, 2, 3]),
        (FRUITLANDS_FILE, 'museum', [1, 2, 3]),
        (BEACON_FILE, 'walking', [1, 2, 3]),
    ]
    for filename, tour_type, stop_nums in tours:
        full_text = load_tour(filename)
        stops = extract_stops(full_text)
        for stop_num in stop_nums:
            m = build_matrix(stops[stop_num]['text'], tour_type=tour_type,
                             tour_context=full_text)
            cl = m['credit_line']
            if cl['status'] == 'ABSENT':
                continue  # ABSENT is fine
            # Verify it's a real handle and NOT DEVELOPED
            scan = measure(stops[stop_num]['text'])
            found = False
            for h in scan['handles']:
                if h['surface'] == cl['value']:
                    found = True
                    assert h['state'] != 'DEVELOPED', \
                        f"{filename} stop {stop_num}: credit_line {cl['value']!r} is DEVELOPED"
                    break
            assert found, \
                f"{filename} stop {stop_num}: credit_line {cl['value']!r} not in scan handles"


def test_all_slots_have_provenance():
    """Every slot is {value, status, source, rung} with valid status."""
    tours = [
        (MFA_FILE, 'museum_exhibition', [1, 2, 3]),
        (FRUITLANDS_FILE, 'museum', [1, 2, 3]),
        (BEACON_FILE, 'walking', [1, 2, 3]),
    ]
    valid_statuses = {'STRUCTURAL', 'CLAIMED', 'DERIVED', 'ABSENT'}
    for filename, tour_type, stop_nums in tours:
        full_text = load_tour(filename)
        stops = extract_stops(full_text)
        for stop_num in stop_nums:
            m = build_matrix(stops[stop_num]['text'], tour_type=tour_type,
                             tour_context=full_text)
            for slot in SLOTS:
                assert slot in m, f"{filename} stop {stop_num}: missing slot {slot}"
                cell = m[slot]
                assert 'value' in cell, f"slot {slot} missing 'value'"
                assert 'status' in cell, f"slot {slot} missing 'status'"
                assert 'source' in cell, f"slot {slot} missing 'source'"
                assert 'rung' in cell, f"slot {slot} missing 'rung'"
                assert cell['status'] in valid_statuses, \
                    f"slot {slot} has invalid status {cell['status']!r}"


def test_build_matrix_callable_plain_string():
    """build_matrix must be callable at module scope with a plain string."""
    # Simplest possible call — just a string
    result = build_matrix("Stop 1: Test stop\n\nThis is a test stop about nothing.")
    assert isinstance(result, dict)
    for slot in SLOTS:
        assert slot in result


def test_no_network_no_key():
    """build_matrix is offline and deterministic — calling it twice gives same result."""
    full_text = load_tour(MFA_FILE)
    stops = extract_stops(full_text)
    m1 = build_matrix(stops[2]['text'], tour_type='museum_exhibition',
                      tour_context=full_text)
    m2 = build_matrix(stops[2]['text'], tour_type='museum_exhibition',
                      tour_context=full_text)
    assert m1 == m2, "build_matrix must be deterministic"


# ═══════════════════════════════════════════════════════════════════════════════
# COVERAGE TABLE
# ═══════════════════════════════════════════════════════════════════════════════

def print_coverage_table():
    """Print the coverage table over all 9 stops (not an assertion, for reporting)."""
    tours = [
        (MFA_FILE, 'museum_exhibition', [1, 2, 3]),
        (FRUITLANDS_FILE, 'museum', [1, 2, 3]),
        (BEACON_FILE, 'walking', [1, 2, 3]),
    ]
    print(f"\n{'=' * 90}")
    print("COVERAGE TABLE — ALL 9 STOPS")
    print(f"{'=' * 90}\n")
    header = f"  {'tour':45} {'stop':>4}  "
    for slot in SLOTS:
        header += f"{slot[:7]:>8}"
    print(header)
    print(f"  {'-' * 85}")

    by_type = {}
    for filename, tour_type, stop_nums in tours:
        full_text = load_tour(filename)
        stops = extract_stops(full_text)
        for stop_num in stop_nums:
            m = build_matrix(stops[stop_num]['text'], tour_type=tour_type,
                             tour_context=full_text)
            row = f"  {filename[:44]:45} {stop_num:>4}  "
            absent_count = 0
            for slot in SLOTS:
                cell = m[slot]
                st = cell['status'][0]  # S, C, D, A
                row += f"{'':>4}{st:>4}"
                if cell['status'] == 'ABSENT':
                    absent_count += 1
            print(row)
            by_type.setdefault(tour_type, []).append(absent_count)

    print(f"\n  {'-' * 85}")
    print(f"\n  ABSENT counts by tour type:")
    for t, counts in sorted(by_type.items()):
        avg = sum(counts) / len(counts)
        print(f"    {t:30} avg={avg:.1f}  per-stop: {counts}")
    print(f"\n{'=' * 90}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")

    print(f"\n{'=' * 60}")
    print(f"  {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'=' * 60}")

    # Print coverage table for reporting
    print_coverage_table()

    sys.exit(1 if failed else 0)
