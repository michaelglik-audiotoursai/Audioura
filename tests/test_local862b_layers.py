"""LOCAL-862B (D760) — layers for user stops. Offline: every network call is injected."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_stop_context as usc
import user_stop_enrichment as use
import user_stop_narration as usn
import user_stop_verify as usv

usc._default_wiki_fn = lambda t: None           # never hit the network from a test
usc._default_wiki_search_fn = lambda q: []

LOC = "Ho Chi Minh City, Vietnam"
POI = {"name": "Longan", "user_explicit": True, "type_specialty": "Bar",
       "coordinates": "10.779100, 106.699600"}

LONGAN_WIKI = {
    "title": "Longan", "disambiguation": False, "url": "https://en.wikipedia.org/wiki/Longan",
    "text": ("Longan (; Dimocarpus longan), also called lungan or dragon's eye, is a tropical "
             "tree species that produces edible fruit.\n\n== Etymology ==\n"
             "The word Longan is derived from simplified Chinese: lóngyǎn. "
             "The character for long means \"dragon\" while yǎn means \"eye\", so together "
             "it literally means \"dragon eye\".\n"),
}
RAMBUTAN_WIKI = {
    "title": "Rambutan", "disambiguation": False,
    "url": "https://en.wikipedia.org/wiki/Rambutan",
    "text": ("Rambutan is a medium-sized tropical tree in the family Sapindaceae.\n\n"
             "== Etymology ==\nThe name rambutan is derived from the Malay word rambut "
             "meaning 'hair', for hairy protuberances on the fruits.\n"),
}
BUIVIEN_WIKI = {
    "title": "Bùi Viện Street", "disambiguation": False,
    "url": "https://en.wikipedia.org/wiki/B%C3%B9i_Vi%E1%BB%87n_Street",
    "text": ("Bùi Viện Street is a small street in Bến Thành, Ho Chi Minh City. "
             "This is the city's famous nightlife street with many small bars.\n\n"
             "== Location ==\nThe area is popularized as the Backpacker Quarter in modern times.\n"),
}


def wiki(title):
    return {"longan": LONGAN_WIKI, "rambutan": RAMBUTAN_WIKI,
            "bùi viện street": BUIVIEN_WIKI}.get(title.lower())


def wiki_search(q):
    return ["Bùi Viện Street"] if "Viện" in q or "Vien" in q else []


class Disclosure(unittest.TestCase):
    def test_markers(self):
        for s in ("A Vietnamese folk tale tells that a dragon laid an egg.",
                  "According to one local legend, a dragon watched the village.",
                  "Legend has it that the fruit grew from a dragon's eye.",
                  "We couldn't confirm this, but the bar is said to be a former tea house."):
            self.assertTrue(usc.has_disclosure(s), s)
        for s in ("A dragon hatched from the egg and helped the village.",
                  "The fruit grew from a dragon's eye.", "Longan is a bar."):
            self.assertFalse(usc.has_disclosure(s), s)


class ScrubTier(unittest.TestCase):
    """The 855B always-drop legend tier: disclosed kept, undisclosed dropped."""
    LEGEND = "a dragon laid an egg that hatched a boy who saved the village"

    def _scrub(self, text):
        return usn.scrub_user_stop_body(text, POI, LOC, source_gated=False)

    def test_disclosed_legend_kept(self):
        t = f"Longan is a bar in District 1. A Vietnamese folk tale tells that {self.LEGEND}."
        out, dropped = self._scrub(t)
        self.assertEqual(dropped, [])
        self.assertIn("folk tale tells", out)

    def test_same_legend_undisclosed_dropped(self):
        t = f"Longan is a bar in District 1. In the story, {self.LEGEND}."
        out, dropped = self._scrub(t)
        self.assertEqual(len(dropped), 1)
        self.assertNotIn("hatched", out)

    def test_name_meaning_context_kept(self):
        t = ("Longan is a bar in District 1. The word longan comes from the Chinese "
             "lóngyǎn, which literally means dragon eye.")
        out, dropped = self._scrub(t)
        self.assertEqual(dropped, [])
        self.assertIn("dragon eye", out)

    def test_invented_date_still_dropped(self):
        t = "Longan is a bar in District 1. Longan opened its doors in 2014 beside the river."
        out, dropped = usn.scrub_user_stop_body(t, POI, LOC, source_gated=True)
        self.assertEqual(len(dropped), 1)
        self.assertNotIn("2014", out)

    def test_disclosure_does_not_license_a_first(self):
        t = ("Longan is a bar in District 1. A local legend says Longan was the first "
             "bar in the city to host a drag show.")
        out, dropped = self._scrub(t)
        self.assertEqual(len(dropped), 1)


class Gate(unittest.TestCase):
    SRC = ["name: Longan", "kind: Bar",
           "[context] The word Longan is derived from the Chinese lóngyǎn, literally dragon eye.",
           "[legend] Legend says a dragon's eye became the longan fruit and a boy ate it to gain strength."]

    def gate(self, s):
        return usc.layer_gate(s, "Longan", self.SRC)

    def test_disclosed_legend_kept(self):
        self.assertIsNone(self.gate(
            "A folk tale tells that a dragon's eye became the longan fruit and a boy "
            "ate it to gain strength."))

    def test_undisclosed_legend_dropped(self):
        why = self.gate("A dragon's eye became the longan fruit and a boy ate it to "
                        "gain strength.")
        self.assertIn("undisclosed", why)

    def test_name_meaning_kept(self):
        self.assertIsNone(self.gate(
            "The bar's name comes from the Chinese lóngyǎn, which literally means dragon eye."))

    def test_marker_without_layer3_source_dropped(self):
        why = self.gate("A folk tale tells that the bar's owner buried a pearl in the garden.")
        self.assertIn("without a layer-3 source", why)

    def test_invented_date_dropped_even_when_marked(self):
        self.assertIn("2009", self.gate(
            "A folk tale tells that a dragon's eye became the longan fruit in 2009."))
        self.assertIn("2014", self.gate("Longan opened in 2014."))

    def test_invented_first_and_geography_dropped(self):
        self.assertIsNotNone(self.gate(
            "Legend says the dragon's eye was the first longan the bar served."))
        self.assertIn("first", self.gate("The bar was the first in the city to open late."))
        self.assertIn("geography", self.gate("Longan stands beside the river."))

    def test_year_in_source_is_kept(self):
        src = self.SRC + ["Review sources say it has been open since 2011."]
        self.assertIsNone(usc.layer_gate("Longan has been open since 2011.", "Longan", src))

    def test_unconfirmed_claim_needs_marker(self):
        src = ["[unconfirmed] The bar is rumoured to occupy a former French pharmacy."]
        self.assertIsNone(usc.layer_gate(
            "We couldn't confirm this, but the bar is rumoured to occupy a former French pharmacy.",
            "Longan", src))


class Cleaning(unittest.TestCase):
    def test_truncated_snippet_cut_to_whole_clause(self):
        t = ("The name dragon eye fruit comes from a well-known legend in china: a hero who "
             "slayed a dragon to save his village, and from his spirit grew the ...")
        out = usc._trim_truncated(t)
        self.assertTrue(out.endswith("village."), out)
        self.assertEqual(usc._trim_truncated("Too short, and ..."), "")

    def test_cjk_sentence_keeps_only_the_gloss(self):
        s = ('The character 龙 means "dragon" while 眼 means "eye", so together 龙眼 '
             'literally means "dragon eye".')
        self.assertEqual(usc._clean_sentence(s),
                         'The Chinese characters together literally mean "dragon eye".')

    def test_legend_must_tell_something(self):
        def serp(q):
            return ([{"title": "x", "link": "http://a",
                      "snippet": "An ancient Philippine legend tells the story of how rambutan "
                                 "came to be. One day, a man came across a ..."},
                     {"title": "y", "link": "http://b",
                      "snippet": "The name dragon eye fruit comes from a well-known legend in "
                                 "china: a hero who slayed a dragon to save his village, and "
                                 "from his spirit grew the ..."}], 0)
        out = usc._legend_facts("longan", serp, {})
        self.assertEqual(len(out), 1)
        self.assertIn("slayed a dragon", out[0]["text"])


class Context(unittest.TestCase):
    def test_name_meaning_longan_and_rambutan(self):
        ctx = usc.gather_context(POI, LOC, wiki_fn=wiki, wiki_search_fn=wiki_search,
                                 serp_fn=lambda q: ([], 0.0))
        txt = " ".join(f["text"] for f in ctx["facts"] if f["layer"] == 2)
        self.assertIn("dragon eye", txt)
        ctx = usc.gather_context({"name": "Rambutan"}, LOC, wiki_fn=wiki,
                                 wiki_search_fn=wiki_search, serp_fn=lambda q: ([], 0.0))
        self.assertIn("Malay word rambut", " ".join(f["text"] for f in ctx["facts"]))

    def test_street_story(self):
        poi = {"name": "Thi Bar Saigon", "address": "224 Đề Thám, Phường Phạm Ngũ Lão"}
        place = {"_serper_address": "224 Bùi Viện, Phường Phạm Ngũ Lão, Quận 1"}
        ctx = usc.gather_context(poi, LOC, place=place, wiki_fn=wiki,
                                 wiki_search_fn=wiki_search, serp_fn=lambda q: ([], 0.0))
        self.assertTrue(any(f["kind"] == "street" and "nightlife street" in f["text"]
                            for f in ctx["facts"]), ctx)

    def test_street_name_for_street_stop(self):
        poi = {"name": "The Crazy street"}
        st = usc._street_candidates(poi, None, "Bui Vien Walking Street")
        self.assertEqual(st[0], "Bui Vien")
        self.assertEqual(usc.street_from_address("224 Đề Thám, Phường Phạm Ngũ Lão, Quận 1"),
                         "Đề Thám")

    def test_tradition_from_serper(self):
        def serp(q):
            return ([{"title": "Karaoke in Vietnam", "link": "http://k/1",
                      "snippet": "Karaoke is hugely popular in Vietnam, where families rent "
                                 "private rooms to sing together."}], 0.1)
        ctx = usc.gather_context({"name": "A Star is Born"}, LOC, kind_tokens={"karaoke"},
                                 wiki_fn=lambda t: None, wiki_search_fn=lambda q: [],
                                 serp_fn=serp)
        tr = [f for f in ctx["facts"] if f["kind"] == "tradition"]
        self.assertTrue(tr and "private rooms" in tr[0]["text"])
        self.assertEqual(tr[0]["layer"], 2)

    def test_legend_from_serper_is_layer3(self):
        def serp(q):
            return ([{"title": "The legend of longan", "link": "http://l/1",
                      "snippet": "Folk tales say a dragon gave its eye to a poor boy, and the "
                                 "longan fruit grew from it. It tastes sweet."}], 0.1)
        ctx = usc.gather_context(POI, LOC, wiki_fn=lambda t: None if t != "Longan" else
                                 dict(LONGAN_WIKI, text=LONGAN_WIKI["text"]),
                                 wiki_search_fn=lambda q: [], serp_fn=serp)
        l3 = [f for f in ctx["facts"] if f["layer"] == 3]
        self.assertTrue(l3 and "dragon" in l3[0]["text"])

    def test_district_story_from_address_else_city(self):
        d1 = {"title": "District 1, Ho Chi Minh City", "disambiguation": False,
              "url": "https://en.wikipedia.org/wiki/District_1",
              "text": ("District 1 was the central urban district of Ho Chi Minh City. It is the "
                       "historical birthplace of the city, where the Citadel of Gia Định was built. "
                       "The district had a population of 204,899 people in 2010.\n")}
        hcm = {"title": "Ho Chi Minh City", "disambiguation": False,
               "url": "https://en.wikipedia.org/wiki/Ho_Chi_Minh_City",
               "text": "Ho Chi Minh City, formerly Saigon, is the largest city in Vietnam.\n"}
        wf = lambda t: {"District 1, Ho Chi Minh City": d1, "Ho Chi Minh City": hcm}.get(t)
        ws = lambda q: ["District 1, Ho Chi Minh City"]
        poi = {"name": "X", "address": "15 Lê Thánh Tôn, Quận 1"}
        ctx = usc.gather_context(poi, LOC, wiki_fn=wf, wiki_search_fn=ws,
                                 serp_fn=lambda q: ([], 0))
        dist = [f["text"] for f in ctx["facts"] if f["kind"] == "district"]
        self.assertEqual(len(dist), 2)
        self.assertTrue(all("204,899" not in t for t in dist))      # population skipped
        ctx = usc.gather_context({"name": "Y"}, LOC, wiki_fn=wf, wiki_search_fn=ws,
                                 serp_fn=lambda q: ([], 0))
        self.assertFalse(any(f["kind"] == "city" for f in ctx["facts"]))   # no city padding

    def test_name_is_a_film_title(self):
        page = {"title": "A Star Is Born", "disambiguation": True,
                "url": "https://en.wikipedia.org/wiki/A_Star_Is_Born",
                "text": ("A Star Is Born may refer to:\n== Film ==\n"
                         "A Star Is Born (1937 film), starring Janet Gaynor and Fredric March, directed by W\n"
                         "A Star Is Born (1954 film), starring Judy Garland and James Mason, directed by G\n"
                         "A Star Is Born (1976 film), starring Barbra Streisand and Kris Kristofferson, directed by F\n"
                         "A Star Is Born (2018 film), starring Lady Gaga and Bradley Cooper, directed by B\n")}
        ctx = usc.gather_context({"name": "A Star is Born"}, LOC,
                                 wiki_fn=lambda t: page if t == "A Star is Born" else None,
                                 wiki_search_fn=lambda q: [], serp_fn=lambda q: ([], 0))
        l2 = [f["text"] for f in ctx["facts"] if f["layer"] == 2]
        l3 = [f["text"] for f in ctx["facts"] if f["layer"] == 3]
        self.assertTrue(any("title of a film" in t and "1937" in t for t in l2), l2)
        self.assertTrue(any("Judy Garland in 1954" in t for t in l2), l2)
        self.assertEqual(len(l3), 1)
        self.assertIsNone(usc.layer_gate(
            "We couldn't confirm this, but the name may nod to the film title.", "A Star is Born",
            [f"[context] {t}" for t in l2] + [f"[unconfirmed] {l3[0]}"]))

    def test_no_search_no_facts(self):
        self.assertEqual(usc.gather_context(POI, LOC, allow_search=False)["facts"], [])


TOUR = """Step-by-Step Audio Guided Tour: Ho Chi Minh City - Cycling Tour

