#!/usr/bin/env python3
"""test_local744_screen_work_disclosure.py — LOCAL-744.

Michael, 2026-10-23, asked for "the episode 1 of season 1 biking tour, Salem, MA"
(WGN America's *Salem*, 2014, S1E1 "The Vow"). The generator ignored "episode 1
of season 1" and shipped a GENERIC Salem bike tour (Salem Maritime NHS, Seven
Gables, Willows, Common, Witch Museum — see fixtures/tour716_full.txt). The show
was filmed in Shreveport, Louisiana, so none of those places appears on screen,
and the tour never said so.

Michael's priority (11:3x): *"The tour will say so when the show was filmed
elsewhere — this is the most important part."* He was happy with the real Salem
stops; the fix ADDS an honest, SOURCED opening in the Orientation, it does not
throw out good places.

RED today, GREEN after the fix:
  * the delivered 716 text (the fixture) carries NO filming-location sentence in
    its Orientation — that is the defect;
  * with the LOCAL-744 disclosure spliced in, the Orientation OPENS with the
    sourced sentence.

Also covered:
  * an UNSOURCED lookup → "we could not confirm where it was filmed" (never a
    guess) — unit test with a mocked lookup;
  * a PLAIN place request ("Salem, MA biking tour") gets NO disclosure sentence
    (no false positive);
  * when the toured place IS a filming location (the Shreveport request Michael
    said he would try next), the disclosure says so, with a source;
  * the existence-gate cause/fix for the dropped real Salem places (Pickering
    Wharf / Winter Island Park / Fort Pickering Lighthouse).

Pure/offline: the filming lookup is INJECTED (mirrors geo_refutation.py), so no
network, no LLM, no DB. Run:
    python3 -m pytest test_local744_screen_work_disclosure.py -q
"""
import os
import re
import unittest

import screen_work_tour as swt


_FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "tour716_full.txt")
with open(_FIXTURE, "r", encoding="utf-8") as _f:
    _TOUR_716 = _f.read()


# ── Injected lookups (offline doubles for the real OpenAI lookup) ─────────────

def _lookup_shreveport(work, location):
    """*Salem* (WGN) filmed in Shreveport, Louisiana — sourced."""
    return {"work_name": "Salem", "filmed_place": "Shreveport, Louisiana",
            "source": "Wikipedia: Salem (TV series)"}


def _lookup_filmed_here(work, location):
    """The toured place IS the filming location — sourced."""
    return {"work_name": "Salem", "filmed_here": True,
            "filmed_place": "Shreveport, Louisiana",
            "source": "Wikipedia: Salem (TV series)"}


def _lookup_unsourced(work, location):
    """A place but NO source — must be treated as 'cannot confirm' (never guess)."""
    return {"work_name": "Salem", "filmed_place": "Shreveport, Louisiana"}


def _lookup_unknown(work, location):
    """Could not confirm at all."""
    return None


class TestScreenWorkDetection(unittest.TestCase):
    """Intent: detect a TV show / film / book — including the title-less case."""

    def test_episode_season_request_is_a_screen_work(self):
        # The exact 716 request names NO title, only "episode 1 of season 1".
        work = swt.detect_screen_work("episode 1 of season 1 biking tour, Salem, MA", {})
        self.assertIsNotNone(work)
        self.assertEqual(work["theme_type"], "TV")

    def test_intent_theme_type_movie(self):
        work = swt.detect_screen_work(
            "Harry Potter tour, Boston",
            {"theme_type": "MOVIE", "theme_name": "Harry Potter"})
        self.assertIsNotNone(work)
        self.assertEqual(work["theme_name"], "Harry Potter")

    def test_plain_place_request_is_not_a_screen_work(self):
        # No work named → no disclosure, no false positive.
        self.assertIsNone(swt.detect_screen_work("Salem, MA biking tour", {}))
        self.assertIsNone(swt.detect_screen_work("restaurant tour, Newton, MA", {}))
        self.assertIsNone(
            swt.detect_screen_work("Salem, MA biking tour",
                                   {"theme_type": "STANDARD"}))


class TestFilmedElsewhereDisclosure(unittest.TestCase):
    """Case 1 — filmed elsewhere than the toured place, sourced."""

    def setUp(self):
        self.work = swt.detect_screen_work(
            "episode 1 of season 1 biking tour, Salem, MA", {})
        self.disc = swt.build_filming_disclosure(
            self.work, "episode 1 of season 1 biking tour, Salem, MA",
            _lookup_shreveport)

    def test_states_where_filmed_and_that_it_differs(self):
        self.assertIn("Shreveport, Louisiana", self.disc)
        self.assertIn("not in Salem", self.disc)
        self.assertIn("none of these places appears on screen", self.disc)

    def test_states_how_the_tour_relates(self):
        self.assertIn("real Salem", self.disc)
        self.assertRegex(self.disc, r"story is set")

    def test_names_the_work(self):
        # The sourced lookup supplied the title the request omitted.
        self.assertIn("Salem", self.disc)


