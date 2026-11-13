"""LOCAL-907B: the Topic Library plans only region-relevant topics; Wikipedia fetching is
polite and robust. All network access is mocked."""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import topic_library as tl                    # noqa: E402
import topic_library_build as tb              # noqa: E402
import topic_relevance as tr                  # noqa: E402
import wiki_client as wc                      # noqa: E402

REGION = {
    "region_key": "testville", "display_name": "Testville / Test Province",
    "centre": {"lat": 10.0, "lng": 100.0}, "radius_km": 50,
    "aliases": ["Testvillian", "Teston"], "generic_seeds": [],
    "seed_articles": {"en": ["Testville"]},
    "default_themes": list(tl.THEMES),
}


def meta(title, coords=None, cats=(), lead=""):
    return {"exists": True, "title": title, "url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
            "coords": coords, "categories": list(cats), "lead": lead}


# ───────────────────────── relevance gate ─────────────────────────
def test_pass_by_coordinates():
    ok, reason, _ = tr.check_relevance(meta("Old Fort", coords=(10.1, 100.1)), REGION)
    assert ok and reason == "coord"


def test_far_coordinates_without_other_evidence_are_dropped():
    ok, reason, scores = tr.check_relevance(meta("Bayon", coords=(13.4, 103.8), lead="A temple."), REGION)
    assert not ok and reason == "off-region" and "coords=" in scores


def test_pass_by_mentions_folded_and_diacritic_insensitive():
    lead = "The Tèstvillé shrine. Testville holds it; the people of TESTVILLE and Teston keep it."
    ok, reason, _ = tr.check_relevance(meta("Shrine", lead=lead), REGION)
    assert ok and reason == "mentions"


def test_far_away_article_is_dropped_even_with_many_mentions():
    ok, reason, _ = tr.check_relevance(meta("Far Gorge", coords=(12.0, 102.0), cats=["Gorges of Test Province"],
                                            lead="Testville Testville Testville Testville"), REGION)
    assert not ok and reason == "off-region"


def test_two_mentions_are_not_enough():
    ok, reason, _ = tr.check_relevance(meta("Shrine", lead="Testville and Teston only."), REGION,
                                       full_text="Testville and Teston only.")
    assert not ok and reason == "off-region"


def test_mentions_use_lead_plus_first_two_sections_only():
    text = "Lead.\n\n== One ==\nx\n\n== Two ==\ny\n\n== Three ==\nTestville Testville Testville"
    ok, reason, _ = tr.check_relevance(meta("Thing"), REGION, full_text=text)
    assert not ok


def test_pass_by_category_containing_a_region_name():
    ok, reason, _ = tr.check_relevance(meta("Dish", cats=["Foods of Test Province"]), REGION)
    assert ok and reason == "category"


@pytest.mark.parametrize("title,cats", [
    ("List of rivers of Testville", []),
    ("Testville (disambiguation)", []),
    ("Some Page", ["Disambiguation pages"]),
    ("Cambridge Scholars Publishing", ["Book publishing companies of the United Kingdom"]),
    ("Al Jazeera Arabic", ["Arabic-language television networks"]),
    ("ASEAN Basketball League", ["Basketball leagues in Asia"]),
])
def test_excluded_page_kinds_never_pass(title, cats):
    ok, reason, _ = tr.check_relevance(meta(title, coords=(10.0, 100.0), cats=cats,
                                            lead="Testville Testville Testville"), REGION)
    assert not ok and reason.startswith("excluded")


def test_stadium_venue_is_not_a_sports_league():
    assert tr.excluded_kind("Park", ["American Football League (1926) venues"]) is None


def test_other_country_or_city_as_a_whole_is_excluded():
    ok, reason, _ = tr.check_relevance(
        meta("Cambodia", coords=(10.0, 100.0), cats=["Countries in Asia"]), REGION)
    assert not ok and "whole country/city" in reason
    ok, reason, _ = tr.check_relevance(
        meta("Elsewhere", cats=["Cities in Otherland"], lead="Testville " * 5), REGION)
    assert not ok and "whole country/city" in reason


