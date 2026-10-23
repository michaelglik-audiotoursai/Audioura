"""LOCAL-749: the toured place must never be the work/theme segment of the request.

Michael, 2026-10-23: "Salem TV series filming locations, Shreveport, Louisiana" opened with
"...filmed in Shreveport, Louisiana, not in Salem TV series filming locations..." -- the
first comma segment (the theme) was taken as the city.
"""
from screen_work_tour import _toured_place_label, build_filming_disclosure

SRC = {"filmed_place": "Shreveport, Louisiana", "source": "Salem (TV series) - Wikipedia",
       "work_name": "Salem"}
WORK = {"title": "Salem", "kind": "TV series", "theme_type": "TV"}


def test_theme_segment_is_not_the_place():
    assert _toured_place_label("Salem TV series filming locations, Shreveport, Louisiana") == "Shreveport"


def test_salem_requests_still_salem():
    assert _toured_place_label("the episode 1 of season 1 biking tour, Salem, MA") == "Salem"
    assert _toured_place_label(
        "Biking tour of real locations mentioned in Salem TV show episode 2 of season 1, Salem MA") == "Salem"


def test_shreveport_request_reads_as_filmed_here():
    text = build_filming_disclosure(WORK, "Salem TV series filming locations, Shreveport, Louisiana",
                                    lookup_fn=lambda w, l: SRC)
    assert "not in" not in text
    assert "filming locations," not in text
    assert "were filmed in Shreveport" in text
