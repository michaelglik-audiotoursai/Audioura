"""LOCAL-907C: no minor-place / institution filler, own-subject categories only, dull sections
dropped, theme fallbacks, 25% linked cap. All network access is mocked; names are generic."""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import topic_library as tl                    # noqa: E402
import topic_library_build as tb              # noqa: E402
import topic_relevance as tr                  # noqa: E402

REGION = {
    "region_key": "testville", "display_name": "Testville / Test Province",
    "centre": {"lat": 10.0, "lng": 100.0}, "radius_km": 50,
    "aliases": ["Testvillian"], "generic_seeds": [],
    "seed_articles": {"en": ["Testville"]}, "default_themes": list(tl.THEMES),
}
NAMES = tr.region_names(REGION)


def meta(title, coords=(10.0, 100.0), cats=(), lead=""):
    return {"exists": True, "title": title, "url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
            "coords": coords, "categories": list(cats), "lead": lead}


# ───────── guide-worthiness ─────────
@pytest.mark.parametrize("title,lead,cats,reason", [
    ("Testville Secondary School", "Testville Secondary School is a high school in Testville.", ["High schools in Testville"], "school"),
    ("Testville University of Arts", "Testville University of Arts is a public university.", ["Universities in Testville"], "university/college"),
    ("Grand Hotel", "The Grand Hotel is a hotel in Testville.", ["Hotels in Testville"], "hotel"),
    ("Spice Pot", "Spice Pot is a restaurant chain.", ["Restaurants in Testville"], "restaurant"),
    ("Big Co", "Big Co is a company based in Testville.", ["Companies of Testville"], "company"),
    ("Testville Convention Center", "The Testville Convention Center is a convention centre.", [], "convention centre"),
    ("Test Field", "Test Field is an airfield near Testville.", ["Airfields"], "airfield"),
    ("Rovers", "Testville Rovers is a football club.", ["Football clubs in Testville"], "sports club/venue"),
    ("The Blue Thing", "The Blue Thing is a 1988 film about divers.", ["Films set in Testville"], "film/TV/album/song/book"),
    ("Lantern Fest", "The Lantern Fest is a festival held yearly.", ["Festivals in Testville"], "festival"),
])
def test_excluded_kinds_are_dropped(title, lead, cats, reason):
    assert tr.not_guide_worthy(meta(title, lead=lead, cats=cats)) == reason


def test_small_commune_dropped_by_population_and_by_size():
    small = meta("Ascros", lead="Ascros is a commune in Test Province. It has a population of 120.",
                 cats=["Communes of Test Province"])
    assert tr.not_guide_worthy(small).startswith("minor place")
    unknown_pop = meta("Lanton", lead="Lanton is a village in Test Province.", cats=["Villages in Test Province"])
    assert tr.not_guide_worthy(unknown_pop) is None            # population unstated: decided by size
    assert tr.small_place_by_size(unknown_pop, 900).startswith("minor place")
    assert tr.small_place_by_size(unknown_pop, 4000) is None
    ward = meta("Ward One", lead="Ward One is a ward of Testville.", cats=["Wards of Testville"])
    assert tr.small_place_by_size(ward, 1200).startswith("minor place")


def test_big_neighbourhood_stays():
    big = meta("Old Quarter", lead="The Old Quarter is a neighbourhood of Testville with a population of 85,000.",
               cats=["Neighbourhoods in Testville"])
    assert tr.not_guide_worthy(big) is None
    assert tr.small_place_by_size(big, 6000) is None


def test_stadium_hint_not_filtered_but_linked_stadium_is():
    st = meta("Test Park", lead="Test Park is a stadium in Testville.", cats=["Stadiums in Testville"])
    assert tr.not_guide_worthy(st) == "sports club/venue"


