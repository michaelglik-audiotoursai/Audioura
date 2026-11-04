"""LOCAL-863R: wave 27 regressions (tour 534, rolled back).

1. City geocoding: "Ho Chi Minh City, Vietnam" must resolve to HCMC (within
   10 km of 10.776,106.700), never near Hanoi, and the scope bbox must never be
   the whole country.
2. Only a real user coordinate source (user_share_link, user_share_link_kg,
   user_name_lookup) makes a user pin. A user stop with a model coordinate is
   NOT a pin: pin_snap, the PHASE-3B merge, and the cluster-refetch / D559
   exemptions all treat it as movable.
3. The empty-stop gate never removes a user stop.
4. Emoji are stripped (and logged) at the real TTS egress.

All offline: Nominatim is monkeypatched; no paid API is touched.
"""
import inspect
import math
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import city_scope as cs  # noqa: E402
import pin_snap  # noqa: E402
import stop_existence_gate as seg  # noqa: E402
import text_polish  # noqa: E402


def _km(a, b):
    return cs.haversine_km(a[0], a[1], b[0], b[1])


HCMC = (10.776, 106.700)
WAVE27_BAD_CENTER = (20.9103, 105.5750)
SOPHIA = "Sophia's biking tour in Ho Chi Minh City, Vietnam"


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def _nominatim_returns(mapping, calls=None):
    def _fake(params, context=""):
        q = params["q"]
        if calls is not None:
            calls.append(q)
        return _Resp(mapping.get(q, []))
    return _fake


# ─────────────────────────── (1) city geocoding ─────────────────────────────
class TestCityResolution(unittest.TestCase):
    def test_sophia_request_resolves_to_hcmc(self):
        hit = cs.resolve_city_scope(SOPHIA, log=lambda *_: None)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["name"], "Ho Chi Minh City")
        self.assertLess(_km((hit["lat"], hit["lng"]), HCMC), 10.0)
        self.assertGreater(_km((hit["lat"], hit["lng"]), WAVE27_BAD_CENTER), 1000)

    def test_aliases(self):
        for t in ("Saigon street food", "HCMC cafes", "TP HCM, Vietnam",
                  "Thành phố Hồ Chí Minh"):
            hit = cs.find_curated_city(t)
            self.assertIsNotNone(hit, t)
            self.assertEqual(hit["name"], "Ho Chi Minh City", t)

    def test_ho_chi_minh_mausoleum_is_not_hcmc(self):
        # The namesake in the north is NOT the city.
        hit = cs.find_curated_city("Ho Chi Minh Mausoleum walk, Hanoi")
        self.assertEqual(hit["name"], "Hanoi")

    def test_other_proof_cities(self):
        self.assertEqual(cs.find_curated_city("Boston, MA")["name"], "Boston")
        self.assertEqual(cs.find_curated_city("Old Quarter walk, Hanoi")["name"], "Hanoi")
        self.assertEqual(cs.find_curated_city("Nice, France")["name"], "Nice")

    def test_ordinary_word_alias_needs_country(self):
        self.assertIsNone(cs.find_curated_city("A nice walk by the river"))

    def test_country_mismatch_rejected(self):
        self.assertIsNone(cs.find_curated_city("Paris, Texas, USA"))

    def test_nominatim_attraction_and_wrong_country_rejected(self):
        rows = [
            # the wave-27 shape: a Ho Chi Minh-named attraction near Hanoi
            {"lat": "20.9103", "lon": "105.5750", "category": "tourism",
             "type": "attraction", "addresstype": "tourism"},
            # a wrong-country city
            {"lat": "48.85", "lon": "2.35", "category": "place", "type": "city",
             "addresstype": "city"},
            # the real city
            {"lat": "10.7756", "lon": "106.7019", "category": "boundary",
             "type": "administrative", "addresstype": "city",
             "boundingbox": ["10.37", "11.16", "106.36", "107.02"]},
        ]
        seen = []

        def fetch(params):
            seen.append(params)
            return rows
        # use a city NOT in the curated table so the Nominatim path runs
        hit = cs.resolve_city_scope("Bien Hoa, Vietnam", fetch=fetch,
                                    log=lambda *_: None)
        self.assertIsNotNone(hit)
        self.assertAlmostEqual(hit["lat"], 10.7756, places=3)
        self.assertEqual(seen[0].get("featuretype"), "city")
        self.assertEqual(seen[0].get("countrycodes"), "vn")

    def test_center_sanity(self):
        self.assertFalse(cs.center_is_sane(*WAVE27_BAD_CENTER, SOPHIA))
        self.assertTrue(cs.center_is_sane(*HCMC, SOPHIA))