class TestOrientationRedGreenOn716(unittest.TestCase):
    """The headline red→green on the real 716 delivered text."""

    def test_raw_716_has_no_filming_disclosure_today(self):
        # RED: the delivered tour never says where the show was filmed.
        self.assertNotIn("filmed in", _TOUR_716.lower())
        self.assertNotIn("none of these places appears on screen", _TOUR_716)

    def test_orientation_opens_with_sourced_disclosure_after_fix(self):
        work = swt.detect_screen_work(
            "episode 1 of season 1 biking tour, Salem, MA", {})
        disc = swt.build_filming_disclosure(
            work, "episode 1 of season 1 biking tour, Salem, MA",
            _lookup_shreveport)
        fixed = swt.inject_orientation_disclosure(_TOUR_716, disc)
        # GREEN: the Orientation now LEADS with the disclosure.
        m = re.search(r'(?mi)^Orientation:\s*(.+)$', fixed)
        self.assertIsNotNone(m)
        opening = m.group(1)
        self.assertTrue(opening.startswith("The TV series Salem was filmed in Shreveport"),
                        opening[:80])
        self.assertIn("Shreveport, Louisiana", opening)

    def test_injection_is_idempotent(self):
        work = swt.detect_screen_work(
            "episode 1 of season 1 biking tour, Salem, MA", {})
        disc = swt.build_filming_disclosure(
            work, "episode 1 of season 1 biking tour, Salem, MA",
            _lookup_shreveport)
        once = swt.inject_orientation_disclosure(_TOUR_716, disc)
        twice = swt.inject_orientation_disclosure(once, disc)
        self.assertEqual(once, twice)

    def test_the_real_salem_stops_are_untouched(self):
        # The fix ADDS framing; it never removes the good real places.
        work = swt.detect_screen_work(
            "episode 1 of season 1 biking tour, Salem, MA", {})
        disc = swt.build_filming_disclosure(
            work, "episode 1 of season 1 biking tour, Salem, MA",
            _lookup_shreveport)
        fixed = swt.inject_orientation_disclosure(_TOUR_716, disc)
        for place in ("Salem Maritime National Historic Site",
                      "The House of the Seven Gables", "Salem Willows Park",
                      "Salem Common", "Salem Witch Museum"):
            self.assertIn(place, fixed)


class TestUnsourcedNeverGuesses(unittest.TestCase):
    """Unsourced / unknown lookup → honest 'could not confirm', never a guess."""

    def _disc(self, lookup):
        work = swt.detect_screen_work(
            "episode 1 of season 1 biking tour, Salem, MA", {})
        return swt.build_filming_disclosure(
            work, "episode 1 of season 1 biking tour, Salem, MA", lookup)

    def test_unsourced_place_is_not_claimed(self):
        disc = self._disc(_lookup_unsourced)
        self.assertIn("could not confirm", disc.lower())
        # The unsourced place must NOT be asserted as the filming location.
        self.assertNotIn("Shreveport", disc)

    def test_unknown_lookup_says_could_not_confirm(self):
        disc = self._disc(_lookup_unknown)
        self.assertIn("could not confirm", disc.lower())

    def test_crashing_lookup_is_inconclusive_not_a_guess(self):
        def _boom(work, location):
            raise RuntimeError("search infra down")
        disc = self._disc(_boom)
        self.assertIn("could not confirm", disc.lower())


class TestFilmedHereDisclosure(unittest.TestCase):
    """Case 2 — the toured place IS a filming location (the Shreveport request)."""

    def test_says_filmed_here_with_source(self):
        work = swt.detect_screen_work(
            "the episode 1 of season 1 tour, Shreveport, Louisiana", {})
        self.assertIsNotNone(work)
        disc = swt.build_filming_disclosure(
            work, "the episode 1 of season 1 tour, Shreveport, Louisiana",
            _lookup_filmed_here)
        self.assertIn("were filmed in", disc)
        self.assertIn("this tour visits those real places", disc)
        self.assertNotIn("none of these places appears on screen", disc)

    def test_filmed_place_containing_toured_place_reads_as_here(self):
        # When the sourced filming place CONTAINS the toured place, it was filmed
        # here — do not say "not in X".
        work = {"theme_type": "TV", "theme_name": "Salem"}

        def _lk(w, l):
            return {"work_name": "Salem", "filmed_place": "Shreveport, Louisiana",
                    "source": "Wikipedia: Salem (TV series)"}
        disc = swt.build_filming_disclosure(
            work, "biking tour, Shreveport, Louisiana", _lk)
        self.assertNotIn("not in Shreveport", disc)
        self.assertIn("this tour visits those real places", disc)