# ───────── category rule ─────────
def test_own_subject_category_passes():
    assert tr.own_category("History of Testville", NAMES)
    assert tr.own_category("People from Testville", NAMES)
    assert tr.own_category("Foods of Test Province", NAMES)
    assert tr.own_category("Testville", NAMES)
    ok, reason, _ = tr.check_relevance(meta("Old Gate", coords=None, cats=["History of Testville"]), REGION)
    assert ok and reason == "category"


def test_broader_region_category_fails_levant_verdon_shape():
    # an island / a gorge in ANOTHER département, filed under a broader region category
    assert not tr.own_category("Islands of Testville-Alpha-Coast", NAMES)
    assert not tr.own_category("Gorges of the Testville-Alpha-Coast region", NAMES)
    assert not tr.own_category("Films set in Testville", NAMES)
    assert not tr.own_category("Gorges of France", NAMES)
    for title in ("Levant Isle", "Verdon Pass"):
        ok, reason, _ = tr.check_relevance(
            meta(title, coords=None, cats=["Islands of Testville-Alpha-Coast", "Films set in Testville"],
                 lead="A natural place in the south."), REGION)
        assert not ok, title


# ───────── section denylist ─────────
@pytest.mark.parametrize("art,head", [
    ("Transit Authority", "Funding"), ("Transit Authority", "Management and administration"),
    ("Testville County", "Politics"), ("Testville", "Government"), ("Testville", "Elections"),
    ("Port of Testville", "Cruise facilities"), ("Testville Trolley", "Proposed extensions"),
    ("Testville Trolley", "Fleet"), ("Testville Trolley", "Ridership"), ("Testville", "Budget"),
    ("Testville", "Future"), ("Testville", "See also"), ("Testville", "Finance"),
    ("Testville", "Governance"),
])
def test_dull_sections_denied(art, head):
    assert tr.section_denied(art, head)


def test_administration_of_a_province_is_not_denied_and_history_is_kept():
    assert tr.section_denied("Test Province", "Administration") is None
    assert tr.section_denied("Transit Authority", "History") is None
    assert tr.section_denied("Testville", "Architecture") is None


