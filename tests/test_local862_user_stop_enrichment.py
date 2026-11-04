"""LOCAL-862 — user-stop enrichment (offline: every network call is injected)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_stop_enrichment as use
import user_stop_verify as usv

LOC = "Sophia's biking tour in Ho Chi Minh City"

TOUR = """Step-by-Step Audio Guided Tour: Ho Chi Minh City - Cycling Tour

Stop 1: Rambutan

Coordinates: 10.776100, 106.696200

Type/Specialty: Restaurant and bar

Orientation: Rambutan is one of the places you chose, here in Ho Chi Minh City.

Directions: Cycle east to Longan. It is roughly 500 meters away.

Stop 2: Longan

Coordinates: 10.779100, 106.699600

Type/Specialty: Bar

Orientation: Longan is one of the places you chose.

Directions: Cycle on. It is roughly 100 meters away.

Stop 3: Notre-Dame Cathedral Basilica of Saigon

Coordinates: 10.779800, 106.699000

Type/Specialty: Cathedral

Orientation: Built 1863 to 1880 from Marseille brick.

If you would like to eat nearby we can build you a restaurant tour.
"""

PLACE = {
    "name": "Rambutan", "lat": "10.7761", "lon": "106.6962",
    "_serper_category": "Restaurant", "_serper_address": "15 Lê Thánh Tôn, District 1",
    "_serper_rating": 4.6, "_serper_rating_count": 1234,
    "_serper_price_level": "$$", "_serper_website": "https://rambutan.example/",
    "_serper_cid": "99", "_serper_hours": "Open daily 11:00-23:00",
}
REVIEWS = ["Great cocktails and friendly staff at Rambutan",
           "The cocktails are the reason to come, very friendly",
           "Love the cocktails; cozy place"]
HOME = ('<html><head><meta name="description" content="A bar and kitchen in the '
        'centre of Saigon."></head><body><nav>menu</nav><p>Rambutan was founded in '
        '2016 by two friends from Hanoi who wanted a bar that served cocktails '
        'made with local fruit.</p><a href="/our-story">Our story</a></body></html>')
ABOUT = ('<html><body><p>Our signature drink is the lychee and chili cocktail served '
         'over crushed ice every evening.</p></body></html>')


def make_fetch(pages, log):
    def f(url):
        log.append(url)
        return pages.get(url)
    return f


def places(q, scope, near):
    return [PLACE]


def serp(q):
    return ([{"title": "Rambutan Saigon bar", "url": "http://x/y",
              "snippet": "Rambutan is a bar in Ho Chi Minh City owned by two friends."},
             {"title": "Rambutan fruit recipe", "url": "http://x/z",
              "snippet": "How to peel a rambutan and serve it with ice."}], 0.1)


class Kind(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(use.classify_stop_kind("Longan", "Bar"), "business")
        self.assertEqual(use.classify_stop_kind("A Star is Born", "Karaoke Bar"), "business")
        self.assertEqual(use.classify_stop_kind("An Spa", "Spa and wellness center"), "business")
        self.assertEqual(use.classify_stop_kind("The Crazy street", "Street with vibrant nightlife"), "business")
        self.assertEqual(use.classify_stop_kind("Notre-Dame Cathedral Basilica of Saigon", "Cathedral"), "landmark")
        self.assertEqual(use.classify_stop_kind("Independence Palace", ""), "landmark")
        self.assertEqual(use.classify_stop_kind("Tao Dan Park", "Park"), "landmark")
        self.assertEqual(use.classify_stop_kind("Palace Bar", "Bar"), "business")
        self.assertEqual(use.classify_stop_kind("Thi Bar Saigon", ""), "business")


class PlaceGate(unittest.TestCase):
    def test_wrong_venue_or_far_rejected(self):
        far = dict(PLACE, lat="10.80", lon="106.70")
        self.assertIsNone(use.fetch_place_record("Rambutan", LOC, (10.7761, 106.6962),
                                                 places_fn=lambda *a: [far]))
        other = dict(PLACE, name="Banh Mi Huynh Hoa")
        self.assertIsNone(use.fetch_place_record("Rambutan", LOC, (10.7761, 106.6962),
                                                 places_fn=lambda *a: [other]))
        self.assertIsNotNone(use.fetch_place_record("Rambutan", LOC, (10.7761, 106.6962),
                                                    places_fn=places))


class Site(unittest.TestCase):
    def test_two_pages_max_and_sentences_verbatim(self):
        log = []
        pages = {"https://rambutan.example/robots.txt": "User-agent: *\nAllow: /",
                 "https://rambutan.example/": HOME,
                 "https://rambutan.example/our-story": ABOUT,
                 "https://rambutan.example/menu": "<p>NEVER FETCHED</p>"}
        res = use.fetch_site_facts("https://rambutan.example/", make_fetch(pages, log))
        pg = [u for u in log if not u.endswith("robots.txt")]
        self.assertEqual(len(pg), 2)
        self.assertEqual(res["pages"], ["https://rambutan.example/",
                                        "https://rambutan.example/our-story"])
        self.assertTrue(any("founded in 2016" in s for s in res["sentences"]))
        self.assertTrue(any("lychee and chili" in s for s in res["sentences"]))
        self.assertIn("centre of Saigon", res["description"])

    def test_robots_disallow_means_no_page_fetch(self):
        log = []
        pages = {"https://rambutan.example/robots.txt": "User-agent: *\nDisallow: /",
                 "https://rambutan.example/": HOME}
        res = use.fetch_site_facts("https://rambutan.example/", make_fetch(pages, log))
        self.assertTrue(res["blocked_by_robots"])
        self.assertEqual([u for u in log if not u.endswith("robots.txt")], [])

    def test_social_hosts_skipped(self):
        log = []
        res = use.fetch_site_facts("https://www.facebook.com/rambutan", make_fetch({}, log))
        self.assertEqual(log, [])
        self.assertEqual(res["sentences"], [])


class Material(unittest.TestCase):
    def _mat(self, **kw):
        pages = {"https://rambutan.example/robots.txt": "",
                 "https://rambutan.example/": HOME,
                 "https://rambutan.example/our-story": ABOUT}
        poi = {"name": "Rambutan", "coordinates": "10.776100, 106.696200",
               "type_specialty": "Restaurant and bar"}
        return use.gather_material(poi, LOC, places_fn=places,
                                   fetch_page=make_fetch(pages, []), serp_fn=serp,
                                   review_snippets=REVIEWS, **kw)

    def test_rich_material_has_sources(self):
        m = self._mat()
        kinds = {f["kind"] for f in m["facts"]}
        self.assertTrue({"rating", "price", "hours", "signature", "site", "story"} <= kinds)
        self.assertGreaterEqual(m["specifics"], 5)
        for f in m["facts"]:
            self.assertTrue(f["source"])
        story = [f for f in m["facts"] if f["kind"] == "story"]
        self.assertEqual(len(story), 1)          # the fruit-recipe snippet is rejected
        self.assertIn("two friends", story[0]["text"])
        self.assertEqual(m["calls"]["story_search"], 1)
        self.assertEqual(m["calls"]["places"], 1)

    def test_no_search_no_material(self):
        poi = {"name": "Longan", "coordinates": "10.7791, 106.6996"}
        m = use.gather_material(poi, LOC, allow_search=False, review_snippets=[])
        self.assertEqual(m["specifics"], 0)


class Pipeline(unittest.TestCase):
    def _run(self, llm_text, places_fn=places, serp_fn=serp):
        pages = {"https://rambutan.example/robots.txt": "",
                 "https://rambutan.example/": HOME,
                 "https://rambutan.example/our-story": ABOUT}

        def llm(system, user):
            self.assertIn("ONLY source", system)
            self.assertIn("FACT LIST", user)
            self.assertIn("Rambutan", user)
            return ({"stops": [{"id": 0, "text": llm_text, "used": ["F1"]}]}, 900, 200)
        return use.enrich_user_stops_in_text(
            TOUR, ["Rambutan", "Longan", "Notre-Dame Cathedral Basilica of Saigon"], LOC,
            api_key="k", places_fn=places_fn, fetch_page=make_fetch(pages, []),
            serp_fn=serp_fn, review_snippets=REVIEWS, llm_fn=llm)

    NARR = ("Rambutan is a restaurant and bar on Lê Thánh Tôn in District 1. "
            "It was founded in 2016 by two friends from Hanoi. "
            "Google reviewers give it 4.6 out of 5 from about 1,200 reviews. "
            "Reviewers keep mentioning the cocktails. "
            "The lychee and chili cocktail is the signature drink.")

    def test_rich_stop_narrated_thin_stop_short_landmark_untouched(self):
        out, rep = self._run(self.NARR)
        # Rambutan: narrated, and the field/Directions structure survives
        blk = out.split("Stop 2:")[0]
        self.assertIn("founded in 2016", blk)
        self.assertIn("Coordinates: 10.776100, 106.696200", blk)
        self.assertIn("Directions: Cycle east to Longan", blk)
        self.assertNotIn("one of the places you chose", blk)
        # Longan: the places stub only matches Rambutan -> thin deterministic
        blk2 = out.split("Stop 2:")[1].split("Stop 3:")[0]
        self.assertIn("Longan", blk2)
        self.assertIn("Directions: Cycle on", blk2)
        # Notre-Dame untouched, conclusion recap kept
        self.assertIn("Built 1863 to 1880 from Marseille brick.", out)
        self.assertIn("If you would like to eat nearby", out)
        modes = {s["stop"]: s.get("mode", s["kind"]) for s in rep["stops"]}
        self.assertEqual(modes["Rambutan"], "narrated")
        self.assertEqual(modes["Longan"], "thin_deterministic")
        self.assertEqual(modes["Notre-Dame Cathedral Basilica of Saigon"], "landmark")
        self.assertIn("Longan", rep["precomposed"])
        self.assertIn("Rambutan", rep["material_by_title"])
        self.assertLessEqual(rep["total_cost_usd"], 0.02)

    def test_orientation_and_body_slots(self):
        pages = {"https://rambutan.example/robots.txt": "",
                 "https://rambutan.example/": HOME,
                 "https://rambutan.example/our-story": ABOUT}

        def llm(system, user):
            self.assertIn("more than three items", system)
            return ({"stops": [{"id": 0,
                                "orientation": "Rambutan is a restaurant at 15 Lê Thánh Tôn.",
                                "body": "It was founded in 2016 by two friends from Hanoi. "
                                        "Google reviewers give it 4.6 out of 5."}]}, 1, 1)
        out, _ = use.enrich_user_stops_in_text(
            TOUR, ["Rambutan"], LOC, api_key="k", places_fn=places,
            fetch_page=make_fetch(pages, []), serp_fn=serp,
            review_snippets=REVIEWS, llm_fn=llm)
        self.assertIn("Orientation: Rambutan is a restaurant at 15 Lê Thánh Tôn.\n", out)
        self.assertIn("\nIt was founded in 2016 by two friends from Hanoi. Google", out)

    def test_thin_stop_uses_places_data_not_empty(self):
        def one_longan(q, scope, near):
            return [dict(PLACE, name="Longan", lat="10.7791", lon="106.6996",
                         _serper_website="", _serper_cid="7")]
        out, rep = self._run(self.NARR, places_fn=one_longan, serp_fn=lambda q: ([], 0.0))
        blk2 = out.split("Stop 2:")[1].split("Stop 3:")[0]
        # rating + price + hours are in the thin body
        self.assertIn("4.6", blk2)
        self.assertIn("11:00-23:00", blk2)

    def test_verifier_uses_material_and_skips_serper(self):
        out, rep = self._run(self.NARR)
        calls = []

        def must_not_search(q):
            calls.append(q)
            return ([], 0.0)
        # verifier labels everything SUPPORTED; the Rambutan sentences must survive
        orig = usv._call_openai

        def fake(system, user, key, model, timeout=40, max_tokens=1500):
            self.assertIn("lychee and chili", user)      # material is the fact sheet
            import re
            ids = re.findall(r"STOP id=(\d+)", user)
            return ({"stops": [{"id": int(i), "labels": [
                {"i": j, "label": "SUPPORTED"} for j in range(12)]} for i in ids]}, 100, 50)
        usv._call_openai = fake
        try:
            new, vrep = usv.verify_user_stops_in_text(
                out, ["Rambutan", "Longan", "Notre-Dame Cathedral Basilica of Saigon"],
                LOC, api_key="k", serp_fn=must_not_search,
                material_by_title=rep["material_by_title"],
                precomposed_titles=rep["precomposed"])
        finally:
            usv._call_openai = orig
        self.assertEqual(calls, [])                    # no extra Serper query
        self.assertIn("founded in 2016", new)
        self.assertEqual(vrep["dropped_total"], 0)


class Filters(unittest.TestCase):
    """The first live run let fruit / film / province / other-branch snippets
    through. Each case below is a REAL snippet from that run."""
    def test_rejects_off_venue_snippets(self):
        bad = [
            (["Rambutan"], "Some of the unique fruits you might find in Vietnam during "
             "this time include: 1. Rambutan: A small, red fruit with a hairy outer layer"),
            (["Longan"], ".longan.gov.vn. Tôn Thạnh Temple, an ancient temple in Long An. "
             "The region is between Ho Chi Minh City and Southeast region"),
            (["A Star is Born"], "The film follows three people in the city of Ho Chi Minh "
             "and shows the ways in which these lives intertwine. A Star is Born"),
            (["The Crazy street"], "From the crazy street traffic of Hanoi to the beauty "
             "of Halong bay to the charming lanterns of Hoi An"),
            (["Rambutan"], "Bar & Grill fans group for expats and travellers in Asia. ... rambutan - while we were in Ho Chi Minh "
             "City, Vietnam. Our attempts at picking fruit that was ripe and ready to eat"),
            (["A Star is Born"], "... history as the first overseas Vietnamese to receive "
             "the Ho Chi Minh ... A star is born ! French TV show. Vietnamese TV show"),
            (["An Spa"], "Independence Palace: A living chapter of Vietnam's history ... "
             "Healing Destination Hoi An - Spa & Garden Dining"),
        ]
        for names, txt in bad:
            self.assertFalse(use.snippet_is_about_venue(txt, names, LOC), txt[:40])

    def test_rejects_other_branch_address(self):
        place = {"_serper_address": "6E1 Ngô Thời Nhiệm"}
        txt = ("Tucked away in a quiet alley at 384/17 Nam Kỳ Khởi Nghĩa, Acoustic Bar "
               "feels like one of those rare finds in Saigon.")
        self.assertFalse(use.snippet_is_about_venue(txt, ["Acoustic Bar"], LOC, place=place))

    def test_keeps_real_venue_snippets(self):
        good = [
            (["Acoustic Bar"], "Minh, a former musician himself, created Acoustic Bar in "
             "Saigon because he wanted to feel the joy of live music."),
            (["Thi Bar Saigon"], "Thi Bar Saigon is a popular spot located in the heart of "
             "Saigon's tourist area, offering live music and friendly staff."),
            (["The Crazy street", "Bui Vien Walking Street"], "Bui Vien Walking Street is "
             "the backpacker nightlife street of District 1, Ho Chi Minh City."),
        ]
        for names, txt in good:
            self.assertTrue(use.snippet_is_about_venue(txt, names, LOC), txt[:40])


class PlaceAliasAndBrand(unittest.TestCase):
    def test_alias_from_maps_url_matches(self):
        rec = {"name": "Bui Vien Walking Street", "lat": "10.7673", "lon": "106.6939",
               "_serper_category": "Tourist attraction"}
        got = use.fetch_place_record("The Crazy street", LOC, (10.7672, 106.6930),
                                     places_fn=lambda *a: [rec],
                                     alias="Bui Vien Walking Street")
        self.assertIsNotNone(got)
        self.assertIsNone(use.fetch_place_record("The Crazy street", LOC,
                                                 (10.7672, 106.6930),
                                                 places_fn=lambda *a: [rec]))

    def test_brand_domain_extends_radius_only_for_own_domain(self):
        rec = {"name": "AN’s spa", "lat": "10.7880", "lon": "106.6905",
               "_serper_website": "https://an-spa.vn/"}
        pin = (10.7820, 106.6935)
        self.assertIsNotNone(use.fetch_place_record("An Spa", LOC, pin,
                                                    places_fn=lambda *a: [rec]))
        other = dict(rec, _serper_website="https://somechain.com/")
        self.assertIsNone(use.fetch_place_record("An Spa", LOC, pin,
                                                 places_fn=lambda *a: [other]))

    def test_brand_match_gives_brand_facts_not_branch_address_or_rating(self):
        rec = {"name": "AN’s spa", "lat": "10.7880", "lon": "106.6905",
               "_serper_website": "https://an-spa.vn/", "_serper_category": "Massage spa",
               "_serper_address": "Hẻm 18Bis/13 Nguyễn Thị Minh Khai",
               "_serper_rating": 4.9, "_serper_rating_count": 5300}
        poi = {"name": "An Spa", "coordinates": "10.7820, 106.6935"}
        m = use.gather_material(poi, LOC, places_fn=lambda *a: [rec],
                                fetch_page=lambda u: None, serp_fn=lambda q: ([], 0),
                                review_snippets=[])
        kinds = [f["kind"] for f in m["facts"]]
        self.assertIn("category", kinds)
        self.assertNotIn("address", kinds)
        self.assertNotIn("rating", kinds)
        self.assertNotIn("Minh Khai", use.thin_stop_body(poi, m, LOC))

    def test_type_line_set_from_places(self):
        lines = ["Stop 1: X", "", "Coordinates: 1.0, 2.0", "", "Orientation: x"]
        d = use._set_type_line(lines, 1, len(lines), "Gay bar")
        self.assertEqual(d, 2)
        self.assertIn("Type/Specialty: Gay bar", lines)


class HonestThin(unittest.TestCase):
    """Live run 2: the thin body spoke the GENERATOR's Type/Examples guesses —
    'A Star is Born is a café … artisan coffee, homemade pastries' (it is a
    karaoke bar). The thin body and the field lines may state only sourced kind."""
    def test_thin_body_ignores_generator_guesses(self):
        poi = {"name": "A Star is Born", "type_specialty": "Café",
               "specific_examples": "Artisan coffee, homemade pastries"}
        mat = {"name": "A Star is Born", "facts": [], "place": None, "category": ""}
        body = use.thin_stop_body(poi, mat, LOC)
        self.assertNotIn("café", body.lower())
        self.assertNotIn("pastries", body.lower())
        self.assertIn("A Star is Born", body)

    def test_kind_from_name_only_when_name_says_it(self):
        mat = {"facts": [], "category": ""}
        self.assertEqual(use.sourced_kind("An Spa", mat), "spa")
        self.assertEqual(use.sourced_kind("Longan", mat), "")
        self.assertEqual(use.sourced_kind("Longan", {"facts": [], "category": "Bar"}), "Bar")

    def test_unsourced_field_lines_removed(self):
        lines = ["Stop 1: Longan", "", "Coordinates: 1.0, 2.0", "",
                 "Type/Specialty: Dessert Shop", "",
                 "Specific Examples: Sweet soups", "", "Orientation: x", "",
                 "Directions: on"]
        d = use._set_sourced_fields(lines, 1, len(lines), "", "")
        self.assertEqual(d, -4)
        self.assertFalse(any(l.startswith(("Type/", "Specific")) for l in lines))
        self.assertIn("Directions: on", lines)


class PhraseListReviewCounts(unittest.TestCase):
    def test_review_count_is_not_population(self):
        import user_stop_narration as usn
        poi = {"name": "Acoustic Bar", "user_explicit": True,
               "type_specialty": "Live music bar"}
        txt = "Google reviewers give it 4.5 out of 5 from about 3,200 reviews."
        out, dropped = usn.scrub_user_stop_body(txt, poi, LOC, outdoor_facts=["x"])
        self.assertEqual(dropped, [])
        pop = "Cần Thơ has 4,199,824 inhabitants and a bar."
        _, d2 = usn.scrub_user_stop_body(pop + " " + txt, poi, LOC, outdoor_facts=["x"])
        self.assertEqual(len(d2), 1)


class LandmarkRobust(unittest.TestCase):
    def test_palace_typed_historical_site_is_landmark(self):
        self.assertEqual(use.classify_stop_kind("Independence Palace", "Historical Site"),
                         "landmark")
        self.assertEqual(use.classify_stop_kind("War Remnants", "Historical museum"),
                         "landmark")

    def test_verifier_skips_palace_whatever_its_type(self):
        txt = ("Stop 1: Independence Palace\n\nCoordinates: 10.77, 106.69\n\n"
               "Type/Specialty: Historical Site\n\nOrientation: Built 1962 to 1966.\n")
        orig = usv._call_openai
        usv._call_openai = lambda *a, **k: self.fail("verifier must not run")
        try:
            out, rep = usv.verify_user_stops_in_text(
                txt, ["Independence Palace"], LOC, api_key="k", retrieve=False)
        finally:
            usv._call_openai = orig
        self.assertIn("Built 1962 to 1966.", out)


class EmptyOrientation(unittest.TestCase):
    def test_orientation_never_left_empty(self):
        txt = ("Stop 1: Acoustic Bar\n\nCoordinates: 10.78, 106.68\n\n"
               "Orientation: Invented one. Invented two.\n\n"
               "Acoustic Bar was founded in 2007. It shares music culture.\n\n"
               "Directions: on\n")
        orig = usv._call_openai
        usv._call_openai = lambda *a, **k: ({"stops": [{"id": 0, "labels": [
            {"i": 0, "label": "UNSUPPORTED"}, {"i": 1, "label": "UNSUPPORTED"},
            {"i": 2, "label": "SUPPORTED"}, {"i": 3, "label": "SUPPORTED"}]}]}, 1, 1)
        try:
            out, _ = usv.verify_user_stops_in_text(
                txt, ["Acoustic Bar"], LOC, api_key="k",
                material_by_title={"Acoustic Bar": ["Founded in 2007, Acoustic Bar …"]})
        finally:
            usv._call_openai = orig
        self.assertIn("Orientation: Acoustic Bar was founded in 2007.", out)


if __name__ == "__main__":
    unittest.main()