class TestNoDisclosureForPlainPlace(unittest.TestCase):
    """A plain place request gets NO disclosure sentence anywhere."""

    def test_detect_none_means_no_disclosure(self):
        # The wiring only builds a disclosure when detect_screen_work is truthy.
        self.assertIsNone(swt.detect_screen_work("Salem, MA biking tour", {}))

    def test_inject_empty_disclosure_is_a_noop(self):
        for empty in ("", None):
            self.assertEqual(
                swt.inject_orientation_disclosure(_TOUR_716, empty), _TOUR_716)


class TestExistenceGateRealSalemPlaces(unittest.TestCase):
    """LOCAL-744 task 4: the existence gate must not drop real Salem places.

    Root cause (documented by this test): the robust Wikidata-P625-within-metro /
    OSM existence check (`_check_walking_stop_existence`, LOCAL-662B) was reached
    only for tour_type in ('walking', 'specialized'). Tour 716 is a BIKING tour,
    so Pickering Wharf / Winter Island Park / Fort Pickering Lighthouse — all real
    Salem places — never reached the check and were dropped as "no evidence". The
    fix broadens the set to the other place-based outdoor categories and adds a
    generic city-metro coordinate fallback to the geographic tier-1 check (which
    was Riviera-only before).

    This test proves the fix is in place without requiring the network. A live
    verification of the three names runs only when a network check is available
    (skipped otherwise) so the suite stays offline/deterministic.
    """

    def test_biking_reaches_the_walking_existence_fallback(self):
        import inspect
        import stop_existence_gate as seg
        src = inspect.getsource(seg.verify_stop_existence)
        # The fallback gate must admit biking/cycling/driving outdoor tours now.
        m = re.search(r"_WALKING_KINDS\s*=\s*\(([^)]*)\)", src, re.S)
        self.assertIsNotNone(m, "could not find _WALKING_KINDS tuple")
        kinds = m.group(1).lower()
        for k in ("walking", "specialized", "biking", "cycling", "driving"):
            self.assertIn(k, kinds, f"{k!r} not admitted to the existence fallback")

    def test_geographic_tier1_has_generic_metro_fallback(self):
        import inspect
        import stop_existence_gate as seg
        src = inspect.getsource(seg._check_geographic_existence_tier1)
        # A generic (non-Riviera) metro proximity check must exist and be wired.
        self.assertIn("_within_metro_744", src)
        # It must be used somewhere beyond its own definition (at least one call).
        self.assertGreaterEqual(src.count("_within_metro_744"), 2)

    def test_live_salem_places_verify_when_network_available(self):
        import stop_existence_gate as seg
        try:
            import requests
            # Cheap reachability probe; skip if offline.
            requests.get("https://www.wikidata.org/w/api.php",
                         params={"action": "wbsearchentities", "search": "Salem",
                                 "language": "en", "format": "json", "limit": "1"},
                         timeout=6)
        except Exception as e:
            self.skipTest(f"network unavailable: {e}")

        venue = "episode 1 of season 1 biking tour, Salem, MA"
        verified = []
        for name in ("Pickering Wharf", "Winter Island Park",
                     "Fort Pickering Lighthouse"):
            try:
                ok, ev = seg._check_walking_stop_existence(name, venue)
            except RuntimeError as e:
                self.skipTest(f"existence search failed (not absence): {name}: {e}")
                return
            if ok:
                verified.append((name, ev))
            else:
                print(f"  [LOCAL-744] NOT verified by walking check: {name!r}")
        # At least the lighthouse and the wharf are well-known Wikidata/OSM
        # features in Salem; require that the robust check verifies the majority.
        self.assertGreaterEqual(
            len(verified), 2,
            f"expected >=2 of the 3 real Salem places to verify, got {verified}")
        for name, ev in verified:
            print(f"  [LOCAL-744] VERIFIED {name!r} — {ev}")