def seed_article(title, headings, words=700, links=()):
    body = " ".join(["Testville has a long record of trade and travel by sea."] * (words // 11))
    text = "Lead sentence.\n\n" + "\n\n".join(f"== {h} ==\n{body}" for h in headings)
    return {"lang": "en", "site": "wikipedia", "title": title, "url": "https://en.wikipedia.org/wiki/" + title,
            "revision_id": 1, "licence": tl.LICENCE, "text": text, "links": list(links)}


def test_plan_drops_dull_sections_and_takes_at_most_two_per_seed(caplog):
    region = dict(REGION, seed_articles={"en": ["Testville Transit"]})
    heads = ["History", "Funding", "Route network", "Stations", "Safety record", "Early plans", "Management and administration"]
    fetch = lambda l, t: seed_article("Testville Transit", heads)
    with caplog.at_level(logging.INFO, logger="topic_library"):
        topics = tb.plan_topics(region, "en", 20, fetch_fn=fetch, meta_fn=lambda l, ts: {})
    titles = [t["title"] for t in topics]
    assert len(titles) == 2, titles
    assert not any("Funding" in t or "administration" in t for t in titles)
    assert any("[LOCAL-907C] topic" in r.getMessage() and "not guide-worthy (section 'Funding')" in r.getMessage()
               for r in caplog.records)


# ───────── theme fallbacks ─────────
@pytest.mark.parametrize("title,lead,cats,theme", [
    ("Book Fest", "The Book Fest is an annual literary festival held in Testville in autumn.", ["Festivals in Testville"], "arts"),
    ("Harvest Fair", "The Harvest Fair is an annual trade fair for farmers and traders.", ["Festivals"], "people_economy"),
    ("Rovers Park", "Rovers Park is a baseball park and stadium in Testville, home of the Rovers.", ["Baseball venues"], "people_economy"),
    ("Harbour Light", "Harbour Light is a lighthouse on an island in the bay of Testville.", ["Lighthouses"], "history"),
    ("Old Light", "Old Light is a lighthouse said to be haunted by the ghost of a keeper.", ["Lighthouses"], "legends"),
    ("Snow Peak", "Snow Peak is a ski resort in the mountains of Testville.", ["Ski resorts"], "nature"),
])
def test_theme_fallbacks(title, lead, cats, theme):
    assert tr.classify_article(title, lead, cats) == theme


def test_religious_festival_is_left_to_the_classifier():
    t = tr.classify_article("Pagoda Festival", "The Pagoda Festival is an annual Buddhist festival of worship "
                            "and ritual at the temple.", ["Buddhist festivals", "Religion in Testville"])
    assert t == "religion_customs"


def test_hint_keeps_editorial_theme_only_if_classifier_agrees_or_unsure():
    assert tr.reconcile_hint_theme("history", None) == "history"
    assert tr.reconcile_hint_theme("history", "history") == "history"
    assert tr.reconcile_hint_theme("religion_customs", "arts") == "arts"


# ───────── 25% linked cap ─────────
def linked_article(title, links=()):
    body = " ".join(["Testville has a long record of trade and travel by sea."] * 150)
    return {"lang": "en", "site": "wikipedia", "title": title, "url": "https://en.wikipedia.org/wiki/" + title,
            "revision_id": 1, "licence": tl.LICENCE, "text": body, "links": list(links)}


def test_linked_articles_fill_at_most_25_percent_and_plan_stays_thin():
    names = [f"Harbour Site {c}" for c in "ABCDEFGHIJ"]
    table = {n: meta(n, lead=f"{n} is a historic battle site and fortress dating from the war in Testville.",
                     cats=["History of Testville", "Forts in Testville"]) for n in names}
    # a single flat seed with no sections -> 1 seed topic; linked would otherwise fill the rest
    def fetch(l, t):
        return linked_article(t, links=names) if t == "Testville" else linked_article(t)
    topics = tb.plan_topics(REGION, "en", 8, fetch_fn=fetch, meta_fn=lambda l, ts: {t: table[t] for t in ts if t in table})
    linked = [t for t in topics if t["tier"] == 1]
    assert len(linked) <= 2 and len(topics) <= 3          # 25% of 8 = 2, plus the 1 seed


def test_thin_plan_is_reported():
    topics = [{"theme": "history", "title": "A", "reason": "seed", "source_words": 900, "est_cost_usd": 0.1}]
    out = tb.format_plan(REGION, "en", topics, requested=5, dropped={"school": 2})
    assert "thin: 1 of 5" in out and "school=2" in out


def test_hcmc_no_longer_hints_the_central_coast_goddess_but_mui_ne_does():
    regions = tl.load_regions()
    h = lambda k: {x["title"] for x in regions[k]["topic_hints"]["en"]}
    assert "Thiên Y A Na" not in h("ho_chi_minh_city")
    assert "Thiên Y A Na" in h("mui_ne_binh_thuan")


def test_organisation_and_other_division_and_people_group_and_shared_reservoir():
    assert tr.not_guide_worthy(meta("Hot Club", lead="Hot Club is a non-profit organisation in Testville.")) == "organisation"
    assert tr.not_guide_worthy(meta("Beta", lead="Beta is a former province of Testland.")) == "other administrative division"
    ok, why, _ = tr.check_relevance(meta("Hill Folk", coords=None, cats=["Ethnic groups in Testland"],
                                         lead="The Hill Folk of Testville, Testville and Testville."), REGION)
    assert not ok and "people group" in why
    ok, why, _ = tr.check_relevance(meta("Big Reservoir", coords=(10.5, 100.5), cats=["Lakes"],
                                         lead="Testville Testville Testville Testville reservoir " * 3), REGION)
    assert not ok                                          # located outside the radius: mentions cannot rescue it


def test_hint_theme_yields_only_to_a_clear_classifier_verdict():
    assert tr.reconcile_hint_theme("history", "modern", 3) == "history"
    assert tr.reconcile_hint_theme("history", "modern", 9) == "modern"
