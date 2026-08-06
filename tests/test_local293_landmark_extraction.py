#!/usr/bin/env python3
"""LOCAL-293: Verify that _wikipedia_landmark_extraction no longer admits
section headings as landmarks. Every Landmark returned must have:
  - A non-empty QID
  - Non-zero coordinates
  - Coordinates within the area's bounding radius (×1.5 margin)

Tests three areas: French Riviera, Nice, Cannes.

NOTE: These tests require network access to Wikipedia/Wikidata APIs.
"""
import sys
import os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from area_resolver import (
    resolve_area,
    discover_landmarks,
    _wikipedia_landmark_extraction,
    Landmark,
)
from venue_resolver import _haversine as _haversine_km


@pytest.fixture(scope="module")
def riviera_area():
    area = resolve_area("French Riviera, France")
    if area is None:
        pytest.skip("Could not resolve area (network issue)")
    return area


@pytest.fixture(scope="module")
def nice_area():
    area = resolve_area("Nice, France")
    if area is None:
        pytest.skip("Could not resolve area (network issue)")
    return area


@pytest.fixture(scope="module")
def cannes_area():
    area = resolve_area("Cannes, France")
    if area is None:
        pytest.skip("Could not resolve area (network issue)")
    return area


def test_wikipedia_extraction_all_resolved(riviera_area, nice_area, cannes_area):
    """Every Landmark from Path 3 must have QID + in-area coordinates."""
    for area in [riviera_area, nice_area, cannes_area]:
        landmarks = _wikipedia_landmark_extraction(area)
        for lm in landmarks:
            assert lm.qid, f"Landmark '{lm.name}' has no QID"
            assert lm.lat != 0.0 or lm.lng != 0.0, (
                f"Landmark '{lm.name}' ({lm.qid}) has no coordinates"
            )
            dist = _haversine_km(area.center_lat, area.center_lng, lm.lat, lm.lng)
            max_dist = area.bounding_radius_km * 1.5
            assert dist <= max_dist, (
                f"Landmark '{lm.name}' ({lm.qid}) at ({lm.lat:.4f}, {lm.lng:.4f}) "
                f"is {dist:.1f}km from center, exceeds max {max_dist:.1f}km"
            )


def test_section_headings_excluded(riviera_area):
    """Known section headings from the French Riviera article must NOT appear."""
    landmarks = _wikipedia_landmark_extraction(riviera_area)
    landmark_names = {lm.name.lower() for lm in landmarks}

    # These are known section headings from the French Riviera Wikipedia article
    known_headings = [
        "Canton of Sainte-Maxime",
        "Origin of term",
        "Main communities",
        "Tourism",
        "Ecology",
    ]
    for heading in known_headings:
        assert heading.lower() not in landmark_names, (
            f"Section heading '{heading}' was admitted as a landmark!"
        )


def test_discover_landmarks_no_qidless_coordless(nice_area):
    """discover_landmarks must not contain any Landmark without both QID and coordinates."""
    landmarks = discover_landmarks(nice_area)
    no_qid_no_coords = [lm for lm in landmarks if not lm.qid and lm.lat == 0.0 and lm.lng == 0.0]
    assert not no_qid_no_coords, (
        f"Found {len(no_qid_no_coords)} landmarks with neither QID nor coordinates: "
        f"{[lm.name for lm in no_qid_no_coords[:5]]}"
    )