def test_a_category_naming_the_region_is_not_a_whole_other_place():
    assert tr.whole_place_category(["Towns in Test Province"], tr.region_names(REGION)) is None


def test_biography_without_coordinates_is_not_a_linked_topic():
    ok, reason, _ = tr.check_relevance(
        meta("A Person", cats=["1800 births", "People from Testville"]), REGION)
    assert not ok and "biography" in reason


def test_region_names_come_from_data_and_are_folded():
    names = tr.region_names(REGION)
    assert "testville" in names and "teston" in names and "test province" in names


# ───────────────────────── theme classification ─────────────────────────
@pytest.mark.parametrize("title,lead,cats,theme", [
    ("Saint Petersburg", "Saint Petersburg is a city in Russia. It is the country's second-largest city, "
                         "with a population of five million.", ["Cities and towns in Russia"], "modern"),   # never "legends"
    ("Pho", "Phở is a Vietnamese soup dish consisting of broth, rice noodles and meat. It is a popular "
            "food and street cuisine.", ["Vietnamese noodle dishes", "Vietnamese cuisine"], "food"),
    ("Harbour Metro", "The Harbour Metro is a rapid transit railway system with stations and tunnels "
                      "serving the airport.", ["Railway lines", "Transport in Testville"], "transport"),
    ("Old Temple", "The Old Temple is a Buddhist temple and place of worship with an annual festival "
                   "and ritual.", ["Buddhist temples", "Religion in Testville"], "religion_customs"),
    ("Dune Reserve", "The Dune Reserve is a coastal nature reserve of sand dunes, wetland and rare "
                     "bird species.", ["Nature reserves", "Coasts"], "nature"),
    ("Communist Party of Kampuchea", "The Communist Party of Kampuchea was a communist party that ruled "
                                     "the country.", ["Political parties", "Communist parties"], None),
])
def test_theme_comes_from_the_articles_own_lead_and_categories(title, lead, cats, theme):
    assert tr.classify_article(title, lead, cats) == theme


def test_an_event_article_is_never_filed_under_religion():
    t = tr.classify_article("2016 Nice truck attack", "The attack took place on Bastille Day, a national "
                            "holiday, when a truck was driven into crowds.", ["Holidays", "Attacks"])
    assert t in ("history", None)          # unclear -> dropped, never a wrong theme


