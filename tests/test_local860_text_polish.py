r"""
LOCAL-860 — wave-26 text findings (GCloud_Storied_1, gen 00031-hp4).
====================================================================
1. possessive apostrophe survives input sanitising ("Sophias" -> "Sophia's")
2. tour_name uses the transport label ("biking Tour" -> "Cycling Tour")
3. an orphaned back-reference sentence ("This juxtaposition…") is dropped with
   the sentence it pointed at; never empties a stop
4. emoji / pictographs never reach TTS
5. + 7. "A and B walk, City" names two places -> both become stops
        (Boston Common + Old North Church; Hoan Kiem Lake + Temple of Literature)
6. the per-stop Serper query context is the city/district, not the tour title

These tests CALL the real functions (D418/D421).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import text_polish as tp


# ── 1. apostrophe ────────────────────────────────────────────────────────────
class TestApostropheKept(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tour_orchestrator_service as orch
        cls.orch = orch

    def test_straight_apostrophe_kept_in_title(self):
        self.assertEqual(
            "Sophia's biking tour in Ho Chi Minh City",
            self.orch.sanitize_input("Sophia's biking tour in Ho Chi Minh City"))

    def test_curly_apostrophe_kept(self):
        self.assertEqual("Sophia\u2019s biking tour",
                         self.orch.sanitize_input("Sophia\u2019s biking tour"))

    def test_injection_characters_still_removed(self):
        out = self.orch.sanitize_input("<script>\"x\"</script> O'Brien")
        for ch in "<>\"":
            self.assertNotIn(ch, out)
        self.assertIn("O'Brien", out)

    def test_user_stop_names_keep_apostrophe(self):
        clean, err = self.orch.validate_stops(["Rambutan", "Joe's Diner"])
        self.assertIsNone(err)
        self.assertEqual(["Rambutan", "Joe's Diner"], clean)


# ── 2. tour_name label ───────────────────────────────────────────────────────
class TestTourLabel(unittest.TestCase):
    def test_transport_labels(self):
        self.assertEqual("Cycling Tour", tp.tour_type_display_label("biking"))
        self.assertEqual("Cycling Tour", tp.tour_type_display_label("bike"))
        self.assertEqual("Cycling Tour", tp.tour_type_display_label("cycling"))
        self.assertEqual("Walking Tour", tp.tour_type_display_label("walking"))
        self.assertEqual("Driving Tour", tp.tour_type_display_label("driving"))

    def test_never_lowercase_biking(self):
        self.assertNotIn("biking", tp.tour_type_display_label("biking"))

    def test_idempotent_and_no_double_tour(self):
        self.assertEqual("Cycling Tour", tp.tour_type_display_label("Cycling Tour"))
        self.assertEqual("Museum Tour", tp.tour_type_display_label("museum"))

    def test_orchestrator_fallback_uses_label(self):
        # The fallback line in the orchestrator must call the label helper.
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "tour_orchestrator_service.py"),
            encoding="utf-8").read()
        self.assertIn("_effective_tour_suffix = _tt_label860(tour_type)", src)
        self.assertNotIn('_effective_tour_suffix = f"{tour_type} Tour"', src)


# ── 3. orphaned back-reference ───────────────────────────────────────────────
class TestOrphanRule(unittest.TestCase):
    S = ["An Spa is a wellness spa in District 3.",           # 0 kept
         "It was founded as a colonial villa in 1902.",       # 1 dropped
         "This juxtaposition of old and new is striking.",    # 2 orphan
         "Their treatments use local herbs.",                 # 3 orphan (cascade)
         "Look for the green door."]                          # 4 kept

    def test_next_backref_dropped_and_cascades(self):
        flags, newly = tp.apply_orphan_rule(self.S, [True, False, True, True, True])
        self.assertEqual([True, False, False, False, True], flags)
        self.assertEqual([2, 3], newly)

    def test_non_backref_after_drop_is_kept(self):
        s = ["A.", "B dropped.", "Longan sits on Nguyen Hue.", "C."]
        flags, newly = tp.apply_orphan_rule(s, [True, False, True, True])
        self.assertEqual([True, False, True, True], flags)
        self.assertEqual([], newly)

    def test_backref_without_a_drop_is_kept(self):
        s = ["A bar.", "This place is lively."]
        flags, newly = tp.apply_orphan_rule(s, [True, True])
        self.assertEqual([True, True], flags)

    def test_all_openers(self):
        for op in ("This", "These", "That", "Those", "It", "Its", "His", "Her",
                   "Their", "Such", "The contrast", "The juxtaposition"):
            self.assertTrue(tp.starts_with_backref(f"{op} is notable."), op)
        self.assertFalse(tp.starts_with_backref("Thursday is busy."))
        self.assertFalse(tp.starts_with_backref("Items sell fast."))
        self.assertFalse(tp.starts_with_backref("The garden is quiet."))

    def test_never_empties_a_stop(self):
        s = ["Dropped one.", "This remains."]
        flags, newly = tp.apply_orphan_rule(s, [False, True])
        self.assertEqual([False, True], flags, "the last kept sentence stays")
        self.assertEqual([], newly)

    def test_does_not_mutate_input(self):
        flags_in = [True, False, True]
        tp.apply_orphan_rule(["a", "b", "This c."], flags_in)
        self.assertEqual([True, False, True], flags_in)

    def test_scrub_user_stop_body_drops_orphan(self):
        from user_stop_narration import scrub_user_stop_body
        poi = {"name": "An Spa", "title": "An Spa", "user_explicit": True,
               "type_specialty": "Spa"}
        body = ("An Spa is a quiet spa in District 3. "
                "Hồ Chí Minh led the 1975 offensive and the city is named for him. "
                "This juxtaposition of calm and history is striking. "
                "Book a massage at the front desk.")
        out, dropped = scrub_user_stop_body(body, poi, "Ho Chi Minh City")
        self.assertNotIn("This juxtaposition", out)
        self.assertIn("An Spa is a quiet spa", out)
        self.assertIn("Book a massage", out)
        self.assertEqual(2, len(dropped))

    def test_verifier_path_drops_orphan(self):
        import user_stop_verify as usv
        tour = (
            "Stop 1: An Spa\n"
            "Coordinates: 10.7820, 106.6935\n"
            "Type/Specialty: Spa\n"
            "Orientation: Look for An Spa in District 3.\n"
            "An Spa is a quiet spa. It was a colonial villa in 1902. "
            "This juxtaposition is striking. Book a massage.\n"
            "Directions: Head north.\n")
        # Offline: no key => the verify call does not run; call the pure helper
        # on the same sentences instead (the integration is the apply_orphan_rule
        # call inside verify_user_stops_in_text).
        src = open(usv.__file__, encoding="utf-8").read()
        self.assertIn("apply_orphan_rule(sentences, keep_flags)", src)
        sents = ["An Spa is a quiet spa.", "It was a colonial villa in 1902.",
                 "This juxtaposition is striking.", "Book a massage."]
        flags, _ = tp.apply_orphan_rule(sents, [True, False, True, True])
        self.assertEqual([True, False, False, True], flags)
        self.assertTrue(tour)


# ── 4. emoji never spoken ────────────────────────────────────────────────────
class TestEmojiStripped(unittest.TestCase):
    def test_exact_string(self):
        self.assertEqual("The LGBT bar Thi Bar Saigon",
                         tp.strip_emoji_for_tts("The LGBT bar \U0001F308Thi Bar Saigon"))

    def test_zwj_flag_and_keycap_sequences(self):
        out = tp.strip_emoji_for_tts("Pride \U0001F3F3\uFE0F\u200D\U0001F308 stop 1\uFE0F\u20E3 now")
        self.assertEqual("Pride stop 1 now", out)

    def test_plain_text_and_diacritics_untouched(self):
        s = "Chùa Ngọc Hoàng, 10:30 — Nguyễn Huệ & Co. (open) © 2026"
        self.assertEqual(s, tp.strip_emoji_for_tts(s))

    def test_newlines_preserved(self):
        self.assertEqual("Stop 2: Bar\nDirections: go.",
                         tp.strip_emoji_for_tts("Stop 2: \U0001F378Bar\nDirections: go."))

    def test_modernized_tts_payload_has_no_emoji(self):
        import tour_generation_modernized as tgm
        text = ("Stop 3: \U0001F308Thi Bar\nOrientation: The LGBT bar "
                "\U0001F308Thi Bar Saigon is lively.\nDirections: Walk to \U0001F6B2 Rambutan.")
        out = tgm._strip_nav_fields_for_tts(text)
        self.assertNotRegex(out, "[\U0001F000-\U0001FAFF\u2600-\u27BF]")
        self.assertIn("Thi Bar Saigon is lively.", out)
        self.assertIn("Rambutan", out)

    def test_polly_service_cleans_text_before_synthesis(self):
        import polly_tts_service as pts

        seen = []

        class FakeStream:
            def read(self):
                return b"ID3fake"

        class FakePolly:
            def synthesize_speech(self, **kw):
                seen.append(kw["Text"])
                return {"AudioStream": FakeStream()}

        old = pts.polly_client
        pts.polly_client = FakePolly()
        try:
            client = pts.app.test_client()
            resp = client.post("/synthesize", json={
                "text": "The LGBT bar \U0001F308Thi Bar Saigon", "voice_id": "Joanna"})
        finally:
            pts.polly_client = old
        self.assertEqual(200, resp.status_code, resp.data[:200])
        self.assertTrue(seen, "Polly was never called")
        for t in seen:
            self.assertNotIn("\U0001F308", t)
            self.assertIn("Thi Bar Saigon", t)


# ── 5 + 7. named places in the subject ───────────────────────────────────────
class TestNamedPlacesFromSubject(unittest.TestCase):
    def test_boston_exact_string(self):
        self.assertEqual(
            ["Boston Common", "Old North Church"],
            tp.named_places_from_subject(
                "Boston Common and Old North Church walk, Boston"))

    def test_hanoi_exact_string(self):
        self.assertEqual(
            ["Hoan Kiem Lake", "Temple of Literature"],
            tp.named_places_from_subject(
                "Hoan Kiem Lake and Temple of Literature walk, Hanoi"))

    def test_leading_tour_phrase_form(self):
        self.assertEqual(
            ["Boston Common", "Old North Church"],
            tp.named_places_from_subject(
                "Walking tour of Boston Common and Old North Church, Boston"))

    def test_themes_and_single_places_are_not_named_stops(self):
        for s in ("Food and Wine walk, Boston",
                  "Arts and Crafts walking tour, Boston",
                  "Beacon Hill walking tour, Boston",
                  "Dinner at Sycamore and Little Big Diner in Newton Centre",
                  "Sophia's biking tour in Ho Chi Minh City",
                  "Boston Common and Old North Church",   # no tour phrase at all
                  ""):
            self.assertEqual([], tp.named_places_from_subject(s), s)

    def test_clause_extractor_unions_subject_form(self):
        from area_resolver import extract_named_places_from_clause as enp
        self.assertEqual(["Boston Common", "Old North Church"],
                         enp("Boston Common and Old North Church walk, Boston"))
        self.assertEqual(["Hoan Kiem Lake", "Temple of Literature"],
                         enp("Hoan Kiem Lake and Temple of Literature walk, Hanoi"))
        # the original "including" grammar is unchanged
        self.assertEqual(["Witchcraft Victims Memorial"],
                         enp("Walking tour in Danvers, MA including Witchcraft Victims Memorial"))


class TestNamedPlacesBecomeStops(unittest.TestCase):
    """The pool the discovery returned held the State House and Paul Revere
    House; the two named places must be stops (front of the list, anchored so the
    tail trim and the gates cannot drop them), with real pins."""

    @staticmethod
    def _new_poi(name, address=""):
        return {"name": name, "address": address}

    def _run(self, request, pool, hits, city):
        import area_resolver as ar
        area = ar.AreaResolution(city_qid="Q1", city_name=city, center_lat=42.36,
                                 center_lng=-71.06, bounding_radius_km=8.0,
                                 resolved=True)
        names = ar.extract_named_places_from_clause(request)

        def fake_ps(name, scope="", scope_center=None, scope_bbox=None):
            return hits.get(name, [])

        return ar.apply_named_place_policy(
            [dict(p) for p in pool], names, area, [], self._new_poi,
            places_search_fn=fake_ps, scope=city, geocode_to_stop=True)

    def test_boston_two_stops(self):
        pool = [{"name": "Massachusetts State House"},
                {"name": "Paul Revere House"}]
        hits = {
            "Boston Common": [{"name": "Boston Common", "latitude": 42.3550,
                               "longitude": -71.0656, "type": "park"}],
            "Old North Church": [{"name": "Old North Church", "latitude": 42.3663,
                                  "longitude": -71.0544, "type": "church"}],
        }
        pois, announce = self._run(
            "Boston Common and Old North Church walk, Boston", pool, hits, "Boston")
        top2 = [p["name"] for p in pois[:2]]
        self.assertEqual({"Boston Common", "Old North Church"}, set(top2))
        self.assertEqual([], announce)
        for p in pois[:2]:
            self.assertTrue(p["user_explicit"] and p["_anchor"])
            self.assertIsNotNone(p["latitude"])
            self.assertIsNotNone(p["longitude"])

    def test_hanoi_temple_of_literature_is_a_stop(self):
        pool = [{"name": "Hoan Kiem Lake"}, {"name": "Ngoc Son Temple"}]
        hits = {"Temple of Literature": [{"name": "Temple of Literature",
                                          "latitude": 21.0285, "longitude": 105.8355,
                                          "type": "temple"}]}
        pois, announce = self._run(
            "Hoan Kiem Lake and Temple of Literature walk, Hanoi", pool, hits, "Hanoi")
        names = [p["name"] for p in pois]
        self.assertIn("Temple of Literature", names)
        self.assertIn("Hoan Kiem Lake", names)
        lake = next(p for p in pois if p["name"] == "Hoan Kiem Lake")
        self.assertTrue(lake["user_explicit"], "the existing candidate is flagged, not replaced")
        self.assertEqual([], announce)


# ── 6. Serper query context ──────────────────────────────────────────────────
class TestSerperQueryContext(unittest.TestCase):
    TITLE = "Sophia's biking tour in Ho Chi Minh City"

    def test_city_from_scope(self):
        self.assertEqual("Ho Chi Minh City", tp.city_from_scope(self.TITLE))
        self.assertEqual("Ho Chi Minh City", tp.city_from_scope("Sophia's bike tour of HCMC"))
        self.assertEqual("Ho Chi Minh City", tp.city_from_scope("Ho Chi Minh City, Vietnam"))
        self.assertEqual("Museum of Fine Arts", tp.city_from_scope("Museum of Fine Arts, Boston"))
        self.assertEqual("", tp.city_from_scope("Sophia's biking tour"))

    def test_exact_query_from_title(self):
        import user_stop_verify as usv
        self.assertEqual('"Rambutan" Ho Chi Minh City',
                         usv._build_stop_query("Rambutan", {}, self.TITLE))

    def test_district_still_preferred(self):
        import user_stop_verify as usv
        poi = {"address": "15 Pasteur, Ben Nghe, District 1, Ho Chi Minh City"}
        self.assertEqual('"Rambutan" District 1',
                         usv._build_stop_query("Rambutan", poi, self.TITLE))

    def test_query_never_contains_title_words(self):
        import user_stop_verify as usv
        q = usv._build_stop_query("Rambutan", {}, self.TITLE)
        for w in ("Sophia", "biking", "bike", "tour"):
            self.assertNotIn(w, q)

    def test_retrieval_sends_clean_query(self):
        import user_stop_verify as usv
        sent = []

        def fake_serp(q):
            sent.append(q)
            return [], 0.0

        usv.retrieve_user_stop_snippets("Rambutan", {}, self.TITLE, serp_fn=fake_serp)
        self.assertEqual(['"Rambutan" Ho Chi Minh City'], sent)

    def test_fallback_orientation_says_city_not_title(self):
        import user_stop_verify as usv
        o = usv._deterministic_orientation({"name": "Rambutan"}, self.TITLE)
        self.assertEqual("Look for Rambutan in Ho Chi Minh City.", o)


if __name__ == "__main__":
    unittest.main()
