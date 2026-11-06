"""LOCAL-872C -- Wikipedia evidence reaches the narrator; a claim that CONTRADICTS the
evidence is dropped/corrected (never disclosed); a stop is never empty."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import landmark_claim_gate as lg  # noqa: E402
import landmark_wikipedia_evidence as lw  # noqa: E402

LOC = "Ho Chi Minh City, Vietnam"
PALACE = ("Independence Palace - Wikipedia (en). The Independence Palace is a landmark in Ho Chi "
          "Minh City. It was designed by Ngô Viết Thụ and built from 1962 to 1966.\n"
          "Infobox: architect: Ngô Viết Thụ; years built: 1962–1966; completion date: 31 October 1966")
OPERA = ("Saigon Opera House - Wikipedia (en). The Saigon Opera House is a 800-seat theatre. It was "
         "designed by the French architects Félix Olivier, Ernest Guichard and Eugène Ferret and "
         "opened in 1900.\nInfobox: architect: Félix Olivier, Ernest Guichard, Eugène Ferret; opened: 1900")
NOTRE = ("Notre-Dame Cathedral Basilica of Saigon - Wikipedia (en). The cathedral was built "
         "between 1863 and 1880.\nInfobox: years built: 1863-1880")


def test_narrator_block_carries_facts_and_instruction():
    b = lw.narrator_block("Saigon Opera House", [OPERA])
    assert "Olivier" in b and "Guichard" in b and "1900" in b
    assert "PRIMARY SOURCE" in b and "EXACTLY" in b
    assert lw.narrator_block("x", []) == ""


def test_authority_years_expand_ranges_and_architects():
    a = lw.authority([PALACE])
    assert {"1962", "1966"} <= a["years"] and "1885" not in a["years"]
    assert a["architects"] == ["Ngô Viết Thụ"]


def test_built_1885_is_dropped_and_corrected_not_disclosed():
    body = "Orientation: Stand at the gate. The palace was built in 1885 by a French engineer. It has a rooftop."
    new, removed = lg.filter_stop_body(body, [PALACE], "Independence Palace", location=LOC,
                                       authority_items=[PALACE])
    assert "1885" not in new and "sometimes said" not in new
    assert "1962" in new and "Ngô Viết Thụ" in new
    assert any(r["kind"] == "contradiction" for r in removed)


def test_wrong_architect_is_replaced_by_evidence_architect():
    body = "The opera house was designed by Pierre Martin in 1900. It is lovely."
    new, removed = lg.filter_stop_body(body, [OPERA], "Saigon Opera House", location=LOC,
                                       authority_items=[OPERA])
    assert "Martin" not in new and "Ferret" in new and "sometimes said" not in new


def test_unrelated_plausible_claim_is_still_disclosed():
    body = "The palace was renovated in 1990 to receive guests."
    new, _ = lg.filter_stop_body(body, [PALACE], "Independence Palace", location=LOC,
                                 authority_items=[PALACE])
    assert "sometimes said" in new and "1990" in new


def test_without_authority_behaviour_is_unchanged():
    body = "The palace was built in 1885."
    new, _ = lg.filter_stop_body(body, ["The palace is a landmark."], "Independence Palace",
                                 location=LOC)
    assert "sometimes said" in new


def _tour(pier_body):
    return ("Stop 1: Independence Palace\nIt was built in 1885 by someone.\n\n"
            f"Stop 2: Bạch Đằng Pier\n{pier_body}\n")


def test_empty_stop_gets_evidence_short_form():
    t = "Stop 1: Saigon Opera House\n\nStop 2: Independence Palace\nIt is a palace of note here.\n"
    out, rep = lg.filter_tour_text(t, stop_titles={1: "Saigon Opera House", 2: "Independence Palace"},
                                   stop_evidence={1: [OPERA]}, stop_authority={1: [OPERA]}, location=LOC)
    assert "1900" in out.split("Stop 2")[0] and rep["filled"][0]["source"] == "wikipedia"


def test_bach_dang_pier_all_dropped_gets_grounded_body_not_empty():
    t = ("Stop 1: Bạch Đằng Pier\nThe pier hosted the Miss Saigon gala in 1999.\n\n"
         "Stop 2: Other Place\nThe place is a long-standing landmark of the old quarter.\n")
    out, rep = lg.filter_tour_text(t, stop_titles={1: "Bạch Đằng Pier", 2: "Other Place"},
                                   stop_fallback={1: "Bạch Đằng Pier is a pier on the river. Look at the water."},
                                   location=LOC)
    first = out.split("Stop 2")[0]
    assert "Miss Saigon" not in first and "pier on the river" in first
    assert rep["filled"][0]["source"] == "grounded"


def test_empty_stop_without_any_source_gets_minimal_body():
    t = "Stop 1: Bạch Đằng Pier\n\nStop 2: Other\nA fine place by the river bank today.\n"
    out, rep = lg.filter_tour_text(t, stop_titles={1: "Bạch Đằng Pier", 2: "Other"}, location=LOC)
    assert "Bạch Đằng Pier is one of the stops" in out


def test_notre_dame_range_corrected_to_evidence_range():
    body = "The cathedral was constructed between 1877 and 1880 under French administrators."
    new, removed = lg.filter_stop_body(body, [NOTRE, "built 1877 and 1880 per a snippet"],
                                       "Notre-Dame Cathedral Basilica of Saigon", location=LOC,
                                       authority_items=[NOTRE])
    assert "between 1863 and 1880" in new and "1877" not in new
    assert removed and removed[0]["kind"] == "contradiction"


def test_narrator_block_has_key_facts_line():
    assert "KEY FACTS YOU MUST STATE" in lw.narrator_block("Notre-Dame", [NOTRE])
    assert "1863-1880" in lw.narrator_block("Notre-Dame", [NOTRE])


def test_missing_establishment_year_is_added_once():
    ND = ("Notre-Dame - Wikipedia (en). The cathedral was constructed between 1877 and 1880.\n"
          "Infobox: established: 1863; completed: 1880")
    body = "The cathedral was completed in 1880. Two towers rise 58 metres."
    new, _ = lg.filter_stop_body(body, [ND], "Notre-Dame", location=LOC, authority_items=[ND])
    assert "1863" in new and new.count("1863") == 1
    again, _ = lg.filter_stop_body(new, [ND], "Notre-Dame", location=LOC, authority_items=[ND])
    assert again == new   # idempotent


def test_added_date_never_lands_in_directions_line():
    ND = "X - Wikipedia (en). A museum.\nInfobox: established: 1975"
    body = "\nA museum of the war years.\n\nDirections: Walk north. Enjoy the stroll!\n"
    new, _ = lg.filter_stop_body(body, [ND], "X", location=LOC, authority_items=[ND])
    assert "years. According to Wikipedia, it was established in 1975." in new
    assert "stroll! According" not in new


PIER_LIVE = ("Stop 9: Bạch Đằng Pier\n\nCoordinates: 10.775240, 106.707002\n\n"
             "Orientation: Bạch Đằng Pier is one of the places you chose, here in Ho Chi Minh City.\n\n"
             "Directions: Head southwest for about 1.7 kilometers, and you'll arrive at Thi Bar Saigon. "
             "Enjoy the stroll!\n\nStop 10: Thi Bar Saigon\nThi Bar is a bar with live music every night.\n")


def test_bach_dang_pier_live_shape_orientation_only_is_filled_before_directions():
    fb = ("Bạch Đằng Pier is a waterfront in Ho Chi Minh City. It is known for river views, boat "
          "tours, and sunset vistas. Take a moment at the entrance to get your bearings before you go in.")
    out, filled = lg.fill_empty_stops(PIER_LIVE, {1: "Bạch Đằng Pier", 2: "Thi Bar Saigon"},
                                      {}, {1: fb}, LOC)
    pier = out.split("Stop 10")[0]
    assert filled and filled[0]["source"] == "grounded"
    assert pier.index("boat tours") < pier.index("Directions:")
    assert lg.fill_empty_stops(out, {1: "Bạch Đằng Pier"}, {}, {1: fb}, LOC)[0] == out  # idempotent
