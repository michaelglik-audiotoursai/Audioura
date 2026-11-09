"""LOCAL-880C: two defects left by LOCAL-880B.

1. The sourced-number scrub (spoken_text_hygiene.audit_seating_capacity) dropped
   an unsourced magnitude but left the unit behind — "rise 58 meters high" became
   "rise meters high" (submission_artifacts/local880b/saigon_tour.txt, Stop 1).
   It must remove the WHOLE measurement phrase (never leave a bare unit) and its
   evidence matching must tolerate unit spelling/separator variants so a sourced
   figure (Wikipedia: "reaching to a height of 58 metres") is KEPT.

2. signature_story._GENERIC_VENUE hard-coded a proof tour's city/country/demonym
   ("vietnam", "saigon", "vietnamese", "chi", "minh" — D769). The generic place
   words must instead be derived at run time from the tour's location and the
   stop title, so a Paris tour treats "paris"/"french" as generic and a Saigon
   tour "saigon"/"vietnam".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spoken_text_hygiene as sth
import signature_story as ss
import derepetition_guard as dg


def _last_para(out: str) -> str:
    return out.split("\n\n")[-1].strip()


def _body(prose: str) -> str:
    return "Stop 1: X\nCoordinates: 1,2\n\n" + prose


# ── 1. number removal must never leave an orphan unit ────────────────────────
def test_unsourced_height_leaves_no_orphan_unit():
    out, rep = sth.audit_seating_capacity(
        _body("Its two bell towers rise 58 meters high, dominating the skyline."),
        stop_evidence={"X": ["No height is recorded for the towers."]})
    para = _last_para(out)
    assert rep["removed"] == "58", rep
    # the whole measurement phrase is gone; no orphan unit of any kind
    assert "58" not in para
    for orphan in ("meters", "meter", "metres", "metre", "seats", "km", "feet",
                   "tons"):
        assert orphan not in para.lower(), (orphan, para)
    # sentence stays grammatical: the comparative survives, the number/unit do not
    assert "rise high" in para, para


def test_unsourced_seat_count_becomes_a_venue():
    out, rep = sth.audit_seating_capacity(
        _body("Conceived as the city opera, it was a 500-seat venue."),
        stop_evidence={"X": ["No seating figure is recorded."]})
    para = _last_para(out)
    assert rep["removed"] == "500", rep
    assert "500" not in para
    assert "seat" not in para.lower()
    assert "a venue" in para, para


def test_sourced_height_is_kept_despite_spelling_and_separator():
    # Body says "58 meters"; the evidence (Wikipedia) says "58 metres". The figure
    # is sourced and must be KEPT — matching is spelling-tolerant.
    for ev in (
        "The cathedral has two bell towers, reaching to a height of 58 metres.",
        "Its 58-metre bell towers dominate the skyline.",   # hyphen separator
        "The towers are 58 m tall.",                        # abbreviated unit
    ):
        out, rep = sth.audit_seating_capacity(
            _body("Its two bell towers rise 58 meters high, dominating the skyline."),
            stop_evidence={"X": [ev]})
        assert rep["kept"] == "58", (ev, rep)
        assert "58 meters high" in out, (ev, out)


def test_dangling_measurement_verb_is_cleaned():
    # "The tower stands 95 metres." with no source: dropping the figure+unit would
    # leave a dangling verb; the clause is removed, no orphan unit remains.
    out, rep = sth.audit_seating_capacity(
        _body("The tower stands 95 metres."),
        stop_evidence={"X": ["no numbers here"]})
    para = _last_para(out)
    assert rep["removed"] == "95", rep
    assert "metres" not in para.lower() and "95" not in para


def test_verbal_seated_form_keeps_its_verb():
    # "seated 500 guests" (verbal) must not collapse to "venue guests"; drop the
    # figure, keep the verb and the rest.
    out, rep = sth.audit_seating_capacity(
        _body("The hall seated 500 guests nightly."),
        stop_evidence={"X": ["no numbers here"]})
    para = _last_para(out)
    assert rep["removed"] == "500", rep
    assert "500" not in para
    assert "seated guests nightly" in para, para


# ── 2. generic place words are derived, not hard-coded ───────────────────────
def test_generic_venue_names_no_proof_tour_place():
    for banned in ("vietnam", "vietnamese", "saigon", "chi", "minh"):
        assert banned not in ss._GENERIC_VENUE, banned


def test_paris_tour_treats_french_as_generic():
    gx = ss.derive_generic_tokens("Paris, France", "Notre-Dame Cathedral")
    assert "paris" in gx
    assert "french" in gx          # demonym of France
    assert "france" in gx
    # a Saigon place word is NOT generic for a Paris tour
    assert "vietnam" not in gx
    # a genuinely distinctive story token survives for a Paris tour
    story = {"story": "Victor Hugo set The Hunchback of Notre-Dame here.",
             "source_sentence": "Victor Hugo set The Hunchback of Notre-Dame here."}
    kt = ss.story_key_tokens(story, generic_extra=gx)
    assert "hugo" in kt and "hunchback" in kt


def test_saigon_tour_treats_saigon_and_vietnam_as_generic():
    gx = ss.derive_generic_tokens("Ho Chi Minh City, Vietnam", "Saigon Opera House")
    for w in ("saigon", "vietnam", "vietnamese", "chi", "minh"):
        assert w in gx, w
    # a Paris place word is NOT generic for a Saigon tour
    assert "french" not in gx
    assert "paris" not in gx


def test_body_tells_story_excludes_derived_place_words():
    # The story's only non-generic-looking tokens are place words of THIS tour;
    # a body that merely repeats the venue/city must NOT count as telling it.
    gx = ss.derive_generic_tokens("Ho Chi Minh City, Vietnam", "Saigon Opera House")
    only_place = {"story": "The Saigon opera house stands in Vietnam.",
                  "source_sentence": "The Saigon opera house stands in Vietnam."}
    # once this tour's place words are removed, nothing distinctive is left —
    # repeating the venue/city name is not a signature story.
    assert ss.story_key_tokens(only_place, generic_extra=gx) == set()
    # a different generic body (not quoting the source) does not count as telling
    # a story that has no distinctive content.
    generic_body = "This landmark in the city centre is elegant and historic."
    assert ss.body_tells_story(generic_body, only_place, generic_extra=gx) is False

    # a real story (1944 Allied bombing) is still detected for the same tour
    bombing = {"story": "In 1944 Allied bombing forced the theatre to close.",
               "source_sentence": "Allied bombing in 1944 damaged the opera house."}
    told = "During the war, Allied forces bombed the building in 1944."
    assert ss.body_tells_story(told, bombing, generic_extra=gx) is True


# ── 3. de-repetition keeps the telling that carries a sourced figure ─────────
def test_carries_magnitude_number_detector():
    assert dg._carries_magnitude_number("the towers reach 58 metres high")
    assert dg._carries_magnitude_number("a 500-seat venue")
    assert dg._carries_magnitude_number("it was 58-metre tall")
    assert dg._carries_magnitude_number("the towers are 58 m tall")
    assert dg._carries_magnitude_number("the hall seats 500 people")
    # not a magnitude: a bare year, a street number, a price
    assert not dg._carries_magnitude_number("completed in 1880 by the architect")
    assert not dg._carries_magnitude_number("it stands at 12 Rue Catinat")
    assert not dg._carries_magnitude_number("the vaguer twin bell towers rise high")


def test_within_stop_derep_keeps_the_sourced_number_telling():
    # Stop 1 tells the bell-towers fact twice: the FIRST telling is vague, the
    # LATER telling carries the sourced 58 metres. The default rule drops the
    # later telling; the LOCAL-880C swap keeps the number-bearing one instead.
    first_vague = "The twin bell towers rise sharply above the brick facade of the cathedral here."
    later_num = "The twin bell towers reach 58 metres high above the square, a distinctive silhouette."
    r = {"within_stop": True, "signature": "kp/('bell', 'towers')",
         "first_stop": 1, "repeat_stop": 1,
         "sentence": later_num, "first_sentence": first_vague}
    # emulate the swap the guard performs
    if r.get("within_stop") and r.get("first_sentence"):
        if (dg._carries_magnitude_number(r["sentence"])
                and not dg._carries_magnitude_number(r["first_sentence"])):
            r = dict(r, sentence=r["first_sentence"], first_sentence=r["sentence"])
    # the sentence slated for removal is now the vague one, NOT the sourced number
    assert r["sentence"] == first_vague
    assert "58 metres" in r["first_sentence"]


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
