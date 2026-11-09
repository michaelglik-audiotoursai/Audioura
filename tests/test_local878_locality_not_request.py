"""test_local878_locality_not_request.py — LOCAL-878 Bug 3.

Tour 547: the orchestrator/generator took the user's free-text request
("Saigon centre landmarks, …") as the LOCALITY. Narration said "in Saigon centre
landmarks" and the city-context Wikipedia fetch hit /wiki/Saigon_Centre (an office
building), not Ho Chi Minh City.

THE FIX (asserted here, offline): the locality is derived from a proper
place-extraction over the request — a leading free-text TOPIC segment ("Saigon
centre landmarks", "best attractions", "top sights") is never the locality; the
real place segment ("Ho Chi Minh City" / "Saigon") is taken instead. A request
that is ONLY a topic yields no locality rather than the topic string.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from text_polish import city_from_scope, _is_topic_segment  # noqa: E402
from actionable_failure import derive_locality  # noqa: E402

# The exact request string from the ticket.
REQ_547 = "Saigon centre landmarks, Ho Chi Minh City, Vietnam"


def test_city_from_scope_skips_the_topic_segment():
    out = city_from_scope(REQ_547)
    assert out == "Ho Chi Minh City"
    assert out != "Saigon centre landmarks"
    assert "landmark" not in out.lower()


def test_city_from_scope_without_country_tail():
    assert city_from_scope("Saigon centre landmarks, Ho Chi Minh City") == "Ho Chi Minh City"


def test_city_from_scope_saigon_alias_resolves_to_hcmc():
    # "Saigon" on its own is the city alias, never the Saigon Centre building.
    assert city_from_scope("Top sights, Saigon") == "Ho Chi Minh City"


def test_city_from_scope_topic_only_gives_no_place():
    # Only a topic, no place — never narrate the topic as a locality.
    assert city_from_scope("Saigon centre landmarks") == ""


def test_derive_locality_skips_topic_segment():
    loc = derive_locality(REQ_547)
    assert "Ho Chi Minh City" in loc
    assert "landmark" not in loc.lower()
    assert loc != "Saigon centre landmarks"


def test_topic_segment_detector():
    assert _is_topic_segment("Saigon centre landmarks")
    assert _is_topic_segment("best attractions")
    assert _is_topic_segment("top 10 sights")
    assert _is_topic_segment("things to see")
    assert not _is_topic_segment("Ho Chi Minh City")
    assert not _is_topic_segment("District 1")


def test_plain_place_strings_are_unchanged():
    # Back-compat: ordinary place / title strings still resolve as before.
    assert city_from_scope("Ho Chi Minh City, Vietnam") == "Ho Chi Minh City"
    assert city_from_scope("Museum of Fine Arts, Boston") == "Museum of Fine Arts"
    assert city_from_scope("Sophia's biking tour in Ho Chi Minh City") == "Ho Chi Minh City"


def test_never_the_saigon_centre_building():
    # The whole point: the locality is the city, so the city-context fetch resolves
    # the CITY article, never /wiki/Saigon_Centre.
    for req in (REQ_547, "Saigon centre landmarks, Ho Chi Minh City",
                "Saigon Centre landmarks walk, Ho Chi Minh City, Vietnam"):
        assert city_from_scope(req) == "Ho Chi Minh City"
