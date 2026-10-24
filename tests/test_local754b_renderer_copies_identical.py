"""LEAD guard (LOCAL-754B): user-tracking/tour_html_map.py is a copy of the root
tour_html_map.py (the user-api image builds from ./user-tracking). If they ever
differ, organiser-audio tours stop looking like generated ones. Edit both."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_renderer_copies_identical():
    a = (ROOT / "tour_html_map.py").read_text()
    b = (ROOT / "user-tracking" / "tour_html_map.py").read_text()
    assert a == b, "tour_html_map.py and user-tracking/tour_html_map.py differ — update both"
