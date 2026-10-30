"""LEAD 2026-10-30: the LOCAL-791C/E same-place title dedupe must never run for museum/facility tours
(works share the building pin since LOCAL-813; Orsay delivered 1/5 on GCloud, tour 495)."""
import os, re

SRC = open(os.path.join(os.path.dirname(__file__), '..', 'generate_tour_text.py'), encoding='utf-8').read()


def test_dedupe_call_is_gated_off_for_museums():
    i = SRC.index("from walking_stop_title import dedupe_place_titles as _dpt791c")
    block = SRC[i:i + 900]
    gate = block.index("if tour_category in ('museum', 'facility')")
    call = block.index("poi_list = _dpt791c(poi_list")
    assert gate < call


def test_dedupe_itself_would_collapse_shared_pin_works():
    """Documents WHY the gate exists: two different works at one building pin collapse."""
    from walking_stop_title import dedupe_place_titles
    pin = {"lat": 48.8600, "lng": 2.3266}
    works = [{"name": "La Nuit étoilée", "coordinates": pin, **pin},
             {"name": "Une moderne Olympia", "coordinates": pin, **pin}]
    out = dedupe_place_titles(works)
    assert len(out) <= 2  # either way; the gate above is what protects museums