class TestFilmingPlaceFromArticle(unittest.TestCase):
    """LOCAL-744 live-run fix: derive the filming place from the WORK'S Wikipedia
    article (authoritative), not from the model's unreliable guess.

    The live run exposed the real defect: the model named the right work (the TV
    series *Salem*) but gave the WRONG place ("Salem, Massachusetts" — the
    setting), so the trust-then-corroborate path failed closed and the Orientation
    said "could not confirm" even though the Salem (TV series) article states
    verbatim "It was filmed in Shreveport, Louisiana". These tests mock the
    Wikipedia extract so they stay offline, and pin the article-derived behaviour.
    """

    def _mock_requests(self, extract_text, title="Salem (TV series)"):
        import generate_tour_text as gtt

        class _Resp:
            status_code = 200

            def json(self):
                return {"query": {"pages": {"123": {"title": title,
                                                    "extract": extract_text}}}}

        class _FakeRequests:
            @staticmethod
            def get(*a, **k):
                return _Resp()
        return gtt, _FakeRequests

    def test_extracts_shreveport_from_salem_article(self):
        import generate_tour_text as gtt
        orig = gtt.requests
        _, fake = self._mock_requests(
            "The series premiered in 2014. It was filmed in Shreveport, Louisiana, "
            "on sets built to represent 17th century Massachusetts.")
        gtt.requests = fake
        try:
            place, src = gtt._filming_place_from_article("Salem (TV series)")
        finally:
            gtt.requests = orig
        self.assertEqual(place, "Shreveport, Louisiana")
        self.assertIn("Wikipedia", src)

    def test_setting_only_article_yields_no_place(self):
        # An article that only names the SETTING (no "filmed in <place>") must not
        # fabricate a filming location.
        import generate_tour_text as gtt
        orig = gtt.requests
        _, fake = self._mock_requests(
            "Salem is a 2014 television series set in Salem, Massachusetts during "
            "the witch trials. It stars several actors.")
        gtt.requests = fake
        try:
            place, src = gtt._filming_place_from_article("Salem (TV series)")
        finally:
            gtt.requests = orig
        self.assertIsNone(place)

    def test_full_lookup_prefers_article_place_over_model_guess(self):
        # End-to-end: the model names the work 'Salem' and WRONGLY proposes
        # 'Salem, Massachusetts'; the article says Shreveport. The lookup must
        # return the article-derived Shreveport, and the disclosure must say
        # "filmed in Shreveport, Louisiana, not in Salem".
        import generate_tour_text as gtt
        orig_req = gtt.requests
        orig_post_model = getattr(gtt, "_check_model", None)

        class _ChatResp:
            status_code = 200

            def json(self):
                import json as _j
                return {"choices": [{"message": {"content": _j.dumps({
                    "work_name": "Salem", "work_kind": "tv series",
                    "filmed_place": "Salem, Massachusetts, USA",
                    "filmed_in_requested_place": True,
                    "source": "some-unchecked-source",
                    "confidence": "high"})}}]}

        class _WikiResp:
            status_code = 200

            def json(self):
                return {"query": {"pages": {"1": {
                    "title": "Salem (TV series)",
                    "extract": "It was filmed in Shreveport, Louisiana, on sets "
                               "built to represent 17th century Massachusetts."}}}}

        class _FakeRequests:
            @staticmethod
            def post(*a, **k):
                return _ChatResp()

            @staticmethod
            def get(*a, **k):
                return _WikiResp()

        gtt.requests = _FakeRequests
        try:
            lookup = gtt.filming_location_lookup("fake-key")
            work = swt.detect_screen_work(
                "episode 1 of season 1 biking tour, Salem, MA", {})
            disc = swt.build_filming_disclosure(
                work, "episode 1 of season 1 biking tour, Salem, MA", lookup)
        finally:
            gtt.requests = orig_req
        self.assertIn("Shreveport, Louisiana", disc)
        self.assertIn("not in Salem", disc)
        self.assertNotIn("could not confirm", disc.lower())


    def test_disambiguation_bare_title_tries_tv_series_variant(self):
        # The live run's real failure: the model returns bare "Salem", whose
        # Wikipedia page is a DISAMBIGUATION (no filming cue). The extractor must
        # then try "Salem (TV series)" and find "Shreveport, Louisiana".
        import generate_tour_text as gtt
        orig = gtt.requests
        _calls = {"n": 0}

        class _Resp:
            def __init__(self, title, extract):
                self.status_code = 200
                self._t = title
                self._e = extract

            def json(self):
                return {"query": {"pages": {"1": {"title": self._t,
                                                  "extract": self._e}}}}

        class _FakeRequests:
            @staticmethod
            def get(*a, **k):
                _calls["n"] += 1
                titles = k.get("params", {}).get("titles", "")
                if titles == "Salem":
                    return _Resp("Salem", "Salem may refer to: Places ... "
                                          "various disambiguation entries.")
                return _Resp("Salem (TV series)",
                             "It was filmed in Shreveport, Louisiana, on sets "
                             "built to represent 17th century Massachusetts.")

        gtt.requests = _FakeRequests
        try:
            place, src = gtt._filming_place_from_article("Salem", "tv series")
        finally:
            gtt.requests = orig
        self.assertEqual(place, "Shreveport, Louisiana")
        self.assertIn("Salem (TV series)", src)
        self.assertGreaterEqual(_calls["n"], 2)  # tried bare then disambiguated


if __name__ == "__main__":
    unittest.main(verbosity=2)
