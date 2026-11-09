#!/usr/bin/env python3
"""LOCAL-882 — a LANDMARK's OWN pivotal event is not scrubbed as an off-venue
military / national-figure / unsourced-dated digression.

Wave 40: the Independence Palace stop lost "30 April 1975" because the LOCAL-855B
scrub dropped "On 30 April 1975 a tank crashed through the gates of the
Independence Palace" as an "off-venue military-history digression". That filter is
right for a bar/spa/street, but the Fall of Saigon AT the Independence Palace is
the stop's defining content. The fix: for a landmark/monument/historical-site
stop, a sentence that NAMES the venue is its own event and is kept; a bar/street
keeps the full protection, and a war sentence that does not name the venue is
still dropped. Fully offline.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_stop_narration as usn  # noqa: E402

LOC = "Ho Chi Minh City, Vietnam"
PALACE = {"name": "Independence Palace", "type_specialty": "Historic Landmark",
          "user_explicit": True}
BAR = {"name": "Thi Bar", "type_specialty": "Gay bar", "user_explicit": True}


def test_landmark_keeps_its_own_fall_of_saigon_tank_event():
    txt = ("Approaching the Independence Palace, you cross a wide forecourt. "
           "On 30 April 1975, a North Vietnamese tank crashed through the gates of "
           "the Independence Palace, marking the Fall of Saigon and the end of the "
           "war. The palace is open to the public today.")
    s, _ = usn.scrub_user_stop_body(txt, PALACE, LOC)
    assert "tank crashed through the gates" in s
    assert "30 April 1975" in s
    assert "Fall of Saigon" in s


def test_landmark_national_figure_event_kept_when_it_names_the_venue():
    # A national-figure sentence that is the venue's own event (names the venue)
    # survives the national-figure always-drop tier. (The admin-geography tier is
    # separate and still removes a "ordered the construction" phrasing; the point
    # here is that national_figure alone no longer drops a landmark's own event.)
    txt = ("The Independence Palace is a landmark. President Ngô Đình Diệm lived "
           "in the Independence Palace until the 1963 coup. The gardens are quiet.")
    s, _ = usn.scrub_user_stop_body(txt, PALACE, LOC)
    assert "Ngô Đình Diệm" in s and "Independence Palace" in s


def test_bar_still_drops_off_venue_war_digression():
    txt = ("Thi Bar is lively. In early 1975, an attack was launched on the Central "
           "Highlands, capturing Buôn Ma Thuột on March 18. The cocktails are great.")
    s, d = usn.scrub_user_stop_body(txt, BAR, LOC)
    assert d
    assert "Buôn Ma Thu" not in s
    assert "cocktails" in s


def test_landmark_still_drops_a_war_sentence_that_does_not_name_it():
    # A landmark is not a free pass for ANY war sentence — only its OWN named event.
    txt = ("The Independence Palace is a landmark. In early 1975, an attack was "
           "launched on the Central Highlands, capturing Buôn Ma Thuột. The gardens "
           "are quiet today.")
    s, d = usn.scrub_user_stop_body(txt, PALACE, LOC)
    assert "Buôn Ma Thu" not in s                 # off-venue war, no venue name → dropped
    assert "gardens are quiet" in s


if __name__ == "__main__":
    _p = _f = 0
    for _n, _fn in sorted(globals().items()):
        if _n.startswith("test_") and callable(_fn):
            try:
                _fn()
                print(f"PASS {_n}")
                _p += 1
            except Exception as e:
                import traceback
                print(f"FAIL {_n}: {e}")
                traceback.print_exc()
                _f += 1
    print(f"\n{_p} passed, {_f} failed")
    sys.exit(1 if _f else 0)
