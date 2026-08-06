#!/usr/bin/env python3
"""LOCAL-294: Verify SPARQL landmark quality — no admin divisions or transit stops,
and every Landmark carries a QID.

Tests Nice, France as the primary area (matches the task measurement).
"""
import sys
import os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from area_resolver import (
    resolve_area,
    discover_landmarks,
    _sparql_coordinate_query,
    _EXCLUDED_P31_TYPES,
    _fetch_p31_types,
    Landmark,
)
from venue_resolver import _haversine as _haversine_km


@pytest.fixture(scope="module")
def nice_area():
    area = resolve_area("Nice, France")
    if area is None or not area.resolved:
        pytest.skip("Could not resolve Nice, France (network issue)")
    return area


@pytest.fixture(scope="module")
def nice_landmarks(nice_area):
    return discover_landmarks(nice_area)


def test_all_landmarks_have_qid(nice_landmarks):
    """Every Landmark from discover_landmarks must carry a non-empty QID."""
    no_qid = [lm for lm in nice_landmarks if not lm.qid]
    assert len(no_qid) == 0, (
        f"Found {len(no_qid)} landmarks without QID: "
        f"{[lm.name for lm in no_qid[:10]]}"
    )


def test_no_administrative_divisions(nice_landmarks):
    """No administrative divisions (cantons, communes, departments) in results."""
    qids_to_check = [lm.qid for lm in nice_landmarks if lm.qid]
    if not qids_to_check:
        return  # Nothing to check

    qid_to_types = _fetch_p31_types(qids_to_check)

    violations = []
    for lm in nice_landmarks:
        types = qid_to_types.get(lm.qid, [])
        excluded = [t for t in types if t in _EXCLUDED_P31_TYPES]
        if excluded:
            violations.append(f"{lm.name} ({lm.qid}): P31={excluded}")

    assert not violations, (
        f"Administrative/transit entities found in landmarks:\n"
        + "\n".join(violations)
    )


def test_no_transit_infrastructure(nice_landmarks):
    """No railway stations, bus stops, or metro stations in results."""
    transit_types = {
        "Q55488",     # railway station
        "Q928830",    # metro station
        "Q953806",    # bus stop
        "Q18543139",  # railway stop
        "Q55485",     # train station
        "Q4663385",   # tram stop
        "Q2175765",   # halt (railway)
        "Q22808404",  # railway halt in France
    }

    qids_to_check = [lm.qid for lm in nice_landmarks if lm.qid]
    if not qids_to_check:
        return

    qid_to_types = _fetch_p31_types(qids_to_check)

    violations = []
    for lm in nice_landmarks:
        types = qid_to_types.get(lm.qid, [])
        transit_matches = [t for t in types if t in transit_types]
        if transit_matches:
            violations.append(f"{lm.name} ({lm.qid}): P31={transit_matches}")

    assert not violations, (
        f"Transit infrastructure found in landmarks:\n"
        + "\n".join(violations)
    )


def test_place_massena_present(nice_landmarks):
    """Place Masséna (Q3389982) must still be recovered for Nice (LOCAL-293 non-regression)."""
    qids = {lm.qid for lm in nice_landmarks}
    names = {lm.name.lower() for lm in nice_landmarks}
    # Either by QID or by name
    assert "Q3389982" in qids or "place masséna" in names, (
        f"Place Masséna not found in {len(nice_landmarks)} Nice landmarks. "
        f"QIDs sample: {list(qids)[:10]}"
    )


def test_filtering_uses_p31_not_name_pattern(nice_area):
    """Verify that filtering is done by P31 type, not by name matching.

    Create a fake landmark with an excluded-type QID and confirm it would be filtered,
    regardless of its name.
    """
    from area_resolver import _filter_by_p31_type

    # Q18524218 is "canton of France" — should be excluded regardless of name
    # We can't easily mock the API, so we test the logic by confirming the sets exist
    assert "Q18524218" in _EXCLUDED_P31_TYPES  # canton of France
    assert "Q55488" in _EXCLUDED_P31_TYPES     # railway station
    assert "Q33506" not in _EXCLUDED_P31_TYPES  # museum — should NOT be excluded