class TestScopeGeocodeNeverWholeCountry(unittest.TestCase):
    def test_hcmc_scope_center_and_bbox_are_curated(self):
        calls = []
        import unittest.mock as m
        with m.patch.object(seg, "_nominatim_request",
                            _nominatim_returns({}, calls)):
            c = seg._geocode_scope_center("Ho Chi Minh City, Vietnam")
            b = seg._geocode_scope_bbox("Ho Chi Minh City, Vietnam")
        self.assertLess(_km(c, HCMC), 10.0)
        s, n, w, e = map(float, b)
        self.assertTrue(s < HCMC[0] < n and w < HCMC[1] < e)
        # a city-size box, not Vietnam (~15° tall)
        self.assertLess(n - s, 1.0)
        self.assertEqual(calls, [], "curated city must not need the network")

    def test_wave27_bad_hit_is_rejected(self):
        # Nominatim returns the Hanoi-area namesake for the bare city name.
        import unittest.mock as m
        bad = [{"lat": "20.9103", "lon": "105.5750", "category": "tourism",
                "type": "attraction", "addresstype": "tourism",
                "boundingbox": ["20.90", "20.92", "105.56", "105.58"]}]
        with m.patch.object(seg, "_nominatim_request",
                            _nominatim_returns({"Sophia area, Ho Chi Minh City, Vietnam": bad})):
            c = seg._geocode_scope_center("Sophia area, Ho Chi Minh City, Vietnam")
        self.assertIsNotNone(c)
        self.assertLess(_km(c, HCMC), 10.0)

    def test_bare_country_tail_is_never_used(self):
        import unittest.mock as m
        calls = []
        country = [{"lat": "16.0", "lon": "108.0", "addresstype": "country",
                    "boundingbox": ["8.0", "23.4", "102.1", "109.5"]}]
        with m.patch.object(seg, "_nominatim_request",
                            _nominatim_returns({"Vietnam": country}, calls)):
            self.assertIsNone(seg._geocode_scope_bbox("Unknownplace xyz, Vietnam"))
            self.assertIsNone(seg._geocode_scope_center("Unknownplace xyz, Vietnam"))
        self.assertNotIn("Vietnam", calls)

    def test_subarea_keeps_its_own_tighter_geocode(self):
        # LOCAL-786: "West Roxbury, Boston, MA" must NOT be widened to Boston.
        import unittest.mock as m
        wr = [{"lat": "42.279", "lon": "-71.149", "addresstype": "suburb",
               "boundingbox": ["42.26", "42.30", "-71.18", "-71.12"]}]
        with m.patch.object(seg, "_nominatim_request",
                            _nominatim_returns({"West Roxbury, Boston, MA": wr})):
            b = seg._geocode_scope_bbox("West Roxbury, Boston, MA")
        self.assertEqual(b, ["42.26", "42.30", "-71.18", "-71.12"])


# ─────────────────────────── (2) user-pin provenance ────────────────────────
MODEL_COORD = "10.7800, 106.6900"


class TestOnlyRealSourceIsAUserPin(unittest.TestCase):
    def test_pin_snap_real_sources(self):
        for src in ("user_share_link", "user_share_link_kg", "user_name_lookup"):
            self.assertTrue(pin_snap._is_user_pin(
                {"coord_source": src, "coordinates": MODEL_COORD}), src)

    def test_pin_snap_model_coordinate_on_user_stop_is_not_a_pin(self):
        # The wave-27 shape: user_explicit, a Phase-3B guess, no real source.
        for src in (None, "", "model", "llm", "phase3b"):
            poi = {"name": "Crazy street", "user_explicit": True, "_anchor": True,
                   "coordinates": MODEL_COORD, "coord_source": src}
            self.assertFalse(pin_snap._is_user_pin(poi), src)

    def test_snap_does_not_log_user_pin_kept_for_model_coordinate(self):
        logs = []
        poi = {"name": "Crazy street", "title": "Crazy street",
               "user_explicit": True, "_anchor": True,
               "coordinates": MODEL_COORD, "coord_source": "model"}
        rows = pin_snap.snap_poi_coordinates(
            [poi], scope="Ho Chi Minh City", scope_center=HCMC,
            scope_bbox=None, tour_language="en", log=logs.append,
            reference_fn=lambda *a, **k: None,
            landmark_fn=lambda *a, **k: None)[1]
        self.assertFalse(any("user pin kept" in str(l) for l in logs), logs)
        self.assertFalse(any((r or {}).get("reason") == "user pin kept"
                             for r in rows), rows)


