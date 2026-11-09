"""LOCAL-880: offline tests for signature_story (no network; injected narrate_fn)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import signature_story as ss


OPERA_EVIDENCE = (
    "The Saigon Opera House opened on 1 January 1900. During World War II, Allied "
    "forces bombed the building in 1944, causing serious damage and forcing its "
    "closure. Lam Son Square, outside the opera house, is mentioned in Graham "
    "Greene's novel The Quiet American, where a bombing incident unfolds. The "
    "building originally seated around 800 people."
)


def _fake_narrate_opera(system, user, model, **kw):
    parsed = {"stories": [
        {"story": "During World War II, Allied forces bombed the opera house in 1944, "
                  "forcing it to close.",
         "why_memorable": "conflict",
         "source_sentence": "During World War II, Allied forces bombed the building "
                            "in 1944, causing serious damage and forcing its closure."},
        {"story": "The square outside appears in Graham Greene's The Quiet American, "
                  "where a bombing unfolds.",
         "why_memorable": "famous book",
         "source_sentence": "Lam Son Square, outside the opera house, is mentioned in "
                            "Graham Greene's novel The Quiet American, where a bombing "
                            "incident unfolds."},
    ]}
    return parsed, 900, 120


def _fake_narrate_hallucinated(system, user, model, **kw):
    # a story whose source_sentence is NOT in the evidence -> must be dropped
    return ({"stories": [
        {"story": "A ghost is said to haunt the balcony.",
         "why_memorable": "surprise",
         "source_sentence": "Many visitors report seeing a ghost on the balcony at night."},
    ]}, 400, 40)


def _fake_narrate_dimension(system, user, model, **kw):
    return ({"stories": [
        {"story": "It is 58 meters tall.", "why_memorable": "dimension",
         "source_sentence": "The towers rise 58 meters above the city."},
    ]}, 300, 20)


def test_keeps_sourced_stories_and_caps_cost():
    stories, rep = ss.select_signature_stories(
        "Saigon Opera House", OPERA_EVIDENCE, location="Ho Chi Minh City",
        narrate_fn=_fake_narrate_opera)
    assert len(stories) == 2, stories
    assert any("1944" in s["story"] for s in stories)
    assert any("Quiet American" in s["story"] for s in stories)
    assert rep["cost_usd"] <= ss.COST_CAP_USD, rep["cost_usd"]
    assert rep["kept"] == 2


def test_drops_unsourced_quote():
    stories, rep = ss.select_signature_stories(
        "Saigon Opera House", OPERA_EVIDENCE, narrate_fn=_fake_narrate_hallucinated)
    assert stories == [], stories
    assert rep["dropped_unsourced"] == 1


def test_rejects_dimension_only():
    stories, _ = ss.select_signature_stories(
        "Notre-Dame Cathedral", "The towers rise 58 meters above the city.",
        narrate_fn=_fake_narrate_dimension)
    assert stories == [], stories


def test_required_element_block_mentions_story():
    stories, _ = ss.select_signature_stories(
        "Saigon Opera House", OPERA_EVIDENCE, narrate_fn=_fake_narrate_opera)
    block = ss.required_element_block(stories)
    assert "SIGNATURE STORY" in block
    assert "1944" in block
    assert ss.required_element_block([]) == ""


def test_body_tells_story_detection():
    stories, _ = ss.select_signature_stories(
        "Saigon Opera House", OPERA_EVIDENCE, narrate_fn=_fake_narrate_opera)
    bombing = next(s for s in stories if "1944" in s["story"])
    told = ("The opera house opened in 1900. In 1944 Allied bombing forced the "
            "theatre to close for repairs.")
    not_told = ("The opera house is an elegant French colonial building with "
                "crystal chandeliers and a pale facade.")
    assert ss.body_tells_story(told, bombing) is True
    assert ss.body_tells_story(not_told, bombing) is False


TOUR = """\
Step-by-step audio guided tour of Ho Chi Minh City, Vietnam, walking tour.

Stop 1: Opera House
Coordinates: 10.776390, 106.702780
Type/Specialty: Cultural Venue
Orientation: Standing across from the Opera House on Lam Son Square.

The municipal theatre opened on 1 January 1900. It is an elegant French colonial building with crystal chandeliers and a pale facade that catches the light.
Directions: Head west for 200 meters to City Hall.

Stop 2: City Hall
Coordinates: 10.776470, 106.700970
Type/Specialty: Government Building

You are standing before a yellow French-style building from the colonial period. It now houses the city People's Committee.
Directions: Continue east.
"""


def _regen_narrate(system, user, model, **kw):
    return ({"sentences": [
        "The municipal theatre opened on 1 January 1900.",
        "During World War II, Allied forces bombed the building in 1944, forcing it to close.",
        "The square outside appears in Graham Greene's The Quiet American, where a bombing unfolds.",
        "Today the restored theatre hosts performances once more.",
        "Its pale colonial facade still catches the afternoon light.",
    ]}, 1200, 160)


def test_ensure_regenerates_only_missing_stop():
    stories, _ = ss.select_signature_stories(
        "Opera House", OPERA_EVIDENCE, narrate_fn=_fake_narrate_opera)
    new_text, rep = ss.ensure_signature_in_tour(
        TOUR, {"Opera House": stories}, narrate_fn=_regen_narrate)
    assert rep["missing"] == 1, rep
    assert rep["regenerated"] == 1, rep
    assert "1944" in new_text
    assert "Quiet American" in new_text
    # header, coordinates, orientation, directions preserved
    assert "Stop 1: Opera House" in new_text
    assert "Coordinates: 10.776390, 106.702780" in new_text
    assert "Orientation: Standing across from the Opera House" in new_text
    assert "Directions: Head west for 200 meters to City Hall." in new_text
    # the stop that had no signature story is untouched
    assert "You are standing before a yellow French-style building" in new_text


def test_ensure_noop_when_story_already_told():
    story = {"story": "Allied forces bombed it in 1944.",
             "why_memorable": "conflict",
             "source_sentence": "Allied forces bombed the building in 1944."}
    told_tour = TOUR.replace(
        "It is an elegant French colonial building",
        "In 1944 Allied forces bombed the building, forcing it to close; it is an elegant French colonial building")
    _calls = []

    def _never(system, user, model, **kw):
        _calls.append(1)
        return None, 0, 0

    new_text, rep = ss.ensure_signature_in_tour(
        told_tour, {"Opera House": [story]}, narrate_fn=_never)
    assert rep["missing"] == 0, rep
    assert _calls == [], "must not call the LLM when the story is already told"
    assert new_text == told_tour


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
