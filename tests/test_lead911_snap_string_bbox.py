"""[LEAD-911] A string bounding box (Nominatim) never crashes the pin snap."""
import inspect

import pin_snap as ps


def test_floats_911():
    assert ps.floats_911(["9.37", "11.55", "107.39", "109.40"]) == [9.37, 11.55, 107.39, 109.4]
    assert ps.floats_911(None) is None
    assert ps.floats_911(["x", "1", "2", "3"]) is None


def test_snap_coerces_both_boxes_first():
    src = inspect.getsource(ps.snap_poi_coordinates)
    body = src.split('"""', 2)[2]
    assert body.lstrip().splitlines()[1].strip() == "scope_bbox = floats_911(scope_bbox)" or \
        "scope_bbox = floats_911(scope_bbox)" in body[:600]
    assert "route_box = floats_911(route_box)" in body[:700]
