"""LOCAL-880: offline tests for the deterministic defect scrubs (wave-38 strings)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spoken_text_hygiene as sth


def test_defect1_contradicted_former_use_dropped_even_with_correct_fact():
    body = (
        "Stop 5: War Remnants Museum\n"
        "Coordinates: 10.779500, 106.692000\n\n"
        "The museum opened in 1975 in the building that once housed the United "
        "States Information Agency. During the Vietnam War, this building served "
        "as the US military's intelligence headquarters, anchoring the museum. "
        "Inside are themed rooms.\n"
    )
    out, n = sth.strip_contradicted_former_use(body)
    assert n == 1, (n, out)
    assert "intelligence" not in out.lower()
    # the correct, sourced fact survives
    assert "United States Information Agency" in out
    assert "Inside are themed rooms." in out


def test_defect2_truncated_tail_dropped():
    body = ("In 1876, a design competition was held, and French architect Jules "
            "Bourard won with a proposal inspired directly by the iconic. The "
            "imported bricks embody the ambitions of a bygone era.")
    out, n = sth.strip_truncated_tail_sentences(body)
    assert n == 1, (n, out)
    assert "inspired directly by the iconic." not in out
    assert "imported bricks" in out


def test_defect3_folklore_disclosed():
    body = ("Witnesses have reported a mysterious single tear shedding from a "
            "statue here. The statue remains a touchstone.")
    out, n = sth.disclose_or_drop_folklore(body)
    assert n == 1, (n, out)
    assert out.lower().startswith("a story told in 2005 claims")
    # idempotent
    out2, n2 = sth.disclose_or_drop_folklore(out)
    assert n2 == 0, out2


def test_defect4_orientation_filler_removed():
    body = ("Stop 7: City Hall\nCoordinates: 1,2\n\n"
            "Orientation: Position yourself to best view this location.\n\n"
            "You are standing before a yellow building.")
    out, n = sth.strip_orientation_filler(body)
    assert n >= 1
    assert "Position yourself to best view this location" not in out
    assert "yellow building" in out


def test_defect5_intro_grammar_fixed():
    for intro in (
        "Step-by-step audio guided tour of Ho Chi Minh City, Vietnam, is a walking tour.",
        "Step-by-step audio-guided tour of Ho Chi Minh City, Vietnam, walking tour.",
    ):
        out, n = sth.fix_intro_grammar(intro + "\n\nStop 1: X\nbody")
        assert n == 1, intro
        assert out.startswith("This is a step-by-step audio-guided walking tour of "
                              "Ho Chi Minh City, Vietnam.")
        assert "is a walking tour." not in out.split("\n")[0]


def test_defect6_orphan_closing_names_threads():
    tour = ("Stop 1: Cathedral\nbody\n\nStop 2: Opera House\nbody\n\n"
            "Each was picked by you, and together they trace your own route "
            "through the city. That's 10 stops in all.")
    out, n = sth.fix_orphan_closing(tour, ["Cathedral", "Opera House"])
    assert n == 1
    assert "Each was picked by you, and together they trace" not in out
    assert "Cathedral" in out and "Opera House" in out


def test_defect7_empty_current_affairs_note_removed():
    tour = ("Thi Bar body.\n\nIf you would like to eat nearby we can build you a "
            "restaurant tour.\n\nA note on current affairs: this tour draws on "
            "documented history, and we found no verified developments from the "
            "past five years to include here. For the very latest, check a "
            "current local news source.\n")
    out, n = sth.strip_empty_current_affairs_note(tour)
    assert n == 1, (n, out)
    assert "note on current affairs" not in out.lower()
    assert "restaurant tour" in out


def test_defect8_promo_dropped():
    for promo in (
        "You can't miss this unique multi-story complex as you explore the city.",
        "Book Street is recognized as a distinctive cultural brand of Ho Chi Minh City.",
    ):
        out, n = sth.strip_promotional_sentences("A fact here. " + promo)
        assert n == 1, (promo, out)
        assert "A fact here." in out


def test_defect9_capacity_removed_when_unsourced_kept_when_sourced():
    body = ("Stop 6: Opera House\nCoordinates: 1,2\n\n"
            "Conceived as the Opera de Saigon, it was a 500-seat venue created to "
            "bring French operatic culture to colonial Saigon.")
    out, rep = sth.audit_seating_capacity(body, evidence_text="no numbers here")
    assert rep["removed"] == "500", rep
    assert "500" not in out
    assert "venue created to bring French operatic" in out
    out2, rep2 = sth.audit_seating_capacity(
        body, evidence_text="The theatre originally had 800 seats. Also 500 seats sometimes.")
    # 500 IS in the evidence here -> kept, with the source sentence logged
    assert rep2["kept"] == "500", rep2
    assert "500" in out2


def test_defect10_opera_house_government_use_corrected():
    body = ("Stop 6: Opera House\nCoordinates: 1,2\n\n"
            "When the legislature split into two houses—the Lower House and the "
            "Senate—the Opera House was transformed into the meeting place for both.")
    out, n = sth.fix_opera_house_government_use(body)
    assert n == 1, (n, out)
    assert "meeting place for both" not in out
    assert "Lower House" in out and "1956 to 1975" in out


if __name__ == "__main__":
    import traceback
    _passed = _failed = 0
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            try:
                _fn()
                print(f"PASS {_name}")
                _passed += 1
            except Exception:
                print(f"FAIL {_name}")
                traceback.print_exc()
                _failed += 1
    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)
