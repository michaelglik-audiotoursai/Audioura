"""test_local878_evidence_geo_gate.py — LOCAL-878 Bug 1.

Wave 36, tour 547: stop 6 "Opera House" (pin in District 1, Ho Chi Minh City) was
narrated as the SYDNEY Opera House (Utzon, Bennelong Point, 1973). Cause: the
bare-name Wikipedia search returned the Sydney article and ``_name_ok`` accepted it;
only ONE far-place sentence (Harbour Bridge) was later filtered, so the rest of the
Sydney lead reached the narrator and the gate.

THE FIX (asserted here, fully offline via an injected fetcher):
  * Before an article is used, its OWN coordinate (prop=coordinates, else a P625
    fallback) is checked against the stop pin; >2 km away is rejected.
  * "Opera House" with the HCMC pin gets the Saigon article (via the "<name> <city>"
    retry), or none — never Sydney.
  * "Opera House" with a Sydney pin still gets Sydney.
  * "Post Office" with the HCMC pin gets the Saigon Central Post Office, or none.
  * A coordinate-less article is accepted only when it names the city.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import landmark_wikipedia_evidence as lw  # noqa: E402

LOC = "Ho Chi Minh City, Vietnam"
HCMC_OPERA_PIN = (10.776390, 106.702780)     # District 1 Opera House pin
SYDNEY_OPERA_PIN = (-33.856784, 151.215297)  # Sydney Opera House pin

# Article coordinates (as prop=coordinates would return them).
SYDNEY_COORD = (-33.856784, 151.215297)
SAIGON_OPERA_COORD = (10.776553, 106.702972)
SAIGON_POST_COORD = (10.779840, 106.699097)

SYDNEY_PAGE = {
    "title": "Sydney Opera House",
    "lead": "The Sydney Opera House is a multi-venue performing arts centre in Sydney. "
            "Designed by Jørn Utzon, it opened in 1973 on Bennelong Point.",
    "wikitext": "{{Infobox building\n| architect = [[Jørn Utzon]]\n| opened = 1973\n}}",
    "langlinks": [], "coord": SYDNEY_COORD, "qid": "Q45178",
}
SAIGON_OPERA_PAGE = {
    "title": "Saigon Opera House",
    "lead": "The Saigon Opera House (Nhà hát Thành phố) is an opera house in Ho Chi Minh "
            "City. It was designed by Eugène Ferret and opened in 1900.",
    "wikitext": "{{Infobox building\n| architect = [[Eugène Ferret]]\n| opened = 1900\n}}",
    "langlinks": [], "coord": SAIGON_OPERA_COORD, "qid": "Q2040251",
}
SAIGON_POST_PAGE = {
    "title": "Saigon Central Post Office",
    "lead": "Saigon Central Post Office is a post office in Ho Chi Minh City, built "
            "1886–1891 in the French colonial style.",
    "wikitext": "{{Infobox building\n| opened = 1891\n}}",
    "langlinks": [], "coord": SAIGON_POST_COORD, "qid": "Q1319076",
}


def _fetcher(by_query_lang):
    """fetch_fn(name, lang) -> {'pages': [...]}. Keyed by (name, lang); a missing key
    returns no pages."""
    def f(name, lang):
        return {"pages": list(by_query_lang.get((name, lang), []))}
    return f


def test_opera_house_hcmc_pin_never_gets_sydney():
    # Bare "Opera House" returns Sydney (what the live search did); the city-qualified
    # retry "Opera House Ho Chi Minh City" returns the Saigon article.
    fetch = _fetcher({
        ("Opera House", "en"): [SYDNEY_PAGE],
        ("Opera House Ho Chi Minh City", "en"): [SAIGON_OPERA_PAGE],
    })
    ev = lw.evidence_for("Opera House", LOC, langs=["en"], fetch_fn=fetch,
                         use_cache=False, pin=HCMC_OPERA_PIN)
    assert len(ev) == 1
    assert "Saigon Opera House" in ev[0]
    assert "Sydney" not in ev[0] and "Utzon" not in ev[0] and "Bennelong" not in ev[0]


def test_opera_house_hcmc_pin_gets_none_rather_than_sydney():
    # Only Sydney exists anywhere: the stop gets NO evidence, never Sydney.
    fetch = _fetcher({
        ("Opera House", "en"): [SYDNEY_PAGE],
        ("Opera House Ho Chi Minh City", "en"): [SYDNEY_PAGE],
    })
    ev = lw.evidence_for("Opera House", LOC, langs=["en"], fetch_fn=fetch,
                         use_cache=False, pin=HCMC_OPERA_PIN)
    assert ev == []


def test_opera_house_sydney_pin_still_gets_sydney():
    fetch = _fetcher({("Opera House", "en"): [SYDNEY_PAGE]})
    ev = lw.evidence_for("Opera House", "Sydney, Australia", langs=["en"], fetch_fn=fetch,
                         use_cache=False, pin=SYDNEY_OPERA_PIN)
    assert len(ev) == 1 and "Sydney Opera House" in ev[0]


def test_post_office_hcmc_pin_gets_saigon_central_post_office():
    fetch = _fetcher({
        ("Post Office", "en"): [SAIGON_POST_PAGE],
    })
    ev = lw.evidence_for("Post Office", LOC, langs=["en"], fetch_fn=fetch,
                         use_cache=False, pin=(10.779840, 106.699097))
    assert len(ev) == 1 and "Saigon Central Post Office" in ev[0]


def test_post_office_hcmc_pin_rejects_a_far_post_office():
    far = dict(SAIGON_POST_PAGE, title="General Post Office, Sydney",
               lead="The General Post Office in Sydney.", coord=(-33.8675, 151.2070))
    fetch = _fetcher({
        ("Post Office", "en"): [far],
        ("Post Office Ho Chi Minh City", "en"): [far],
    })
    ev = lw.evidence_for("Post Office", LOC, langs=["en"], fetch_fn=fetch,
                         use_cache=False, pin=(10.779840, 106.699097))
    assert ev == []


def test_coordinateless_article_needs_the_city_name():
    # No coord on the page; it is accepted only if it names the city.
    names_city = dict(SAIGON_OPERA_PAGE, coord=None)
    no_city = dict(SAIGON_OPERA_PAGE, coord=None,
                   title="Opera House", lead="An opera house of great renown.")
    assert lw._geo_ok(HCMC_OPERA_PIN, "Ho Chi Minh City", names_city, allow_p625=False)
    assert not lw._geo_ok(HCMC_OPERA_PIN, "Ho Chi Minh City", no_city, allow_p625=False)


def test_pick_skips_the_far_page_and_takes_the_near_one():
    raw = {"pages": [SYDNEY_PAGE, SAIGON_OPERA_PAGE]}
    art = lw._pick("Opera House", raw, pin=HCMC_OPERA_PIN, city="Ho Chi Minh City")
    assert art and art["title"] == "Saigon Opera House"


def test_geo_gate_distance_constant_is_two_km():
    # The Sydney article is thousands of km from the HCMC pin.
    d = lw._haversine_km(HCMC_OPERA_PIN, SYDNEY_COORD)
    assert d > 6000.0
    assert lw.GEO_GATE_KM == 2.0


def test_pin_cell_rounds_to_about_one_km():
    assert lw._pin_cell(HCMC_OPERA_PIN) == "10.78,106.70"
    assert lw._pin_cell(None) == ""
    # Two pins in different cities never share a cache cell.
    assert lw._pin_cell(HCMC_OPERA_PIN) != lw._pin_cell(SYDNEY_OPERA_PIN)


def test_no_pin_no_city_keeps_old_behaviour():
    # With no geo signal the gate must not block a plain name-match (back-compat).
    fetch = _fetcher({("Saigon Opera House", "en"): [SAIGON_OPERA_PAGE]})
    ev = lw.evidence_for("Saigon Opera House", "", langs=["en"], fetch_fn=fetch,
                         use_cache=False)
    assert len(ev) == 1 and "Saigon Opera House" in ev[0]
