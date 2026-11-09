"""LOCAL-880B: offline tests for the GENERIC, evidence-driven defect scrubs.

LOCAL-880 hard-coded four answers to one proof tour (tour 547, Saigon):
  * fix_opera_house_government_use — a fixed Saigon sentence on any "opera" stop;
  * the §9 capacity scrub keyed on an "opera" header;
  * strip_contradicted_former_use — a keyword list of "intelligence HQ/agency";
  * a dated "2005 Saigon statue-tear" disclosure.

LOCAL-880B removes the first, and makes the other three driven only by the stop's
own evidence, with no venue / city / date / claim from any single tour. These
tests prove the mechanisms generalise and that nothing Saigon-specific leaks."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spoken_text_hygiene as sth


# ── §1 scrub removed entirely ────────────────────────────────────────────────
def test_opera_house_government_use_scrub_is_gone():
    assert not hasattr(sth, "fix_opera_house_government_use")
    assert "fix_opera_house_government_use" not in sth.__all__


def test_sydney_opera_parliament_gets_no_saigon_sentence():
    # A Sydney Opera House stop that mentions a parliament/house history: the old
    # scrub would have injected "From 1956 to 1975 … Lower House of South Vietnam's
    # National Assembly." Nothing Saigon-specific may appear now.
    body = (
        "Stop 1: Sydney Opera House\n"
        "Coordinates: -33.8568, 151.2153\n\n"
        "When the New South Wales legislature split into two houses, the chamber "
        "served as the meeting place for both for a brief period after 1856.\n"
    )
    # the only defect scrubs that touch an opera stop now are the generic ones;
    # run the whole pipeline-order set and confirm no Saigon injection.
    out = body
    out, _ = sth.strip_contradicted_former_use(out, stop_evidence={})
    out, _ = sth.audit_seating_capacity(out, stop_evidence={})
    out, _ = sth.disclose_or_drop_folklore(out, evidence_text="")
    assert "Lower House" not in out
    assert "South Vietnam" not in out
    assert "National Assembly" not in out
    assert "1956 to 1975" not in out
    # the original sentence is untouched (no evidence contradicts it)
    assert "meeting place for both" in out


# ── §1 former-use: evidence-driven, no keyword list ──────────────────────────
def test_former_use_kept_when_evidence_supports_it_cia():
    # CIA HQ: the body's former/current use IS what the evidence names — keep it.
    body = (
        "Stop 2: CIA Headquarters\n"
        "Coordinates: 38.9517, -77.1467\n\n"
        "This building has served as the headquarters of the Central Intelligence "
        "Agency since 1961. Tours are not open to the public.\n"
    )
    ev = {"CIA Headquarters": [
        "The George Bush Center for Intelligence is the headquarters of the "
        "Central Intelligence Agency, located in Langley, Virginia."]}
    out, n = sth.strip_contradicted_former_use(body, stop_evidence=ev)
    assert n == 0, (n, out)
    assert "Central Intelligence Agency" in out
    assert "headquarters" in out.lower()


def test_former_use_kept_mi6_vauxhall():
    body = (
        "Stop 1: Vauxhall Cross\n"
        "Coordinates: 51.4875, -0.1246\n\n"
        "The building serves as the headquarters of the Secret Intelligence "
        "Service, also known as MI6.\n"
    )
    ev = {"Vauxhall Cross": [
        "Vauxhall Cross is the headquarters of the Secret Intelligence Service "
        "(SIS, MI6)."]}
    out, n = sth.strip_contradicted_former_use(body, stop_evidence=ev)
    assert n == 0, (n, out)
    assert "Secret Intelligence Service" in out


def test_former_use_dropped_when_evidence_names_a_different_use():
    # War Remnants: evidence says Information Agency; the body says the building
    # was the military's intelligence headquarters. Different former use, not
    # supported -> the body sentence is dropped. The sourced sentence survives.
    body = (
        "Stop 5: War Remnants Museum\n"
        "Coordinates: 10.779500, 106.692000\n\n"
        "The museum opened in 1975 in the building that once housed the United "
        "States Information Agency. During the war, this building served as the "
        "US military's intelligence headquarters, anchoring the museum. Inside "
        "are themed rooms.\n"
    )
    ev = {"War Remnants Museum": [
        "The War Remnants Museum building formerly housed the United States "
        "Information Agency and the United States Information Service."]}
    out, n = sth.strip_contradicted_former_use(body, stop_evidence=ev)
    assert n == 1, (n, out)
    assert "intelligence headquarters" not in out.lower()
    assert "United States Information Agency" in out  # sourced fact survives
    assert "Inside are themed rooms." in out


def test_former_use_no_drop_without_evidence():
    # With no evidence for the stop, nothing is dropped (we cannot know it is wrong).
    body = (
        "Stop 5: War Remnants Museum\n"
        "Coordinates: 10.779500, 106.692000\n\n"
        "This building served as the US military's intelligence headquarters.\n"
    )
    out, n = sth.strip_contradicted_former_use(body, stop_evidence={})
    assert n == 0
    assert "intelligence headquarters" in out.lower()


# ── §9 magnitude number: sourced-only, any venue ─────────────────────────────
def test_capacity_removed_when_unsourced_any_venue():
    body = ("Stop 6: Grand Theatre\nCoordinates: 1,2\n\n"
            "Conceived as the city opera, it was a 500-seat venue created to "
            "bring operatic culture to the colony.")
    out, rep = sth.audit_seating_capacity(
        body, stop_evidence={"Grand Theatre": ["No seating figure is recorded."]})
    assert rep["removed"] == "500", rep
    assert "500" not in out
    assert "venue created to bring operatic" in out


def test_capacity_kept_when_sourced_any_venue():
    body = ("Stop 6: Grand Theatre\nCoordinates: 1,2\n\n"
            "Conceived as the city opera, it was a 500-seat venue.")
    ev = {"Grand Theatre": [
        "The theatre originally had 800 seats; after renovation it seats 500."]}
    out, rep = sth.audit_seating_capacity(body, stop_evidence=ev)
    assert rep["kept"] == "500", rep
    assert "500" in out


def test_capacity_rule_applies_to_a_non_opera_stop():
    # The rule has no venue key: a cathedral height with no source is dropped.
    body = ("Stop 3: Cathedral\nCoordinates: 1,2\n\n"
            "The twin bell towers rise 58 metres above the square.")
    out, rep = sth.audit_seating_capacity(
        body, stop_evidence={"Cathedral": ["The cathedral is a brick landmark."]})
    assert rep["removed"] == "58", rep
    assert "58" not in out


def test_capacity_fallback_blob_still_works():
    # back-compat: a single evidence blob applies to every stop.
    body = ("Stop 6: Opera House\nCoordinates: 1,2\n\n"
            "It was a 500-seat venue.")
    out, rep = sth.audit_seating_capacity(
        body, evidence_text="The hall seats 500 people.")
    assert rep["kept"] == "500", rep
    assert "500" in out


def test_capacity_never_strips_directions_distances():
    # §9 must never touch a structural Directions line — those carry computed
    # walking distances, not sourced narration claims.
    body = ("Stop 2: Circular Quay\nCoordinates: 1,2\n\n"
            "Orientation: A harbourfront precinct.\n\n"
            "Directions: Head west for 400 meters, and you'll arrive at The Rocks.")
    out, rep = sth.audit_seating_capacity(
        body, stop_evidence={"Circular Quay": ["no numbers here"]})
    assert rep["removed"] is None, rep
    assert "Head west for 400 meters" in out


# ── §3 folklore: generic disclosure, date only from evidence ─────────────────
def test_folklore_disclosed_without_date_when_no_dated_evidence():
    body = ("Witnesses have reported a mysterious single tear shedding from a "
            "statue here. The statue remains a touchstone.")
    out, n = sth.disclose_or_drop_folklore(body)
    assert n == 1, (n, out)
    low = out.lower()
    assert low.startswith("a story told by visitors holds that")
    # no invented date
    assert "2005" not in out
    # idempotent
    out2, n2 = sth.disclose_or_drop_folklore(out)
    assert n2 == 0, out2


def test_folklore_dated_only_when_evidence_supplies_the_year():
    body = ("Witnesses have reported a mysterious single tear shedding from a "
            "statue here.")
    ev = ("A rumour that began in 2005 held that the statue shed a tear; "
          "the diocese dismissed it.")
    out, n = sth.disclose_or_drop_folklore(body, evidence_text=ev)
    assert n == 1, (n, out)
    assert out.lower().startswith("a story told in 2005 holds that")


def test_folklore_ignores_unrelated_year_in_evidence():
    body = ("Witnesses have reported a mysterious single tear shedding from a "
            "statue here.")
    # 1880 is in the evidence but attached to construction, not the legend.
    ev = "The cathedral was completed in 1880 using imported bricks."
    out, n = sth.disclose_or_drop_folklore(body, evidence_text=ev)
    assert n == 1, (n, out)
    assert out.lower().startswith("a story told by visitors holds that")
    assert "1880" not in out


# ── the generic scrubs that LOCAL-880 already generalised still pass ─────────
def test_defect2_truncated_tail_dropped():
    body = ("In 1876, a design competition was held, and the architect won with a "
            "proposal inspired directly by the iconic. The imported bricks embody "
            "the ambitions of a bygone era.")
    out, n = sth.strip_truncated_tail_sentences(body)
    assert n == 1, (n, out)
    assert "inspired directly by the iconic." not in out
    assert "imported bricks" in out


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
        "Step-by-step audio guided tour of Sydney, Australia, is a walking tour.",
        "Step-by-step audio-guided tour of Sydney, Australia, walking tour.",
    ):
        out, n = sth.fix_intro_grammar(intro + "\n\nStop 1: X\nbody")
        assert n == 1, intro
        assert out.startswith("This is a step-by-step audio-guided walking tour of "
                              "Sydney, Australia.")
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
        "This place is recognized as a distinctive cultural brand of the city.",
    ):
        out, n = sth.strip_promotional_sentences("A fact here. " + promo)
        assert n == 1, (promo, out)
        assert "A fact here." in out


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