class TestMergeFields(unittest.TestCase):
    def setUp(self):
        import generate_tour_text as g
        self.g = g

    def test_model_coordinate_on_user_stop_is_not_kept(self):
        orig = {"name": "Crazy street", "user_explicit": True, "_anchor": True,
                "coordinates": MODEL_COORD}          # no real coord_source
        entry = {"name": "Crazy street", "coordinates": "10.70, 106.60"}
        out = self.g._user_pin_merge_fields(entry, orig)
        self.assertFalse(out["coord_kept"])

    def test_real_sources_are_kept(self):
        for src in ("user_share_link", "user_share_link_kg", "user_name_lookup"):
            orig = {"name": "Thi Bar Saigon", "user_explicit": True,
                    "coord_source": src, "coordinates": "10.7712, 106.7041"}
            entry = {"name": "Thi Bar Saigon", "coordinates": "1.0, 2.0"}
            out = self.g._user_pin_merge_fields(entry, orig)
            self.assertTrue(out["coord_kept"], src)
            self.assertEqual(out["coordinates"], "10.7712, 106.7041")

    def test_has_real_user_coord(self):
        f = self.g._has_real_user_coord
        self.assertTrue(f({"coord_source": "user_name_lookup"}))
        self.assertFalse(f({"user_explicit": True, "_anchor": True,
                            "coordinates": MODEL_COORD}))

    def test_merge_keeps_real_source_label(self):
        # Phase-3B merge must not relabel a KG / name-lookup pin as share_link.
        src = inspect.getsource(self.g._generate_tour_text_impl)
        self.assertIn("merged['coord_source'] = 'model'", src)
        self.assertNotIn("merged['coord_source'] = 'user_share_link'\n", src)

    def test_cluster_refetch_and_d559_use_real_source_predicate(self):
        src = inspect.getsource(self.g._generate_tour_text_impl)
        # the old loose exemption (user_explicit/_anchor + title) is gone
        self.assertNotIn(
            "or ((p.get('user_explicit') or p.get('_anchor'))\n"
            "                                and _is_user_stop_title(p.get('name')))", src)
        self.assertNotIn(
            "or ((_p.get('user_explicit') or _p.get('_anchor'))\n"
            "                                and _is_user_stop_title(_p.get('name')))", src)
        self.assertIn("if _has_real_user_coord(p):", src)
        self.assertIn("return _has_real_user_coord(_p)", src)


# ─────────────────────────── (3) empty-stop gate ────────────────────────────
class TestEmptyStopGateKeepsUserStops(unittest.TestCase):
    def test_gate_has_user_stop_exemption_with_short_form(self):
        import generate_tour_text as g
        src = inspect.getsource(g._generate_tour_text_impl)
        i = src.index("[LOCAL-292] EMPTY STOP REMOVAL GATE")
        block = src[i:i + 4000]
        self.assertIn("grounded_user_stop_body", block)
        self.assertIn("user stop KEPT with D760 short form", block)
        # the user-stop branch continues BEFORE the failed-stop append
        self.assertLess(block.index("continue"),
                        block.index("_l292_failed_stops.append"))

    def test_short_form_is_non_empty_and_not_a_failure_marker(self):
        import user_stop_narration as usn
        poi = {"name": "Crazy street", "user_explicit": True, "description": ""}
        body = usn.grounded_user_stop_body(poi, "Ho Chi Minh City, Vietnam")
        self.assertTrue(body.strip())
        self.assertIn("Crazy street", body)
        self.assertNotIn("GENERATION_FAILED", body)
        self.assertFalse(body.startswith("["))


# ─────────────────────────── (4) emoji at TTS egress ────────────────────────
class TestEmojiStripAtTTSEgress(unittest.TestCase):
    def test_logged_strip(self):
        logs = []
        out = text_polish.strip_emoji_for_tts_logged(
            "The LGBT bar 🌈Thi Bar Saigon.", "unit", log=logs.append)
        self.assertNotIn("🌈", out)
        self.assertEqual(out, "The LGBT bar Thi Bar Saigon.")
        self.assertEqual(len(logs), 1)
        self.assertIn("[LOCAL-863] TTS emoji strip at unit: removed 1", logs[0])

    def test_no_log_when_clean(self):
        logs = []
        s = "No emoji here."
        self.assertIs(text_polish.strip_emoji_for_tts_logged(s, "u", log=logs.append), s)
        self.assertEqual(logs, [])

    def test_modernized_payload_has_no_rainbow(self):
        import tour_generation_modernized as tgm
        text = ("Thi Bar Saigon 🌈\nAddress: 1 Đ. Nguyễn Huệ\n"
                "Orientation: 🌈 A bar on the corner.\nWelcome to 🌈Thi Bar.")
        out = tgm._strip_nav_fields_for_tts(text)
        self.assertNotIn("🌈", out)
        self.assertNotIn("Address:", out)

    def test_modernized_fallback_when_text_polish_missing(self):
        import builtins
        import unittest.mock as m
        import tour_generation_modernized as tgm
        real_import = builtins.__import__

        def _no_tp(name, *a, **k):
            if name == "text_polish":
                raise ImportError("simulated: not in image")
            return real_import(name, *a, **k)
        with m.patch.object(builtins, "__import__", _no_tp):
            out = tgm._tts_strip_emoji("Hi 🌈 there", "test")
        self.assertNotIn("🌈", out)

    def test_editing_payload_has_no_rainbow(self):
        import tour_editing_phase2 as tep
        out = tep._strip_nav_fields_for_tts("Welcome to 🌈Thi Bar Saigon.")
        self.assertNotIn("🌈", out)


if __name__ == "__main__":
    unittest.main()