Stop 1: Longan

Coordinates: 10.779100, 106.699600

Type/Specialty: Bar

Orientation: Longan is one of the places you chose.

Directions: Cycle on. It is roughly 100 meters away.
"""


class Pipeline(unittest.TestCase):
    NARR = {"orientation": "Longan is one of the stops on your route in Ho Chi Minh City.",
            "body": ("The word longan comes from the Chinese lóngyǎn, which literally means "
                     "dragon eye. The bar's name comes from that fruit. "
                     "A folk tale tells that a dragon gave its eye to a poor boy. "
                     "Nothing else is known.")}

    def _run(self, serp=None):
        seen = {}

        def llm(system, user):
            seen["user"], seen["system"] = user, system
            return ({"stops": [dict(self.NARR, id=0, used=["F1"])]}, 500, 150)
        serp = serp or (lambda q: ([{"title": "Longan legend", "link": "http://l/1",
                                     "snippet": "Folk tales say a dragon gave its eye to a poor "
                                                "boy, and the longan fruit grew from it."}], 0.1))
        usc._CACHE.clear()
        usc._default_wiki_fn = wiki
        try:
            out, rep = use.enrich_user_stops_in_text(
                TOUR, ["Longan"], LOC, api_key="k", places_fn=lambda *a: [],
                fetch_page=lambda u: None, serp_fn=serp, review_snippets=[], llm_fn=llm)
        finally:
            usc._default_wiki_fn = lambda t: None
        return out, rep, seen

    def test_context_only_stop_is_narrated_not_thin(self):
        out, rep, seen = self._run()
        entry = rep["stops"][0]
        self.assertEqual(entry["mode"], "narrated")          # layer 1 empty, layers 2/3 present
        self.assertEqual(entry["specifics"], 0)
        self.assertGreaterEqual(entry["layers"]["2"], 1)
        self.assertGreaterEqual(entry["layers"]["3"], 1)
        self.assertIn("LAYER 2", seen["user"])
        self.assertIn("[legend]", seen["user"])
        self.assertIn("disclosure", seen["system"])
        self.assertNotIn("one of the places you chose", out)

    def test_all_layers_empty_stays_short_deterministic(self):
        usc._CACHE.clear()
        out, rep = use.enrich_user_stops_in_text(
            TOUR, ["Longan"], LOC, api_key="k", places_fn=lambda *a: [],
            fetch_page=lambda u: None, serp_fn=lambda q: ([], 0.0), review_snippets=[],
            llm_fn=lambda s, u: ({"stops": []}, 0, 0))
        self.assertEqual(rep["stops"][0]["mode"], "thin_deterministic")
        self.assertIn("Longan", out)

    def test_verifier_keeps_disclosed_drops_undisclosed_and_invented(self):
        body = (
            "Longan is one of the stops on your route in Ho Chi Minh City. "
            "The word longan comes from the Chinese lóngyǎn, which literally means dragon eye. "
            "A folk tale tells that a dragon gave its eye to a poor boy. "
            "A dragon gave its eye to a poor boy and the longan fruit grew from it. "
            "Longan opened in 2014.")
        text = TOUR.replace("Orientation: Longan is one of the places you chose.",
                            "Orientation: " + body)

        def fake(system, user, key, model, timeout=40, max_tokens=1500):
            return ({"stops": [{"id": 0, "labels": [
                {"i": j, "label": "SUPPORTED"} for j in range(10)]}]}, 10, 5)
        orig = usv._call_openai
        usv._call_openai = fake
        try:
            new, vrep = usv.verify_user_stops_in_text(
                text, ["Longan"], LOC, api_key="k", serp_fn=lambda q: ([], 0.0),
                material_by_title={"Longan": [
                    "[context] The word Longan is derived from Chinese lóngyǎn, literally dragon eye.",
                    "[legend] Folk tales say a dragon gave its eye to a poor boy, and the longan "
                    "fruit grew from it."]},
                retrieve=False)
        finally:
            usv._call_openai = orig
        self.assertIn("folk tale tells", new)
        self.assertIn("literally means dragon eye", new)
        self.assertNotIn("2014", new)
        self.assertEqual(new.count("a dragon gave its eye"), 1)   # only the disclosed copy


if __name__ == "__main__":
    unittest.main()