# ───────────────────────── planning ─────────────────────────
def article(title, words=900, links=()):
    body = " ".join(["Testville has a long record of trade and travel by sea."] * (words // 11))
    return {"lang": "en", "site": "wikipedia", "title": title, "url": "https://en.wikipedia.org/wiki/" + title,
            "revision_id": 1, "licence": tl.LICENCE, "text": body + "\n\n== History ==\n" + body,
            "links": list(links)}


def make_meta_fn(table):
    calls = []

    def fn(lang, titles):
        calls.append(list(titles))
        return {t: table[t] for t in titles if t in table}
    fn.calls = calls
    return fn


def test_plan_uses_hints_checks_they_exist_and_gates_links(caplog):
    region = dict(REGION, topic_hints={"en": [
        {"title": "Cham Harbour", "theme": "transport"}, {"title": "No Such Page", "theme": "arts"}]})
    table = {
        "Cham Harbour": meta("Cham Harbour", lead="A harbour of Testville."),
        "No Such Page": {"exists": False, "title": "No Such Page"},
        "Local Dish": meta("Local Dish", lead="A dish of Testville cuisine. Testville and Testville.",
                           cats=["Cuisine of Testville"]),
        "Ancient Rome": meta("Ancient Rome", lead="Rome and its empire.", cats=["Ancient history"]),
        "Bayon": meta("Bayon", coords=(13.4, 103.8), lead="A temple in Cambodia."),
    }
    fetch = lambda lang, t: article(t, links=["Local Dish", "Ancient Rome", "Bayon", "List of things"])
    with caplog.at_level(logging.INFO, logger="topic_library"):
        topics = tb.plan_topics(region, "en", 20, fetch_fn=fetch, meta_fn=make_meta_fn(table))
    titles = {t["title"]: t for t in topics}
    assert titles["Cham Harbour"]["reason"] == "hint" and titles["Cham Harbour"]["theme"] == "transport"
    assert "No Such Page" not in titles
    assert titles["Local Dish"]["reason"] in ("category", "mentions")
    assert "Ancient Rome" not in titles and "Bayon" not in titles
    assert any("[LOCAL-907B] topic 'Ancient Rome' dropped: off-region (" in r.getMessage() for r in caplog.records)
    assert any("Bayon" in r.getMessage() and "dropped" in r.getMessage() for r in caplog.records)
    assert all("List of things" != t for t in titles)
    assert all(t["url"] for t in topics)


def test_plan_order_is_seed_sections_then_hints_then_links():
    region = dict(REGION, topic_hints={"en": [{"title": "Hinted", "theme": "history"}]})
    table = {"Hinted": meta("Hinted", lead="Of Testville."),
             "Linked": meta("Linked", coords=(10.0, 100.0), lead="A war and a battle in history.",
                            cats=["Military history"])}
    fetch = lambda lang, t: article(t, words=1200, links=["Linked"])
    topics = tb.plan_topics(region, "en", 12, fetch_fn=fetch, meta_fn=make_meta_fn(table))   # 907C: linked cap 25%
    history = [t for t in topics if t["theme"] == "history"]
    assert [t["reason"] for t in history][:3] == ["seed", "hint", "coord"]


def test_a_failed_fetch_is_skipped_not_a_crash(caplog):
    region = dict(REGION, topic_hints={"en": [{"title": "Hinted", "theme": "history"}]})
    table = {"Hinted": meta("Hinted", lead="Of Testville.")}

    def fetch(lang, t):
        if t == "Hinted":
            raise wc.WikiFetchError("giving up after 5 tries (HTTP 429)")
        return article(t)
    with caplog.at_level(logging.WARNING, logger="topic_library"):
        topics = tb.plan_topics(region, "en", 5, fetch_fn=fetch, meta_fn=make_meta_fn(table))
    assert topics and all(t["title"] != "Hinted" for t in topics)
    assert any("skipped" in r.getMessage() for r in caplog.records)


def test_dry_run_output_shows_reason_url_source_words_and_theme_counts():
    out = tb.run_build("mui_ne_binh_thuan", "en", max_segments=4, dry_run=True,
                       fetch_fn=lambda l, t: article(t, words=1200), meta_fn=make_meta_fn({}),
                       log=lambda s: None)
    text = out["plan_text"]
    assert "why: seed" in text and "words" in text and "https://en.wikipedia.org/wiki/" in text
    assert "Themes:" in text and "Themes with >= 2 topics" in text


def test_region_data_has_hints_aliases_and_the_gate_inputs():
    for key, r in tl.load_regions().items():
        hints = r["topic_hints"]["en"]
        assert 10 <= len(hints) <= 40, key
        assert all(h["title"] and h["theme"] in tl.THEMES for h in hints), key
        assert r["aliases"], key


# ───────────────────────── polite fetching ─────────────────────────
class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {"query": {}}, headers or {}

    def json(self):
        return self._body


class Net:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, params, headers, timeout):
        self.calls.append((url, dict(params), dict(headers)))
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def client(net, **kw):
    sleeps, now = [], [0.0]

    def sleep(s):
        sleeps.append(s)
        now[0] += s
    c = wc.WikiClient(getter=net, sleep=sleep, clock=lambda: now[0], **kw)
    c.sleeps = sleeps
    return c


def test_429_then_success_is_retried_with_backoff_and_ua_and_maxlag():
    net = Net([Resp(429), Resp(429), Resp(200, {"query": {"ok": 1}})])
    c = client(net)
    assert c.get_json("https://en.wikipedia.org/w/api.php", {"action": "query"}) == {"query": {"ok": 1}}
    assert len(net.calls) == 3
    backoffs = [s for s in c.sleeps if s >= 2]
    assert backoffs == [2, 4]
    ua = net.calls[0][2]["User-Agent"]
    assert ua == "AudiouraTopicLibrary/1.0 (contact: audiotoursai@gmail.com)"
    assert net.calls[0][1]["maxlag"] == 5


def test_retry_after_header_is_honoured():
    net = Net([Resp(503, headers={"Retry-After": "7"}), Resp(200)])
    c = client(net)
    c.get_json("u", {})
    assert 7.0 in c.sleeps


def test_five_429s_give_up_with_a_catchable_error():
    net = Net([Resp(429)])
    c = client(net)
    with pytest.raises(wc.WikiFetchError):
        c.get_json("u", {})
    assert len(net.calls) == 5
    assert [s for s in c.sleeps if s >= 2] == [2, 4, 8, 16]


def test_requests_are_serial_at_least_200ms_apart():
    net = Net([Resp(200)])
    c = client(net)
    for _ in range(3):
        c.get_json("u", {})
    assert sum(c.sleeps) >= 0.4 - 1e-9 and all(0 < s <= 0.2 + 1e-9 for s in c.sleeps)


def test_maxlag_error_body_is_retried():
    net = Net([Resp(200, {"error": {"code": "maxlag", "info": "lagged"}}), Resp(200, {"query": {}})])
    c = client(net)
    assert c.get_json("u", {}) == {"query": {}}
    assert len(net.calls) == 2


def test_network_error_is_retried():
    net = Net([ConnectionError("boom"), Resp(200)])
    c = client(net)
    assert c.get_json("u", {}) == {"query": {}}


def test_metadata_lookup_batches_fifty_titles_and_skips_failed_batches(tmp_path):
    seen = []

    class FakeClient:
        def get_json(self, url, params):
            titles = params["titles"].split("|")
            seen.append(len(titles))
            if len(seen) == 2:
                raise wc.WikiFetchError("429 x5")
            return {"query": {"pages": [{"pageid": i, "title": t} for i, t in enumerate(titles, 1)]}}
    wm = tr.WikiMeta(client=FakeClient(), cache_dir=str(tmp_path))
    out = wm("en", [f"T{i}" for i in range(120)])
    assert seen == [50, 50, 20]
    assert len(out) == 70 and len(wm.failed) == 50          # the failed batch is skipped, no crash
    again = wm("en", [f"T{i}" for i in range(50)])           # disk cache: no new request
    assert len(again) == 50 and seen == [50, 50, 20]


def test_metadata_parses_coordinates_categories_redirects_and_missing(tmp_path):
    class FakeClient:
        def get_json(self, url, params):
            return {"query": {
                "redirects": [{"from": "Cham people", "to": "Chams"}],
                "pages": [
                    {"pageid": 1, "title": "Chams", "fullurl": "https://en.wikipedia.org/wiki/Chams",
                     "coordinates": [{"lat": 1.5, "lon": 2.5, "primary": True}],
                     "categories": [{"title": "Category:Chams"}], "extract": "The Chams are."},
                    {"title": "Nope", "missing": True}]}}
    wm = tr.WikiMeta(client=FakeClient(), cache_dir=str(tmp_path))
    out = wm("en", ["Cham people", "Nope"])
    assert out["Cham people"]["title"] == "Chams" and out["Cham people"]["coords"] == (1.5, 2.5)
    assert out["Cham people"]["categories"] == ["Chams"] and out["Cham people"]["lead"] == "The Chams are."
    assert out["Nope"]["exists"] is False
